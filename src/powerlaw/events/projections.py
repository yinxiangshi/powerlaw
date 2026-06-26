from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from powerlaw.events.types import EventType
from powerlaw.models.tables import (
    Condition,
    CrossRef,
    DefinedTerm,
    Dependency,
    Document,
    Event,
    EvidenceArtifact,
    IngestionJob,
    Party,
    PartyAlias,
    PartyRole,
    Project,
    Segment,
    TermMembership,
)


async def apply_event(
    session: AsyncSession, event: Event, payload_override: dict[str, Any] | None = None
) -> None:
    payload = payload_override or event.payload
    event_type = event.event_type

    if event_type == EventType.PROJECT_CREATED:
        await _upsert_project(session, event, payload)
    elif event_type == EventType.PROJECT_DELETED:
        await _delete_project(session, event, payload)
    elif event_type == EventType.DOCUMENT_INGESTED:
        await _upsert_document(session, event, payload)
    elif event_type == EventType.DOCUMENT_TYPED:
        await _update_document_typed(session, event, payload)
    elif event_type == EventType.DOCUMENT_SEGMENTED:
        await _replace_segments(session, event, payload)
    elif event_type == EventType.CONDITION_EXTRACTED:
        await _upsert_condition(session, event, payload)
    elif event_type == EventType.DEFINED_TERM_EXTRACTED:
        await _upsert_defined_term(session, payload)
    elif event_type == EventType.PARTY_IDENTIFIED:
        await _upsert_party(session, payload)
    elif event_type == EventType.TERM_MEMBERSHIP_RESOLVED:
        await _upsert_term_membership(session, payload)
    elif event_type == EventType.CROSS_REFERENCE_RESOLVED:
        await _upsert_cross_ref(session, payload)
    elif event_type == EventType.DEPENDENCY_LINKED:
        await _upsert_dependency(session, payload)
    elif event_type == EventType.EVIDENCE_ARTIFACT_EXPECTED:
        await _upsert_evidence(session, payload)
    elif event_type == EventType.DOCUMENT_LINKED:
        await _set_document_status(session, event, payload["document_id"], "linked")
    elif event_type == EventType.DOCUMENT_ERRORED:
        await _set_document_status(session, event, payload["document_id"], "error")
    elif event_type == EventType.CONDITION_CONFIRMED:
        await _confirm_condition(session, event)
    elif event_type == EventType.CONDITION_CORRECTED:
        await _correct_condition(session, event, payload)
    elif event_type == EventType.JOB_CREATED:
        await _upsert_job(session, event, payload)
    elif event_type == EventType.JOB_UPDATED:
        await _update_job(session, event, payload)


async def project_counters(session: AsyncSession, project_id: UUID) -> dict[str, Any]:
    docs = await session.scalar(
        select(func.count()).select_from(Document).where(Document.project_id == project_id)
    )
    conditions = await session.scalar(
        select(func.count()).select_from(Condition).where(Condition.project_id == project_id)
    )
    satisfied = await session.scalar(
        select(func.count())
        .select_from(Condition)
        .where(Condition.project_id == project_id, Condition.status.in_(["verified", "waived"]))
    )
    flagged = await session.scalar(
        select(func.count())
        .select_from(Event)
        .where(
            Event.project_id == project_id,
            Event.event_type == EventType.EXTRACTION_FLAGGED,
        )
    )
    total_conditions = int(conditions or 0)
    return {
        "documents_ingested": int(docs or 0),
        "conditions_extracted": total_conditions,
        "percent_satisfied": (
            round((int(satisfied or 0) / total_conditions) * 100, 2) if total_conditions else 0
        ),
        "awaiting_review": int(flagged or 0),
    }


async def project_state_as_of(
    session: AsyncSession, project_id: UUID, as_of: datetime | None
) -> dict[str, Any]:
    query = select(Event).where(Event.project_id == project_id).order_by(Event.id)
    if as_of is not None:
        query = query.where(Event.ts <= as_of)
    events = (await session.scalars(query)).all()

    state: dict[str, Any] = {
        "project_id": str(project_id),
        "as_of": as_of.isoformat() if as_of else None,
        "documents": {},
        "conditions": {},
        "events_folded": len(events),
    }
    for event in events:
        payload = event.payload
        if event.event_type == EventType.PROJECT_CREATED:
            state["name"] = payload["name"]
            state["aliases"] = payload.get("aliases", [])
        elif event.event_type == EventType.PROJECT_DELETED:
            state["deleted_at"] = event.ts.isoformat()
        elif event.event_type == EventType.DOCUMENT_INGESTED:
            state["documents"][payload["id"]] = {
                "filename": payload["filename"],
                "status": "ingested",
            }
        elif event.event_type == EventType.DOCUMENT_TYPED:
            doc = state["documents"].setdefault(payload["document_id"], {})
            doc.update(
                {
                    "title": payload.get("title"),
                    "type": payload.get("type"),
                    "status": "typed",
                }
            )
        elif event.event_type == EventType.DOCUMENT_LINKED:
            doc = state["documents"].setdefault(payload["document_id"], {})
            doc["status"] = "linked"
        elif event.event_type == EventType.CONDITION_EXTRACTED:
            state["conditions"][payload["id"]] = {
                "trigger": payload["trigger"],
                "status": payload.get("status", "open"),
                "verification_status": payload.get("verification_status", "unverified"),
            }
        elif event.event_type == EventType.CONDITION_CONFIRMED:
            condition = state["conditions"].setdefault(str(event.target_id), {})
            condition["verification_status"] = "lawyer_confirmed"
        elif event.event_type == EventType.CONDITION_CORRECTED:
            condition = state["conditions"].setdefault(str(event.target_id), {})
            condition[payload["field"]] = payload["after"]
            condition["verification_status"] = "lawyer_corrected"
    state["document_count"] = len(state["documents"])
    state["condition_count"] = len(state["conditions"])
    return state


async def _upsert_project(session: AsyncSession, event: Event, payload: dict[str, Any]) -> None:
    project = await session.get(Project, payload["id"])
    values = {
        "name": payload["name"],
        "aliases": payload.get("aliases", []),
        "updated_by_event": event.id,
    }
    if project is None:
        session.add(Project(id=payload["id"], **values))
    else:
        for key, value in values.items():
            setattr(project, key, value)


async def _delete_project(session: AsyncSession, event: Event, payload: dict[str, Any]) -> None:
    await session.execute(
        update(Project)
        .where(Project.id == payload["id"], Project.deleted_at.is_(None))
        .values(deleted_at=event.ts, updated_by_event=event.id)
    )


async def _upsert_document(session: AsyncSession, event: Event, payload: dict[str, Any]) -> None:
    document = await session.get(Document, payload["id"])
    values = {
        "project_id": event.project_id,
        "filename": payload["filename"],
        "mime": payload.get("mime"),
        "content_hash": payload["content_hash"],
        "storage_path": payload["storage_path"],
        "version": payload.get("version", 1),
        "status": "ingested",
        "updated_by_event": event.id,
    }
    if document is None:
        session.add(Document(id=payload["id"], **values))
    else:
        for key, value in values.items():
            setattr(document, key, value)


async def _update_document_typed(
    session: AsyncSession, event: Event, payload: dict[str, Any]
) -> None:
    await session.execute(
        update(Document)
        .where(Document.id == payload["document_id"])
        .values(
            type=payload.get("type"),
            title=payload.get("title"),
            execution_date=payload.get("execution_date"),
            confidence=payload.get("confidence"),
            status="typed",
            updated_by_event=event.id,
        )
    )


async def _replace_segments(session: AsyncSession, event: Event, payload: dict[str, Any]) -> None:
    document_id = payload["document_id"]
    await session.execute(delete(Segment).where(Segment.document_id == document_id))
    for segment in payload["segments"]:
        session.add(Segment(document_id=document_id, **segment))
    await _set_document_status(session, event, document_id, "segmented")


async def _upsert_condition(session: AsyncSession, event: Event, payload: dict[str, Any]) -> None:
    condition = await session.get(Condition, payload["id"])
    values = {
        "segment_id": payload["segment_id"],
        "project_id": event.project_id,
        "beneficiary_party": payload.get("beneficiary_party"),
        "obligor_party": payload.get("obligor_party"),
        "trigger": payload.get("trigger"),
        "requirement_text": payload["requirement_text"],
        "discretionary": payload.get("discretionary", False),
        "dating_rule": payload.get("dating_rule"),
        "status": payload.get("status", "open"),
        "waivable_by": payload.get("waivable_by"),
        "confidence": payload.get("confidence"),
        "verification_status": payload.get("verification_status", "unverified"),
        "updated_by_event": event.id,
    }
    if condition is None:
        session.add(Condition(id=payload["id"], **values))
    else:
        for key, value in values.items():
            setattr(condition, key, value)


async def _upsert_defined_term(session: AsyncSession, payload: dict[str, Any]) -> None:
    defined_term = await session.get(DefinedTerm, payload["id"])
    values = {
        "document_id": payload.get("document_id"),
        "term": payload["term"],
        "defining_segment_id": payload.get("defining_segment_id"),
        "definition_kind": payload.get("definition_kind"),
    }
    if defined_term is None:
        session.add(DefinedTerm(id=payload["id"], **values))
    else:
        for key, value in values.items():
            setattr(defined_term, key, value)


async def _upsert_party(session: AsyncSession, payload: dict[str, Any]) -> None:
    party = await session.get(Party, payload["id"])
    values = {
        "project_id": payload["project_id"],
        "canonical_name": payload["canonical_name"],
        "entity_type": payload.get("entity_type"),
    }
    if party is None:
        session.add(Party(id=payload["id"], **values))
    else:
        for key, value in values.items():
            setattr(party, key, value)
    for alias in payload.get("aliases", []):
        alias_row = await session.get(PartyAlias, {"party_id": payload["id"], "alias": alias})
        if alias_row is None:
            session.add(PartyAlias(party_id=payload["id"], alias=alias))
    for role in payload.get("roles", []):
        role_row = await session.get(
            PartyRole,
            {
                "party_id": payload["id"],
                "document_id": role["document_id"],
                "role": role["role"],
            },
        )
        if role_row is None:
            session.add(
                PartyRole(
                    party_id=payload["id"],
                    document_id=role["document_id"],
                    role=role["role"],
                )
            )


async def _upsert_term_membership(session: AsyncSession, payload: dict[str, Any]) -> None:
    key = {"defined_term": payload["defined_term"], "member_name": payload["member_name"]}
    membership = await session.get(TermMembership, key)
    values = {
        "member_document": payload.get("member_document"),
        "member_party": payload.get("member_party"),
        "resolved": payload.get("resolved", False),
    }
    if membership is None:
        session.add(TermMembership(**key, **values))
    else:
        for attr, value in values.items():
            setattr(membership, attr, value)


async def _upsert_cross_ref(session: AsyncSession, payload: dict[str, Any]) -> None:
    key = {"from_segment": payload["from_segment"], "to_label": payload["to_label"]}
    cross_ref = await session.get(CrossRef, key)
    values = {"to_segment": payload.get("to_segment"), "resolved": payload.get("resolved", False)}
    if cross_ref is None:
        session.add(CrossRef(**key, **values))
    else:
        for attr, value in values.items():
            setattr(cross_ref, attr, value)


async def _upsert_dependency(session: AsyncSession, payload: dict[str, Any]) -> None:
    key = {"from_condition": payload["from_condition"], "to_condition": payload["to_condition"]}
    dependency = await session.get(Dependency, key)
    if dependency is None:
        session.add(Dependency(**key, source_segment=payload.get("source_segment")))


async def _upsert_evidence(session: AsyncSession, payload: dict[str, Any]) -> None:
    evidence = await session.get(EvidenceArtifact, payload["id"])
    values = {
        "type": payload["type"],
        "expected_by_condition": payload.get("expected_by_condition"),
        "fulfilled_by_document": payload.get("fulfilled_by_document"),
        "provider_party": payload.get("provider_party"),
        "description": payload.get("description"),
    }
    if evidence is None:
        session.add(EvidenceArtifact(id=payload["id"], **values))
    else:
        for attr, value in values.items():
            setattr(evidence, attr, value)


async def _set_document_status(
    session: AsyncSession, event: Event, document_id: UUID | str, status: str
) -> None:
    await session.execute(
        update(Document)
        .where(Document.id == document_id)
        .values(status=status, updated_by_event=event.id)
    )


async def _confirm_condition(session: AsyncSession, event: Event) -> None:
    await session.execute(
        update(Condition)
        .where(Condition.id == event.target_id)
        .values(verification_status="lawyer_confirmed", updated_by_event=event.id)
    )


async def _correct_condition(session: AsyncSession, event: Event, payload: dict[str, Any]) -> None:
    field = payload["field"]
    allowed = {
        "beneficiary_party",
        "obligor_party",
        "trigger",
        "requirement_text",
        "discretionary",
        "dating_rule",
        "status",
        "waivable_by",
        "confidence",
    }
    if field not in allowed:
        return
    values = {field: payload["after"], "updated_by_event": event.id}
    if field == "status":
        if payload["after"] == "verified":
            values["verification_status"] = "lawyer_confirmed"
    else:
        values["verification_status"] = "lawyer_corrected"
    await session.execute(update(Condition).where(Condition.id == event.target_id).values(**values))


async def _upsert_job(session: AsyncSession, event: Event, payload: dict[str, Any]) -> None:
    job = await session.get(IngestionJob, payload["id"])
    values = {
        "project_id": event.project_id,
        "document_id": payload.get("document_id"),
        "status": payload.get("status", "queued"),
        "error": payload.get("error"),
        "updated_by_event": event.id,
    }
    if job is None:
        session.add(IngestionJob(id=payload["id"], **values))
    else:
        for key, value in values.items():
            setattr(job, key, value)


async def _update_job(session: AsyncSession, event: Event, payload: dict[str, Any]) -> None:
    await session.execute(
        update(IngestionJob)
        .where(IngestionJob.id == payload["id"])
        .values(
            status=payload.get("status"),
            error=payload.get("error"),
            updated_by_event=event.id,
        )
    )

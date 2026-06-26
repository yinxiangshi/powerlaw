from __future__ import annotations

import json
import re
import uuid
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from powerlaw.config import Settings, get_settings
from powerlaw.events.store import append_event
from powerlaw.events.types import ActorType, EventType
from powerlaw.ingestion.entities import (
    extract_defined_terms,
    extract_parties,
    payload_for_defined_term,
    payload_for_party,
    stable_uuid,
)
from powerlaw.ingestion.extraction import (
    ConditionDraft,
    extract_article3_conditions,
    infer_evidence_type,
)
from powerlaw.ingestion.intake import normalize_file
from powerlaw.ingestion.linking import (
    resolve_condition_cross_refs,
    resolve_term_memberships,
    unresolved_memberships,
)
from powerlaw.ingestion.segmentation import SegmentDraft, segment_document
from powerlaw.ingestion.typing import classify_document
from powerlaw.llm.client import LlmClient, LlmDisabledError
from powerlaw.models.tables import Condition, Document, Party, Segment

CHECKLIST_PROMPT_VERSION = "condition_checklist_v1"


async def ingest_existing_file(
    session: AsyncSession,
    *,
    project_id: UUID,
    path: Path,
    settings: Settings | None = None,
) -> tuple[UUID, UUID]:
    settings = settings or get_settings()
    normalized = normalize_file(path)
    document_id = uuid.uuid4()
    job_id = uuid.uuid4()
    await append_event(
        session,
        project_id=project_id,
        actor_id="pipeline",
        actor_type=ActorType.SYSTEM,
        event_type=EventType.DOCUMENT_INGESTED,
        target_type="document",
        target_id=document_id,
        payload={
            "id": document_id,
            "filename": path.name,
            "mime": normalized.mime,
            "content_hash": normalized.content_hash,
            "storage_path": str(path.resolve()),
            "version": 1,
        },
    )
    await append_event(
        session,
        project_id=project_id,
        actor_id="pipeline",
        actor_type=ActorType.SYSTEM,
        event_type=EventType.JOB_CREATED,
        target_type="job",
        target_id=job_id,
        payload={"id": job_id, "document_id": document_id, "status": "queued"},
    )
    await process_document(session, document_id=document_id, job_id=job_id, settings=settings)
    return document_id, job_id


async def process_document(
    session: AsyncSession,
    *,
    document_id: UUID,
    job_id: UUID | None = None,
    settings: Settings | None = None,
) -> None:
    settings = settings or get_settings()
    document = await session.get(Document, document_id)
    if document is None:
        raise ValueError(f"document not found: {document_id}")

    try:
        if job_id is not None:
            await _job_update(session, document.project_id, job_id, "running")
        path = Path(document.storage_path or "")
        normalized = normalize_file(path)
        typed = classify_document(normalized.text)
        await append_event(
            session,
            project_id=document.project_id,
            actor_id="pipeline",
            actor_type=ActorType.SYSTEM,
            event_type=EventType.DOCUMENT_TYPED,
            target_type="document",
            target_id=document.id,
            payload={
                "document_id": document.id,
                "type": typed.type,
                "title": typed.title,
                "execution_date": typed.execution_date,
                "confidence": typed.confidence,
            },
        )

        segments = segment_document(normalized.text, document.id)
        await append_event(
            session,
            project_id=document.project_id,
            actor_id="pipeline",
            actor_type=ActorType.SYSTEM,
            event_type=EventType.DOCUMENT_SEGMENTED,
            target_type="document",
            target_id=document.id,
            payload={
                "document_id": document.id,
                "segments": [segment.event_payload() for segment in segments],
            },
        )

        parties = extract_parties(document.project_id, document.id, normalized.text)
        for party in parties:
            await append_event(
                session,
                project_id=document.project_id,
                actor_id="pipeline",
                actor_type=ActorType.SYSTEM,
                event_type=EventType.PARTY_IDENTIFIED,
                target_type="party",
                target_id=party.id,
                payload=payload_for_party(document.project_id, document.id, party),
            )

        defined_terms = extract_defined_terms(document.id, segments)
        for defined_term in defined_terms:
            await append_event(
                session,
                project_id=document.project_id,
                actor_id="pipeline",
                actor_type=ActorType.SYSTEM,
                event_type=EventType.DEFINED_TERM_EXTRACTED,
                target_type="defined_term",
                target_id=defined_term.id,
                payload=payload_for_defined_term(document.id, defined_term),
            )

        await append_event(
            session,
            project_id=document.project_id,
            actor_id="pipeline",
            actor_type=ActorType.SYSTEM,
            event_type=EventType.DOCUMENT_LINKED,
            target_type="document",
            target_id=document.id,
            payload={"document_id": document.id},
        )
        if job_id is not None:
            await _job_update(session, document.project_id, job_id, "done")
    except Exception as exc:
        await append_event(
            session,
            project_id=document.project_id,
            actor_id="pipeline",
            actor_type=ActorType.SYSTEM,
            event_type=EventType.DOCUMENT_ERRORED,
            target_type="document",
            target_id=document.id,
            payload={"document_id": document.id, "error": str(exc)},
        )
        if job_id is not None:
            await _job_update(session, document.project_id, job_id, "error", error=str(exc))
        raise


async def generate_project_checklist(
    session: AsyncSession,
    *,
    project_id: UUID,
    settings: Settings | None = None,
) -> list[UUID]:
    settings = settings or get_settings()
    existing = (
        await session.scalars(select(Condition.id).where(Condition.project_id == project_id))
    ).all()
    if existing:
        return list(existing)

    documents = (
        await session.scalars(
            select(Document)
            .where(Document.project_id == project_id, Document.type == "financing_agreement")
            .order_by(Document.created_at)
        )
    ).all()
    condition_ids: list[UUID] = []
    for document in documents:
        segments = await _segments_for_document(session, document.id)
        condition_drafts = extract_article3_conditions(segments)
        if not condition_drafts:
            continue

        party_ids_by_name = await _party_ids_by_name(session, project_id)
        generated: list[ConditionDraft] = []
        for condition in condition_drafts:
            segment = next(
                (segment for segment in segments if segment.id == condition.segment_id), None
            )
            if segment is None:
                continue
            reviewed, derivation = await _review_condition_with_llm(
                session,
                document=document,
                segment=segment,
                condition=condition,
                settings=settings,
            )
            if reviewed is None:
                continue
            await _append_condition_with_evidence(
                session,
                project_id=project_id,
                document_id=document.id,
                condition=reviewed,
                party_ids_by_name=party_ids_by_name,
                settings=settings,
                derivation=derivation,
            )
            generated.append(reviewed)
            condition_ids.append(reviewed.id)

        await _append_condition_links(
            session,
            project_id=project_id,
            document_id=document.id,
            conditions=generated,
            segments=segments,
        )

    return condition_ids


async def link_project_bundles(session: AsyncSession, project_id: UUID) -> None:
    documents = list(
        (await session.scalars(select(Document).where(Document.project_id == project_id))).all()
    )
    financing = next(
        (document for document in documents if document.type == "financing_agreement"), None
    )
    if financing is None:
        return

    from powerlaw.models.tables import DefinedTerm

    rows = (
        await session.scalars(select(DefinedTerm).where(DefinedTerm.document_id == financing.id))
    ).all()
    defined_terms = [
        # Recreate the narrow fields needed by resolve_term_memberships from stored rows.
        type(
            "StoredTerm",
            (),
            {
                "id": row.id,
                "term": row.term,
                "members": _members_from_known_bundle(row.term),
            },
        )()
        for row in rows
    ]
    memberships = resolve_term_memberships(defined_terms, documents)
    for membership in memberships:
        await append_event(
            session,
            project_id=project_id,
            actor_id="pipeline",
            actor_type=ActorType.SYSTEM,
            event_type=EventType.TERM_MEMBERSHIP_RESOLVED,
            target_type="defined_term",
            target_id=cast(UUID, membership["defined_term"]),
            payload=membership,
        )
    for reason in unresolved_memberships(memberships):
        await _flag(session, project_id=project_id, document_id=financing.id, reason=reason)


async def _job_update(
    session: AsyncSession,
    project_id: UUID,
    job_id: UUID,
    status: str,
    error: str | None = None,
) -> None:
    await append_event(
        session,
        project_id=project_id,
        actor_id="pipeline",
        actor_type=ActorType.SYSTEM,
        event_type=EventType.JOB_UPDATED,
        target_type="job",
        target_id=job_id,
        payload={"id": job_id, "status": status, "error": error},
    )


async def _flag(session: AsyncSession, *, project_id: UUID, document_id: UUID, reason: str) -> None:
    await append_event(
        session,
        project_id=project_id,
        actor_id="pipeline",
        actor_type=ActorType.SYSTEM,
        event_type=EventType.EXTRACTION_FLAGGED,
        target_type="document",
        target_id=document_id,
        payload={"document_id": document_id, "reason": reason},
    )


async def _segments_for_document(session: AsyncSession, document_id: UUID) -> list[SegmentDraft]:
    rows = (
        await session.scalars(
            select(Segment)
            .where(Segment.document_id == document_id)
            .order_by(Segment.char_start, Segment.order_index)
        )
    ).all()
    return [
        SegmentDraft(
            id=row.id,
            document_id=row.document_id,
            parent_id=row.parent_id,
            label=row.label or "",
            heading=row.heading,
            text=row.text,
            char_start=row.char_start,
            char_end=row.char_end,
            order_index=row.order_index,
        )
        for row in rows
    ]


async def _party_ids_by_name(session: AsyncSession, project_id: UUID) -> dict[str, UUID]:
    parties = (
        await session.scalars(select(Party).where(Party.project_id == project_id))
    ).all()
    return {party.canonical_name: party.id for party in parties}


async def _append_condition_with_evidence(
    session: AsyncSession,
    *,
    project_id: UUID,
    document_id: UUID,
    condition: ConditionDraft,
    party_ids_by_name: dict[str, UUID],
    settings: Settings,
    derivation: dict[str, Any] | None,
) -> None:
    payload = condition.payload(
        beneficiary_party=party_ids_by_name.get(condition.beneficiary_name),
        obligor_party=party_ids_by_name.get(condition.obligor_name),
    )
    actor_type = ActorType.MODEL if derivation is not None else ActorType.SYSTEM
    await append_event(
        session,
        project_id=project_id,
        actor_id="openai" if derivation is not None else "pipeline",
        actor_type=actor_type,
        event_type=EventType.CONDITION_EXTRACTED,
        target_type="condition",
        target_id=condition.id,
        payload=payload,
        derivation=derivation,
    )
    artifact_type, description = infer_evidence_type(condition.requirement_text)
    artifact_id = stable_uuid(condition.id, "evidence", artifact_type)
    await append_event(
        session,
        project_id=project_id,
        actor_id="pipeline",
        actor_type=ActorType.SYSTEM,
        event_type=EventType.EVIDENCE_ARTIFACT_EXPECTED,
        target_type="evidence_artifact",
        target_id=artifact_id,
        payload={
            "id": artifact_id,
            "type": artifact_type,
            "expected_by_condition": condition.id,
            "fulfilled_by_document": None,
            "provider_party": party_ids_by_name.get(condition.obligor_name),
            "description": description,
        },
    )
    if condition.confidence < settings.extraction_confidence_threshold:
        await _flag(
            session,
            project_id=project_id,
            document_id=document_id,
            reason=f"{condition.label} confidence below threshold",
        )


async def _append_condition_links(
    session: AsyncSession,
    *,
    project_id: UUID,
    document_id: UUID,
    conditions: list[ConditionDraft],
    segments: list[SegmentDraft],
) -> None:
    cross_refs, dependencies, unresolved = resolve_condition_cross_refs(
        conditions=conditions,
        segments=segments,
    )
    for cross_ref in cross_refs:
        await append_event(
            session,
            project_id=project_id,
            actor_id="pipeline",
            actor_type=ActorType.SYSTEM,
            event_type=EventType.CROSS_REFERENCE_RESOLVED,
            target_type="segment",
            target_id=cross_ref.from_segment,
            payload={
                "from_segment": cross_ref.from_segment,
                "to_label": cross_ref.to_label,
                "to_segment": cross_ref.to_segment,
                "resolved": cross_ref.resolved,
            },
        )
    for dependency in dependencies:
        await append_event(
            session,
            project_id=project_id,
            actor_id="pipeline",
            actor_type=ActorType.SYSTEM,
            event_type=EventType.DEPENDENCY_LINKED,
            target_type="condition",
            target_id=dependency.from_condition,
            payload={
                "from_condition": dependency.from_condition,
                "to_condition": dependency.to_condition,
                "source_segment": dependency.source_segment,
            },
        )
    for reason in unresolved:
        await _flag(session, project_id=project_id, document_id=document_id, reason=reason)


async def _review_condition_with_llm(
    session: AsyncSession,
    *,
    document: Document,
    segment: SegmentDraft,
    condition: ConditionDraft,
    settings: Settings,
) -> tuple[ConditionDraft | None, dict[str, Any] | None]:
    if not settings.openai_api_key:
        return condition, None

    prompt = _condition_review_prompt(document=document, segment=segment, condition=condition)
    try:
        response = await LlmClient(settings).call_json(
            session,
            document_id=document.id,
            segment_id=segment.id,
            purpose="condition_checklist",
            prompt_version=CHECKLIST_PROMPT_VERSION,
            prompt=prompt,
        )
    except LlmDisabledError:
        return condition, None
    except Exception as exc:
        await _flag(
            session,
            project_id=document.project_id,
            document_id=document.id,
            reason=f"{condition.label} LLM checklist review failed: {exc}",
        )
        return condition, None

    parsed = _parse_response_json(response)
    if parsed.get("is_condition") is False:
        reason = _string_or_none(parsed.get("reason")) or "Model rejected this clause."
        await _flag(
            session,
            project_id=document.project_id,
            document_id=document.id,
            reason=f"{condition.label} skipped by LLM checklist review: {reason}",
        )
        return None, None

    reviewed = replace(
        condition,
        trigger=_string_or_none(parsed.get("trigger")) or condition.trigger,
        requirement_text=_string_or_none(parsed.get("requirement_text"))
        or condition.requirement_text,
        discretionary=_bool_or_default(parsed.get("discretionary"), condition.discretionary),
        dating_rule=_string_or_none(parsed.get("dating_rule")) or condition.dating_rule,
        waivable_by=_string_or_none(parsed.get("waivable_by")) or condition.waivable_by,
        confidence=_confidence_or_default(parsed.get("confidence"), condition.confidence),
    )
    reason = _string_or_none(parsed.get("reason")) or "Model reviewed the checklist condition."
    derivation = {
        "model": settings.openai_model,
        "prompt_version": CHECKLIST_PROMPT_VERSION,
        "input_spans": [
            {
                "document_id": str(document.id),
                "segment_id": str(segment.id),
                "char_start": segment.char_start,
                "char_end": segment.char_end,
            }
        ],
        "confidence": reviewed.confidence,
        "reason": reason,
        "llm_call_id": response.get("_llm_call_id"),
    }
    return reviewed, derivation


def _condition_review_prompt(
    *, document: Document, segment: SegmentDraft, condition: ConditionDraft
) -> str:
    return f"""You are extracting a project finance closing checklist from a financing agreement.
Return valid JSON only with these keys:
- is_condition: boolean
- trigger: string, one of "closing_date" or "each_credit_event"
- requirement_text: string, the complete checklist requirement from the clause
- discretionary: boolean
- dating_rule: string or null
- waivable_by: string or null
- confidence: number from 0 to 1
- reason: short explanation of why this is or is not a checklist condition

Document: {document.title or document.filename}
File: {document.filename}
Clause label: {condition.label}
Clause heading: {segment.heading or ""}
Deterministic trigger: {condition.trigger}
Deterministic requirement: {condition.requirement_text}

Full source clause:
{segment.text}
"""


def _parse_response_json(response: dict[str, Any]) -> dict[str, Any]:
    text = _response_text(response)
    if not text:
        return {}
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match is None:
            return {}
        try:
            parsed = json.loads(match.group(0))
        except json.JSONDecodeError:
            return {}
    return parsed if isinstance(parsed, dict) else {}


def _response_text(response: dict[str, Any]) -> str:
    output_text = response.get("output_text")
    if isinstance(output_text, str):
        return output_text
    chunks: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if isinstance(content, dict) and isinstance(content.get("text"), str):
                chunks.append(content["text"])
    return "\n".join(chunks)


def _string_or_none(value: object) -> str | None:
    if isinstance(value, str):
        stripped = value.strip()
        if stripped and stripped.lower() != "null":
            return stripped
    return None


def _bool_or_default(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _confidence_or_default(value: object, default: float) -> float:
    if isinstance(value, int | float):
        return max(0.0, min(1.0, float(value)))
    return default


def _members_from_known_bundle(term: str) -> list[str]:
    bundles = {
        "Material Project Documents": [
            "Power Purchase Agreement",
            "Interconnection Agreement",
            "EPC Agreement",
            "EPC Guaranty",
            "Module Supply Agreement",
            "O&M Agreement",
            "MIPA",
            "Warranty Agreements",
            "Development Agreement",
            "Leases",
        ],
        "Project Documents": [
            "Material Project Documents",
            "Real Property Documents",
            "Additional Project Documents",
        ],
        "Financing Documents": ["Agreement", "Notes", "Collateral Documents"],
        "Tax Equity Documents": [
            "Tax Equity ECCA",
            "Holdings Operating Agreement",
            "Tax Equity Guaranty",
        ],
    }
    return bundles.get(term, [])

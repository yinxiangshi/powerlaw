from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from powerlaw.events.types import EventType
from powerlaw.models.tables import (
    Condition,
    CrossRef,
    DefinedTerm,
    Dependency,
    Document,
    Event,
    Party,
    PartyAlias,
    PartyRole,
    Segment,
    TermMembership,
)
from powerlaw.schemas.api import (
    ConditionRead,
    CrossReferenceRead,
    DefinedTermRead,
    PartyRead,
    ProvenanceRead,
    SegmentRead,
)


async def condition_read(session: AsyncSession, condition: Condition) -> ConditionRead:
    provenance = await condition_provenance(session, condition.segment_id)
    source_context = await condition_source_context(session, condition.segment_id)
    cross_refs = await cross_reference_reads(session, condition.segment_id)
    dependencies = (
        await session.scalars(
            select(Dependency.to_condition).where(Dependency.from_condition == condition.id)
        )
    ).all()
    llm_reason, llm_call_id = await condition_llm_reason(session, condition.id)
    return ConditionRead.model_validate(
        condition,
        from_attributes=True,
    ).model_copy(
        update={
            "provenance": provenance,
            "source_context": source_context,
            "cross_refs": cross_refs,
            "dependencies": list(dependencies),
            "llm_reason": llm_reason,
            "llm_call_id": llm_call_id,
        }
    )


async def condition_provenance(session: AsyncSession, segment_id: UUID) -> ProvenanceRead | None:
    segment = await session.get(Segment, segment_id)
    if segment is None:
        return None
    document = await session.get(Document, segment.document_id)
    if document is None:
        return None
    return ProvenanceRead(
        segment_id=segment.id,
        label=segment.label,
        heading=segment.heading,
        document_id=document.id,
        document_title=document.title,
        filename=document.filename,
        char_start=segment.char_start,
        char_end=segment.char_end,
        text=segment.text,
    )


async def condition_source_context(
    session: AsyncSession, segment_id: UUID
) -> ProvenanceRead | None:
    segment = await session.get(Segment, segment_id)
    if segment is None:
        return None
    context_segment_id = segment.parent_id or segment.id
    return await condition_provenance(session, context_segment_id)


async def cross_reference_reads(
    session: AsyncSession, segment_id: UUID
) -> list[CrossReferenceRead]:
    refs = (
        await session.scalars(select(CrossRef).where(CrossRef.from_segment == segment_id))
    ).all()
    reads: list[CrossReferenceRead] = []
    for ref in refs:
        source = await condition_provenance(session, ref.to_segment) if ref.to_segment else None
        reads.append(
            CrossReferenceRead(
                to_label=ref.to_label,
                to_segment=ref.to_segment,
                resolved=ref.resolved,
                source=source,
            )
        )
    return reads


async def condition_llm_reason(
    session: AsyncSession, condition_id: UUID
) -> tuple[str | None, UUID | None]:
    event = await session.scalar(
        select(Event)
        .where(
            Event.event_type == EventType.CONDITION_EXTRACTED,
            Event.target_id == condition_id,
            Event.derivation.is_not(None),
        )
        .order_by(Event.id.desc())
    )
    if event is None or event.derivation is None:
        return None, None
    reason = event.derivation.get("reason")
    llm_call_id = event.derivation.get("llm_call_id")
    parsed_llm_call_id = None
    if isinstance(llm_call_id, str):
        try:
            parsed_llm_call_id = UUID(llm_call_id)
        except ValueError:
            parsed_llm_call_id = None
    return (reason if isinstance(reason, str) else None, parsed_llm_call_id)


def build_segment_tree(segments: list[Segment]) -> list[SegmentRead]:
    by_id: dict[UUID, SegmentRead] = {}
    roots: list[SegmentRead] = []
    for segment in segments:
        by_id[segment.id] = SegmentRead(
            id=segment.id,
            document_id=segment.document_id,
            parent_id=segment.parent_id,
            label=segment.label,
            heading=segment.heading,
            text=segment.text,
            char_start=segment.char_start,
            char_end=segment.char_end,
            order_index=segment.order_index,
            children=[],
        )
    for segment in segments:
        node = by_id[segment.id]
        if segment.parent_id and segment.parent_id in by_id:
            by_id[segment.parent_id].children.append(node)
        else:
            roots.append(node)
    return roots


async def defined_term_reads(
    session: AsyncSession, document_ids: list[UUID]
) -> list[DefinedTermRead]:
    terms = (
        await session.scalars(select(DefinedTerm).where(DefinedTerm.document_id.in_(document_ids)))
    ).all()
    reads: list[DefinedTermRead] = []
    for term in terms:
        memberships = (
            await session.scalars(
                select(TermMembership).where(TermMembership.defined_term == term.id)
            )
        ).all()
        reads.append(
            DefinedTermRead(
                id=term.id,
                document_id=term.document_id,
                term=term.term,
                definition_kind=term.definition_kind,
                members=[
                    {
                        "member_name": membership.member_name,
                        "member_document": membership.member_document,
                        "member_party": membership.member_party,
                        "resolved": membership.resolved,
                    }
                    for membership in memberships
                ],
            )
        )
    return reads


async def party_reads(session: AsyncSession, project_id: UUID) -> list[PartyRead]:
    parties = (await session.scalars(select(Party).where(Party.project_id == project_id))).all()
    reads: list[PartyRead] = []
    for party in parties:
        aliases = (
            await session.scalars(select(PartyAlias.alias).where(PartyAlias.party_id == party.id))
        ).all()
        roles = (
            await session.scalars(select(PartyRole).where(PartyRole.party_id == party.id))
        ).all()
        reads.append(
            PartyRead(
                id=party.id,
                project_id=party.project_id,
                canonical_name=party.canonical_name,
                entity_type=party.entity_type,
                aliases=list(aliases),
                roles=[{"document_id": role.document_id, "role": role.role} for role in roles],
            )
        )
    return reads


async def cross_refs_for_segment(session: AsyncSession, segment_id: UUID) -> list[dict[str, Any]]:
    refs = (
        await session.scalars(select(CrossRef).where(CrossRef.from_segment == segment_id))
    ).all()
    return [
        {
            "to_label": ref.to_label,
            "to_segment": ref.to_segment,
            "resolved": ref.resolved,
        }
        for ref in refs
    ]

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from powerlaw.config import Settings, get_settings
from powerlaw.db import get_session
from powerlaw.events.store import append_event
from powerlaw.events.types import ActorType, EventType
from powerlaw.ingestion.pipeline import generate_project_checklist
from powerlaw.models.tables import Condition, Document, Project, Rationale, Segment
from powerlaw.repositories.read import condition_read, defined_term_reads, party_reads
from powerlaw.schemas.api import (
    ConditionConfirmRequest,
    ConditionCorrectRequest,
    ConditionRead,
    ConditionStatusUpdateRequest,
    DefinedTermRead,
    PartyRead,
)

router = APIRouter(tags=["graph"])


@router.get("/projects/{project_id}/conditions", response_model=list[ConditionRead])
async def list_conditions(
    project_id: UUID,
    trigger: str | None = None,
    status: str | None = None,
    verification_status: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[ConditionRead]:
    query = select(Condition).join(Segment).where(Condition.project_id == project_id)
    if trigger:
        query = query.where(Condition.trigger == trigger)
    if status:
        query = query.where(Condition.status == status)
    if verification_status:
        query = query.where(Condition.verification_status == verification_status)
    rows = (await session.scalars(query.order_by(Segment.char_start))).all()
    return [await condition_read(session, row) for row in rows]


@router.post("/projects/{project_id}/generate-checklist", response_model=list[ConditionRead])
async def generate_checklist(
    project_id: UUID,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[ConditionRead]:
    async with session.begin():
        project = await session.get(Project, project_id)
        if project is None or project.deleted_at is not None:
            raise HTTPException(status_code=404, detail="project not found")
        await generate_project_checklist(session, project_id=project_id, settings=settings)

    rows = (
        await session.scalars(
            select(Condition)
            .join(Segment)
            .where(Condition.project_id == project_id)
            .order_by(Segment.char_start)
        )
    ).all()
    return [await condition_read(session, row) for row in rows]


@router.get("/conditions/{condition_id}", response_model=ConditionRead)
async def get_condition(
    condition_id: UUID, session: AsyncSession = Depends(get_session)
) -> ConditionRead:
    condition = await session.get(Condition, condition_id)
    if condition is None:
        raise HTTPException(status_code=404, detail="condition not found")
    return await condition_read(session, condition)


@router.post("/conditions/{condition_id}/confirm", response_model=ConditionRead)
async def confirm_condition(
    condition_id: UUID,
    body: ConditionConfirmRequest,
    session: AsyncSession = Depends(get_session),
) -> ConditionRead:
    condition = await session.get(Condition, condition_id)
    if condition is None:
        raise HTTPException(status_code=404, detail="condition not found")
    rationale = Rationale(text=body.rationale, author=body.author, is_privileged=True)
    session.add(rationale)
    await session.flush()
    await append_event(
        session,
        project_id=condition.project_id,
        actor_id=body.author,
        actor_type=ActorType.HUMAN,
        event_type=EventType.CONDITION_CONFIRMED,
        target_type="condition",
        target_id=condition.id,
        payload={"condition_id": condition.id},
        rationale_id=rationale.id,
    )
    await session.commit()
    refreshed = await session.get(Condition, condition_id)
    if refreshed is None:
        raise HTTPException(status_code=500, detail="condition projection failed")
    return await condition_read(session, refreshed)


@router.post("/conditions/{condition_id}/correct", response_model=ConditionRead)
async def correct_condition(
    condition_id: UUID,
    body: ConditionCorrectRequest,
    session: AsyncSession = Depends(get_session),
) -> ConditionRead:
    condition = await session.get(Condition, condition_id)
    if condition is None:
        raise HTTPException(status_code=404, detail="condition not found")
    before = (
        body.previous_value
        if body.previous_value is not None
        else getattr(condition, body.field, None)
    )
    rationale = Rationale(text=body.rationale, author=body.author, is_privileged=True)
    session.add(rationale)
    await session.flush()
    await append_event(
        session,
        project_id=condition.project_id,
        actor_id=body.author,
        actor_type=ActorType.HUMAN,
        event_type=EventType.CONDITION_CORRECTED,
        target_type="condition",
        target_id=condition.id,
        payload={"field": body.field, "before": before, "after": body.new_value},
        rationale_id=rationale.id,
    )
    await session.commit()
    refreshed = await session.get(Condition, condition_id)
    if refreshed is None:
        raise HTTPException(status_code=500, detail="condition projection failed")
    return await condition_read(session, refreshed)


@router.post("/conditions/{condition_id}/status", response_model=ConditionRead)
async def update_condition_status(
    condition_id: UUID,
    body: ConditionStatusUpdateRequest,
    session: AsyncSession = Depends(get_session),
) -> ConditionRead:
    condition = await session.get(Condition, condition_id)
    if condition is None:
        raise HTTPException(status_code=404, detail="condition not found")
    before = condition.status
    rationale = Rationale(
        text=body.rationale
        or f"Workflow status changed from {before} to {body.status} in the project dashboard.",
        author=body.author,
        is_privileged=True,
    )
    session.add(rationale)
    await session.flush()
    await append_event(
        session,
        project_id=condition.project_id,
        actor_id=body.author,
        actor_type=ActorType.HUMAN,
        event_type=EventType.CONDITION_CORRECTED,
        target_type="condition",
        target_id=condition.id,
        payload={
            "field": "status",
            "before": before,
            "after": body.status,
            "source": "condition_status_control",
        },
        rationale_id=rationale.id,
    )
    await session.commit()
    refreshed = await session.get(Condition, condition_id)
    if refreshed is None:
        raise HTTPException(status_code=500, detail="condition projection failed")
    return await condition_read(session, refreshed)


@router.get("/projects/{project_id}/defined-terms", response_model=list[DefinedTermRead])
async def list_defined_terms(
    project_id: UUID,
    session: AsyncSession = Depends(get_session),
    terms: list[str] | None = Query(default=None),
) -> list[DefinedTermRead]:
    documents = (
        await session.scalars(select(Document).where(Document.project_id == project_id))
    ).all()
    reads = await defined_term_reads(session, [document.id for document in documents])
    if terms:
        wanted = {term.lower() for term in terms}
        reads = [read for read in reads if read.term.lower() in wanted]
    return reads


@router.get("/projects/{project_id}/parties", response_model=list[PartyRead])
async def list_parties(
    project_id: UUID, session: AsyncSession = Depends(get_session)
) -> list[PartyRead]:
    return await party_reads(session, project_id)

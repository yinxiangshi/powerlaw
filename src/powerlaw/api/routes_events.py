from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from powerlaw.db import get_session
from powerlaw.models.tables import Event, Rationale
from powerlaw.schemas.api import EventRead

router = APIRouter(tags=["audit"])


@router.get("/projects/{project_id}/events", response_model=list[EventRead])
async def list_events(
    project_id: UUID,
    actor_type: str | None = None,
    event_type: str | None = None,
    document_id: UUID | None = None,
    limit: int = Query(default=1000, ge=1, le=5000),
    session: AsyncSession = Depends(get_session),
) -> list[EventRead]:
    query = (
        select(Event, Rationale)
        .outerjoin(Rationale, Event.rationale_id == Rationale.id)
        .where(Event.project_id == project_id)
    )
    if actor_type:
        query = query.where(Event.actor_type == actor_type)
    if event_type:
        query = query.where(Event.event_type == event_type)
    if document_id:
        doc_id_text = str(document_id)
        query = query.where(
            or_(
                Event.target_id == document_id,
                Event.payload["id"].as_string() == doc_id_text,
                Event.payload["document_id"].as_string() == doc_id_text,
            )
        )
    query = query.order_by(Event.id.desc()).limit(limit)
    rows = (await session.execute(query)).all()
    return [
        EventRead.model_validate(event).model_copy(
            update={
                "rationale_text": rationale.text if rationale else None,
                "rationale_author": rationale.author if rationale else None,
            }
        )
        for event, rationale in rows
    ]

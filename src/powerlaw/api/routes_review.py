from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from powerlaw.db import get_session
from powerlaw.events.types import EventType
from powerlaw.models.tables import Event

router = APIRouter(tags=["review"])


@router.get("/projects/{project_id}/review-queue")
async def review_queue(
    project_id: UUID, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    rows = (
        await session.scalars(
            select(Event)
            .where(Event.project_id == project_id, Event.event_type == EventType.EXTRACTION_FLAGGED)
            .order_by(Event.id.desc())
        )
    ).all()
    return [
        {
            "event_id": row.id,
            "target_type": row.target_type,
            "target_id": row.target_id,
            "reason": row.payload.get("reason"),
            "payload": row.payload,
            "created_at": row.ts,
        }
        for row in rows
    ]

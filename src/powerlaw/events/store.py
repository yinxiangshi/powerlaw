from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from powerlaw.events.projections import apply_event
from powerlaw.events.types import ActorType
from powerlaw.models.tables import Event


class EventValidationError(ValueError):
    pass


async def append_event(
    session: AsyncSession,
    *,
    project_id: UUID,
    actor_id: str,
    actor_type: ActorType | str,
    event_type: str,
    payload: dict[str, Any],
    target_type: str | None = None,
    target_id: UUID | None = None,
    derivation: dict[str, Any] | None = None,
    rationale_id: UUID | None = None,
    caused_by: int | None = None,
) -> Event:
    actor_type_value = actor_type.value if isinstance(actor_type, ActorType) else actor_type
    if actor_type_value == ActorType.MODEL and derivation is None:
        raise EventValidationError("model events must carry derivation")
    if actor_type_value == ActorType.HUMAN and rationale_id is None:
        raise EventValidationError("human events must carry rationale_id")

    event = Event(
        project_id=project_id,
        actor_id=actor_id,
        actor_type=actor_type_value,
        event_type=event_type.value if isinstance(event_type, Enum) else event_type,
        target_type=target_type,
        target_id=target_id,
        payload=_jsonable(payload),
        derivation=_jsonable(derivation) if derivation is not None else None,
        rationale_id=rationale_id,
        caused_by=caused_by,
    )
    session.add(event)
    await session.flush()
    await apply_event(session, event, payload)
    await session.flush()
    return event


def _jsonable(value: Any) -> Any:
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, date | datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list | tuple):
        return [_jsonable(item) for item in value]
    return value

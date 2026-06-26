from datetime import datetime
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from powerlaw.db import get_session
from powerlaw.events.projections import project_counters, project_state_as_of
from powerlaw.events.store import append_event
from powerlaw.events.types import ActorType, EventType
from powerlaw.models.tables import Project
from powerlaw.schemas.api import (
    ProjectCreate,
    ProjectDeleteResult,
    ProjectDetail,
    ProjectRead,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.post("", response_model=ProjectRead)
async def create_project(
    body: ProjectCreate, session: AsyncSession = Depends(get_session)
) -> Project:
    project_id = uuid4()
    async with session.begin():
        await append_event(
            session,
            project_id=project_id,
            actor_id="api",
            actor_type=ActorType.SYSTEM,
            event_type=EventType.PROJECT_CREATED,
            target_type="project",
            target_id=project_id,
            payload={"id": project_id, "name": body.name, "aliases": body.aliases},
        )
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=500, detail="project projection failed")
    return project


@router.get("", response_model=list[ProjectDetail])
async def list_projects(session: AsyncSession = Depends(get_session)) -> list[ProjectDetail]:
    projects = (
        await session.scalars(
            select(Project).where(Project.deleted_at.is_(None)).order_by(Project.created_at.desc())
        )
    ).all()
    result: list[ProjectDetail] = []
    for project in projects:
        result.append(await _project_detail(session, project))
    return result


@router.get("/{project_id}", response_model=ProjectDetail)
async def get_project(
    project_id: UUID, session: AsyncSession = Depends(get_session)
) -> ProjectDetail:
    project = await session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="project not found")
    return await _project_detail(session, project)


@router.delete("/{project_id}", response_model=ProjectDeleteResult)
async def delete_project(
    project_id: UUID, session: AsyncSession = Depends(get_session)
) -> ProjectDeleteResult:
    async with session.begin():
        project = await session.get(Project, project_id)
        if project is None or project.deleted_at is not None:
            raise HTTPException(status_code=404, detail="project not found")
        await append_event(
            session,
            project_id=project_id,
            actor_id="api",
            actor_type=ActorType.SYSTEM,
            event_type=EventType.PROJECT_DELETED,
            target_type="project",
            target_id=project_id,
            payload={"id": project_id},
        )
    return ProjectDeleteResult(id=project_id, deleted=True)


@router.get("/{project_id}/state")
async def get_project_state(
    project_id: UUID,
    as_of: datetime | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    project = await session.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(status_code=404, detail="project not found")
    return await project_state_as_of(session, project_id, as_of)


async def _project_detail(session: AsyncSession, project: Project) -> ProjectDetail:
    base = ProjectRead.model_validate(project, from_attributes=True).model_dump()
    return ProjectDetail(**base, counters=await project_counters(session, project.id))

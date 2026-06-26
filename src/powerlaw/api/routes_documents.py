from pathlib import Path
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from powerlaw.config import Settings, get_settings
from powerlaw.db import get_session
from powerlaw.events.store import append_event
from powerlaw.events.types import ActorType, EventType
from powerlaw.ingestion.intake import normalize_file
from powerlaw.ingestion.pipeline import link_project_bundles, process_document
from powerlaw.models.tables import Document, IngestionJob, Segment
from powerlaw.repositories.read import build_segment_tree
from powerlaw.schemas.api import DocumentRead, JobRead, SegmentRead, UploadResult

router = APIRouter(tags=["documents"])


@router.post("/projects/{project_id}/documents", response_model=list[UploadResult])
async def upload_documents(
    project_id: UUID,
    files: list[UploadFile] = File(...),
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> list[UploadResult]:
    results: list[UploadResult] = []
    project_dir = settings.storage_dir / str(project_id)
    project_dir.mkdir(parents=True, exist_ok=True)

    async with session.begin():
        for upload in files:
            document_id = uuid4()
            job_id = uuid4()
            destination = _safe_destination(project_dir, document_id, upload.filename or "upload")
            destination.write_bytes(await upload.read())
            normalized = normalize_file(destination)
            await append_event(
                session,
                project_id=project_id,
                actor_id="api",
                actor_type=ActorType.SYSTEM,
                event_type=EventType.DOCUMENT_INGESTED,
                target_type="document",
                target_id=document_id,
                payload={
                    "id": document_id,
                    "filename": upload.filename or destination.name,
                    "mime": upload.content_type or normalized.mime,
                    "content_hash": normalized.content_hash,
                    "storage_path": str(destination),
                    "version": 1,
                },
            )
            await append_event(
                session,
                project_id=project_id,
                actor_id="api",
                actor_type=ActorType.SYSTEM,
                event_type=EventType.JOB_CREATED,
                target_type="job",
                target_id=job_id,
                payload={"id": job_id, "document_id": document_id, "status": "queued"},
            )
            if settings.process_uploads_inline:
                await process_document(
                    session, document_id=document_id, job_id=job_id, settings=settings
                )
            results.append(
                UploadResult(
                    document_id=document_id,
                    job_id=job_id,
                    filename=upload.filename or destination.name,
                    status="done" if settings.process_uploads_inline else "queued",
                )
            )
        if settings.process_uploads_inline:
            await link_project_bundles(session, project_id)
    return results


@router.get("/projects/{project_id}/documents", response_model=list[DocumentRead])
async def list_project_documents(
    project_id: UUID, session: AsyncSession = Depends(get_session)
) -> list[Document]:
    return list(
        (
            await session.scalars(
                select(Document)
                .where(Document.project_id == project_id)
                .order_by(Document.created_at.desc())
            )
        ).all()
    )


@router.get("/documents/{document_id}", response_model=DocumentRead)
async def get_document(document_id: UUID, session: AsyncSession = Depends(get_session)) -> Document:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    return document


@router.get("/documents/{document_id}/segments", response_model=list[SegmentRead])
async def get_document_segments(
    document_id: UUID, session: AsyncSession = Depends(get_session)
) -> list[SegmentRead]:
    segments = (
        await session.scalars(
            select(Segment)
            .where(Segment.document_id == document_id)
            .order_by(Segment.char_start, Segment.order_index)
        )
    ).all()
    return build_segment_tree(list(segments))


@router.get("/documents/{document_id}/text")
async def get_document_text(
    document_id: UUID, session: AsyncSession = Depends(get_session)
) -> dict[str, str]:
    document = await session.get(Document, document_id)
    if document is None or not document.storage_path:
        raise HTTPException(status_code=404, detail="document not found")
    path = Path(document.storage_path)
    if not path.exists():
        raise HTTPException(status_code=404, detail="stored file not found")
    return {"text": normalize_file(path).text}


@router.post("/documents/{document_id}/reprocess", response_model=JobRead)
async def reprocess_document(
    document_id: UUID,
    session: AsyncSession = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> IngestionJob:
    document = await session.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="document not found")
    job_id = uuid4()
    await append_event(
        session,
        project_id=document.project_id,
        actor_id="api",
        actor_type=ActorType.SYSTEM,
        event_type=EventType.JOB_CREATED,
        target_type="job",
        target_id=job_id,
        payload={"id": job_id, "document_id": document_id, "status": "queued"},
    )
    await process_document(session, document_id=document_id, job_id=job_id, settings=settings)
    await link_project_bundles(session, document.project_id)
    await session.commit()
    job = await session.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(status_code=500, detail="job projection failed")
    return job


@router.get("/jobs/{job_id}", response_model=JobRead)
async def get_job(job_id: UUID, session: AsyncSession = Depends(get_session)) -> IngestionJob:
    job = await session.get(IngestionJob, job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return job


def _safe_destination(directory: Path, document_id: UUID, filename: str) -> Path:
    suffix = Path(filename).suffix
    return directory / f"{document_id}{suffix}"

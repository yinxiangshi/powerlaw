from uuid import UUID

from powerlaw.config import get_settings
from powerlaw.db import AsyncSessionLocal
from powerlaw.ingestion.pipeline import process_document

try:
    import procrastinate
    from procrastinate.contrib.aiopg import AiopgConnector
except Exception:  # pragma: no cover - worker dependency is installed by uv sync
    procrastinate = None
    AiopgConnector = None


if procrastinate is not None and AiopgConnector is not None:
    settings = get_settings()
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    app = procrastinate.App(connector=AiopgConnector(dsn=dsn))

    @app.task
    async def process_document_job(document_id: str, job_id: str | None = None) -> None:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await process_document(
                    session,
                    document_id=UUID(document_id),
                    job_id=UUID(job_id) if job_id else None,
                )

else:
    app = None

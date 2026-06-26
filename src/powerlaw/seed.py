import argparse
import asyncio
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from powerlaw.db import AsyncSessionLocal
from powerlaw.events.projections import project_counters
from powerlaw.events.store import append_event
from powerlaw.events.types import ActorType, EventType
from powerlaw.ingestion.pipeline import (
    generate_project_checklist,
    ingest_existing_file,
    link_project_bundles,
)
from powerlaw.models.tables import Project


async def seed(data_dir: Path, project_name: str) -> None:
    async with AsyncSessionLocal() as session:
        async with session.begin():
            project_id = uuid4()
            await append_event(
                session,
                project_id=project_id,
                actor_id="seed",
                actor_type=ActorType.SYSTEM,
                event_type=EventType.PROJECT_CREATED,
                target_type="project",
                target_id=project_id,
                payload={"id": project_id, "name": project_name, "aliases": ["NC-31"]},
            )
            for path in sorted(data_dir.glob("*.txt")):
                await ingest_existing_file(session, project_id=project_id, path=path)
            await link_project_bundles(session, project_id)
            await generate_project_checklist(session, project_id=project_id)

        project = await session.scalar(select(Project).where(Project.id == project_id))
        if project is None:
            raise RuntimeError("project projection failed during seed")
        counters = await project_counters(session, project_id)
        print(f"Seeded project {project.name}: {project_id}")
        print(counters)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, default=Path("data/exhibits"))
    parser.add_argument("--project-name", default="NC-31 Solar Financing")
    args = parser.parse_args()
    asyncio.run(seed(args.data_dir, args.project_name))


if __name__ == "__main__":
    main()

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from powerlaw.api import (
    routes_conditions,
    routes_copilot,
    routes_documents,
    routes_events,
    routes_projects,
    routes_review,
)
from powerlaw.logging import configure_logging


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="PowerLaw Layer 1 Backend", version="0.1.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3101",
            "https://localhost:3101",
            "http://127.0.0.1:3101",
            "https://127.0.0.1:3101",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    prefix = "/api/v1"
    app.include_router(routes_projects.router, prefix=prefix)
    app.include_router(routes_documents.router, prefix=prefix)
    app.include_router(routes_conditions.router, prefix=prefix)
    app.include_router(routes_events.router, prefix=prefix)
    app.include_router(routes_review.router, prefix=prefix)
    app.include_router(routes_copilot.router, prefix=prefix)
    return app


app = create_app()

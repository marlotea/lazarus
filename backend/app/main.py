import logging
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select, text
from sqlalchemy.exc import SQLAlchemyError

from app.db import SessionLocal
from app.models import WorkerHeartbeat, Workspace
from app.schemas.health import HealthResponse
from app.settings import get_settings

log = logging.getLogger(__name__)

WORKSPACE_NAME = "cpsc-448"  # seeded by supabase/seed.sql


def load_workspace_id() -> uuid.UUID | None:
    with SessionLocal() as db:
        return db.scalar(select(Workspace.id).where(Workspace.name == WORKSPACE_NAME))


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # Read the workspace id once; every insert uses it. If the DB is down at startup the
    # app still starts (so /api/health can report db: false) and get_workspace_id retries.
    try:
        app.state.workspace_id = load_workspace_id()
    except SQLAlchemyError as exc:
        log.warning("Could not read workspace id at startup: %s", exc)
        app.state.workspace_id = None
    if app.state.workspace_id is None:
        log.warning("Workspace %r not found yet; run `make db-reset`.", WORKSPACE_NAME)
    yield


def get_workspace_id(request: Request) -> uuid.UUID:
    """FastAPI dependency: the seeded workspace id (503 if the DB is not ready)."""
    state = request.app.state
    if state.workspace_id is None:
        try:
            state.workspace_id = load_workspace_id()
        except SQLAlchemyError:
            state.workspace_id = None
        if state.workspace_id is None:
            raise HTTPException(503, f"Workspace {WORKSPACE_NAME!r} missing; run `make db-reset`.")
    return state.workspace_id


settings = get_settings()

app = FastAPI(title="Research Tracker API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health", response_model=HealthResponse, tags=["health"])
def health() -> HealthResponse:
    """Liveness, database reachability and the newest worker heartbeat."""
    try:
        with SessionLocal() as db:
            db.execute(text("select 1"))
            last_seen = db.scalar(select(func.max(WorkerHeartbeat.last_seen)))
    except SQLAlchemyError:
        return HealthResponse(ok=True, db=False, worker_last_seen=None)
    return HealthResponse(ok=True, db=True, worker_last_seen=last_seen)

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.db import SessionLocal
from app.deps import WORKSPACE_NAME, get_workspace_id, load_workspace_id
from app.models import WorkerHeartbeat
from app.routers import catalog, experiments, runs
from app.schemas.health import HealthResponse
from app.settings import get_settings

__all__ = ["WORKSPACE_NAME", "app", "get_workspace_id"]

log = logging.getLogger(__name__)


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


settings = get_settings()

app = FastAPI(title="Research Tracker API", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_UNAVAILABLE = "Cannot reach the database. Is Supabase running? Start it with 'make db'."
DB_ERROR = "Database error. If the tables are missing, run 'make db-reset'."


# Registered handlers run inside the CORS middleware, so the browser can read these errors
# (an unhandled 500 has no CORS headers and looks like the API is down).
@app.exception_handler(OperationalError)
def db_unavailable(request: Request, exc: OperationalError) -> JSONResponse:
    log.warning("database unavailable: %s", exc)
    return JSONResponse(status_code=503, content={"detail": DB_UNAVAILABLE})


@app.exception_handler(SQLAlchemyError)
def db_error(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    log.exception("database error", exc_info=exc)
    return JSONResponse(status_code=500, content={"detail": DB_ERROR})


app.include_router(experiments.router)
app.include_router(catalog.router)
app.include_router(runs.router)


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

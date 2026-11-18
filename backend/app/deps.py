"""Shared FastAPI dependencies. Kept out of app.main so routers can import them."""

import uuid

from fastapi import HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.db import SessionLocal
from app.models import Workspace

WORKSPACE_NAME = "cpsc-448"  # seeded by supabase/seed.sql


def load_workspace_id() -> uuid.UUID | None:
    with SessionLocal() as db:
        return db.scalar(select(Workspace.id).where(Workspace.name == WORKSPACE_NAME))


def get_workspace_id(request: Request) -> uuid.UUID:
    """FastAPI dependency: the seeded workspace id (503 if the DB is not ready)."""
    state = request.app.state
    if getattr(state, "workspace_id", None) is None:
        try:
            state.workspace_id = load_workspace_id()
        except OperationalError:
            raise  # database unreachable: app.main turns this into a 503 saying so
        except SQLAlchemyError:  # e.g. tables missing before the first `make db-reset`
            state.workspace_id = None
        if state.workspace_id is None:
            raise HTTPException(503, f"Workspace {WORKSPACE_NAME!r} missing; run `make db-reset`.")
    return state.workspace_id

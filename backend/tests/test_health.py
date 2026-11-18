"""M1 checks. Needs the local database: `make db && make db-reset`."""

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.db import SessionLocal
from app.deps import WORKSPACE_NAME
from app.main import app
from app.models import Workspace


def test_seed_workspace_exists():
    with SessionLocal() as db:
        names = db.scalars(select(Workspace.name)).all()
    assert WORKSPACE_NAME in names


def test_health_reports_db_and_reads_workspace_at_startup():
    with TestClient(app) as client:  # context manager runs the lifespan
        res = client.get("/api/health")
        assert app.state.workspace_id is not None
    assert res.status_code == 200
    body = res.json()
    assert body["ok"] is True
    assert body["db"] is True
    assert "worker_last_seen" in body

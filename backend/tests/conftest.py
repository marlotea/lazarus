"""Shared fixtures. Tests that use `client` or `fake_catalog` need the local database
(`make db && make db-reset`)."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.ibl.catalog_sync import sync_catalog
from app.main import app


@pytest.fixture(scope="session")
def client() -> Iterator[TestClient]:
    with TestClient(app) as c:  # context manager runs the lifespan
        yield c


@pytest.fixture(scope="session")
def fake_catalog() -> None:
    """Upsert the fake IBL catalog (idempotent, so safe on a dev database)."""
    with SessionLocal() as db:
        sync_catalog(db, fake=True)

from fastapi.testclient import TestClient

from app.main import app


def test_openapi_schema_is_served():
    res = TestClient(app).get("/openapi.json")
    assert res.status_code == 200
    assert res.json()["info"]["title"] == "Research Tracker API"


def test_database_outage_is_a_503_with_a_hint_and_cors_headers():
    """A request while Postgres is down gets a readable 503 the browser can see (CORS)."""
    from sqlalchemy.exc import OperationalError

    from app.db import get_db

    def broken_db():
        raise OperationalError("select 1", {}, Exception("connection refused"))
        yield  # pragma: no cover

    app.dependency_overrides[get_db] = broken_db
    try:
        res = TestClient(app).get(
            "/api/catalog/regions", headers={"Origin": "http://localhost:3000"}
        )
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert res.status_code == 503
    assert "make db" in res.json()["detail"]
    assert res.headers["access-control-allow-origin"] == "http://localhost:3000"

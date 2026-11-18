from fastapi.testclient import TestClient

from app.main import app


def test_openapi_schema_is_served():
    res = TestClient(app).get("/openapi.json")
    assert res.status_code == 200
    assert res.json()["info"]["title"] == "Research Tracker API"

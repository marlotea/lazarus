"""Experiments API. Needs the local database; every experiment created here is deleted."""

import uuid
from collections.abc import Iterator
from datetime import datetime, timedelta

import pytest
from sqlalchemy import delete

from app.db import SessionLocal
from app.ibl.fake import fake_sessions
from app.models import Experiment, ExperimentItem, Run


@pytest.fixture
def created(client) -> Iterator[list[str]]:
    """Collects ids of experiments made by a test and deletes them afterwards."""
    ids: list[str] = []
    yield ids
    if ids:
        with SessionLocal() as db:
            db.execute(delete(Experiment).where(Experiment.id.in_([uuid.UUID(i) for i in ids])))
            db.commit()


def make(client, created, **body):
    res = client.post("/api/experiments", json={"title": "Test experiment", **body})
    assert res.status_code == 201, res.text
    created.append(res.json()["id"])
    return res.json()


def test_create_returns_201_with_defaults(client, created):
    exp = make(client, created, title="  Control 01  ")
    assert exp["title"] == "Control 01"  # surrounding whitespace is stripped
    assert exp["description"] == ""
    assert exp["item_count"] == exp["session_count"] == exp["run_count"] == 0
    created_at = datetime.fromisoformat(exp["created_at"])
    assert created_at.tzinfo is not None
    assert abs(datetime.now(created_at.tzinfo) - created_at) < timedelta(minutes=1)


@pytest.mark.parametrize(
    "body", [{}, {"title": ""}, {"title": "   "}, {"title": "x" * 201}, {"title": None}]
)
def test_create_rejects_bad_title(client, body):
    assert client.post("/api/experiments", json=body).status_code == 422


def test_create_accepts_200_char_title(client, created):
    assert make(client, created, title="x" * 200)["title"] == "x" * 200


def test_list_is_newest_first(client, created):
    a = make(client, created, title="first")
    b = make(client, created, title="second", description="desc")
    res = client.get("/api/experiments")
    assert res.status_code == 200
    rows = res.json()
    ids = [r["id"] for r in rows]
    assert ids.index(b["id"]) < ids.index(a["id"])
    times = [r["created_at"] for r in rows]
    assert times == sorted(times, reverse=True)
    row = next(r for r in rows if r["id"] == b["id"])
    assert set(row) >= {"id", "title", "description", "created_at", "item_count", "run_count"}
    assert row["description"] == "desc"


def test_get_one_and_404(client, created):
    exp = make(client, created, description="hello")
    res = client.get(f"/api/experiments/{exp['id']}")
    assert res.status_code == 200
    assert res.json() == exp
    assert client.get(f"/api/experiments/{uuid.uuid4()}").status_code == 404
    assert client.get("/api/experiments/not-a-uuid").status_code == 422


def test_patch_updates_fields_and_updated_at(client, created):
    exp = make(client, created, title="before", description="old")
    res = client.patch(f"/api/experiments/{exp['id']}", json={"title": "after"})
    assert res.status_code == 200
    body = res.json()
    assert body["title"] == "after"
    assert body["description"] == "old"  # untouched
    assert body["created_at"] == exp["created_at"]
    assert datetime.fromisoformat(body["updated_at"]) > datetime.fromisoformat(exp["updated_at"])

    res = client.patch(f"/api/experiments/{exp['id']}", json={"description": ""})
    assert res.json()["description"] == "" and res.json()["title"] == "after"
    assert client.get(f"/api/experiments/{exp['id']}").json()["title"] == "after"


def test_patch_validation_and_404(client, created):
    exp = make(client, created)
    url = f"/api/experiments/{exp['id']}"
    assert client.patch(url, json={"title": ""}).status_code == 422
    assert client.patch(url, json={"title": None}).status_code == 422
    assert client.patch(url, json={"description": None}).status_code == 422
    assert client.patch(url, json={"title": "y" * 201}).status_code == 422
    missing = client.patch(f"/api/experiments/{uuid.uuid4()}", json={"title": "z"})
    assert missing.status_code == 404


@pytest.mark.usefixtures("fake_catalog")
def test_counts_items_sessions_and_runs(client, created):
    exp = make(client, created)
    exp_id = uuid.UUID(exp["id"])
    s1, s2 = fake_sessions()[:2]
    with SessionLocal() as db:
        db.add_all(
            [
                ExperimentItem(experiment_id=exp_id, eid=s1.eid, region="CA1"),
                ExperimentItem(experiment_id=exp_id, eid=s1.eid, region="DG"),
                ExperimentItem(experiment_id=exp_id, eid=s2.eid, region="CA1"),
            ]
        )
        db.add(
            Run(
                workspace_id=client.app.state.workspace_id,
                experiment_id=exp_id,
                name="time-01",
                mode="time",
                params={},
                preprocess={},
                inputs=[],
            )
        )
        db.commit()
    one = client.get(f"/api/experiments/{exp_id}").json()
    assert (one["item_count"], one["session_count"], one["run_count"]) == (3, 2, 1)
    row = next(r for r in client.get("/api/experiments").json() if r["id"] == exp["id"])
    assert (row["item_count"], row["session_count"], row["run_count"]) == (3, 2, 1)

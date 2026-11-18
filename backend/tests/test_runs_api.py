"""CEBRA schema and runs API on the fake catalog. Needs the local database (and IBL_FAKE=1
in backend/.env); every experiment created here is deleted, which deletes its runs."""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.ibl.fake import fake_sessions
from app.models import Experiment, Run, TrialSplit
from app.settings import get_settings

pytestmark = [
    pytest.mark.usefixtures("fake_catalog"),
    pytest.mark.skipif(not get_settings().ibl_fake, reason="needs IBL_FAKE=1"),
]

S1, S2 = fake_sessions()[:2]  # S1: CA1 DG LP, S2: CA1 VISp


@pytest.fixture
def exp_id(client) -> Iterator[str]:
    res = client.post("/api/experiments", json={"title": "Runs test"})
    assert res.status_code == 201
    eid = res.json()["id"]
    yield eid
    with SessionLocal() as db:
        db.execute(delete(Experiment).where(Experiment.id == uuid.UUID(eid)))
        db.commit()


@pytest.fixture
def with_items(client, exp_id) -> str:
    pairs = [(S1.eid, "CA1"), (S1.eid, "DG"), (S2.eid, "VISp")]
    body = {"items": [{"eid": str(e), "region": r} for e, r in pairs]}
    assert client.put(f"/api/experiments/{exp_id}/items", json=body).status_code == 200
    return exp_id


def post_run(client, exp_id, **body):
    return client.post(
        f"/api/experiments/{exp_id}/runs", json={"name": "time-01", "mode": "time", **body}
    )


def test_cebra_schema(client):
    res = client.get("/api/cebra/schema")
    assert res.status_code == 200
    body = res.json()
    assert set(body["modes"]) == {"time", "behaviour", "hybrid"}
    time_props = list(body["modes"]["time"]["properties"])
    assert time_props[:3] == ["model_architecture", "output_dimension", "batch_size"]
    assert "continuous_labels" not in time_props
    beh = body["modes"]["behaviour"]["properties"]
    assert list(beh)[-2:] == ["continuous_labels", "discrete_label"]
    assert beh["output_dimension"] == {
        "default": 8,
        "description": "Size of the embedding.",
        "maximum": 64,
        "minimum": 2,
        "title": "Output dimension",
        "type": "integer",
    }
    for schema in body["modes"].values():
        assert "conditional" not in schema["properties"]
        assert "hybrid" not in schema["properties"]
    pre = body["preprocess"]["properties"]
    assert list(pre) == [
        "bin_size_ms",
        "align_event",
        "window_pre_s",
        "window_post_s",
        "good_units_only",
    ]
    assert pre["good_units_only"]["const"] is True


def test_queue_run_snapshots_items_and_splits(client, with_items):
    exp_id = with_items
    assert client.get(f"/api/experiments/{exp_id}/runs").json() == []
    res = post_run(
        client,
        exp_id,
        name="  beh-01 ",
        mode="behaviour",
        params={"output_dimension": 3, "discrete_label": "choice"},
        preprocess={"bin_size_ms": 50},
    )
    assert res.status_code == 201, res.text
    run = res.json()
    assert run["name"] == "beh-01"
    assert (run["status"], run["stage"], run["mode"]) == ("queued", "cebra", "behaviour")
    assert run["progress"] == {"done": 0, "total": 6}
    assert run["params"]["output_dimension"] == 3
    assert run["params"]["continuous_labels"] == ["wheel_velocity"]  # default filled in
    assert run["params"]["discrete_label"] == "choice"
    assert "conditional" not in run["params"]
    assert run["preprocess"]["bin_size_ms"] == 50
    assert run["preprocess"]["align_event"] == "stimOn_times"
    assert run["started_at"] is None and run["finished_at"] is None and run["error"] is None

    with SessionLocal() as db:
        splits = {
            s.eid: str(s.id)
            for s in db.scalars(
                select(TrialSplit).where(
                    TrialSplit.experiment_id == uuid.UUID(exp_id),
                    TrialSplit.superseded_at.is_(None),
                )
            )
        }
        row = db.get(Run, uuid.UUID(run["id"]))
        assert row is not None and row.status == "queued"
    assert sorted((i["eid"], i["region"], i["split_id"]) for i in run["inputs"]) == sorted(
        [
            (str(S1.eid), "CA1", splits[S1.eid]),
            (str(S1.eid), "DG", splits[S1.eid]),
            (str(S2.eid), "VISp", splits[S2.eid]),
        ]
    )

    # A reshuffle afterwards does not change the queued run's snapshot.
    assert client.post(f"/api/experiments/{exp_id}/splits/{S1.eid}/reshuffle").status_code == 201
    listed = client.get(f"/api/experiments/{exp_id}/runs").json()
    assert [r["id"] for r in listed] == [run["id"]]
    assert listed[0]["inputs"] == run["inputs"]
    assert client.get(f"/api/experiments/{exp_id}").json()["run_count"] == 1


def test_duplicate_name_is_409(client, with_items):
    assert post_run(client, with_items).status_code == 201
    res = post_run(client, with_items, mode="hybrid")
    assert res.status_code == 409
    assert res.json()["detail"] == [
        {
            "type": "duplicate_name",
            "loc": ["body", "name"],
            "msg": "Name already used in this experiment",
        }
    ]
    assert post_run(client, with_items, name="time-02").status_code == 201


def test_no_items_is_422(client, exp_id):
    res = post_run(client, exp_id)
    assert res.status_code == 422
    assert res.json()["detail"][0]["type"] == "no_items"
    assert client.get(f"/api/experiments/{exp_id}/runs").json() == []


def test_invalid_params_are_422_with_field_locs(client, with_items):
    def locs(res):
        assert res.status_code == 422, res.text
        return sorted(tuple(e["loc"]) for e in res.json()["detail"])

    res = post_run(
        client,
        with_items,
        mode="behaviour",
        params={"output_dimension": 100},
        preprocess={"bin_size_ms": 0, "good_units_only": False},
    )
    assert locs(res) == [
        ("body", "params", "output_dimension"),
        ("body", "preprocess", "bin_size_ms"),
        ("body", "preprocess", "good_units_only"),
    ]
    # The model-level "no labels" error is attached to the continuous labels field.
    res = post_run(
        client, with_items, mode="hybrid", params={"continuous_labels": [], "discrete_label": None}
    )
    assert locs(res) == [("body", "params", "continuous_labels")]
    assert res.json()["detail"][0]["msg"] == "Pick at least one behaviour label"
    # Fields of another mode are rejected, not silently dropped.
    res = post_run(client, with_items, params={"continuous_labels": ["wheel_velocity"]})
    assert res.status_code == 422
    assert res.json()["detail"][0]["loc"] == ["body", "params", "continuous_labels"]
    # Bad name / mode come from FastAPI's own body validation.
    assert post_run(client, with_items, name="  ").status_code == 422
    assert post_run(client, with_items, mode="jgw").status_code == 422
    assert client.get(f"/api/experiments/{with_items}/runs").json() == []


def test_missing_experiment_is_404(client):
    assert client.get(f"/api/experiments/{uuid.uuid4()}/runs").status_code == 404
    assert post_run(client, uuid.uuid4()).status_code == 404

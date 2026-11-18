"""Item selection and split endpoints on the fake catalog. Needs the local database (and
IBL_FAKE=1 in backend/.env); every experiment created here is deleted."""

import uuid
from collections.abc import Iterator

import pytest
from sqlalchemy import delete, select

from app.db import SessionLocal
from app.ibl.fake import fake_sessions, fake_valid_trials
from app.models import Experiment, IblSession, TrialSplit
from app.settings import get_settings

pytestmark = [
    pytest.mark.usefixtures("fake_catalog"),
    pytest.mark.skipif(not get_settings().ibl_fake, reason="needs IBL_FAKE=1"),
]

S1, S2, S3 = fake_sessions()[:3]  # S1: CA1 DG LP, S2: CA1 VISp, S3: CA1 DG PO


@pytest.fixture
def exp_id(client) -> Iterator[str]:
    res = client.post("/api/experiments", json={"title": "Items test"})
    assert res.status_code == 201
    eid = res.json()["id"]
    yield eid
    with SessionLocal() as db:
        db.execute(delete(Experiment).where(Experiment.id == uuid.UUID(eid)))
        db.commit()


def put(client, exp_id, pairs):
    body = {"items": [{"eid": str(e), "region": r} for e, r in pairs]}
    return client.put(f"/api/experiments/{exp_id}/items", json=body)


def splits_of(exp_id, eid):
    with SessionLocal() as db:
        return db.scalars(
            select(TrialSplit)
            .where(TrialSplit.experiment_id == uuid.UUID(exp_id), TrialSplit.eid == eid)
            .order_by(TrialSplit.created_at)
        ).all()


def test_empty_selection(client, exp_id):
    res = client.get(f"/api/experiments/{exp_id}/items")
    assert res.status_code == 200 and res.json() == []
    assert client.get(f"/api/experiments/{uuid.uuid4()}/items").status_code == 404
    assert put(client, uuid.uuid4(), []).status_code == 404


def test_put_then_get_items_with_splits(client, exp_id):
    res = put(client, exp_id, [(S2.eid, "VISp"), (S1.eid, "CA1"), (S1.eid, "DG"), (S1.eid, "DG")])
    assert res.status_code == 200, res.text
    items = res.json()
    assert client.get(f"/api/experiments/{exp_id}/items").json() == items
    # Ordered by subject, date, session, region; duplicates dropped.
    assert [(i["eid"], i["region"]) for i in items] == [
        (str(S1.eid), "CA1"),
        (str(S1.eid), "DG"),
        (str(S2.eid), "VISp"),
    ]
    first = items[0]
    assert set(first) == {
        "eid", "region", "subject", "lab", "session_date", "n_good_units", "split"
    }  # fmt: skip
    assert (first["subject"], first["lab"], first["session_date"]) == (
        S1.subject,
        S1.lab,
        S1.session_date.isoformat(),
    )
    assert first["n_good_units"] == S1.regions["CA1"]
    # One split per session, shared by that session's items.
    assert items[0]["split"] == items[1]["split"]
    assert items[0]["split"]["id"] != items[2]["split"]["id"]
    for item, session in [(items[0], S1), (items[2], S2)]:
        split = item["split"]
        assert set(split) == {"id", "seed", "n_a", "n_b"}
        n_valid = len(fake_valid_trials(session.eid))
        assert split["n_a"] + split["n_b"] == n_valid
        assert split["n_a"] == round(n_valid * 0.5)
        assert 0 <= split["seed"] < 2**31

    rows = splits_of(exp_id, S1.eid)
    assert len(rows) == 1 and rows[0].superseded_at is None
    assert set(rows[0].group_a).isdisjoint(rows[0].group_b)
    with SessionLocal() as db:
        assert db.get(IblSession, S1.eid).n_trials == S1.n_trials  # stored when split made

    exp = client.get(f"/api/experiments/{exp_id}").json()
    assert (exp["item_count"], exp["session_count"]) == (3, 2)


def test_put_replaces_selection_and_keeps_existing_splits(client, exp_id):
    items = put(client, exp_id, [(S1.eid, "CA1"), (S2.eid, "CA1")]).json()
    split_s1 = items[0]["split"]
    items = put(client, exp_id, [(S1.eid, "DG"), (S1.eid, "LP"), (S3.eid, "PO")]).json()
    assert [(i["eid"], i["region"]) for i in items] == [
        (str(S1.eid), "DG"),
        (str(S1.eid), "LP"),
        (str(S3.eid), "PO"),
    ]
    assert items[0]["split"] == split_s1  # S1 stayed selected, so its split is unchanged
    assert items[2]["split"] is not None  # S3 is new and got a split
    assert len(splits_of(exp_id, S1.eid)) == 1
    # S2 left the selection; its split row is kept (old runs may point at it).
    assert len(splits_of(exp_id, S2.eid)) == 1
    # Adding S2 back reuses that split instead of making a second current one.
    items = put(client, exp_id, [(S2.eid, "VISp")]).json()
    assert len(splits_of(exp_id, S2.eid)) == 1
    assert items[0]["split"]["id"] == str(splits_of(exp_id, S2.eid)[0].id)
    assert put(client, exp_id, []).json() == []
    assert client.get(f"/api/experiments/{exp_id}/items").json() == []


def test_put_rejects_unknown_items(client, exp_id):
    res = put(client, exp_id, [(S1.eid, "CA1"), (S1.eid, "VISp"), (uuid.uuid4(), "CA1")])
    assert res.status_code == 422
    assert len(res.json()["detail"]["items"]) == 2
    assert client.get(f"/api/experiments/{exp_id}/items").json() == []  # nothing changed
    bad = client.put(f"/api/experiments/{exp_id}/items", json={"items": [{"eid": "x"}]})
    assert bad.status_code == 422


def test_reshuffle_supersedes_old_split(client, exp_id):
    items = put(client, exp_id, [(S1.eid, "CA1"), (S1.eid, "DG"), (S2.eid, "CA1")]).json()
    old = items[0]["split"]
    other = items[2]["split"]

    res = client.post(f"/api/experiments/{exp_id}/splits/{S1.eid}/reshuffle")
    assert res.status_code == 201, res.text
    new = res.json()
    assert new["id"] != old["id"] and new["seed"] != old["seed"]
    assert new["n_a"] + new["n_b"] == old["n_a"] + old["n_b"]

    items = client.get(f"/api/experiments/{exp_id}/items").json()
    assert items[0]["split"] == new and items[1]["split"] == new
    assert items[2]["split"] == other  # other sessions are untouched

    rows = splits_of(exp_id, S1.eid)
    assert [str(r.id) for r in rows] == [old["id"], new["id"]]
    assert rows[0].superseded_at is not None  # old row kept, marked superseded
    assert rows[1].superseded_at is None
    assert rows[0].group_a != rows[1].group_a

    # A second reshuffle leaves exactly one current split.
    assert client.post(f"/api/experiments/{exp_id}/splits/{S1.eid}/reshuffle").status_code == 201
    rows = splits_of(exp_id, S1.eid)
    assert len(rows) == 3 and sum(r.superseded_at is None for r in rows) == 1


def test_reshuffle_404s(client, exp_id):
    put(client, exp_id, [(S1.eid, "CA1")])
    url = f"/api/experiments/{exp_id}/splits/{S2.eid}/reshuffle"
    assert client.post(url).status_code == 404  # session not selected
    assert (
        client.post(f"/api/experiments/{uuid.uuid4()}/splits/{S1.eid}/reshuffle").status_code == 404
    )

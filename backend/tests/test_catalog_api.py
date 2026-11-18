"""Catalog endpoints on the fake catalog. Needs the local database."""

from collections import Counter

import pytest

from app.ibl.fake import fake_sessions

pytestmark = pytest.mark.usefixtures("fake_catalog")

FAKE = fake_sessions()


def fake_rows(**params):
    """Only the fake rows, so the checks hold even if real IBL rows are synced too."""
    return {"subject": "FAKE", **params}


def test_items_region_filter_returns_only_that_region(client):
    res = client.get("/api/catalog/items", params={"region": "CA1"})
    assert res.status_code == 200
    rows = res.json()
    assert rows and {r["region"] for r in rows} == {"CA1"}
    fake_ca1 = {str(s.eid) for s in FAKE if "CA1" in s.regions}
    assert fake_ca1 <= {r["eid"] for r in rows}


def test_items_shape_and_values(client):
    rows = client.get("/api/catalog/items", params=fake_rows()).json()
    assert len(rows) == sum(len(s.regions) for s in FAKE)
    by_key = {(r["eid"], r["region"]): r for r in rows}
    s = FAKE[0]
    row = by_key[(str(s.eid), "CA1")]
    assert row == {
        "eid": str(s.eid),
        "region": "CA1",
        "subject": s.subject,
        "lab": s.lab,
        "session_date": s.session_date.isoformat(),
        "n_good_units": s.regions["CA1"],
    }


def test_items_multiple_regions(client):
    for params in ({"region": ["CA1", "DG"]}, {"region": "CA1,DG"}):
        rows = client.get("/api/catalog/items", params=fake_rows(**params)).json()
        expected = sum(("CA1" in s.regions) + ("DG" in s.regions) for s in FAKE)
        assert len(rows) == expected
        assert {r["region"] for r in rows} == {"CA1", "DG"}


def test_items_subject_lab_and_min_units(client):
    rows = client.get("/api/catalog/items", params={"subject": "fake03"}).json()
    assert rows and {r["subject"] for r in rows} == {"FAKE03"}

    rows = client.get("/api/catalog/items", params=fake_rows(lab="hoferlab")).json()
    assert rows and {r["lab"] for r in rows} == {"hoferlab"}
    assert len(rows) == sum(len(s.regions) for s in FAKE if s.lab == "hoferlab")

    rows = client.get("/api/catalog/items", params=fake_rows(min_units=60)).json()
    assert rows and all(r["n_good_units"] >= 60 for r in rows)
    assert len(rows) == sum(n >= 60 for s in FAKE for n in s.regions.values())


def test_items_subject_search_treats_wildcards_literally(client):
    assert client.get("/api/catalog/items", params={"subject": "%"}).json() == []


def test_items_limit_offset(client):
    all_rows = client.get("/api/catalog/items", params=fake_rows()).json()
    page = client.get("/api/catalog/items", params=fake_rows(limit=5, offset=3)).json()
    assert page == all_rows[3:8]
    assert client.get("/api/catalog/items", params={"limit": 0}).status_code == 422
    assert client.get("/api/catalog/items", params={"min_units": -1}).status_code == 422


def test_regions_counts_sessions(client):
    res = client.get("/api/catalog/regions")
    assert res.status_code == 200
    rows = res.json()
    names = [r["region"] for r in rows]
    assert len(names) == len(set(names))
    counts = {r["region"]: r["n_sessions"] for r in rows}
    fake_counts = Counter(r for s in FAKE for r in s.regions)
    for region, n in fake_counts.items():
        assert counts[region] >= n

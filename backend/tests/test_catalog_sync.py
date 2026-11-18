"""Fake catalog and the pure parts of catalog sync. No database needed."""

import uuid

import pytest

from app.ibl import one_client
from app.ibl.catalog_sync import _parse_regions, fake_catalog, filter_catalog, main
from app.ibl.fake import FAKE_REGIONS, fake_sessions, get_fake_session


def test_fake_sessions_shape():
    sessions = fake_sessions()
    assert len(sessions) == 10
    assert len({s.subject for s in sessions}) == 6
    assert {r for s in sessions for r in s.regions} == set(FAKE_REGIONS)
    assert len({s.eid for s in sessions}) == 10
    for s in sessions:
        assert set(s.region_pids) == set(s.regions)
        for pids in s.region_pids.values():
            assert pids and set(pids) <= set(s.pids)


def test_fake_sessions_are_deterministic():
    a, b = fake_sessions(), fake_sessions()
    assert a == b
    # uuid5 ids do not depend on the process
    first = a[0]
    assert first.eid == uuid.uuid5(
        uuid.UUID("5f1c9a0e-4482-4f4b-9d4b-448448448448"), "session/FAKE01/2026-01-12"
    )
    assert get_fake_session(str(first.eid)) == first


def test_filter_by_region_and_limit():
    sessions, regions = fake_catalog()
    assert len(sessions) == 10
    s, r = filter_catalog(sessions, regions, ["CA1"])
    assert {x.region for x in r} == {"CA1"}
    assert {x.eid for x in r} == {x.eid for x in s}
    s, r = filter_catalog(sessions, regions, ["CA1", "DG"], limit=2)
    assert len(s) == 2
    assert {x.region for x in r} <= {"CA1", "DG"}
    assert {x.eid for x in r} == {x.eid for x in s}
    s, r = filter_catalog(sessions, regions, limit=3)
    assert [x.eid for x in s] == [x.eid for x in sessions[:3]]


def test_parse_regions_and_bad_limit():
    assert _parse_regions(" CA1, DG ,,") == ["CA1", "DG"]
    with pytest.raises(SystemExit):
        main(["--limit", "0"])


def test_one_client_does_not_connect_on_import(monkeypatch):
    # Importing worked above; calling it in fake mode must refuse instead of connecting.
    monkeypatch.setattr(one_client.get_settings(), "ibl_fake", True)
    one_client.get_one.cache_clear()
    with pytest.raises(RuntimeError, match="IBL_FAKE"):
        one_client.get_one()

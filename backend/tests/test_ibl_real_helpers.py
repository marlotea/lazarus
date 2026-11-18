"""Pure helpers of the real IBL path (column mapping, valid-trial mask, unit selection).

No network and no database: the inputs are hand-made tables with the real column names of
brainwidemap @ 705b7cb (`bwm_query`, `bwm_units`) and of ONE's trials object.
"""

import uuid
from datetime import date

import numpy as np
import pandas as pd
import pytest

from app.ibl.catalog_sync import _parse_eids, catalog_from_tables, filter_catalog
from app.ibl.loaders import select_units
from app.pipeline.splits import valid_trial_ids

E1 = "9a6e127b-bb07-4be2-92e2-53dd858c2762"
E2 = "446f4724-1690-49f9-819a-2bd8e2ea88ce"
E3 = "00000000-0000-4000-8000-000000000003"  # units only, no bwm_query row
P1 = "e5bc1f00-f4b8-4b35-a9b6-60d9cc7959a1"
P2a = "be9a2119-a4d7-4e62-82a1-b1a6623ecc99"
P2b = "11111111-1111-4111-8111-111111111111"


def _bwm_df() -> pd.DataFrame:
    # Real bwm_query columns: one row per probe; `date` comes back as datetime.date.
    return pd.DataFrame(
        {
            "pid": [P2a, P1, P2b],
            "eid": [E2, E1, E2],
            "probe_name": ["probe00", "probe00", "probe01"],
            "session_number": [1, 1, 1],
            "date": [date(2022, 6, 20), date(2022, 2, 21), date(2022, 6, 20)],
            "subject": ["KS096", "PL015", "KS096"],
            "lab": ["cortexlab", "hausserlab", "cortexlab"],
        }
    )


def _unit_df() -> pd.DataFrame:
    # A subset of the real bwm_units columns (the table has 36); `Beryl` is the region.
    rows = [
        ("CA1", E1, P1, 10),
        ("CA1", E1, P1, 11),
        ("DG", E1, P1, 12),
        ("CA1", E2, P2a, 3),
        ("CA1", E2, P2b, 4),
        ("CA1", E2, P2b, 5),
        ("CA1", E3, P1, 1),
    ]
    df = pd.DataFrame(rows, columns=["Beryl", "eid", "pid", "cluster_id"])
    df["label"] = 1.0
    df["acronym"] = df["Beryl"] + "-sp"  # Allen acronym, not used for the region
    return df


def test_catalog_from_tables_maps_real_columns():
    sessions, regions = catalog_from_tables(_bwm_df(), _unit_df())
    # one session per eid, ordered by date then eid
    assert [(str(s.eid), s.subject, s.lab, s.session_date) for s in sessions] == [
        (E1, "PL015", "hausserlab", date(2022, 2, 21)),
        (E2, "KS096", "cortexlab", date(2022, 6, 20)),
    ]
    by_key = {(str(r.eid), r.region): r for r in regions}
    assert set(by_key) == {(E1, "CA1"), (E1, "DG"), (E2, "CA1")}  # E3 has no session row
    assert by_key[(E1, "CA1")].n_good_units == 2
    assert by_key[(E1, "CA1")].pids == (uuid.UUID(P1),)
    assert by_key[(E2, "CA1")].n_good_units == 3
    assert by_key[(E2, "CA1")].pids == tuple(sorted([uuid.UUID(P2a), uuid.UUID(P2b)]))


def test_catalog_from_tables_reports_missing_columns():
    with pytest.raises(SystemExit, match="Beryl"):
        catalog_from_tables(_bwm_df(), _unit_df().drop(columns=["Beryl"]))
    with pytest.raises(SystemExit, match="subject"):
        catalog_from_tables(_bwm_df().drop(columns=["subject"]), _unit_df())


def test_filter_catalog_by_eids():
    sessions, regions = catalog_from_tables(_bwm_df(), _unit_df())
    s, r = filter_catalog(sessions, regions, ["CA1"], eid_filter=[uuid.UUID(E2)])
    assert [str(x.eid) for x in s] == [E2]
    assert [(str(x.eid), x.region) for x in r] == [(E2, "CA1")]
    s, r = filter_catalog(sessions, regions, ["DG"], eid_filter=[uuid.UUID(E2)])
    assert s == [] and r == []  # E2 has no DG


def test_parse_eids():
    assert _parse_eids(f" {E1},{E2} ,") == [uuid.UUID(E1), uuid.UUID(E2)]
    with pytest.raises(Exception, match="session uuids"):
        _parse_eids("not-a-uuid")


class _AlfBunchLike(dict):
    """ONE's trials object is an AlfBunch: a dict whose keys are also attributes."""

    __getattr__ = dict.__getitem__


def test_valid_trial_ids_on_trials_objects():
    nan = np.nan
    data = {
        "stimOn_times": np.array([1.0, 2.0, nan, 4.0, 5.0, 6.0]),
        "firstMovement_times": np.array([1.2, nan, 3.2, 4.2, 5.2, 6.2]),
        "feedback_times": np.array([1.5, 2.5, 3.5, 4.5, nan, 6.5]),
        "goCue_times": np.array([nan] * 6),  # other columns do not matter
    }
    expected = [0, 3, 5]
    assert valid_trial_ids(_AlfBunchLike(data)).tolist() == expected
    assert valid_trial_ids(pd.DataFrame(data)).tolist() == expected  # attribute access
    ids = valid_trial_ids(data)
    assert ids.dtype == np.int64


def test_select_units_label_and_beryl_mapping():
    # merge_clusters output: one entry per cluster, `cluster_id` from the metrics table.
    clusters = {
        "cluster_id": np.array([0, 1, 2, 3, 4, 5]),
        "label": np.array([1.0, 1.0, 0.66, 1.0, 1.0, 0.0]),
        "acronym": np.array(["CA1sp", "CA1so", "CA1sp", "DG-mo", "CA1sr", "CA1sp"]),
    }

    def to_beryl(acr):
        return np.array(["CA1" if a.startswith("CA1") else a.split("-")[0] for a in acr])

    assert select_units(clusters, "CA1", to_beryl).tolist() == [0, 1, 4]
    assert select_units(clusters, "DG", to_beryl).tolist() == [3]
    without_ids = {k: v for k, v in clusters.items() if k != "cluster_id"}
    assert select_units(without_ids, "CA1", to_beryl).tolist() == [0, 1, 4]


def test_real_path_refuses_fake_sessions(monkeypatch):
    from app.ibl import loaders
    from app.ibl.fake import fake_sessions, get_fake_session, is_fake_eid
    from app.pipeline import splits

    fake = fake_sessions()[0]
    assert is_fake_eid(fake.eid) and not is_fake_eid(E1)
    real_settings = type("S", (), {"ibl_fake": False})()
    monkeypatch.setattr(loaders, "get_settings", lambda: real_settings)
    monkeypatch.setattr(splits, "get_settings", lambda: real_settings)
    # Fails before any IBL import or network call.
    with pytest.raises(ValueError, match="fake session"):
        loaders.load_session_behaviour(fake.eid)
    with pytest.raises(ValueError, match="fake session"):
        loaders.load_item_units(fake.eid, "CA1", [str(p) for p in fake.pids])
    with pytest.raises(ValueError, match="fake session"):
        splits.load_session_trials(fake.eid)
    with pytest.raises(KeyError, match="IBL_FAKE=0"):
        get_fake_session(E1)

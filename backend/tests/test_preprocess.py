"""Binning core and the preprocessing cache (no database)."""

import numpy as np
import pytest

from app.ibl.fake import fake_sessions, fake_valid_trials
from app.pipeline import preprocess
from app.pipeline.preprocess import (
    bin_average,
    bin_spikes,
    load_group,
    n_bins_per_trial,
    preprocess_hash,
    preprocess_item,
    signed_contrast,
)
from app.pipeline.splits import make_split
from app.schemas.preprocess import PreprocessParams
from app.settings import get_settings


def test_bin_spikes_hand_made_train():
    # Two units (cluster ids 7 and 3, in that column order) and a cluster 5 we drop.
    # Events at 10 s and 20 s, window 0.2 s before to 0.3 s after, 0.1 s bins:
    # 5 bins per trial with edges at t-0.2, t-0.1, t, t+0.1, t+0.2, t+0.3.
    spikes = [
        # trial 0 (event 10.0)
        (9.85, 7),  # bin 0
        (9.95, 7),  # bin 1
        (9.96, 3),  # bin 1
        (10.0, 7),  # exactly on an edge: belongs to bin 2 (bins are [start, end))
        (10.05, 7),  # bin 2
        (10.05, 5),  # dropped cluster
        (10.25, 3),  # bin 4
        (10.30, 3),  # window end is exclusive: not counted
        (9.79, 7),  # before the window
        # trial 1 (event 20.0)
        (19.81, 3),  # bin 0
        (20.15, 7),  # bin 3
        (20.16, 7),  # bin 3
        (20.17, 7),  # bin 3
    ]
    order = np.random.default_rng(0).permutation(len(spikes))  # unsorted input is fine
    times = np.array([spikes[i][0] for i in order])
    clusters = np.array([spikes[i][1] for i in order])

    X, trial_index, time_in_trial = bin_spikes(
        times, clusters, [7, 3], np.array([10.0, 20.0]), 0.2, 0.3, 0.1, trial_ids=[4, 9]
    )
    expected = np.array(
        [
            # unit 7, unit 3
            [1, 0],  # trial 4, bin 0
            [1, 1],
            [2, 0],
            [0, 0],
            [0, 1],
            [0, 1],  # trial 9, bin 0
            [0, 0],
            [0, 0],
            [3, 0],
            [0, 0],
        ],
        dtype=np.float32,
    )
    assert X.dtype == np.float32
    assert np.array_equal(X, expected)
    assert trial_index.tolist() == [4] * 5 + [9] * 5
    assert np.allclose(time_in_trial, np.tile([-0.15, -0.05, 0.05, 0.15, 0.25], 2))


def test_bin_spikes_edge_cases():
    # Overlapping windows: each trial counts the spike.
    X, _, _ = bin_spikes([1.0], [0], [0], np.array([1.0, 1.05]), 0.1, 0.1, 0.1)
    assert X[:, 0].tolist() == [0, 1, 1, 0]
    # No units, no trials.
    X, ti, tt = bin_spikes([1.0], [0], [], np.array([1.0]), 0.1, 0.1, 0.1)
    assert X.shape == (2, 0)
    X, ti, tt = bin_spikes([1.0], [0], [0], np.array([]), 0.1, 0.1, 0.1)
    assert X.shape == (0, 1) and ti.shape == (0,)
    # A window that is not a whole number of bins drops the remainder at the end.
    assert n_bins_per_trial(0.5, 1.0, 0.02) == 75
    assert n_bins_per_trial(0.5, 1.0, 1.0) == 1
    with pytest.raises(ValueError):
        bin_spikes([1.0], [0], [0], np.array([np.nan]), 0.1, 0.1, 0.1)


def test_bin_average_and_signed_contrast():
    t = np.arange(0, 2, 0.001)
    v = np.where(t < 1.0, 1.0, 3.0)
    out = bin_average(t, v, np.array([1.0]), 0.2, 0.2, 0.1)
    assert np.allclose(out, [1, 1, 3, 3])
    trials = {
        "contrastRight": np.array([0.25, np.nan, 0.0]),
        "contrastLeft": np.array([np.nan, 1, np.nan]),
    }
    assert signed_contrast(trials).tolist() == [0.25, -1.0, 0.0]


def test_preprocess_hash_is_stable_and_sensitive():
    base = ("e", "CA1", ["p2", "p1"], {}, "s")
    h = preprocess_hash(*base)
    assert h == preprocess_hash("e", "CA1", ["p1", "p2"], PreprocessParams(), "s")  # pid order
    assert h != preprocess_hash("e", "CA1", ["p1", "p2"], {"bin_size_ms": 50}, "s")
    assert h != preprocess_hash("e", "CA1", ["p1", "p2"], {}, "s2")
    assert h != preprocess_hash("e", "DG", ["p1", "p2"], {}, "s")
    assert len(h) == 64


@pytest.mark.skipif(not get_settings().ibl_fake, reason="needs IBL_FAKE=1")
def test_preprocess_fake_item_writes_and_reuses_cache(tmp_path, monkeypatch):
    s = fake_sessions()[0]  # DG is crossed by both probes of this session
    a, b = make_split(fake_valid_trials(s.eid), seed=5)
    params = {"bin_size_ms": 50, "window_pre_s": 0.2, "window_post_s": 0.8}
    folder = preprocess_item(s.eid, "DG", s.region_pids["DG"], "split-1", a, b, params, tmp_path)
    assert folder.parent == tmp_path / "preprocess"
    assert sorted(p.name for p in folder.iterdir()) == ["A.npz", "B.npz"]
    assert [p.name for p in folder.parent.iterdir()] == [folder.name]  # no .tmp left behind

    for group, ids in (("A", a), ("B", b)):
        g = load_group(folder, group)
        n_rows = len(ids) * 20
        assert g["X"].shape == (n_rows, s.regions["DG"])  # units of both probes merged
        assert g["X"].dtype == np.float32
        assert g["trial_index"].tolist() == np.repeat(ids, 20).tolist()
        assert (
            len({(p, c) for p, c in zip(g["unit_pid"], g["unit_cluster_id"], strict=True)})
            == s.regions["DG"]
        )
        assert set(g["unit_pid"]) == {str(p) for p in s.region_pids["DG"]}
        for key in ("wheel_velocity", "signed_contrast"):
            assert g[key].shape == (n_rows,) and g[key].dtype == np.float32
        for key in ("choice", "feedback"):
            assert g[key].dtype == np.int64 and set(np.unique(g[key])) <= {-1, 0, 1}
        assert g["X"].sum() > 0

    # Second call reuses the folder without loading anything.
    def boom(*args, **kwargs):
        raise AssertionError("should not reload")

    monkeypatch.setattr(preprocess, "load_item_units", boom)
    again = preprocess_item(
        s.eid, "DG", list(reversed(s.region_pids["DG"])), "split-1", a, b, params, tmp_path
    )
    assert again == folder

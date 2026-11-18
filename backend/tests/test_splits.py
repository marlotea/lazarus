"""Pure split functions; no database needed."""

import numpy as np
import pytest

from app.ibl.fake import fake_sessions, fake_valid_trials
from app.pipeline import splits
from app.pipeline.splits import make_split, new_seed, valid_trial_ids

IDS = np.array([0, 2, 3, 5, 7, 8, 9, 11, 12, 15, 16, 20, 21])


def test_make_split_is_deterministic():
    a1, b1 = make_split(IDS, seed=81723)
    a2, b2 = make_split(IDS.copy(), seed=81723)
    assert np.array_equal(a1, a2) and np.array_equal(b1, b2)
    a3, _ = make_split(list(IDS), seed=81723)  # a plain list gives the same result
    assert np.array_equal(a1, a3)


def test_make_split_differs_by_seed():
    ids = np.arange(600)
    assert not np.array_equal(make_split(ids, 1)[0], make_split(ids, 2)[0])


@pytest.mark.parametrize("seed", [0, 1, 81723, 2**31 - 1])
@pytest.mark.parametrize("n", [0, 1, 2, 13, 603])
def test_make_split_halves_partition_the_ids(seed, n):
    ids = np.sort(np.random.default_rng(99).choice(5000, size=n, replace=False))
    a, b = make_split(ids, seed)
    assert len(np.intersect1d(a, b)) == 0  # no overlap
    assert np.array_equal(np.sort(np.concatenate([a, b])), ids)  # nothing lost or added
    assert len(a) == round(n * 0.5)
    assert np.all(np.diff(a) > 0) and np.all(np.diff(b) > 0)  # each half sorted
    assert a.dtype == b.dtype == np.int64


def test_make_split_ratio():
    a, b = make_split(np.arange(100), seed=5, ratio=0.3)
    assert (len(a), len(b)) == (30, 70)
    with pytest.raises(ValueError):
        make_split(np.arange(10), seed=5, ratio=1.5)


def test_new_seed_is_31_bit():
    seeds = {new_seed() for _ in range(200)}
    assert all(0 <= s < 2**31 for s in seeds)
    assert len(seeds) > 190


def test_valid_trial_ids_drops_any_nan_event():
    nan = np.nan
    trials = {
        "stimOn_times": [1.0, nan, 3.0, 4.0, 5.0],
        "firstMovement_times": [1.1, 2.1, nan, 4.1, 5.1],
        "feedback_times": [1.2, 2.2, 3.2, nan, 5.2],
    }
    assert valid_trial_ids(trials).tolist() == [0, 4]


def test_load_valid_trials_fake(monkeypatch):
    monkeypatch.setattr(splits, "get_settings", lambda: type("S", (), {"ibl_fake": True})())
    s = fake_sessions()[0]
    trials = splits.load_session_trials(s.eid)
    assert trials.n_trials == s.n_trials
    ids = splits.load_valid_trials(str(s.eid))
    assert ids.tolist() == fake_valid_trials(s.eid)  # deterministic
    assert 0.9 * s.n_trials < len(ids) < s.n_trials  # a few trials are invalid
    assert ids.min() >= 0 and ids.max() < s.n_trials and np.all(np.diff(ids) > 0)

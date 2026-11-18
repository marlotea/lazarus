"""Per-session random split of valid behavioural trials into groups A and B.

Pure functions plus the one IBL call a request may make (loading a session's trials table).
Runnable without FastAPI, e.g.:

    from app.pipeline.splits import load_session_trials, make_split, new_seed
    trials = load_session_trials(eid)
    a, b = make_split(trials.valid_ids, new_seed())
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass

import numpy as np

from app.settings import get_settings

# A trial is valid when all three align events exist, so any align event works on any split.
REQUIRED_EVENTS = ("stimOn_times", "firstMovement_times", "feedback_times")


@dataclass(frozen=True)
class SessionTrials:
    n_trials: int  # all trials in the session's trials table
    valid_ids: np.ndarray  # sorted int64 indices of the valid trials


def new_seed() -> int:
    """A fresh split seed. 31 bits so it fits Postgres int and bigint alike."""
    return secrets.randbits(31)


def valid_trial_ids(trials: dict[str, np.ndarray] | object) -> np.ndarray:
    """Indices of trials whose stimOn, firstMovement and feedback times are all non-NaN.

    `trials` is an IBL trials object (or any mapping / object with those attributes).
    """

    def get(name: str) -> np.ndarray:
        value = trials[name] if isinstance(trials, dict) else getattr(trials, name)
        return np.asarray(value, dtype=float)

    ok = np.ones(len(get(REQUIRED_EVENTS[0])), dtype=bool)
    for name in REQUIRED_EVENTS:
        ok &= ~np.isnan(get(name))
    return np.flatnonzero(ok).astype(np.int64)


def load_session_trials(eid: uuid.UUID | str) -> SessionTrials:
    """Trial count and valid trial ids for one session.

    With IBL_FAKE=1 this reads the fake session (no network). Otherwise it loads
    `one.load_object(eid, 'trials')` from the public IBL server.
    """
    if get_settings().ibl_fake:
        from app.ibl.fake import fake_valid_trials, get_fake_session

        session = get_fake_session(eid)
        return SessionTrials(session.n_trials, np.asarray(fake_valid_trials(eid), dtype=np.int64))

    from app.ibl.one_client import get_one

    trials = get_one().load_object(str(eid), "trials")
    n_trials = len(np.asarray(trials["stimOn_times"]))
    return SessionTrials(n_trials, valid_trial_ids(trials))


def load_valid_trials(eid: uuid.UUID | str) -> np.ndarray:
    """Sorted indices of the session's valid trials (see `load_session_trials`)."""
    return load_session_trials(eid).valid_ids


def make_split(
    valid_ids: np.ndarray | list[int], seed: int, ratio: float = 0.5
) -> tuple[np.ndarray, np.ndarray]:
    """Shuffle `valid_ids` with `seed`, cut at `round(len * ratio)`, sort each half.

    Same inputs always give the same halves; the halves never overlap and together hold
    every id once.
    """
    if not 0.0 <= ratio <= 1.0:
        raise ValueError(f"ratio must be between 0 and 1, got {ratio}")
    ids = np.asarray(valid_ids, dtype=np.int64)
    rng = np.random.default_rng(seed)
    perm = rng.permutation(ids)
    cut = round(len(ids) * ratio)
    return np.sort(perm[:cut]), np.sort(perm[cut:])

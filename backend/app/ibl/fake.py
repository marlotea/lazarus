"""Synthetic IBL catalog for development and tests (IBL_FAKE=1).

Ten sessions across six subjects, regions CA1, DG, LP, VISp, MOs and PO. Everything is a
fixed table or derived from it with uuid5, so every call returns the same ids and counts.
Subjects are named FAKE01..FAKE06 so fake rows are never mistaken for real IBL data.

The second half generates a synthetic recording (spikes, trials, wheel) for preprocessing.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import date
from functools import lru_cache

import numpy as np

from app.ibl.loaders import ProbeUnits, SessionBehaviour, select_units

FAKE_NAMESPACE = uuid.UUID("5f1c9a0e-4482-4f4b-9d4b-448448448448")
FAKE_REGIONS = ("CA1", "DG", "LP", "VISp", "MOs", "PO")


@dataclass(frozen=True)
class FakeSession:
    eid: uuid.UUID
    subject: str
    lab: str
    session_date: date
    n_trials: int  # for later milestones (splits); catalog sync leaves n_trials null
    regions: dict[str, int]  # Beryl acronym -> good-unit count
    pids: tuple[uuid.UUID, ...]  # probes in this session
    region_pids: dict[str, tuple[uuid.UUID, ...]]  # probes that cross each region


# subject, lab, date, n_trials, {region: n_good_units}
_TABLE: list[tuple[str, str, date, int, dict[str, int]]] = [
    ("FAKE01", "cortexlab", date(2026, 1, 12), 603, {"CA1": 64, "DG": 41, "LP": 23}),
    ("FAKE01", "cortexlab", date(2026, 1, 14), 548, {"CA1": 52, "VISp": 88}),
    ("FAKE02", "cortexlab", date(2026, 2, 3), 711, {"CA1": 37, "DG": 29, "PO": 18}),
    ("FAKE03", "churchlandlab", date(2026, 2, 10), 492, {"MOs": 75, "CA1": 44}),
    ("FAKE03", "churchlandlab", date(2026, 2, 11), 655, {"MOs": 61, "PO": 26, "LP": 33}),
    ("FAKE04", "hoferlab", date(2026, 3, 2), 580, {"VISp": 102, "LP": 47}),
    ("FAKE04", "hoferlab", date(2026, 3, 5), 624, {"VISp": 91, "CA1": 39, "DG": 22}),
    ("FAKE05", "mainenlab", date(2026, 3, 20), 517, {"MOs": 58, "PO": 31}),
    ("FAKE06", "angelakilab", date(2026, 4, 7), 689, {"CA1": 70, "DG": 35, "VISp": 49}),
    ("FAKE06", "angelakilab", date(2026, 4, 9), 572, {"LP": 27, "PO": 19, "MOs": 40}),
]


def _build() -> list[FakeSession]:
    sessions = []
    for subject, lab, day, n_trials, regions in _TABLE:
        eid = uuid.uuid5(FAKE_NAMESPACE, f"session/{subject}/{day.isoformat()}")
        # Sessions with 3+ regions have two probes; the middle region is crossed by both,
        # so probe merging is exercised.
        n_probes = 2 if len(regions) >= 3 else 1
        pids = tuple(uuid.uuid5(FAKE_NAMESPACE, f"probe/{eid}/probe0{k}") for k in range(n_probes))
        region_pids: dict[str, tuple[uuid.UUID, ...]] = {}
        names = list(regions)
        for i, region in enumerate(names):
            if n_probes == 1:
                region_pids[region] = pids
            elif len(names) % 2 == 1 and i == len(names) // 2:
                region_pids[region] = pids
            else:
                region_pids[region] = (pids[0],) if i < len(names) / 2 else (pids[1],)
        sessions.append(
            FakeSession(eid, subject, lab, day, n_trials, dict(regions), pids, region_pids)
        )
    return sessions


FAKE_SESSIONS: tuple[FakeSession, ...] = tuple(_build())


def fake_sessions() -> list[FakeSession]:
    """All fake sessions, in a fixed order."""
    return list(FAKE_SESSIONS)


def get_fake_session(eid: uuid.UUID | str) -> FakeSession:
    key = uuid.UUID(str(eid))
    for s in FAKE_SESSIONS:
        if s.eid == key:
            return s
    raise KeyError(
        f"No fake session with eid {key}. It looks like a real IBL session: "
        "run with IBL_FAKE=0 to load it."
    )


def is_fake_eid(eid: uuid.UUID | str) -> bool:
    """True for the eids of the fake catalog (they can coexist with real ones in the DB)."""
    key = uuid.UUID(str(eid))
    return any(s.eid == key for s in FAKE_SESSIONS)


def fake_valid_trials(eid: uuid.UUID | str) -> list[int]:
    """Valid trial indices of a fake session: 0..n_trials-1 minus a fixed ~4% of trials,
    standing in for trials with a NaN stimOn/firstMovement/feedback time. Same eid, same list."""
    s = get_fake_session(eid)
    # A tiny LCG keyed on the eid keeps this deterministic without numpy.
    state = s.eid.int % 2**31
    valid = []
    for i in range(s.n_trials):
        state = (1103515245 * state + 12345) % 2**31
        if state % 25 != 0:
            valid.append(i)
    return valid


# --- Synthetic recording (spikes, trials, wheel) for preprocessing -----------------------
#
# Deterministic per eid / pid. The neurons are tuned to wheel velocity, the signed stimulus
# contrast and movement, so CEBRA embeddings carry behaviour structure instead of noise.

FAKE_CONTRASTS = (0.0, 0.0625, 0.125, 0.25, 1.0)
FAKE_GRID_DT = 0.01  # s; fake wheel sampling and spike-rate grid (100 Hz)
_FAKE_START_S = 5.0
_NOISE_LABELS = (0.0, 1 / 3, 2 / 3)  # IBL labels below "good"


def _rng(*parts: object) -> np.random.Generator:
    digest = hashlib.sha256("/".join(map(str, parts)).encode()).digest()
    return np.random.default_rng(int.from_bytes(digest[:8], "little"))


@dataclass(frozen=True)
class _FakeCovariates:
    grid: np.ndarray  # (n_grid,) bin starts, seconds
    velocity: np.ndarray  # wheel velocity on the grid, rad/s
    stimulus: np.ndarray  # signed-contrast drive, decays after stimOn
    moving: np.ndarray  # 1 between first movement and feedback


@dataclass(frozen=True)
class _FakeRecording:
    behaviour: SessionBehaviour
    covariates: _FakeCovariates


@lru_cache(maxsize=4)
def _fake_recording(eid: uuid.UUID) -> _FakeRecording:
    s = get_fake_session(eid)
    rng = _rng("behaviour", s.eid)
    n = s.n_trials
    quiescence = 0.6 + rng.exponential(0.4, n)
    reaction = 0.15 + rng.gamma(2.0, 0.1, n)
    movement = 0.25 + rng.gamma(2.0, 0.08, n)
    iti = 1.0 + rng.uniform(0.0, 0.5, n)
    starts = _FAKE_START_S + np.concatenate(
        [[0.0], np.cumsum(quiescence + reaction + movement + iti)[:-1]]
    )
    stim_on = starts + quiescence
    first_move = stim_on + reaction
    feedback = first_move + movement

    contrast = rng.choice(FAKE_CONTRASTS, n)
    side = rng.choice([-1, 1], n)  # -1 stimulus on the left, +1 on the right
    signed = side * contrast
    correct_choice = -side  # IBL convention: a right stimulus needs choice -1
    p_correct = 0.5 + 0.45 * np.tanh(8 * np.abs(signed))
    choice = np.where(rng.random(n) < p_correct, correct_choice, -correct_choice)
    feedback_type = np.where(choice == correct_choice, 1, -1)

    # Trials outside fake_valid_trials lack a first-movement time, like real NaN trials.
    valid = np.zeros(n, dtype=bool)
    valid[fake_valid_trials(eid)] = True
    trials = {
        "stimOn_times": stim_on,
        "firstMovement_times": np.where(valid, first_move, np.nan),
        "feedback_times": feedback,
        "contrastLeft": np.where(side < 0, contrast, np.nan),
        "contrastRight": np.where(side > 0, contrast, np.nan),
        "choice": choice.astype(np.float64),
        "feedbackType": feedback_type.astype(np.float64),
    }

    dt = FAKE_GRID_DT
    grid = np.arange(0.0, feedback[-1] + 3.0, dt)
    velocity = np.zeros_like(grid)
    stimulus = np.zeros_like(grid)
    moving = np.zeros_like(grid)
    peak = rng.uniform(3.0, 8.0, n)
    for i in range(n):
        i0, i1 = np.searchsorted(grid, [first_move[i], feedback[i]])
        phase = np.linspace(0.0, np.pi, max(i1 - i0, 1))
        velocity[i0 : i0 + len(phase)] += -choice[i] * peak[i] * np.sin(phase)
        moving[i0:i1] = 1.0
        j0, j1 = np.searchsorted(grid, [stim_on[i], stim_on[i] + 0.6])
        stimulus[j0:j1] += signed[i] * np.exp(-(grid[j0:j1] - stim_on[i]) / 0.15)
    velocity += 0.3 * rng.standard_normal(len(grid))  # small jitter of a resting wheel
    position = np.cumsum(velocity) * dt

    behaviour = SessionBehaviour(trials=trials, wheel_times=grid.copy(), wheel_position=position)
    return _FakeRecording(behaviour, _FakeCovariates(grid, velocity, stimulus, moving))


def fake_behaviour(eid: uuid.UUID | str) -> SessionBehaviour:
    """Trial table and wheel trace of a fake session (all n_trials trials)."""
    return _fake_recording(uuid.UUID(str(eid))).behaviour


def _probe_region_counts(s: FakeSession, pid: uuid.UUID) -> dict[str, int]:
    """Good units per region on one probe. A region crossed by two probes splits its units
    between them, so the counts summed over probes equal the catalog's n_good_units."""
    counts = {}
    for region, n in s.regions.items():
        crossing = s.region_pids[region]
        if pid not in crossing:
            continue
        counts[region] = n if len(crossing) == 1 else (n - n // 2 if pid == crossing[0] else n // 2)
    return counts


@lru_cache(maxsize=2)
def _fake_probe(eid: uuid.UUID, pid: uuid.UUID) -> tuple[np.ndarray, np.ndarray, dict]:
    """Spike times, spike clusters and the cluster table of one fake probe."""
    s = get_fake_session(eid)
    if pid not in s.pids:
        raise KeyError(f"Probe {pid} is not in fake session {eid}")
    cov = _fake_recording(eid).covariates
    rng = _rng("probe", eid, pid)

    labels: list[float] = []
    acronyms: list[str] = []
    for region, n_good in _probe_region_counts(s, pid).items():
        n_noise = max(1, n_good // 3)
        labels += [1.0] * n_good + list(rng.choice(_NOISE_LABELS, n_noise))
        acronyms += [region] * (n_good + n_noise)
    labels += list(rng.choice(_NOISE_LABELS, 5))  # a few clusters outside every region
    acronyms += ["void"] * 5
    order = rng.permutation(len(labels))  # cluster ids are not grouped by region
    labels_arr = np.asarray(labels)[order]
    acronym_arr = np.asarray(acronyms)[order]
    n_clusters = len(labels_arr)

    dt = FAKE_GRID_DT
    v = cov.velocity / 5.0
    times_parts, cluster_parts = [], []
    for cid in range(n_clusters):
        base = rng.lognormal(np.log(4.0), 0.5)  # Hz
        w_vel, w_stim, w_move = rng.normal(0, 0.6), rng.normal(0, 1.0), rng.normal(0.3, 0.5)
        log_rate = np.log(base) + w_vel * v + w_stim * cov.stimulus + w_move * cov.moving
        rate = np.minimum(np.exp(log_rate), 200.0)
        counts = rng.poisson(rate * dt)
        idx = np.repeat(np.arange(len(cov.grid)), counts)
        times_parts.append(cov.grid[idx] + rng.random(len(idx)) * dt)
        cluster_parts.append(np.full(len(idx), cid, dtype=np.int64))
    times = np.concatenate(times_parts)
    clusters = np.concatenate(cluster_parts)
    sort = np.argsort(times, kind="stable")
    table = {
        "cluster_id": np.arange(n_clusters, dtype=np.int64),
        "label": labels_arr,
        "acronym": acronym_arr,
    }
    return times[sort], clusters[sort], table


def fake_probe_units(eid: uuid.UUID | str, pid: uuid.UUID | str, region: str) -> ProbeUnits:
    """One fake probe's spikes and its good units in `region` (already Beryl acronyms)."""
    times, clusters, table = _fake_probe(uuid.UUID(str(eid)), uuid.UUID(str(pid)))
    return ProbeUnits(
        pid=str(pid),
        spike_times=times,
        spike_clusters=clusters,
        cluster_ids=select_units(table, region),
    )

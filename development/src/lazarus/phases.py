"""Task phases and condition-averaged embedding trajectories.

A representation of (region, phase) is the set of trial-averaged embedding trajectories in that
phase's event-aligned window, one trajectory per trial condition. Two representations are compared
point-for-point: same condition, same time bin relative to the event.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Phase:
    name: str
    event: str      # trials column the window is aligned to
    t0: float       # window start relative to event (s)
    t1: float       # window end relative to event (s)


# Equal-length 300 ms windows so every phase has the same number of bins and phases can be compared
# with each other point-for-point (the cross-phase pairs are a null). With IBL reaction times of
# ~150-400 ms, `stim` and `move` overlap on fast trials; that biases cross-phase similarity *up*, so it
# only makes the same-phase vs different-phase contrast conservative.
PHASES: tuple[Phase, ...] = (
    Phase("pre_stim", "stimOn_times", -0.3, 0.0),        # quiescence, wheel held still
    Phase("stim", "stimOn_times", 0.0, 0.3),             # stimulus onset / early sensory
    Phase("move", "firstMovement_times", -0.1, 0.2),     # movement initiation (choice)
    Phase("feedback", "feedback_times", 0.0, 0.3),       # reward / error tone
)


def add_conditions(trials: pd.DataFrame) -> pd.Series:
    """Trial condition = stimulus side x choice (4 conditions; errors are the off-diagonal ones)."""
    side = np.where(trials.contrastLeft.notna(), "L", "R")
    choice = np.where(trials.choice > 0, "+", "-")
    return pd.Series([f"stim{s}_ch{c}" for s, c in zip(side, choice)], index=trials.index)


@dataclass
class Trajectories:
    """Condition-averaged embedding per phase for one recording."""
    key: str
    meta: dict
    phases: dict[str, dict[str, np.ndarray]]   # phase -> condition -> (n_bins, d) mean embedding
    counts: dict[str, dict[str, int]]          # phase -> condition -> n trials averaged
    single: dict[str, tuple[np.ndarray, np.ndarray]]  # phase -> (n_trials, n_bins, d), condition labels

    def to_npz(self, path):
        arrays = {}
        for p, conds in self.phases.items():
            for c, m in conds.items():
                arrays[f"mean|{p}|{c}"] = m
                arrays[f"count|{p}|{c}"] = np.array(self.counts[p][c])
            arrays[f"single|{p}"], arrays[f"labels|{p}"] = self.single[p]
        np.savez_compressed(path, **arrays)

    @classmethod
    def from_npz(cls, path, key: str, meta: dict) -> "Trajectories":
        z = np.load(path, allow_pickle=False)
        phases, counts, single = {}, {}, {}
        for k in z.files:
            kind, *rest = k.split("|")
            if kind == "mean":
                phases.setdefault(rest[0], {})[rest[1]] = z[k]
            elif kind == "count":
                counts.setdefault(rest[0], {})[rest[1]] = int(z[k])
            elif kind == "single":
                single[rest[0]] = (z[k], z[f"labels|{rest[0]}"])
        return cls(key, meta, phases, counts, single)


def phase_windows(embedding: np.ndarray, bin_start: np.ndarray, bin_chunk: np.ndarray,
                  event_times: np.ndarray, phase: Phase, bin_size: float) -> tuple[np.ndarray, np.ndarray]:
    """Slice (n_trials, n_bins, d) event-aligned windows; returns windows and a validity mask."""
    n_bins = int(round((phase.t1 - phase.t0) / bin_size))
    start = np.searchsorted(bin_start, event_times + phase.t0 - 1e-9)
    ok = np.isfinite(event_times) & (start >= 0) & (start + n_bins <= len(bin_start))
    start = np.where(ok, start, 0)
    idx = start[:, None] + np.arange(n_bins)[None, :]
    # window must sit inside one contiguous chunk and actually start at the requested time
    ok &= bin_chunk[idx[:, 0]] == bin_chunk[idx[:, -1]]
    ok &= np.abs(bin_start[idx[:, 0]] - (event_times + phase.t0)) < bin_size
    return embedding[idx], ok


def compute_trajectories(key: str, meta: dict, embedding: np.ndarray, bin_start: np.ndarray,
                         bin_chunk: np.ndarray, trials: pd.DataFrame, bin_size: float,
                         phases: tuple[Phase, ...] = PHASES) -> Trajectories:
    cond = np.asarray(add_conditions(trials).tolist(), dtype="U")
    out, counts, single = {}, {}, {}
    for ph in phases:
        win, ok = phase_windows(embedding, bin_start, bin_chunk, trials[ph.event].values, ph, bin_size)
        win, labels = win[ok], cond[ok]
        single[ph.name] = (win.astype(np.float32), labels)
        out[ph.name] = {c: win[labels == c].mean(0) for c in np.unique(labels)}
        counts[ph.name] = {c: int((labels == c).sum()) for c in np.unique(labels)}
    return Trajectories(key, meta, out, counts, single)

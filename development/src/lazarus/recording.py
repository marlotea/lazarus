"""Turning (session, region, trial subset) into a binned spike-count matrix for CEBRA.

A *recording* is the unit everything downstream works on. Each control only changes which recordings
get built and which pairs get compared:
  control 1: one session, region r, trial subset A vs. subset B
  control 2: same subject, region r, session s1 vs. session s2 (all trials)
  control 3: region r, subject m1 vs. subject m2
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .ibl import Session


@dataclass
class Recording:
    key: str                 # unique id, e.g. "<eid>/<region>/A"
    eid: str
    subject: str
    region: str
    split: str               # "A", "B", "all", ...
    X: np.ndarray            # (T, n_units) float32 spike counts
    bin_start: np.ndarray    # (T,) bin left edges, absolute session time (s)
    bin_chunk: np.ndarray    # (T,) contiguous-chunk id per bin; phase windows must not straddle chunks.
                             # CEBRA sees chunks concatenated, so time-offset positives can cross a chunk
                             # seam; with ~10-trial chunks that is <1% of samples.
    trials: pd.DataFrame     # BWM-masked trials whose time falls in this recording
    bin_size: float

    @property
    def n_units(self) -> int:
        return self.X.shape[1]

    def metadata(self) -> dict:
        return {"key": self.key, "eid": self.eid, "subject": self.subject, "region": self.region,
                "split": self.split, "n_units": self.n_units, "n_bins": len(self.X),
                "n_trials": len(self.trials), "bin_size": self.bin_size}


# ---------------------------------------------------------------- trial splits

def split_trials(n_trials: int, mode: str = "interleaved", chunk_trials: int = 10
                 ) -> dict[str, list[np.ndarray]]:
    """Split trial indices 0..n_trials-1 into two halves made of contiguous chunks.

    mode="interleaved": alternate chunks of `chunk_trials` consecutive trials between A and B. This
        balances slow drift, engagement, and the probabilityLeft block structure across halves.
    mode="halves": first half vs second half of the session (keeps drift as a confound; useful as a
        harder variant).
    Returns {"A": [chunk, ...], "B": [...]} where each chunk is an array of consecutive trial indices.
    """
    idx = np.arange(n_trials)
    if mode == "halves":
        mid = n_trials // 2
        return {"A": [idx[:mid]], "B": [idx[mid:]]}
    if mode == "interleaved":
        chunks = [idx[i:i + chunk_trials] for i in range(0, n_trials, chunk_trials)]
        return {"A": chunks[0::2], "B": chunks[1::2]}
    raise ValueError(f"unknown split mode {mode!r}")


def all_trials(n_trials: int) -> dict[str, list[np.ndarray]]:
    return {"all": [np.arange(n_trials)]}


# ---------------------------------------------------------------- binning

def _chunk_span(trials: pd.DataFrame, chunk: np.ndarray) -> tuple[float, float]:
    """Time span tiled by a chunk: start of its first trial to start of the next trial (or end of the
    last trial), so the chunks of A and B tile the session without overlap."""
    t0 = trials.intervals_0.iloc[chunk[0]]
    nxt = chunk[-1] + 1
    t1 = trials.intervals_0.iloc[nxt] if nxt < len(trials) else trials.intervals_1.iloc[chunk[-1]]
    return float(t0), float(t1)


def bin_spikes(times: np.ndarray, units: np.ndarray, n_units: int, t0: float, t1: float,
               bin_size: float) -> tuple[np.ndarray, np.ndarray]:
    n_bins = int(np.floor((t1 - t0) / bin_size))
    edges_start = t0 + bin_size * np.arange(n_bins)
    lo, hi = np.searchsorted(times, [t0, t0 + n_bins * bin_size])
    b = ((times[lo:hi] - t0) / bin_size).astype(np.int64)
    b = np.minimum(b, n_bins - 1)
    counts = np.bincount(b * n_units + units[lo:hi], minlength=n_bins * n_units)
    return counts.reshape(n_bins, n_units).astype(np.float32), edges_start


def build_recording(session: Session, region: str, split: str, chunks: list[np.ndarray],
                    bin_size: float = 0.02) -> Recording:
    times, units, n_units = session.region_spikes(region)
    Xs, starts, chunk_ids, trial_idx = [], [], [], []
    for ci, chunk in enumerate(chunks):
        t0, t1 = _chunk_span(session.trials, chunk)
        X, s = bin_spikes(times, units, n_units, t0, t1, bin_size)
        Xs.append(X)
        starts.append(s)
        chunk_ids.append(np.full(len(s), ci))
        trial_idx.append(chunk)
    trial_idx = np.concatenate(trial_idx)
    trial_idx = trial_idx[session.mask[trial_idx]]
    trials = session.trials.iloc[trial_idx].copy()
    trials["trial_index"] = trial_idx
    return Recording(key=f"{session.eid}/{region}/{split}", eid=session.eid, subject=session.subject,
                     region=region, split=split, X=np.concatenate(Xs), bin_start=np.concatenate(starts),
                     bin_chunk=np.concatenate(chunk_ids), trials=trials.reset_index(drop=True),
                     bin_size=bin_size)


def build_recordings(session: Session, regions: list[str], splits: dict[str, list[np.ndarray]],
                     bin_size: float = 0.02) -> list[Recording]:
    return [build_recording(session, r, name, chunks, bin_size)
            for r in regions for name, chunks in splits.items()]

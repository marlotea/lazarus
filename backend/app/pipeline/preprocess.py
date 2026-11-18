"""Preprocessing: bin good units' spikes around one trial event into a time x neuron matrix.

One call per item (session x region) writes both groups of its split:

    DATA_DIR/preprocess/<hash>/A.npz and B.npz

`hash` = SHA-256 of (eid, region, sorted pids, preprocess params, split id), so a run that
uses the same item, split and params reuses the folder. Each npz holds, per row (one time
bin of one trial; trials stacked in trial order):

    X                (n_rows, n_units) float32   spike counts
    trial_index      (n_rows,) int64             IBL trial number
    time_in_trial    (n_rows,) float32           bin centre minus the align event, seconds
    wheel_velocity   (n_rows,) float32           mean wheel velocity in the bin, rad/s
    signed_contrast  (n_rows,) float32           contrastRight - contrastLeft, NaN as 0
    choice           (n_rows,) int64             IBL choice (-1, 0, 1)
    feedback         (n_rows,) int64             IBL feedbackType (-1, 1)
    unit_pid         (n_units,) str              unit id = (unit_pid, unit_cluster_id)
    unit_cluster_id  (n_units,) int64

Runnable without FastAPI:

    from app.pipeline.preprocess import preprocess_item, load_group
    folder = preprocess_item(eid, "CA1", pids, split_id, group_a, group_b, {"bin_size_ms": 20})
    data = load_group(folder, "A")
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import shutil
import uuid
from collections.abc import Iterable, Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from app.ibl.loaders import ProbeUnits, SessionBehaviour, load_item_units, load_session_behaviour
from app.schemas.preprocess import PreprocessParams
from app.settings import get_settings

log = logging.getLogger(__name__)

GROUPS = ("A", "B")
WHEEL_FS = 1000  # Hz; wheel position is interpolated onto this grid before the gradient


# --- pure binning core ------------------------------------------------------------------


def n_bins_per_trial(window_pre_s: float, window_post_s: float, bin_size_s: float) -> int:
    """Whole bins that fit in the window. A remainder shorter than one bin is dropped
    from the end, so the window is `[t - pre, t - pre + n * bin)`."""
    return int(np.floor((window_pre_s + window_post_s) / bin_size_s + 1e-9))


def bin_edges(
    event_times: np.ndarray, window_pre_s: float, window_post_s: float, bin_size_s: float
) -> np.ndarray:
    """(n_trials, n_bins + 1) bin edges around each event."""
    n_bins = n_bins_per_trial(window_pre_s, window_post_s, bin_size_s)
    offsets = -window_pre_s + np.arange(n_bins + 1) * bin_size_s
    return np.asarray(event_times, dtype=np.float64)[:, None] + offsets[None, :]


def bin_spikes(
    spike_times: np.ndarray,
    spike_clusters: np.ndarray,
    cluster_ids: Sequence[int] | np.ndarray,
    event_times: np.ndarray,
    window_pre_s: float,
    window_post_s: float,
    bin_size_s: float,
    trial_ids: Sequence[int] | np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Count spikes per unit per bin in a window around each event.

    Bins are half-open `[start, end)`. Spikes of clusters not in `cluster_ids` are ignored.
    Trials are stacked in the given order; windows may overlap (each trial counts its own).

    Returns `X` (n_trials * n_bins, n_units) float32 with columns in `cluster_ids` order,
    `trial_index` (n_rows,) int64 (`trial_ids`, default 0..n_trials-1, repeated per bin)
    and `time_in_trial` (n_rows,) float32 (bin centre relative to the event).
    """
    if bin_size_s <= 0:
        raise ValueError("bin_size_s must be positive")
    spike_times = np.asarray(spike_times, dtype=np.float64)
    spike_clusters = np.asarray(spike_clusters)
    cluster_ids = np.asarray(cluster_ids, dtype=np.int64)
    event_times = np.asarray(event_times, dtype=np.float64)
    if np.isnan(event_times).any():
        raise ValueError("event_times contains NaN; pass valid trials only")
    n_trials = len(event_times)
    trial_ids = (
        np.arange(n_trials, dtype=np.int64)
        if trial_ids is None
        else np.asarray(trial_ids, dtype=np.int64)
    )
    if len(trial_ids) != n_trials:
        raise ValueError("trial_ids and event_times differ in length")

    edges = bin_edges(event_times, window_pre_s, window_post_s, bin_size_s)
    n_bins = edges.shape[1] - 1
    if n_bins < 1:
        raise ValueError("The window is shorter than one bin")
    X = np.zeros((n_trials, n_bins, len(cluster_ids)), dtype=np.float32)

    # Map cluster id -> column, -1 for clusters we do not keep.
    order = np.argsort(spike_times, kind="stable")
    times = spike_times[order]
    column = np.full(len(times), -1, dtype=np.int64)
    if len(cluster_ids) and len(times):
        sorter = np.argsort(cluster_ids, kind="stable")
        sorted_ids = cluster_ids[sorter]
        clusters = spike_clusters[order].astype(np.int64)
        pos = np.clip(np.searchsorted(sorted_ids, clusters), 0, len(sorted_ids) - 1)
        hit = sorted_ids[pos] == clusters
        column[hit] = sorter[pos[hit]]

    for k in range(n_trials):
        i0, i1 = np.searchsorted(times, [edges[k, 0], edges[k, -1]], side="left")
        cols = column[i0:i1]
        keep = cols >= 0
        if not keep.any():
            continue
        b = np.searchsorted(edges[k], times[i0:i1][keep], side="right") - 1
        np.add.at(X[k], (b, cols[keep]), 1.0)

    centres = -window_pre_s + (np.arange(n_bins) + 0.5) * bin_size_s
    trial_index = np.repeat(trial_ids, n_bins)
    time_in_trial = np.tile(centres, n_trials).astype(np.float32)
    return X.reshape(n_trials * n_bins, len(cluster_ids)), trial_index, time_in_trial


def bin_average(
    times: np.ndarray,
    values: np.ndarray,
    event_times: np.ndarray,
    window_pre_s: float,
    window_post_s: float,
    bin_size_s: float,
) -> np.ndarray:
    """Mean of `values` sampled at sorted `times` within each bin, rows ordered like
    `bin_spikes`. A bin with no sample takes the value interpolated at its centre."""
    times = np.asarray(times, dtype=np.float64)
    values = np.asarray(values, dtype=np.float64)
    edges = bin_edges(event_times, window_pre_s, window_post_s, bin_size_s)
    idx = np.searchsorted(times, edges, side="left")
    csum = np.concatenate([[0.0], np.cumsum(values)])
    count = idx[:, 1:] - idx[:, :-1]
    total = csum[idx[:, 1:]] - csum[idx[:, :-1]]
    centres = (edges[:, :-1] + edges[:, 1:]) / 2
    fallback = np.interp(centres, times, values) if len(times) else np.zeros_like(centres)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = np.where(count > 0, total / np.maximum(count, 1), fallback)
    return mean.reshape(-1)


def wheel_velocity(
    wheel_times: np.ndarray, wheel_position: np.ndarray, fs: int = WHEEL_FS
) -> tuple[np.ndarray, np.ndarray]:
    """Wheel velocity (rad/s) on a uniform `fs` grid: interpolate the position with
    `brainbox.behavior.wheel.interpolate_position`, then take the gradient."""
    from brainbox.behavior.wheel import interpolate_position

    position, t = interpolate_position(wheel_times, wheel_position, freq=fs)
    return np.asarray(t, dtype=np.float64), np.gradient(position) * fs


def signed_contrast(trials: Mapping[str, np.ndarray]) -> np.ndarray:
    """contrastRight - contrastLeft per trial, NaN counted as 0."""
    right = np.nan_to_num(np.asarray(trials["contrastRight"], dtype=np.float64), nan=0.0)
    left = np.nan_to_num(np.asarray(trials["contrastLeft"], dtype=np.float64), nan=0.0)
    return right - left


def build_group(
    probes: Sequence[ProbeUnits],
    behaviour: SessionBehaviour,
    trial_ids: Sequence[int] | np.ndarray,
    params: PreprocessParams,
    wheel: tuple[np.ndarray, np.ndarray] | None = None,
) -> dict[str, np.ndarray]:
    """The arrays of one group's npz (see the module docstring). Probes are merged by
    stacking their unit columns; `wheel` is a precomputed `wheel_velocity(...)`."""
    trial_ids = np.asarray(trial_ids, dtype=np.int64)
    if not len(trial_ids):
        raise ValueError("The group has no trials")
    n_units = sum(len(p.cluster_ids) for p in probes)
    if n_units == 0:
        raise ValueError("No good units in this region")
    pre, post = params.window_pre_s, params.window_post_s
    bin_s = params.bin_size_ms / 1000
    events = np.asarray(behaviour.trials[params.align_event], dtype=np.float64)[trial_ids]

    blocks = []
    trial_index = time_in_trial = None
    for p in probes:
        X, trial_index, time_in_trial = bin_spikes(
            p.spike_times, p.spike_clusters, p.cluster_ids, events, pre, post, bin_s, trial_ids
        )
        blocks.append(X)
    X = np.hstack(blocks).astype(np.float32)
    assert trial_index is not None and time_in_trial is not None
    n_bins = n_bins_per_trial(pre, post, bin_s)

    wt, wv = (
        wheel
        if wheel is not None
        else wheel_velocity(behaviour.wheel_times, behaviour.wheel_position)
    )
    trials = behaviour.trials
    return {
        "X": X,
        "trial_index": trial_index,
        "time_in_trial": time_in_trial,
        "wheel_velocity": bin_average(wt, wv, events, pre, post, bin_s).astype(np.float32),
        "signed_contrast": np.repeat(signed_contrast(trials)[trial_ids], n_bins).astype(np.float32),
        "choice": np.repeat(_as_int(trials["choice"])[trial_ids], n_bins),
        "feedback": np.repeat(_as_int(trials["feedbackType"])[trial_ids], n_bins),
        "unit_pid": np.concatenate([np.full(len(p.cluster_ids), p.pid) for p in probes]),
        "unit_cluster_id": np.concatenate([p.cluster_ids for p in probes]).astype(np.int64),
    }


def _as_int(values: np.ndarray) -> np.ndarray:
    return np.nan_to_num(np.asarray(values, dtype=np.float64), nan=0.0).astype(np.int64)


# --- cache ------------------------------------------------------------------------------


def preprocess_hash(
    eid: uuid.UUID | str,
    region: str,
    pids: Iterable[uuid.UUID | str],
    params: PreprocessParams | Mapping[str, Any],
    split_id: uuid.UUID | str,
) -> str:
    """SHA-256 of (eid, region, sorted pids, preprocess params, split id)."""
    if not isinstance(params, PreprocessParams):
        params = PreprocessParams.model_validate(params)
    key = {
        "eid": str(eid),
        "region": region,
        "pids": sorted(str(p) for p in pids),
        "preprocess": params.model_dump(mode="json"),
        "split_id": str(split_id),
    }
    blob = json.dumps(key, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def preprocess_item(
    eid: uuid.UUID | str,
    region: str,
    pids: Iterable[uuid.UUID | str],
    split_id: uuid.UUID | str,
    group_a: Sequence[int],
    group_b: Sequence[int],
    params: PreprocessParams | Mapping[str, Any],
    data_dir: Path | None = None,
) -> Path:
    """Write `A.npz` and `B.npz` for one item and return their folder, reusing it if it
    already exists. Data comes from IBL, or from the fake recording with IBL_FAKE=1."""
    if not isinstance(params, PreprocessParams):
        params = PreprocessParams.model_validate(params)
    pids = sorted(str(p) for p in pids)
    root = (data_dir or get_settings().data_dir) / "preprocess"
    folder = root / preprocess_hash(eid, region, pids, params, split_id)
    if folder.is_dir():
        log.info("preprocess cache hit %s", folder)
        return folder

    log.info("preprocessing %s %s (pids %s)", eid, region, ", ".join(pids))
    probes = load_item_units(eid, region, pids)
    behaviour = load_session_behaviour(eid)
    wheel = wheel_velocity(behaviour.wheel_times, behaviour.wheel_position)

    root.mkdir(parents=True, exist_ok=True)
    tmp = root / f"{folder.name}.tmp-{uuid.uuid4().hex[:8]}"
    tmp.mkdir()
    try:
        for group, ids in zip(GROUPS, (group_a, group_b), strict=True):
            arrays = build_group(probes, behaviour, ids, params, wheel)
            np.savez_compressed(tmp / f"{group}.npz", **arrays)
            log.info("group %s: %d rows x %d units", group, *arrays["X"].shape)
        try:
            os.rename(tmp, folder)
        except OSError:
            if not folder.is_dir():  # someone else finished first: keep theirs
                raise
            shutil.rmtree(tmp, ignore_errors=True)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return folder


def load_group(folder: Path, group: str) -> dict[str, np.ndarray]:
    """Arrays of one group's npz."""
    if group not in GROUPS:
        raise ValueError(f"group must be A or B, got {group!r}")
    with np.load(folder / f"{group}.npz", allow_pickle=False) as data:
        return {k: data[k] for k in data.files}

"""Similarity between two (region, phase) representations.

Inputs are two matched point clouds P, Q of shape (n_points, d): the condition-averaged trajectories of
the shared conditions, stacked over time bins. Rows correspond (same condition, same time relative to
the event). Embeddings come from independently trained CEBRA models, so they are only defined up to a
transformation; every metric below is invariant to (at least) rotation:

  procrustes     1 - scipy Procrustes disparity (translation, uniform scale, rotation/reflection).
                 For cosine-CEBRA models the identifiability class is orthogonal, so this is the
                 primary metric.
  linear_r2_cv   R^2 of an affine map Q->P, cross-validated over blocks of time bins (each fold holds
                 out the same time block of every condition), averaged over both directions. Analogue
                 of CEBRA's consistency score, but held-out so an 8-d affine map cannot fit noise.
  cka            linear centered kernel alignment (invariant to rotation and isotropic scale).
  rsa            Spearman correlation of the two pairwise-distance matrices (alignment-free).
"""
from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
from scipy.spatial import procrustes as _procrustes
from scipy.spatial.distance import pdist
from scipy.stats import spearmanr
from sklearn.linear_model import LinearRegression

from .phases import Trajectories


def procrustes_similarity(P, Q) -> float:
    return 1.0 - _procrustes(P, Q)[2]


def linear_cka(P, Q) -> float:
    P = P - P.mean(0)
    Q = Q - Q.mean(0)
    hsic = np.linalg.norm(P.T @ Q, "fro") ** 2
    return float(hsic / (np.linalg.norm(P.T @ P, "fro") * np.linalg.norm(Q.T @ Q, "fro")))


def rsa(P, Q, metric: str = "euclidean") -> float:
    return float(spearmanr(pdist(P, metric), pdist(Q, metric)).statistic)


def _r2(y, yhat) -> float:
    return 1.0 - ((y - yhat) ** 2).sum() / ((y - y.mean(0)) ** 2).sum()


def linear_r2_cv(P, Q, folds) -> float:
    def one_way(src, dst):
        pred = np.empty_like(dst)
        for g in np.unique(folds):
            test = folds == g
            pred[test] = LinearRegression().fit(src[~test], dst[~test]).predict(src[test])
        return _r2(dst, pred)
    return float((one_way(Q, P) + one_way(P, Q)) / 2)


METRICS = ("procrustes", "linear_r2_cv", "cka", "rsa")


def compare_points(P, Q, groups, n_folds: int = 5) -> dict[str, float]:
    """groups: condition id per row; rows of one condition are consecutive time bins."""
    t = np.concatenate([np.arange((groups == g).sum()) for g in np.unique(groups)])
    folds = (t * n_folds) // (t.max() + 1)
    out = {"procrustes": procrustes_similarity(P, Q), "cka": linear_cka(P, Q), "rsa": rsa(P, Q),
           "linear_r2_cv": linear_r2_cv(P, Q, folds)}
    return out


def matched_points(a: Trajectories, phase_a: str, b: Trajectories, phase_b: str, min_trials: int):
    """Stack the condition means shared by both sides (with >= min_trials each) into matched rows."""
    conds = sorted(c for c in a.phases[phase_a]
                   if c in b.phases[phase_b]
                   and a.counts[phase_a][c] >= min_trials and b.counts[phase_b][c] >= min_trials)
    if len(conds) < 2:
        return None
    P = np.concatenate([a.phases[phase_a][c] for c in conds])
    Q = np.concatenate([b.phases[phase_b][c] for c in conds])
    groups = np.repeat(np.arange(len(conds)), len(a.phases[phase_a][conds[0]]))
    return P, Q, groups, conds


def compare_trajectories(a: Trajectories, b: Trajectories, phases: list[str] | None = None,
                         min_trials: int = 5, cross_phase: bool = True) -> pd.DataFrame:
    """All (phase_a, phase_b) comparisons between two recordings; one row per pair."""
    phases = phases or list(a.phases)
    pairs = itertools.product(phases, phases) if cross_phase else ((p, p) for p in phases)
    rows = []
    for pa, pb in pairs:
        m = matched_points(a, pa, b, pb, min_trials)
        if m is None:
            continue
        P, Q, groups, conds = m
        rows.append({"key_a": a.key, "key_b": b.key, "phase_a": pa, "phase_b": pb,
                     "n_conditions": len(conds), "n_points": len(P), **compare_points(P, Q, groups)})
    return pd.DataFrame(rows)


def compare_all(trajs: list[Trajectories], pair_filter=None, **kw) -> pd.DataFrame:
    """Compare every unordered pair of recordings (optionally filtered); attaches meta of both sides."""
    frames = []
    for a, b in itertools.combinations(trajs, 2):
        if pair_filter is not None and not pair_filter(a.meta, b.meta):
            continue
        df = compare_trajectories(a, b, **kw)
        for side, t in (("a", a), ("b", b)):
            for k in ("eid", "subject", "region", "split", "seed", "n_units"):
                df[f"{k}_{side}"] = t.meta.get(k)
        frames.append(df)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def label_comparison(df: pd.DataFrame) -> pd.Series:
    """Categorise each row by whether region and phase match."""
    same_r = df.region_a == df.region_b
    same_p = df.phase_a == df.phase_b
    return pd.Series(np.select([same_r & same_p, same_r & ~same_p, ~same_r & same_p],
                               ["same region, same phase", "same region, diff phase",
                                "diff region, same phase"], "diff region, diff phase"), index=df.index)

"""Figures shared by the control scripts."""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.spatial import procrustes
from sklearn.decomposition import PCA

from .compare import matched_points
from .phases import PHASES, Trajectories

CATEGORY_ORDER = ["same region, same phase", "same region, diff phase",
                  "diff region, same phase", "diff region, diff phase"]


def similarity_matrix(df: pd.DataFrame, metric: str, row_side: str = "a", path=None, title=""):
    """Heatmap with rows (region, phase) of side A and columns (region, phase) of side B."""
    oth = "b" if row_side == "a" else "a"
    df = df.assign(row=df[f"region_{row_side}"] + " · " + df[f"phase_{row_side}"],
                   col=df[f"region_{oth}"] + " · " + df[f"phase_{oth}"])
    mat = df.pivot_table(index="row", columns="col", values=metric, aggfunc="mean")
    phase_rank = {p.name: i for i, p in enumerate(PHASES)}
    key = lambda s: (s.split(" · ")[0], phase_rank.get(s.split(" · ")[1], 99))
    mat = mat.reindex(index=sorted(mat.index, key=key), columns=sorted(mat.columns, key=key))
    fig, ax = plt.subplots(figsize=(0.32 * len(mat.columns) + 3, 0.32 * len(mat) + 2))
    im = ax.imshow(mat.values, cmap="viridis", vmin=np.nanmin(mat.values), vmax=1)
    ax.set_xticks(range(len(mat.columns)), mat.columns, rotation=90, fontsize=7)
    ax.set_yticks(range(len(mat.index)), mat.index, fontsize=7)
    ax.set_xlabel("split B"), ax.set_ylabel("split A")
    ax.set_title(title or metric)
    fig.colorbar(im, ax=ax, shrink=0.6, label=metric)
    fig.tight_layout()
    if path:
        fig.savefig(path, dpi=150)
        plt.close(fig)
    return fig


def category_summary(df: pd.DataFrame, metrics, path=None, title="", ceiling: pd.DataFrame | None = None):
    fig, axes = plt.subplots(1, len(metrics), figsize=(3.2 * len(metrics), 3.6), sharey=False)
    for ax, m in zip(np.atleast_1d(axes), metrics):
        cats = [c for c in CATEGORY_ORDER if c in set(df.category)]
        data = [df.loc[df.category == c, m].dropna().values for c in cats]
        ax.boxplot(data, showfliers=False)
        for i, d in enumerate(data):
            ax.scatter(np.full(len(d), i + 1) + np.random.uniform(-0.15, 0.15, len(d)), d, s=6, alpha=0.5)
        if ceiling is not None and len(ceiling):
            ax.axhline(ceiling[m].median(), ls="--", c="k", lw=1, label="seed ceiling (median)")
            ax.legend(fontsize=7, loc="lower left")
        ax.set_xticks(range(1, len(cats) + 1), [c.replace(", ", "\n") for c in cats], fontsize=7)
        ax.set_title(m)
    fig.suptitle(title)
    fig.tight_layout()
    if path:
        fig.savefig(path, dpi=150)
        plt.close(fig)
    return fig


def aligned_trajectories(a: Trajectories, b: Trajectories, phases, path=None, title="", min_trials=5):
    """Per phase: A and B condition trajectories after Procrustes-aligning B to A, shown in A's PCA."""
    fig, axes = plt.subplots(1, len(phases), figsize=(3.2 * len(phases), 3.2))
    for ax, ph in zip(np.atleast_1d(axes), phases):
        m = matched_points(a, ph, b, ph, min_trials)
        if m is None:
            ax.set_axis_off()
            continue
        P, Q, groups, conds = m
        Ps, Qs, disp = procrustes(P, Q)
        pca = PCA(2).fit(Ps)
        pa, pb = pca.transform(Ps), pca.transform(Qs)
        for g, c in enumerate(conds):
            sel = groups == g
            line, = ax.plot(*pa[sel].T, lw=1.5, label=c)
            ax.plot(*pb[sel].T, lw=1.5, ls="--", c=line.get_color())
            ax.scatter(*pa[sel][0], color=line.get_color(), s=12)
        ax.set_title(f"{ph}  (1-disp={1 - disp:.2f})", fontsize=9)
        ax.set_xticks([]), ax.set_yticks([])
    np.atleast_1d(axes)[0].legend(fontsize=6)
    fig.suptitle(title + "   solid = A, dashed = B (aligned); dot = window start", fontsize=9)
    fig.tight_layout()
    if path:
        fig.savefig(path, dpi=150)
        plt.close(fig)
    return fig

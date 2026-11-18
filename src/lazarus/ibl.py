"""Loading IBL Brain-Wide Map sessions: good units grouped by Beryl region, plus BWM-masked trials."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

FREEZE = "2023_12_bwm_release"
REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = REPO_ROOT / "data" / "ONE"
EXCLUDED_REGIONS = {"root", "void"}


@lru_cache(maxsize=1)
def get_one():
    from one.api import ONE
    return ONE(base_url="https://openalyx.internationalbrainlab.org",
               password="international", silent=True, cache_dir=CACHE_DIR)


@lru_cache(maxsize=1)
def bwm_insertions() -> pd.DataFrame:
    from brainwidemap import bwm_query
    return bwm_query(get_one(), freeze=FREEZE)


@lru_cache(maxsize=1)
def bwm_unit_table() -> pd.DataFrame:
    """One row per BWM good unit, with session metadata joined in."""
    from brainwidemap import bwm_units
    units = bwm_units(get_one(), freeze=FREEZE)
    sessions = bwm_insertions().drop_duplicates("eid")[["eid", "subject", "date", "lab"]]
    return units.merge(sessions, on="eid")


def region_unit_counts(min_units: int = 1) -> pd.DataFrame:
    """Good-unit counts per (subject, session, Beryl region); the planning table for all controls."""
    u = bwm_unit_table()
    c = u.groupby(["lab", "subject", "eid", "date", "Beryl"]).size().rename("n_units").reset_index()
    return c[(c.n_units >= min_units) & ~c.Beryl.isin(EXCLUDED_REGIONS)]


@dataclass
class Session:
    eid: str
    subject: str
    date: str
    trials: pd.DataFrame            # full trial table (all trials, used to tile time)
    mask: np.ndarray                # BWM trial-inclusion mask, aligned with `trials`
    spike_times: np.ndarray         # all good-unit spikes of the session, sorted
    spike_units: np.ndarray         # index into `units`
    units: pd.DataFrame             # one row per good unit, column 'Beryl'
    meta: dict = field(default_factory=dict)

    def regions(self, min_units: int = 1) -> pd.Series:
        counts = self.units.Beryl.value_counts()
        counts = counts[~counts.index.isin(EXCLUDED_REGIONS)]
        return counts[counts >= min_units]

    def region_spikes(self, region: str) -> tuple[np.ndarray, np.ndarray, int]:
        """Spike times and *region-local* unit indices (0..n-1) for one region."""
        unit_idx = np.flatnonzero(self.units.Beryl.values == region)
        remap = np.full(len(self.units), -1)
        remap[unit_idx] = np.arange(len(unit_idx))
        local = remap[self.spike_units]
        keep = local >= 0
        return self.spike_times[keep], local[keep], len(unit_idx)


def load_session(eid: str) -> Session:
    from brainwidemap import load_good_units, load_trials_and_mask
    from brainwidemap.bwm_loading import merge_probes
    from iblatlas.regions import BrainRegions

    one = get_one()
    ins = bwm_insertions()
    rows = ins[ins.eid == eid]
    if rows.empty:
        raise ValueError(f"{eid} is not in the {FREEZE} BWM release")

    spikes_list, clusters_list = [], []
    for pid, probe in rows[["pid", "probe_name"]].itertuples(index=False):
        spikes, clusters = load_good_units(one, pid)
        clusters = clusters.assign(pid=pid, probe=probe)
        spikes_list.append({"times": spikes["times"], "clusters": spikes["clusters"].astype(np.int64)})
        clusters_list.append(clusters)
    spikes, clusters = merge_probes(spikes_list, clusters_list)

    br = BrainRegions()
    clusters["Beryl"] = br.id2acronym(clusters["atlas_id"].values, mapping="Beryl")
    units = clusters[["uuids", "pid", "probe", "cluster_id", "acronym", "Beryl", "firing_rate"]] \
        .reset_index(drop=True)

    trials, mask = load_trials_and_mask(one, eid)
    trials = trials.reset_index(drop=True)
    row = rows.iloc[0]
    return Session(eid=eid, subject=row.subject, date=str(row.date), trials=trials,
                   mask=np.asarray(mask, dtype=bool), spike_times=spikes["times"],
                   spike_units=spikes["clusters"], units=units,
                   meta={"lab": row.lab, "probes": rows.probe_name.tolist()})

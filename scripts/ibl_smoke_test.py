"""Smoke test: connect to the IBL public server, query the BWM release, load one session."""
from pathlib import Path

from one.api import ONE
from brainbox.io.one import SpikeSortingLoader
from iblatlas.atlas import AllenAtlas
from brainwidemap import bwm_query, bwm_units, load_trials_and_mask, download_aggregate_tables

FREEZE = "2023_12_bwm_release"
CACHE_DIR = Path(__file__).resolve().parents[1] / "data" / "ONE"

one = ONE(base_url="https://openalyx.internationalbrainlab.org",
          password="international", silent=True, cache_dir=CACHE_DIR)

insertions = bwm_query(one, freeze=FREEZE)
print(f"bwm_query: {len(insertions)} insertions, {insertions.eid.nunique()} sessions, "
      f"{insertions.subject.nunique()} mice")

clusters_path = download_aggregate_tables(one, type="clusters")
print(f"aggregate clusters table: {clusters_path}")

units = bwm_units(one)
print(f"bwm_units: {len(units)} good units in {units.Beryl.nunique()} Beryl regions")

# One session: first insertion in the release
pid, eid = insertions.iloc[0][["pid", "eid"]]
trials, mask = load_trials_and_mask(one, eid)
print(f"session {eid}: {len(trials)} trials, {int(mask.sum())} pass the BWM mask")

ba = AllenAtlas()
ssl = SpikeSortingLoader(pid=pid, one=one, atlas=ba)
spikes, clusters, channels = ssl.load_spike_sorting()
clusters = ssl.merge_clusters(spikes, clusters, channels)
good = clusters["label"] == 1
print(f"insertion {pid}: {len(spikes['times'])} spikes, {int(good.sum())} good units "
      f"of {len(good)}")

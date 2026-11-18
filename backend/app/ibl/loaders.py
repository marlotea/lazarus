"""Load one item's spikes and one session's behaviour, from IBL or from the fake recording.

The return types are plain numpy containers, so `app.pipeline.preprocess` treats real and
fake data the same way. Heavy IBL imports (brainbox, iblatlas) happen inside the real-data
functions only, so importing this module stays cheap.

Real path (checked against the public server in M7):

1. For each pid: `SpikeSortingLoader(pid=pid, one=one, atlas=AllenAtlas())`,
   `load_spike_sorting()`, then `merge_clusters(...)`.
2. Keep clusters with `label == 1` whose acronym maps to the item's region through
   `BrainRegions().acronym2acronym(acr, mapping='Beryl')`. Unit id = `(pid, cluster_id)`.
3. Trials from `one.load_object(eid, 'trials')`, wheel from `one.load_object(eid, 'wheel')`.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from app.settings import get_settings

# Trial table columns preprocessing uses.
TRIAL_COLUMNS = (
    "stimOn_times",
    "firstMovement_times",
    "feedback_times",
    "contrastLeft",
    "contrastRight",
    "choice",
    "feedbackType",
)


@dataclass(frozen=True)
class ProbeUnits:
    """One probe's spikes plus the good units of one region on it."""

    pid: str
    spike_times: np.ndarray  # (n_spikes,) float64 seconds, session clock
    spike_clusters: np.ndarray  # (n_spikes,) int64 cluster id of each spike
    cluster_ids: np.ndarray  # (n_units,) int64 kept clusters, in column order


@dataclass(frozen=True)
class SessionBehaviour:
    """Trial table (full session, indexed by trial number) and raw wheel samples."""

    trials: dict[str, np.ndarray]  # TRIAL_COLUMNS -> (n_trials,)
    wheel_times: np.ndarray  # (n_samples,) seconds
    wheel_position: np.ndarray  # (n_samples,) radians


def select_units(
    clusters: Mapping[str, np.ndarray],
    region: str,
    to_beryl: Callable[[np.ndarray], np.ndarray] | None = None,
) -> np.ndarray:
    """Cluster ids of good units (`label == 1`) whose Beryl acronym is `region`.

    `clusters` needs `label` and `acronym` (and `cluster_id`, else row number = id).
    `to_beryl` maps acronyms to Beryl; None means they already are Beryl acronyms.
    """
    label = np.asarray(clusters["label"], dtype=float)
    acronym = np.asarray(clusters["acronym"]).astype(str)
    if to_beryl is not None:
        acronym = np.asarray(to_beryl(acronym)).astype(str)
    if "cluster_id" in clusters:
        ids = np.asarray(clusters["cluster_id"], dtype=np.int64)
    else:
        ids = np.arange(len(label), dtype=np.int64)
    keep = (label == 1) & (acronym == region)
    return np.sort(ids[keep])


def require_real_session(eid: uuid.UUID | str) -> None:
    """Refuse to look up a fake-catalog session on the IBL server (IBL_FAKE=0)."""
    from app.ibl.fake import is_fake_eid

    if is_fake_eid(eid):
        raise ValueError(
            f"Session {eid} is a fake session (IBL_FAKE=1 data); run with IBL_FAKE=1 to use it."
        )


def load_item_units(eid: uuid.UUID | str, region: str, pids: Iterable[str]) -> list[ProbeUnits]:
    """Good units of `region` on each probe in `pids` (sorted), fake or real."""
    pids = sorted(str(p) for p in pids)
    if get_settings().ibl_fake:
        from app.ibl.fake import fake_probe_units

        return [fake_probe_units(eid, pid, region) for pid in pids]
    require_real_session(eid)
    return [_real_probe_units(pid, region) for pid in pids]


def load_session_behaviour(eid: uuid.UUID | str) -> SessionBehaviour:
    """The session's trial table and wheel trace, fake or real."""
    if get_settings().ibl_fake:
        from app.ibl.fake import fake_behaviour

        return fake_behaviour(eid)
    require_real_session(eid)
    return _real_behaviour(eid)


# --- real IBL ---------------------------------------------------------------------------


@lru_cache
def _atlas():  # -> iblatlas.atlas.AllenAtlas (heavy import, deferred)
    """The 25 um Allen atlas. Its volumes (about 40 MB) are downloaded once into
    `ONE_CACHE_DIR/histology/...`; without `hist_path` iblatlas would use ONE's default
    cache directory (`~/Downloads/ONE/...`) instead of ours.

    iblatlas downloads the volumes with `urllib`, which uses OpenSSL's default CA paths. The
    python.org macOS build has none unless "Install Certificates.command" was run, so the
    download fails with CERTIFICATE_VERIFY_FAILED; point OpenSSL at certifi's bundle (the one
    ONE's `requests` uses) unless SSL_CERT_FILE is already set."""
    import certifi
    from iblatlas.atlas import AllenAtlas

    os.environ.setdefault("SSL_CERT_FILE", certifi.where())
    return AllenAtlas(hist_path=get_settings().one_cache_dir / AllenAtlas.atlas_rel_path)


def _real_probe_units(pid: str, region: str) -> ProbeUnits:
    from brainbox.io.one import SpikeSortingLoader

    from app.ibl.one_client import get_one

    atlas = _atlas()
    ssl = SpikeSortingLoader(pid=pid, one=get_one(), atlas=atlas)
    spikes, clusters, channels = ssl.load_spike_sorting()
    clusters = ssl.merge_clusters(spikes, clusters, channels)
    regions = atlas.regions

    def to_beryl(acronyms: np.ndarray) -> np.ndarray:
        return regions.acronym2acronym(acronyms, mapping="Beryl")

    return ProbeUnits(
        pid=pid,
        spike_times=np.asarray(spikes["times"], dtype=np.float64),
        spike_clusters=np.asarray(spikes["clusters"], dtype=np.int64),
        cluster_ids=select_units(clusters, region, to_beryl),
    )


def _real_behaviour(eid: uuid.UUID | str) -> SessionBehaviour:
    from app.ibl.one_client import get_one

    one = get_one()
    trials = one.load_object(str(eid), "trials")
    wheel = one.load_object(str(eid), "wheel")
    return SessionBehaviour(
        trials={k: np.asarray(trials[k], dtype=np.float64) for k in TRIAL_COLUMNS},
        wheel_times=np.asarray(wheel["timestamps"], dtype=np.float64),
        wheel_position=np.asarray(wheel["position"], dtype=np.float64),
    )

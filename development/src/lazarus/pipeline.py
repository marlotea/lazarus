"""Recording -> CEBRA embedding -> phase trajectories, cached under results/."""
from __future__ import annotations

import json
from pathlib import Path

from .embed import CebraConfig, fit_cebra
from .ibl import REPO_ROOT
from .phases import PHASES, Phase, Trajectories, compute_trajectories
from .recording import Recording

RESULTS_DIR = REPO_ROOT / "results"


def recording_dir(rec: Recording, cfg: CebraConfig, seed: int, root: Path = RESULTS_DIR) -> Path:
    return root / "embeddings" / f"cfg-{cfg.short_hash()}" / rec.key / f"seed{seed}"


def embed_recording(rec: Recording, cfg: CebraConfig, seed: int = 0, phases: tuple[Phase, ...] = PHASES,
                    root: Path = RESULTS_DIR, verbose: bool = False) -> Trajectories:
    out = recording_dir(rec, cfg, seed, root)
    meta = {**rec.metadata(), "seed": seed, "config_hash": cfg.short_hash()}
    key = f"{rec.key}/seed{seed}"
    traj_path = out / "trajectories.npz"
    if traj_path.exists() and (out / "meta.json").exists():
        return Trajectories.from_npz(traj_path, key, json.loads((out / "meta.json").read_text()))
    fit = fit_cebra(rec.X, cfg, seed=seed, out_dir=out, verbose=verbose)
    meta.update(goodness_of_fit_bits=fit.goodness_of_fit_bits, fit_seconds=fit.seconds)
    traj = compute_trajectories(key, meta, fit.embedding, rec.bin_start, rec.bin_chunk, rec.trials,
                                rec.bin_size, phases)
    meta["trials_per_condition"] = traj.counts
    traj.to_npz(traj_path)
    (out / "meta.json").write_text(json.dumps(meta, indent=2))
    (out / "config.json").write_text(json.dumps(cfg.__dict__, indent=2))
    return traj

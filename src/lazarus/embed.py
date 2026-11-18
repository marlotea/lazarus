"""CEBRA training wrapper with on-disk caching keyed by recording + config."""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

import numpy as np
import torch


@dataclass(frozen=True)
class CebraConfig:
    # CEBRA-Time (self-supervised): positives are samples `time_offsets` bins apart. No behaviour or
    # phase labels are used, so "same phase looks similar" cannot be built in by the objective.
    model_architecture: str = "offset10-model"   # 10-bin receptive field = 200 ms at 20 ms bins
    conditional: str = "time"
    time_offsets: int = 10
    output_dimension: int = 8
    num_hidden_units: int = 32
    distance: str = "cosine"
    temperature: float = 1.0
    batch_size: int = 512
    learning_rate: float = 3e-4
    max_iterations: int = 5000
    preprocess: str = "none"                     # "none" | "sqrt" | "zscore"
    device: str = "auto"

    def short_hash(self) -> str:
        cfg = {k: v for k, v in asdict(self).items() if k != "device"}
        return hashlib.sha1(json.dumps(cfg, sort_keys=True).encode()).hexdigest()[:8]


def _device(name: str) -> str:
    if name != "auto":
        return name
    if torch.cuda.is_available():
        return "cuda"
    if torch.backends.mps.is_available():
        return "mps"
    return "cpu"


def preprocess(X: np.ndarray, mode: str) -> np.ndarray:
    if mode == "none":
        return X
    if mode == "sqrt":
        return np.sqrt(X)
    if mode == "zscore":
        sd = X.std(0)
        return (X - X.mean(0)) / np.where(sd > 0, sd, 1)
    raise ValueError(mode)


@dataclass
class FitResult:
    embedding: np.ndarray
    loss: np.ndarray
    goodness_of_fit_bits: float
    seconds: float
    info: dict = field(default_factory=dict)


def fit_cebra(X: np.ndarray, cfg: CebraConfig, seed: int = 0, out_dir: Path | None = None,
              verbose: bool = False) -> FitResult:
    """Fit CEBRA on X (T, n_units) and embed X. Cached in `out_dir` if given."""
    import cebra
    from cebra.integrations.sklearn.metrics import infonce_to_goodness_of_fit

    if out_dir is not None and (out_dir / "embedding.npy").exists():
        info = json.loads((out_dir / "fit.json").read_text())
        return FitResult(np.load(out_dir / "embedding.npy"), np.load(out_dir / "loss.npy"),
                         info["goodness_of_fit_bits"], info["seconds"], info)

    torch.manual_seed(seed)
    np.random.seed(seed)
    Xp = preprocess(X, cfg.preprocess).astype(np.float32)
    params = {k: v for k, v in asdict(cfg).items() if k not in ("preprocess", "device")}
    model = cebra.CEBRA(**params, device=_device(cfg.device), verbose=verbose)
    t = time.time()
    model.fit(Xp)
    seconds = time.time() - t
    emb = model.transform(Xp)
    loss = np.asarray(model.state_dict_["loss"])
    # final loss averaged over the last 5% of iterations -> bits of information above chance
    tail = loss[-max(1, len(loss) // 20):].mean()
    gof = float(infonce_to_goodness_of_fit(tail, model))
    res = FitResult(emb.astype(np.float32), loss, gof, seconds,
                    {"seed": seed, "config": asdict(cfg), "goodness_of_fit_bits": gof,
                     "seconds": seconds, "final_loss": float(tail)})
    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        np.save(out_dir / "embedding.npy", res.embedding)
        np.save(out_dir / "loss.npy", loss)
        (out_dir / "fit.json").write_text(json.dumps(res.info, indent=2))
        model.save(str(out_dir / "model.pt"))
    return res

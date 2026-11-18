"""Train one CEBRA model on one group of one item.

Runnable without FastAPI or the database:

    from app.pipeline.cebra_train import train_group
    result = train_group(folder / "A.npz", "time", {"max_iterations": 100}, out_dir)

The worker records the result in `run_outputs`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from app.schemas.cebra import PARAMS_BY_MODE, CebraParams, LabelledParams

log = logging.getLogger(__name__)

# Param label name -> key in the preprocessing npz.
CONTINUOUS_KEYS = {"wheel_velocity": "wheel_velocity", "signed_contrast": "signed_contrast"}
DISCRETE_KEYS = {"choice": "choice", "feedback": "feedback"}
ROW_LABEL_KEYS = (
    "trial_index",
    "time_in_trial",
    "wheel_velocity",
    "signed_contrast",
    "choice",
    "feedback",
)


class TrainingError(RuntimeError):
    """A model cannot be trained on this data; the message is shown in the UI."""


@dataclass(frozen=True)
class TrainResult:
    n_units: int
    n_samples: int
    final_loss: float
    embedding_path: Path
    model_path: Path
    labels_path: Path


def discrete_codes(values: np.ndarray) -> np.ndarray:
    """Map label values (e.g. choice -1/1) to 0..K-1; CEBRA rejects negative labels."""
    _, codes = np.unique(np.asarray(values), return_inverse=True)
    return codes.astype(np.int64)


def train_group(
    npz_path: Path,
    mode: str,
    params: CebraParams | dict[str, Any],
    out_dir: Path,
    *,
    label: str | None = None,
) -> TrainResult:
    """Fit CEBRA on one group's npz and save `embedding.npy`, `model.pt` and `labels.npz`
    in `out_dir`. `label` names the model in error messages (e.g. "eid CA1 group A")."""
    import cebra
    import torch

    model_cls = PARAMS_BY_MODE[mode]
    p = params if isinstance(params, CebraParams) else model_cls.model_validate(params)
    what = label or str(npz_path)

    # 1. Load the group and check it holds at least one batch.
    with np.load(npz_path, allow_pickle=False) as data:
        arrays = {k: data[k] for k in data.files}
    X = arrays["X"].astype(np.float32)
    n_samples, n_units = X.shape
    if n_samples < p.batch_size:
        raise TrainingError(
            f"{what}: {n_samples} rows (time bins) is fewer than batch_size {p.batch_size}. "
            "Lower the batch size, use smaller bins or a wider window."
        )
    if n_units == 0:
        raise TrainingError(f"{what}: no units to train on")

    # 4. Labels: continuous as (T, k) float32, discrete as 0..K-1 int64.
    y_cont = y_disc = None
    if isinstance(p, LabelledParams):
        if p.continuous_labels:
            y_cont = np.stack(
                [arrays[CONTINUOUS_KEYS[name]] for name in p.continuous_labels], axis=1
            ).astype(np.float32)
        if p.discrete_label is not None:
            y_disc = discrete_codes(arrays[DISCRETE_KEYS[p.discrete_label]])
        if p.hybrid and y_disc is not None:
            raise TrainingError(
                "Hybrid mode cannot use a discrete label (CEBRA does not support it)"
            )

    # 2-3. Kwargs from params + the mode's hidden fields, seeds, model.
    kwargs = p.cebra_kwargs() | {"device": "cuda_if_available", "verbose": False}
    torch.manual_seed(p.seed)
    np.random.seed(p.seed)
    model = cebra.CEBRA(**kwargs)
    labels = [y for y in (y_cont, y_disc) if y is not None]
    log.info(
        "fit %s: %d x %d, mode=%s, labels=%s, max_iterations=%d",
        what,
        n_samples,
        n_units,
        mode,
        [y.shape for y in labels],
        p.max_iterations,
    )
    model.fit(X, *labels)

    # 5. Embedding and files.
    emb = np.asarray(model.transform(X), dtype=np.float32)
    out_dir.mkdir(parents=True, exist_ok=True)
    embedding_path = out_dir / "embedding.npy"
    model_path = out_dir / "model.pt"
    labels_path = out_dir / "labels.npz"
    np.save(embedding_path, emb)
    model.save(str(model_path))
    # Every row label, so later views can colour the embedding by any of them, plus the
    # exact arrays this model was trained on.
    label_arrays = {k: arrays[k] for k in ROW_LABEL_KEYS}
    if y_cont is not None:
        label_arrays["continuous"] = y_cont
        label_arrays["continuous_names"] = np.asarray(p.continuous_labels)  # type: ignore[union-attr]
    if y_disc is not None:
        label_arrays["discrete"] = y_disc
        label_arrays["discrete_name"] = np.asarray(p.discrete_label)  # type: ignore[union-attr]
    np.savez(labels_path, **label_arrays)

    # 6. Final loss: cebra 0.6.1 keeps the per-iteration loss in state_dict_["loss"].
    loss = model.state_dict_["loss"]
    final_loss = float(loss[-1]) if len(loss) else float("nan")
    log.info("done %s: final loss %.4f, embedding %s", what, final_loss, emb.shape)
    return TrainResult(n_units, n_samples, final_loss, embedding_path, model_path, labels_path)

# lazarus

CEBRA + Gromov-Wasserstein alignment on the IBL Brain-Wide Map.

## Setup

```sh
uv sync
uv run python scripts/ibl_smoke_test.py
```

`scripts/ibl_smoke_test.py` connects to the public IBL server (openalyx), runs `bwm_query` / `bwm_units`
pinned to `freeze='2023_12_bwm_release'`, and loads the trials and spike sorting for one session.
Downloaded data is cached in `data/ONE/` (gitignored).

`brainwidemap` is pinned to commit `705b7cb`; later upstream commits switch the default aggregate
tag to `2026_Q2_IBL_et_al_BWM`, which breaks `bwm_units` (no trials table for that tag).

## CEBRA control analyses

Plan, data selection, and comparison metrics for the three controls: [`docs/controls_plan.md`](docs/controls_plan.md).

```sh
uv run python scripts/control1.py                                # ZM_2241 2020-01-30, all regions >= 15 units
uv run python scripts/control1.py --regions MD PO --iters 300 --no-ceiling   # quick check
```

Reusable pieces live in `src/lazarus/` (`ibl` loading, `recording` splits/binning, `embed` CEBRA
wrapper, `phases` trajectories, `compare` metrics, `plots`). Embeddings are cached per
recording/config/seed under `results/embeddings/`; per-control outputs go to `results/control*/`
(gitignored).

ONE writes its auth token to `~/.one`, so the data scripts can't run inside a sandbox that blocks
writes to the home directory.

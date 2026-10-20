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

# Research Tracker

Track Experiments (a selection of IBL session × brain-region items) and the CEBRA runs
trained on them. v0 is described in [`docs/v0-build-plan.md`](docs/v0-build-plan.md).

| Folder | What |
| --- | --- |
| `frontend/` | Next.js (App Router, TypeScript, Tailwind, shadcn/ui), talks only to the API |
| `backend/` | FastAPI app and the CEBRA worker, managed by uv |
| `supabase/` | Local Supabase config, SQL migrations and seed |

## Prerequisites

Node 20+, pnpm, Python 3.11, [uv](https://docs.astral.sh/uv/), Docker, and the
[Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started).
The Makefile runs the CLI through `npx --yes supabase@3.2.0`, so a global install is optional
(override with `make db SUPABASE=supabase`). A CUDA GPU is optional; CEBRA falls back to CPU.

## Setup

```sh
# 1. Environment files
cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local

# 2. Dependencies (uv sync + pnpm install)
make install

# 3. Database: start local Supabase (Postgres on 127.0.0.1:54322), then apply migrations + seed
make db
make db-reset
```

`supabase/config.toml` disables every Supabase service except Postgres (no Studio, Auth,
Storage, Realtime, ...). FastAPI is the only database client.

## Running

Each in its own terminal:

```sh
make api      # FastAPI on http://localhost:8000 (docs at /docs)
make worker   # CEBRA worker loop (polls Postgres for queued runs)
make web      # Next.js on http://localhost:3000
```

### The worker

`make worker` (`python -m app.worker`) polls Postgres every 3 s and trains one run at a time.
For each item it preprocesses the session's split (group A and B) into
`DATA_DIR/preprocess/<hash>/{A,B}.npz` (reused when the item, split and preprocessing params
match), then trains one CEBRA model per group into
`DATA_DIR/runs/<run_id>/<eid>_<region>_<group>/` (`embedding.npy`, `model.pt`, `labels.npz`)
and logs to `DATA_DIR/runs/<run_id>/run.log`. A failed run keeps the end of its traceback in
`runs.error` (click the Failed badge). Ctrl-C or SIGTERM fails the current run with
"worker stopped"; a worker that died mid-run (e.g. `kill -9`) fails that run with
"worker restarted mid-run" when it starts again. With `IBL_FAKE=1` the data is a synthetic
recording whose neurons follow wheel velocity, stimulus contrast and movement.

The pipeline is importable without FastAPI, e.g. from a notebook:

```python
from app.pipeline.preprocess import preprocess_item, load_group
from app.pipeline.cebra_train import train_group
```

### Real IBL data

`IBL_FAKE=1` (the default in `.env.example`) uses synthetic data and never touches the network.
To use the public IBL server, set `IBL_FAKE=0` in `backend/.env`, or per command (an
environment variable wins over `.env`), for the API, the worker and the catalog sync alike:

```sh
IBL_FAKE=0 make sync-catalog ARGS="--regions CA1 --limit 5"
IBL_FAKE=0 make sync-catalog ARGS="--regions CA1 --eids 9a6e127b-bb07-4be2-92e2-53dd858c2762,446f4724-1690-49f9-819a-2bd8e2ea88ce"
IBL_FAKE=0 make api
IBL_FAKE=0 make worker
```

- The catalog comes from `brainwidemap` (pinned to commit `705b7cb`; later commits change the
  aggregate tag that `bwm_units` checks). `bwm_query` reads the 2023-12 BWM freeze and
  `bwm_units` downloads two aggregate tables (about 115 MB) into `ONE_CACHE_DIR/bwm_tables`.
  `--limit N` keeps the first N sessions by date; `--eids` picks sessions by eid.
- Making a split loads the session's trials table (a few MB). The worker downloads each probe's
  spike sorting (roughly 300-400 MB per probe), the wheel, and once the 25 um Allen atlas
  (about 40 MB), all under `ONE_CACHE_DIR`. Watch the free disk space.
- Fake and real sessions live side by side in the catalog (fake subjects are `FAKE01` to
  `FAKE06`); sync only adds or updates rows. Keep each experiment to one kind: a worker started
  with `IBL_FAKE=0` cannot preprocess fake sessions and vice versa (the run fails with a
  message). `make db-reset` clears everything.
- ONE writes its settings to `~/.one` and warns that the shared public account will be retired
  at some point; register your own account on openalyx if it stops working.
- On the python.org macOS Python, the atlas download needs a CA bundle; the loader points
  `SSL_CERT_FILE` at certifi's bundle when it is not set.

## Other commands

| Command | Does |
| --- | --- |
| `make db-stop` | Stop local Supabase |
| `make db-reset` | Drop and re-create the local database from `supabase/migrations` + `seed.sql` |
| `make types` | Regenerate `frontend/lib/api-types.ts` from the running API's OpenAPI schema |
| `make sync-catalog ARGS="--regions CA1,DG --limit 50"` | Fill the IBL catalog tables (fake or real per `IBL_FAKE`; also `--eids EID,EID`) |
| `make test` | Backend `pytest` + frontend `vitest run` (backend tests need the local database: `make db` and `make db-reset`) |
| `make lint` | `ruff` + `eslint` |

## Environment variables

| File | Variable | Meaning |
| --- | --- | --- |
| `backend/.env` | `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres` (local Supabase) |
| `backend/.env` | `DATA_DIR` | Preprocessing cache and run outputs (`~` is expanded) |
| `backend/.env` | `ONE_BASE_URL` | Public IBL server, `https://openalyx.internationalbrainlab.org` |
| `backend/.env` | `ONE_CACHE_DIR` | Where ONE stores downloaded IBL files (default `~/448-data/ONE`) |
| `backend/.env` | `IBL_FAKE` | `1` = synthetic IBL data instead of real downloads (dev and tests) |
| `backend/.env` | `CORS_ORIGINS` | Comma-separated allowed origins, e.g. `http://localhost:3000` |
| `frontend/.env.local` | `NEXT_PUBLIC_API_URL` | `http://localhost:8000` |

## Known limits (v0)

- Trials are concatenated before CEBRA training, so CEBRA's time offsets can pair bins across a
  trial boundary.
- Hybrid mode cannot use a discrete label: CEBRA 0.6.1's sklearn API does not implement that
  combination, so the API rejects it.
- A group needs at least `batch_size` rows (time bins); otherwise that run fails with a message.
- Backend tests that exercise the worker skip themselves while the database has queued or
  running runs, and must not run next to `make worker` (it would claim their runs).

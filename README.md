# Research Tracker

Track Experiments (a selection of IBL session × brain-region items) and the CEBRA runs
trained on them. Each session's behavioural trials are split at random into groups A and B,
and every run trains one CEBRA model per item and group. v0 is described in
[`docs/v0-build-plan.md`](docs/v0-build-plan.md).

| Folder | What |
| --- | --- |
| `frontend/` | Next.js (App Router, TypeScript, Tailwind, shadcn/ui), talks only to the API |
| `backend/` | FastAPI app and the CEBRA worker, managed by uv |
| `supabase/` | Local Supabase config, SQL migrations and seed |

Five processes on one machine: Postgres (local Supabase in Docker), the API (`make api`), the
worker (`make worker`), the web app (`make web`) and your browser. The browser only talks to the
API; the API and the worker only meet in Postgres (the worker polls it for queued runs).

## Prerequisites

- Node 20+ and [pnpm](https://pnpm.io/installation)
- [uv](https://docs.astral.sh/uv/). The backend pins Python 3.11 (`backend/.python-version`);
  uv uses an installed 3.11 or downloads one.
- Docker (Docker Desktop on macOS), running
- The [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started)
  is optional: the Makefile runs it as `npx --yes supabase@3.2.0`. To use a global install,
  pass `SUPABASE=supabase`, e.g. `make db SUPABASE=supabase`.
- GNU make (the macOS one is fine)
- Disk: about 3 GB for the dependencies (PyTorch, CEBRA, ibllib, Next.js) and about 2 GB for
  the Supabase Postgres image (plus a small Kong gateway image). Real IBL data needs much more; see [Real IBL data](#real-ibl-data).
- A CUDA GPU is optional; CEBRA falls back to CPU.

## Setup

```sh
git clone <repo-url> research-tracker && cd research-tracker

# 1. Environment files + dependencies. `make install` copies backend/.env.example to
#    backend/.env and frontend/.env.local.example to frontend/.env.local if they are
#    missing (it never overwrites them), then runs `uv sync` and `pnpm install`.
make install

# 2. Database: start local Supabase (Postgres on 127.0.0.1:54322), then create the tables
#    and the default workspace from supabase/migrations + supabase/seed.sql.
make db
make db-reset

# 3. IBL catalog. With IBL_FAKE=1 (the default in .env.example) this writes 10 synthetic
#    sessions (subjects FAKE01 to FAKE06, regions CA1, DG, LP, VISp, MOs, PO) and needs
#    no network.
make sync-catalog
```

The first `make db` pulls the Postgres image and takes a minute or two. `supabase/config.toml`
disables every Supabase service v0 does not use (Studio, Auth, Storage, Realtime, ...), so it
starts only Postgres; FastAPI is the only database client.

`make db-reset` drops and re-creates the whole local database: experiments, runs and the
catalog. Run `make sync-catalog` again after it. Files under `DATA_DIR` are not touched.

Check the setup with `make test` (backend `pytest` + frontend `vitest`; the backend tests need
the database from step 2 and add the fake catalog themselves).

## Running

Each in its own terminal, from the repo root:

```sh
make api      # FastAPI on http://localhost:8000 (interactive docs at /docs)
make worker   # CEBRA worker: polls Postgres every 3 s, runs one job at a time
make web      # Next.js on http://localhost:3000
```

Open http://localhost:3000. The sidebar footer (top bar on a phone) shows "Worker online"
while `make worker` is running and "Worker offline" otherwise. Stop each with Ctrl-C. make may
print an error line for the stopped command; that is expected (the worker still fails its
current run with "worker stopped" and removes its heartbeat).

## Walkthrough: from an empty database to a succeeded run

With the fake catalog synced and the three processes running:

1. **Create an experiment.** On **Experiments**, click **New experiment**, give it a title
   (for example "CA1 smoke test") and click **Create experiment**. You land on its page.
2. **Select data.** In **1 Data**, click **Select data**. In the panel, filter by Region
   (pick `CA1`), tick two sessions (or a whole subject with its group checkbox) and click
   **Save**. Each session now shows its split, e.g. "Split A 301 · B 302"; the ↻ button next
   to it makes a new random split.
3. **Queue a run.** In **2 CEBRA training**, click **New run**. Keep mode **Time** and the
   suggested name `time-01`. For a quick check set **Max iterations** to `100` (the default,
   5000, takes several minutes per model on a CPU). Click **Queue run**: a "Run queued" toast
   shows and the run appears in the table as **Queued**.
4. **Let the worker train it.** If `make worker` is not running, a yellow bar says so ("The
   worker is not running, so queued runs will wait..."); start it. The badge turns
   **Running 0/4**, counts up as each model finishes (2 items × groups A and B = 4 models),
   and ends **Succeeded** (about 15 s for this example on a laptop CPU). The table polls every
   3 s while a run is queued or running.

If something fails, the badge says **Failed**; click it to read the error the worker
recorded. Outputs land in `DATA_DIR/runs/<run_id>/` (see below).

### What the worker does

`make worker` (`python -m app.worker`) claims the oldest queued run. For each item it
preprocesses the session's split (group A and B) into
`DATA_DIR/preprocess/<hash>/{A,B}.npz` (reused when the item, split and preprocessing params
match): good units only, spike counts in `bin_size_ms` bins over a window around the align
event of each trial. It then trains one CEBRA model per group into
`DATA_DIR/runs/<run_id>/<eid>_<region>_<group>/` (`embedding.npy`, `model.pt`, `labels.npz`)
and logs to `DATA_DIR/runs/<run_id>/run.log`. A failed run keeps the end of its traceback in
`runs.error`. Ctrl-C or SIGTERM fails the current run with "worker stopped"; a worker that died
mid-run (e.g. `kill -9`) fails that run with "worker restarted mid-run" when it starts again.
v0 assumes a single worker. With `IBL_FAKE=1` the data is a synthetic recording whose neurons
follow wheel velocity, stimulus contrast and movement.

The pipeline is importable without FastAPI, e.g. from a notebook:

```python
from app.pipeline.preprocess import preprocess_item, load_group
from app.pipeline.cebra_train import train_group
```

## Real IBL data

`IBL_FAKE=1` (the default in `.env.example`) uses synthetic data and never touches the network.
To use the public IBL server (openalyx), set `IBL_FAKE=0` per command (an environment variable
wins over `.env`) for the catalog sync, the API and the worker alike:

```sh
# Catalog: Brain Wide Map sessions with CA1 units. --limit N keeps the first N sessions by
# date, --eids picks sessions by eid.
IBL_FAKE=0 make sync-catalog ARGS="--regions CA1 --limit 5"
IBL_FAKE=0 make sync-catalog ARGS="--regions CA1 --eids 9a6e127b-bb07-4be2-92e2-53dd858c2762,446f4724-1690-49f9-819a-2bd8e2ea88ce"

IBL_FAKE=0 make api
IBL_FAKE=0 make worker
```

(Or set `IBL_FAKE=0` in `backend/.env`; then `make test` also needs `IBL_FAKE=1 make test`.)

- The two eids above are good first sessions for CA1: PL015 2022-02-21 (62 CA1 units, one
  probe, 627 valid trials) and KS096 2022-06-20 (39 CA1 units, one probe, 701 valid trials).
  The first sessions by date have only 10-11 CA1 units, which is little to train on.
- The catalog comes from `brainwidemap` (pinned to commit `705b7cb`; later commits change the
  aggregate tag that `bwm_units` checks). `bwm_query` reads the bundled 2023-12 BWM freeze and
  `bwm_units` downloads two aggregate tables (about 115 MB, once) into
  `ONE_CACHE_DIR/bwm_tables`. A sync takes about 30 s.
- Selecting a session loads its trials table (a few MB) to make the split, so **Save** in the
  data panel takes a few seconds per new session. The worker downloads each probe's spike
  sorting (about 0.5-0.7 GB per probe, about a minute each), the wheel, and once the 25 µm
  Allen atlas (about 40 MB), all under `ONE_CACHE_DIR` (default `~/448-data/ONE`). Later runs
  on the same sessions reuse the cache: a 2-session Time run with 500 iterations takes about
  90 s once the data is cached.
- Fake and real sessions live side by side in the catalog (fake subjects are `FAKE01` to
  `FAKE06`); sync only adds or updates rows. Keep each experiment to one kind, and run the API
  and the worker in the matching mode: a worker started with `IBL_FAKE=0` cannot preprocess
  fake sessions and vice versa (the run fails with a message saying so), and an API in the wrong
  mode cannot make splits (Save shows the error).
- ONE writes its settings to `~/.one` and warns that the shared public account will be retired
  at some point; register your own account on openalyx if it stops working. It also prints
  `ALFWarning`s about multiple dataset revisions (it picks the latest; harmless).

## Other commands

| Command | Does |
| --- | --- |
| `make db-stop` | Stop local Supabase (the data survives; `make db` starts it again) |
| `make db-reset` | Drop and re-create the local database from `supabase/migrations` + `seed.sql` |
| `make types` | Regenerate `frontend/lib/api-types.ts` from the running API's OpenAPI schema |
| `make sync-catalog ARGS="--regions CA1,DG --limit 50"` | Fill the IBL catalog tables (fake or real per `IBL_FAKE`; also `--eids EID,EID`) |
| `make test` | Backend `pytest` + frontend `vitest run` |
| `make lint` | `ruff` + `eslint` |
| `cd frontend && pnpm build` | Production build of the web app |

## Environment variables

| File | Variable | Meaning |
| --- | --- | --- |
| `backend/.env` | `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres` (local Supabase) |
| `backend/.env` | `DATA_DIR` | Preprocessing cache and run outputs, default `~/448-data` (`~` is expanded) |
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
- A group needs at least `batch_size` rows (time bins; 75 per trial with the default window);
  otherwise that run fails with a message.
- Splits are a plain seeded 50/50 random split of the valid trials (not stratified by choice or
  contrast). A trial is valid when its stimulus, first-movement and feedback times all exist.
- Runs cannot be cancelled or re-run, and the app has no results view yet: read the outputs
  from `DATA_DIR/runs/<run_id>/` (each `run_outputs` row has the embedding and model paths).
- One worker at a time. The worker-online dot uses a 15 s heartbeat, so a worker killed with
  `kill -9` still shows online for up to 15 s.
- The selection panel shows at most 2000 catalog rows per filter (the API's default limit);
  narrow the filters on a big real catalog.
- Backend tests that exercise the worker skip themselves while the database has queued or
  running runs, and must not run next to `make worker` (it would claim their runs).

## Troubleshooting

- **"Cannot reach the API at http://localhost:8000"** (toast or card): `make api` is not
  running, or `NEXT_PUBLIC_API_URL` in `frontend/.env.local` points elsewhere (restart
  `make web` after changing it). A browser on another origin than `CORS_ORIGINS` sees the same
  message.
- **"Cannot reach the database. Is Supabase running?"**: start it with `make db`. **"Workspace
  'cpsc-448' missing; run `make db-reset`"** or **"Database error. If the tables are
  missing..."**: the tables or the seed are missing; run `make db-reset`, then
  `make sync-catalog`.
- **Empty Region filter / no catalog items in Select data**: the catalog is empty (for
  example right after `make db-reset`); run `make sync-catalog`.
- **Queued runs never start / "Worker offline"**: start `make worker`, in the same `IBL_FAKE`
  mode as the experiment's data.
- **Sandboxed shells (e.g. AI coding agents):** ONE writes `~/.one`, the worker and the sync
  write to `DATA_DIR` and `ONE_CACHE_DIR` under your home folder, and the servers bind local
  ports; run these commands outside the sandbox. If uv cannot write its cache inside a sandbox,
  point it elsewhere: `UV_CACHE_DIR=$TMPDIR/uv-cache make test`.
- **SSL certificate errors on IBL downloads** (`CERTIFICATE_VERIFY_FAILED`): the python.org
  macOS Python ships without a CA bundle. The loader points `SSL_CERT_FILE` at certifi's bundle
  when it is unset; if that is not enough, run `Install Certificates.command` from the Python
  folder in Applications, or `export SSL_CERT_FILE="$(backend/.venv/bin/python -m certifi)"`.
- **Disk full:** check `df -h`. The ONE cache (`ONE_CACHE_DIR`) grows by about 0.5-0.7 GB per
  real probe; delete session folders there to free space (they are downloaded again when
  needed). `DATA_DIR/preprocess/` is a cache and safe to delete; `DATA_DIR/runs/` holds run
  outputs. If Docker runs out of space while pulling the Supabase image, free space and run
  `make db` again.
- **Matplotlib cache warnings** from ibllib when your home folder is read-only: set
  `MPLCONFIGDIR=/tmp/mpl`.
- **Port already in use:** another `make api` (8000) or `make web` (3000) is still running;
  stop it first.

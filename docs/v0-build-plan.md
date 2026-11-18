# Research Tracker v0: Build Plan

Nov 17, 2026 · @Leia

## Summary and v0 scope

v0 lets you create an Experiment, pick IBL data for it (session × brain region), split each session's behavioural trials into two groups, and queue CEBRA runs that train on each group separately. Runs execute on the machine that hosts the backend. Everything else in the [technical proposal](https://claude.ai/artifact/KSsDx6URVFPmV7uaBQbF9X) waits for later versions.

This doc is the hand-off for a code agent starting from an empty repository. Stack: Next.js + shadcn/ui (frontend), FastAPI (backend), Supabase Postgres (database). Visual style follows the [design prototype](https://claude.ai/artifact/8FnRcPL1X1tA6AAHcc8qbs).

**In v0**

- Experiments list and Experiment page: title, description, date created.
- Data section: browse and select session × region items, grouped by subject, session or region.
- Per-session random split of behavioural trials into groups A and B, stored and shown.
- Preprocessing (backend only): keep good units, bin spike times into a time × neuron count matrix.
- CEBRA section: runs table (name, status, parameters) and a New run form with Time / Behaviour / Hybrid modes.
- Queueing: the form sends a request to FastAPI; a local worker process runs the job and updates status.

**Not in v0** (do not build)

- Login and multiple users. Schema keeps a `workspace_id` so this is cheap later.
- Run results views (loss curves, embedding plots), JGW / optimal transport, figures, notes, compare view.
- Run cancel, rerun, "start from run", run-key caching across runs, W&B, remote machines, UBC ARC.
- Duplicating or locking experiments.

## Key decisions and terms

The top-level object is called **Experiment**, not Trial. In this codebase "trial" only ever means an IBL behavioural trial. Use these names in code, database and UI.

| Term | Meaning | Where it lives |
| --- | --- | --- |
| Experiment | A named dataset selection plus the CEBRA runs on it | `experiments` table, `/experiments/[id]` page |
| Item | One brain region in one IBL session (session × region). Probes in the same session are merged | `experiment_items` |
| Session | One IBL recording session, keyed by `eid` | `ibl_sessions` (catalog) |
| Region | Beryl atlas acronym, e.g. `CA1` | `ibl_session_regions.region` |
| Trial | One IBL behavioural trial inside a session | Only as integer indices in splits |
| Split | Seeded random 50/50 division of a session's valid trials into groups A and B | `trial_splits` |
| Run | One queued CEBRA job: one config applied to every item, trained once on group A and once on group B | `runs` (stage = `cebra`) |
| Run output | One trained model for one item and one group | `run_outputs` |

**Decisions the agent should not revisit**

- The frontend talks only to FastAPI. FastAPI is the only thing that touches Postgres. (Later the worker can move to another machine because jobs queue through the database.)
- The worker is a separate Python process on the same machine as FastAPI. It polls Postgres for queued runs. No Celery, Redis or cloud queue.
- A run snapshots its inputs: the item list and the split IDs it used are saved in the run row. Editing the selection later never changes an old run.
- Splits are immutable rows. "Reshuffle" creates a new split row and marks the old one superseded.
- Every CEBRA model trains on one group only. A run with 4 items produces 8 models (4 × A, 4 × B).
- Schema changes go through Supabase CLI SQL migrations. One source of truth for local and hosted.

## Repo setup from empty

One monorepo with three top-level folders: `frontend/`, `backend/`, `supabase/`. Local development runs Supabase in Docker, so nothing needs a hosted project until you want one.

**Prerequisites:** Node 20+, pnpm, Python 3.11, [uv](https://docs.astral.sh/uv/), Docker, [Supabase CLI](https://supabase.com/docs/guides/local-development/cli/getting-started). A CUDA GPU is optional; CEBRA falls back to CPU.

```
research-tracker/
├─ frontend/                 # Next.js (App Router, TypeScript, Tailwind, shadcn/ui)
│  ├─ app/
│  │  ├─ layout.tsx           # app shell: sidebar + main
│  │  ├─ page.tsx             # redirects to /experiments
│  │  └─ experiments/
│  │     ├─ page.tsx          # list
│  │     └─ [id]/
│  │        ├─ page.tsx       # experiment page (header, data, CEBRA)
│  │        └─ runs/new/page.tsx
│  ├─ components/
│  │  ├─ ui/                  # shadcn generated, do not hand-edit
│  │  ├─ data/                # DataSection, SelectionEditor, GroupedTree, SplitBadge
│  │  └─ cebra/               # RunsTable, RunStatusBadge, NewRunForm, SchemaField
│  ├─ lib/
│  │  ├─ api.ts               # typed fetch client
│  │  ├─ api-types.ts         # generated from FastAPI OpenAPI
│  │  └─ group-items.ts       # pure grouping functions (unit tested)
│  └─ .env.local.example
├─ backend/                  # FastAPI + worker, managed by uv
│  ├─ pyproject.toml
│  ├─ app/
│  │  ├─ main.py              # FastAPI app, CORS, routers
│  │  ├─ settings.py          # pydantic-settings, reads .env
│  │  ├─ db.py                # SQLAlchemy engine + session dependency
│  │  ├─ models.py            # ORM classes mapped to the migration tables
│  │  ├─ schemas/             # Pydantic request/response + CEBRA param models
│  │  ├─ routers/             # experiments.py, catalog.py, runs.py
│  │  ├─ ibl/                 # one_client.py, catalog_sync.py, loaders.py, fake.py
│  │  ├─ pipeline/            # splits.py, preprocess.py, cebra_train.py
│  │  └─ worker.py            # polling loop
│  ├─ tests/
│  └─ .env.example
├─ supabase/
│  ├─ config.toml              # from `supabase init`
│  ├─ migrations/              # 0001_init.sql ...
│  └─ seed.sql                 # default workspace
├─ Makefile                  # dev commands below
└─ README.md
```

**Setup steps for the agent**

1. `git init`, add a root `.gitignore` (Node, Python, `.env*` except examples, `data/`).
2. Frontend: `pnpm create next-app@latest frontend --ts --tailwind --eslint --app --src-dir=false --import-alias "@/*"`, then `pnpm dlx shadcn@latest init` (base colour: zinc).
3. Add shadcn components: `button card table badge input textarea label select checkbox toggle-group tabs dialog sheet dropdown-menu tooltip skeleton separator scroll-area collapsible sonner form`.
4. Frontend libraries: `@tanstack/react-query`, `react-hook-form`, `zod`, `@hookform/resolvers`, `date-fns`, `lucide-react`; dev: `openapi-typescript`, `vitest`.
5. Backend: `uv init backend --python 3.11`, then `uv add fastapi "uvicorn[standard]" "sqlalchemy>=2" "psycopg[binary]" pydantic pydantic-settings numpy ONE-api ibllib cebra` and dev deps `pytest httpx ruff`.
6. Supabase: `supabase init`, write `migrations/0001_init.sql` (next section) and `seed.sql`, then `supabase start` and `supabase db reset`.
7. Fonts: load Inter and JetBrains Mono with `next/font/google` in `layout.tsx`.

**Environment variables**

| File | Variable | Example / meaning |
| --- | --- | --- |
| `backend/.env` | `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres` (local Supabase) |
| `backend/.env` | `DATA_DIR` | `~/448-data`: preprocessing cache and run outputs |
| `backend/.env` | `ONE_BASE_URL` | `https://openalyx.internationalbrainlab.org` (public IBL server) |
| `backend/.env` | `ONE_CACHE_DIR` | Where ONE stores downloaded IBL files |
| `backend/.env` | `IBL_FAKE` | `1` = use synthetic data instead of IBL (dev and tests) |
| `backend/.env` | `CORS_ORIGINS` | `http://localhost:3000` |
| `frontend/.env.local` | `NEXT_PUBLIC_API_URL` | `http://localhost:8000` |

**Makefile targets**

- `make db` → `supabase start`; `make db-reset` → `supabase db reset` (re-runs migrations + seed).
- `make api` → `cd backend && uv run uvicorn app.main:app --reload --port 8000`.
- `make worker` → `cd backend && uv run python -m app.worker`.
- `make web` → `cd frontend && pnpm dev`.
- `make types` → `pnpm openapi-typescript http://localhost:8000/openapi.json -o lib/api-types.ts`.
- `make sync-catalog` → `uv run python -m app.ibl.catalog_sync` (optional flags `--regions CA1,DG --limit 50`).
- `make test` → backend `pytest` + frontend `vitest run`.

## Database schema

Nine tables in one migration, `supabase/migrations/0001_init.sql`. Two are a read-only IBL catalog, one tracks the worker, the rest belong to experiments. Large arrays never go in Postgres, only their file paths.

```sql
create extension if not exists pgcrypto;

-- Scope for future multi-user support. v0 seeds one row.
create table workspaces (
  id          uuid primary key default gen_random_uuid(),
  name        text not null unique,
  created_at  timestamptz not null default now()
);

-- IBL catalog (filled by catalog_sync, never edited by the app)
create table ibl_sessions (
  eid           uuid primary key,
  subject       text not null,
  lab           text not null,
  session_date  date not null,
  n_trials      int,
  synced_at     timestamptz not null default now()
);

create table ibl_session_regions (
  eid           uuid not null references ibl_sessions(eid) on delete cascade,
  region        text not null,            -- Beryl acronym
  n_good_units  int  not null,
  pids          uuid[] not null,          -- probes that cross this region
  primary key (eid, region)
);
create index on ibl_session_regions (region);

-- Experiments
create table experiments (
  id            uuid primary key default gen_random_uuid(),
  workspace_id  uuid not null references workspaces(id),
  title         text not null check (length(title) between 1 and 200),
  description   text not null default '',
  created_at    timestamptz not null default now(),
  updated_at    timestamptz not null default now()
);

create table experiment_items (
  id             uuid primary key default gen_random_uuid(),
  experiment_id  uuid not null references experiments(id) on delete cascade,
  eid            uuid not null,
  region         text not null,
  added_at       timestamptz not null default now(),
  unique (experiment_id, eid, region),
  foreign key (eid, region) references ibl_session_regions(eid, region)
);

create table trial_splits (
  id             uuid primary key default gen_random_uuid(),
  experiment_id  uuid not null references experiments(id) on delete cascade,
  eid            uuid not null references ibl_sessions(eid),
  seed           bigint not null,
  ratio          real not null default 0.5,
  group_a        int[] not null,          -- trial indices
  group_b        int[] not null,
  superseded_at  timestamptz,             -- null = current split
  created_at     timestamptz not null default now()
);
-- exactly one current split per session per experiment
create unique index one_current_split on trial_splits (experiment_id, eid) where superseded_at is null;

-- Runs (stage column keeps room for 'jgw' later)
create table runs (
  id              uuid primary key default gen_random_uuid(),
  workspace_id    uuid not null references workspaces(id),
  experiment_id   uuid not null references experiments(id) on delete cascade,
  stage           text not null default 'cebra' check (stage in ('cebra')),
  name            text not null,
  mode            text not null check (mode in ('time','behaviour','hybrid')),
  params          jsonb not null,          -- validated CEBRA params
  preprocess      jsonb not null,          -- validated preprocessing params
  inputs          jsonb not null,          -- snapshot: [{eid, region, split_id}]
  status          text not null default 'queued'
                  check (status in ('queued','running','succeeded','failed')),
  progress        jsonb not null default '{"done":0,"total":0}',
  error           text,
  output_dir      text,
  created_at      timestamptz not null default now(),
  started_at      timestamptz,
  finished_at     timestamptz,
  unique (experiment_id, name)
);
create index on runs (status, created_at);

create table run_outputs (
  id              uuid primary key default gen_random_uuid(),
  run_id          uuid not null references runs(id) on delete cascade,
  eid             uuid not null,
  region          text not null,
  split_group     text not null check (split_group in ('A','B')),
  n_units         int,
  n_samples       int,
  final_loss      real,
  embedding_path  text,
  model_path      text,
  created_at      timestamptz not null default now(),
  unique (run_id, eid, region, split_group)
);

-- Worker liveness, shown in the UI when queued runs are not starting
create table worker_heartbeats (
  worker_id  text primary key,
  last_seen  timestamptz not null default now()
);
```

`seed.sql` inserts one workspace named `cpsc-448`. The backend reads its id once at startup and uses it for every insert.

**Notes for the agent**

- Use `updated_at` triggers or set it in the PATCH handler; either is fine.
- Do not enable row-level security in v0. FastAPI connects with the database owner role and there is no browser access to Postgres.
- With `IBL_FAKE=1`, `catalog_sync` writes fake sessions into the same catalog tables, so foreign keys still hold.

## Backend API

Thirteen JSON endpoints under `/api`. FastAPI generates `/openapi.json`; the frontend types come from it, so request and response models must be Pydantic classes, not dicts.

| Method | Path | Does | Notes |
| --- | --- | --- | --- |
| GET | `/api/health` | Liveness + DB check | Returns `{ok, db, worker_last_seen}` |
| GET | `/api/experiments` | List experiments, newest first | Each row: id, title, description, created\_at, item\_count, run\_count |
| POST | `/api/experiments` | Create | Body `{title, description?}` → 201 |
| GET | `/api/experiments/{id}` | One experiment | 404 if missing |
| PATCH | `/api/experiments/{id}` | Edit title / description |  |
| GET | `/api/catalog/items` | Flat catalog rows (session × region) | Query: `region`, `subject`, `lab`, `min_units`, `limit` (default 2000), `offset` |
| GET | `/api/catalog/regions` | Distinct regions with session counts | For the region filter autocomplete |
| GET | `/api/experiments/{id}/items` | Selected items joined with catalog info and the current split per session |  |
| PUT | `/api/experiments/{id}/items` | Replace the whole selection | Body `{items:[{eid, region}]}`. Creates a split for each newly added session |
| POST | `/api/experiments/{id}/splits/{eid}/reshuffle` | New seed for one session | Old split gets `superseded_at`; old runs keep pointing at it |
| GET | `/api/cebra/schema` | JSON Schema for each mode + preprocessing | Built from the Pydantic models below; drives the form |
| GET / POST | `/api/experiments/{id}/runs` | List runs / queue a run | POST → 201 with the run; 409 if the name exists; 422 if params invalid or no items selected |

**Item response shape** (what the data section renders)

```json
{
  "eid": "aad23144-...", "region": "CA1",
  "subject": "KS023", "lab": "cortexlab", "session_date": "2019-12-10",
  "n_good_units": 64,
  "split": { "id": "...", "seed": 81723, "n_a": 301, "n_b": 302 }
}
```

**CEBRA parameter models** (`app/schemas/cebra.py`)

One Pydantic base class holds the shared fields. Each mode subclasses it and pins the CEBRA arguments that define the mode, so the user cannot pick a wrong combination. Field `title`, `description`, defaults and bounds are what the form shows.

| Field | Type, default | Bounds / options | Modes |
| --- | --- | --- | --- |
| `model_architecture` | enum, `offset10-model` | `offset10-model`, `offset5-model`, `offset36-model` | all |
| `output_dimension` | int, 8 | 2–64 | all |
| `batch_size` | int, 512 | 64–4096 | all |
| `learning_rate` | float, 3e-4 | 1e-6–1e-1 | all |
| `temperature` | float, 1.0 | 0.01–10 | all |
| `max_iterations` | int, 5000 | 100–100000 | all |
| `distance` | enum, `cosine` | `cosine`, `euclidean` | all |
| `time_offsets` | int, 10 | 1–100 | all |
| `seed` | int, 0 | ≥ 0 | all |
| `continuous_labels` | multi-enum, `[wheel_velocity]` | `wheel_velocity`, `signed_contrast` | behaviour, hybrid |
| `discrete_label` | enum or null, null | `choice`, `feedback` | behaviour, hybrid |

Hidden fields set by the mode, never shown: Time → `conditional='time'`; Behaviour → `conditional='time_delta'`; Hybrid → `conditional='time_delta', hybrid=True`. Behaviour and Hybrid need at least one label (validator). CEBRA accepts one discrete label at most, which is why `discrete_label` is single.

**Preprocessing parameter model** (`app/schemas/preprocess.py`), shown in the same form:

| Field | Default | Meaning |
| --- | --- | --- |
| `bin_size_ms` | 20 | Width of one time bin |
| `align_event` | `stimOn_times` | Trial event the window is centred on (`stimOn_times`, `firstMovement_times`, `feedback_times`) |
| `window_pre_s` / `window_post_s` | 0.5 / 1.0 | Seconds before / after the event |
| `good_units_only` | true, locked in v0 | IBL cluster `label == 1` |

**Request flow for POST runs:** validate body against the mode's model → load current items and splits → reject if no items → build `inputs` snapshot → insert run with `status='queued'`, `progress.total = items × 2` → return 201. The request never trains anything.

## Pipeline and worker

Four backend jobs make the data flow work: catalog sync (manual command), split creation (inside the items request), and preprocessing + CEBRA training (inside the worker). The browser never waits on training; it polls run status.

&#91;embedded content: v0 architecture · 6 parts on one machine\]

FastAPI never trains; the worker never talks to the browser. FastAPI also reads IBL trial tables when it builds splits (not drawn).

**Extra dependencies:** `brainwidemap` is not on PyPI. Add it with `uv add "brainwidemap @ git+https://github.com/int-brain-lab/paper-brain-wide-map"`. `ibllib` brings `brainbox` and `iblatlas`. Connect to the public server with `ONE(base_url=ONE_BASE_URL, password='international', silent=True)`.

### 1. Catalog sync (`app/ibl/catalog_sync.py`)

1. `bwm_df = bwm_query(one)` gives every Brain Wide Map session and probe (eid, pid, subject, lab, date).
2. `unit_df = bwm_units(one)` gives the good units used in the BWM paper, with eid, pid and Beryl region.
3. Group units by (eid, Beryl region): count units, collect the distinct pids.
4. Upsert into `ibl_sessions` and `ibl_session_regions`. Leave `n_trials` null; it is filled when a split is made.
5. Flags: `--regions CA1,DG` and `--limit N` keep the first sync small. `IBL_FAKE=1` writes 10 fake sessions across 6 subjects and the regions CA1, DG, LP, VISp, MOs, PO.

Print the `unit_df` column names on first run and map them explicitly. Do not guess column names.

### 2. Splits (`app/pipeline/splits.py`)

- `load_valid_trials(eid) -> np.ndarray`: load `one.load_object(eid, 'trials')`. A trial is valid when `stimOn_times`, `firstMovement_times` and `feedback_times` are all non-NaN, so any align event works on any split.
- `make_split(valid_ids, seed, ratio=0.5) -> (a, b)`: `rng = np.random.default_rng(seed)`, permute, cut at `round(len * ratio)`, sort each half. Pure function, unit tested for determinism and no overlap.
- New seeds come from `secrets.randbits(31)`. Store the seed so any split can be rebuilt.
- Splits do not depend on the align event, so the split table has no align column.

### 3. Preprocessing (`app/pipeline/preprocess.py`)

One call per item × group produces a **time × neuron** spike-count matrix.

1. For each pid in the item: `SpikeSortingLoader(pid=pid, one=one, atlas=AllenAtlas())`, then `load_spike_sorting()` and `merge_clusters(...)`.
2. Keep clusters with `label == 1` (IBL good units) whose acronym maps to the item's region via `BrainRegions().acronym2acronym(acr, mapping='Beryl')`. Unit id = `(pid, cluster_id)` so probes merge cleanly.
3. For each trial in the group, take the window `[t − window_pre_s, t + window_post_s]` around `align_event`. Cut it into `bin_size_ms` bins and count spikes per unit per bin.
4. Stack trials in order: `X` shape `(n_trials × bins_per_trial, n_units)`, float32. Also save `trial_index` and `time_in_trial` per row.
5. Labels per row: wheel velocity (interpolate wheel position with `brainbox.behavior.wheel`, take the gradient, average per bin); signed contrast = contrastRight − contrastLeft with NaN as 0; choice and feedbackType as int64 codes.
6. Save `DATA_DIR/preprocess/<hash>/<A|B>.npz`. `hash` = SHA-256 of (eid, region, sorted pids, preprocess params, split id). Write to a `.tmp` folder, then rename. If the folder exists, reuse it.

Known limit: trials are concatenated, so CEBRA's time offsets can pair bins across a trial boundary. Fine for v0; note it in the README.

### 4. CEBRA training (`app/pipeline/cebra_train.py`)

1. Load the item's group npz. Fail the model with a clear message if rows < `batch_size`.
2. Build kwargs from the params plus the mode's hidden fields, `device='cuda_if_available'`, `verbose=False`.
3. `torch.manual_seed(seed)`, `np.random.seed(seed)`, then `model = cebra.CEBRA(**kwargs)`.
4. Fit: Time → `model.fit(X)`. Behaviour / Hybrid → `model.fit(X, y_cont)` or `model.fit(X, y_cont, y_disc)` (continuous labels as `(T, k)` float32).
5. `emb = model.transform(X)`. Save `embedding.npy`, `model.pt` (`model.save`) and `labels.npz` under `DATA_DIR/runs/<run_id>/<eid>_<region>_<group>/`.
6. Final loss from `model.state_dict_['loss'][-1]` (check this key against the installed CEBRA version).
7. Insert the `run_outputs` row and bump `progress.done`.

### 5. Worker loop (`app/worker.py`)

1. On start: mark any `running` runs as `failed` with error `worker restarted mid-run`. v0 assumes one worker.
2. Every 3 s: upsert a heartbeat row, then claim the oldest queued run in one statement:

```sql
update runs set status = 'running', started_at = now()
where id = (select id from runs where status = 'queued'
            order by created_at limit 1 for update skip locked)
returning *;
```

3. For each input item, for group A then B: preprocess (cached), train, record output.
4. Success → `succeeded` + `finished_at`. Any exception → `failed`, `error` = last 2000 characters of the traceback, and the run continues no further.
5. Log to `DATA_DIR/runs/<run_id>/run.log`. Ctrl-C marks the current run `failed` with `worker stopped`.
6. One run at a time. The heartbeat table, already in the schema above:

```sql
create table worker_heartbeats (
  worker_id  text primary key,
  last_seen  timestamptz not null default now()
);
```

## Frontend UI spec

Three routes inside one app shell. Reuse the prototype's look: shadcn zinc theme, white cards on a light grey page, Inter for text and JetBrains Mono for IDs, numbers and parameters. Build only what is described here, even where the prototype shows more.

**Visual tokens**

| Token | Value |
| --- | --- |
| Page background | zinc-50 `#fafafa` |
| Card | white, 1px zinc-200 border, radius 10px |
| Text / muted text | zinc-950 / zinc-500 |
| Running accent | blue-600 text on blue-50, blue-200 border |
| Failed | red-700 text on red-50, red-200 border |
| Body / mono | Inter 14px / JetBrains Mono 12px |
| Main column | padding 28px 40px, max-width 1080px |
| Section heading | 17px semibold with a numbered dark circle (1 Data, 2 CEBRA) |

### App shell (`app/layout.tsx`)

- Left sidebar, 220px: "448" square logo + "Research tracker", one nav link: Experiments.
- Sidebar footer: worker dot from `/api/health`. Green "Worker online" if the heartbeat is under 15 s old, grey "Worker offline" otherwise.
- Under 768px the sidebar becomes a top bar. Tables scroll sideways inside their card.
- Wrap the app in a TanStack `QueryClientProvider` and mount shadcn `Toaster` (sonner).

### Experiments list (`/experiments`)

- Header: "Experiments" + primary button "New experiment".
- "New experiment" opens a Dialog: Title (required, max 200), Description (textarea, optional). Submit → POST → go to the new experiment's page.
- List as rows in one card: title (semibold), description (one line, truncated), created date (`Nov 4, 2026`), "6 items · 3 runs". Whole row links to the experiment.
- Empty state: "No experiments yet" + the same button. Loading: 3 skeleton rows.

### Experiment page (`/experiments/[id]`)

```
Experiments / Control 01
Control 01: CA1 across sessions                         [Edit]
Positive control. Same region, three animals, three labs.
Created Nov 4, 2026 · 6 items in 3 sessions · 3 runs

(1) Data                                       [Edit selection]
  Group by: [Subject] [Session] [Region]
  ▾ KS023
     ▾ 2019-12-10 · cortexlab        Split A 301 · B 302  [↻]
         CA1  64 units    DG  41 units
  ▸ CSHL049  (1 session, 2 regions)

(2) CEBRA training                                  [New run]
  Run        Status        Mode   Out dim  LR    Temp ...
  time-01    Succeeded     Time   8        3e-4  1.0
  beh-01     Running 3/12  Beh.   8        3e-4  1.0
```

**Header.** Breadcrumb, title (26px semibold), description, meta line. "Edit" opens the same Dialog as create, prefilled, and PATCHes.

**Data section**

- Shows the selected items, grouped by a ToggleGroup: Subject (subject → session → regions), Session (session → regions), Region (region → sessions). Default: Subject.
- Group rows are shadcn Collapsible, open by default when there are under 20 groups. Each shows a count, e.g. "2 sessions, 3 regions".
- Region leaves are chips: acronym + good-unit count.
- Every session row shows its split as a badge "Split A 301 · B 302". Tooltip: seed and "trials split at random, seeded". An icon button (lucide `RefreshCw`, `aria-label="Reshuffle split"`) opens a confirm Dialog: "Make a new random split for this session? Runs already queued keep the old split." Confirm → POST reshuffle.
- Empty state: "No data selected yet" + "Select data" button.
- Grouping lives in `lib/group-items.ts` as a pure function `groupItems(items, by)` returning a tree. Unit test all three modes. The same function powers the editor below.

**Selection editor** (opened by "Edit selection")

- A right-side Sheet, 960px wide (full width on small screens).
- Left column, filters: Region (combobox fed by `/api/catalog/regions`, multi-select chips), Subject search, Lab select, Min good units (number, default 0).
- Right column: the same Group by toggle and a grouped tree of catalog items with checkboxes. A group's checkbox selects or clears all its children and shows the indeterminate state when partly selected.
- Already-selected items start checked. Leaf row: region chip, units, subject, date, lab.
- Footer, sticky: "8 items in 4 sessions selected", Cancel, Save. Save → PUT items, button shows a spinner (new sessions need their trials loaded to make splits), then the Sheet closes and the data section refetches.
- Catalog fetch is debounced 300 ms on filter change. Up to 2000 rows render fine because groups start collapsed and leaves render only when expanded.

**CEBRA section**

- Header button "New run" links to `/experiments/[id]/runs/new`. Disabled with a tooltip "Select data first" when there are no items.
- Table columns: Run name, Status, Mode, then one column per parameter in schema order (labels from schema `title`), then the preprocessing fields, then Created. Parameter cells use the mono font. Run name and Status columns stay sticky on horizontal scroll.
- Columns come from `/api/cebra/schema`, so a new parameter appears without frontend changes. A parameter a mode does not use shows “—”.
- Status badge: Queued (dashed grey outline), Running (blue, with "3/12" from `progress`), Succeeded (zinc with a check icon), Failed (red). Clicking a Failed badge opens a Dialog with the full error text in a mono block.
- Polling: `refetchInterval: 3000` while any run is queued or running, off otherwise.
- If runs are queued and the worker is offline, show a warning bar above the table: "The worker is not running, so queued runs will wait. Start it with `make worker`."
- Empty state: "No runs yet." Rows are not clickable in v0.

### New run page (`/experiments/[id]/runs/new`)

Two columns like the prototype: the form card (left, flexible) and a summary card (right, 280px; stacks below on small screens).

1. **Basics:** Run name, prefilled `time-01`, `beh-01` or `hyb-01` (next free number). A 409 from the server shows as a field error "Name already used in this experiment".
2. **Mode:** segmented ToggleGroup Time / Behaviour / Hybrid. Hint under it: Time → "Self-supervised. Uses time only, no behaviour labels." Behaviour → "Supervised by the behaviour labels you pick." Hybrid → "Learns from both time and behaviour labels."
3. **Behaviour labels** (Behaviour and Hybrid only): checkboxes for continuous labels, a Select for the one discrete label (None / choice / feedback).
4. **Model and training:** the shared parameters in a 2-column grid, rendered from the mode's JSON Schema.
5. **Preprocessing:** Collapsible, closed by default, with a summary line "20 ms bins · stimOn\_times −0.5 to +1.0 s · good units only". Inside: bin size, align event, window before and after. "Good units only" shows as a checked, disabled checkbox.
6. **Summary card:** "6 items in 3 sessions", "Trains 12 models (6 items × groups A and B)", "Runs on the backend machine", buttons "Queue run" (primary) and "Cancel".

Submit → POST. On 201: toast "Run queued", go back to the experiment page. On 422: map each error's `loc` to its field with react-hook-form `setError`.

**`SchemaField` renderer** (`components/cebra/SchemaField.tsx`): integer or number → number Input with min, max and step; string enum → Select; array of enum → checkbox group; nullable enum → Select with "None"; boolean → Checkbox. Label = `title`, hint = `description`, initial value = `default`. Unknown types throw in development so gaps show up early.

**Accessibility basics:** real `<button>`, `<a>` and labelled inputs; `aria-label` on icon-only buttons; status is never shown by colour alone (badge text always present).

## Milestones for the code agent

Build in this order, one commit (or PR) per milestone. Each milestone ends with its checks passing. Develop with `IBL_FAKE=1` until M7 so nothing waits on IBL downloads.

| # | Build | Done when |
| --- | --- | --- |
| M0 | Repo scaffold: folders, Makefile, `.env.example` files, README with setup steps, shadcn init, uv project | `make db`, `make api`, `make web` all start; the page shows the empty app shell |
| M1 | Migration + seed, SQLAlchemy models, `/api/health` | `make db-reset` succeeds; `/api/health` returns `db: true`; pytest checks the seed workspace exists |
| M2 | Fake catalog + catalog sync command, catalog endpoints | `make sync-catalog` with `IBL_FAKE=1` fills both catalog tables; `/api/catalog/items?region=CA1` returns only CA1 rows |
| M3 | Experiments API + list page + create/edit Dialog + experiment page header | Create, edit and view an experiment in the browser; the created date shows correctly |
| M4 | Items + splits API, data section, selection editor, reshuffle | Select items in all three group-by modes; save; each session shows a split; reshuffle changes the counts and keeps the old split row with `superseded_at` set; `groupItems` and `make_split` unit tests pass |
| M5 | CEBRA + preprocessing schemas, `/api/cebra/schema`, runs API, runs table, New run page | Switching modes changes the fields; a bad value shows a field error; queuing creates a `queued` row that appears in the table |
| M6 | Worker: claim, fake preprocessing, CEBRA training, outputs, failure handling | With `max_iterations=50`, a fake run goes queued → running (progress counts up) → succeeded, and `run_outputs` has 2 rows per item; a forced error shows Failed with its message; killing the worker mid-run marks it failed on restart |
| M7 | Real IBL path: catalog sync, trial loading, preprocessing from SpikeSortingLoader | Sync `--regions CA1 --limit 5`; select 2 sessions; one Time run with `max_iterations=500` succeeds and writes embeddings with shape `(rows, output_dimension)` |
| M8 | Polish: loading skeletons, empty states, error toasts, worker-offline banner, README run-through | A new person can follow the README from clone to a succeeded run |

**Tests the agent must write**

- Backend (pytest): `make_split` determinism and no overlap; binning on a hand-made spike train (known counts per bin); each mode's param model accepts defaults and rejects a Behaviour run with no labels; runs API returns 409 on a duplicate name; the worker claim never hands one run to two callers (two threads, one queued run).
- Frontend (vitest): `groupItems` for Subject, Session and Region; `SchemaField` renders each supported type.

**Rules for the agent**

- Do not add features from the "Not in v0" list, even if the prototype shows them.
- Regenerate `lib/api-types.ts` (`make types`) after any API model change, and commit it.
- Never train or preprocess inside a request handler. The only IBL call a request may make is loading a session's trials table to build its split.
- Keep the pipeline functions importable and runnable from a plain Python script, without FastAPI.

## Deferred work and open questions

The schema already leaves room for each deferred item, so none needs a rewrite. Open questions do not block M0 to M6.

**Next after v0** (from the technical proposal, in rough order)

- Run detail page: loss curve, embedding preview, logs.
- JGW stage: a second `runs.stage` value that takes a CEBRA run as input, and will compare group A against group B.
- Supabase Auth with an email allowlist and row-level security on `workspace_id`.
- Run-key caching across runs, W&B logging, cancel and rerun.
- Moving the worker to another machine (it already only needs `DATABASE_URL`), then UBC ARC.

**Open questions**

- [ ] Should a split ever be stratified (for example, balanced by choice or contrast), or is a plain random 50/50 enough?
- [ ] Are there sessions where the two halves end up too small for CEBRA (rows < batch size)? If so, should the run skip that item or fail?
- [ ] Which Brain Wide Map regions to sync first (all 138, or a starting set)?
- [ ] Local Supabase for all of v0, or a hosted Supabase project from the start?
- [ ] Disk budget for `DATA_DIR` and the ONE cache on the GPU machine.

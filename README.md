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

## Other commands

| Command | Does |
| --- | --- |
| `make db-stop` | Stop local Supabase |
| `make db-reset` | Drop and re-create the local database from `supabase/migrations` + `seed.sql` |
| `make types` | Regenerate `frontend/lib/api-types.ts` from the running API's OpenAPI schema |
| `make sync-catalog ARGS="--regions CA1,DG --limit 50"` | Fill the IBL catalog tables |
| `make test` | Backend `pytest` + frontend `vitest run` |
| `make lint` | `ruff` + `eslint` |

## Environment variables

| File | Variable | Meaning |
| --- | --- | --- |
| `backend/.env` | `DATABASE_URL` | `postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres` (local Supabase) |
| `backend/.env` | `DATA_DIR` | Preprocessing cache and run outputs (`~` is expanded) |
| `backend/.env` | `ONE_BASE_URL` | Public IBL server, `https://openalyx.internationalbrainlab.org` |
| `backend/.env` | `ONE_CACHE_DIR` | Where ONE stores downloaded IBL files |
| `backend/.env` | `IBL_FAKE` | `1` = synthetic IBL data instead of real downloads (dev and tests) |
| `backend/.env` | `CORS_ORIGINS` | Comma-separated allowed origins, e.g. `http://localhost:3000` |
| `frontend/.env.local` | `NEXT_PUBLIC_API_URL` | `http://localhost:8000` |

## Known limits (v0)

- Trials are concatenated before CEBRA training, so CEBRA's time offsets can pair bins across a
  trial boundary.

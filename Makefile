# Research Tracker dev commands. Paths are quoted because the repo path may contain spaces.

SUPABASE ?= npx --yes supabase@3.2.0
API_URL  ?= http://localhost:8000
ARGS     ?=

ROOT     := $(CURDIR)
BACKEND  := $(ROOT)/backend
FRONTEND := $(ROOT)/frontend

.PHONY: help install db db-stop db-reset api worker web types sync-catalog test test-backend test-frontend lint

help:
	@echo "make install       install backend (uv) and frontend (pnpm) dependencies"
	@echo "make db            start local Supabase (Postgres on 127.0.0.1:54322)"
	@echo "make db-stop       stop local Supabase"
	@echo "make db-reset      re-run migrations + seed on the local database"
	@echo "make api           FastAPI on :8000 with reload"
	@echo "make worker        run the CEBRA worker loop"
	@echo "make web           Next.js dev server on :3000"
	@echo "make types         regenerate frontend/lib/api-types.ts (API must be running)"
	@echo "make sync-catalog  fill the IBL catalog, e.g. ARGS=\"--regions CA1,DG --limit 50\""
	@echo "make test          backend pytest + frontend vitest"

install:
	cd "$(BACKEND)" && uv sync
	cd "$(FRONTEND)" && pnpm install

db:
	cd "$(ROOT)" && $(SUPABASE) start

db-stop:
	cd "$(ROOT)" && $(SUPABASE) stop

db-reset:
	cd "$(ROOT)" && $(SUPABASE) db reset

api:
	cd "$(BACKEND)" && uv run uvicorn app.main:app --reload --port 8000

worker:
	cd "$(BACKEND)" && uv run python -m app.worker

web:
	cd "$(FRONTEND)" && pnpm dev

types:
	cd "$(FRONTEND)" && pnpm openapi-typescript $(API_URL)/openapi.json -o lib/api-types.ts

sync-catalog:
	cd "$(BACKEND)" && uv run python -m app.ibl.catalog_sync $(ARGS)

test: test-backend test-frontend

test-backend:
	cd "$(BACKEND)" && uv run pytest

test-frontend:
	cd "$(FRONTEND)" && pnpm exec vitest run

lint:
	cd "$(BACKEND)" && uv run ruff check .
	cd "$(FRONTEND)" && pnpm lint

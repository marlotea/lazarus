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

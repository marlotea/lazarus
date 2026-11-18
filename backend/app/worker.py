"""CEBRA worker: polls Postgres for queued runs and trains them, one run at a time.

    cd backend && uv run python -m app.worker      # or: make worker

On start, runs left `running` by a previous worker are marked failed ("worker restarted
mid-run"; v0 assumes one worker). A background thread upserts a heartbeat every 3 s (also
while training, so the UI keeps showing "Worker online"); the main loop claims the oldest
queued run every 3 s. For each input item, group A then B: preprocess (cached), train,
record a `run_outputs` row and bump `progress.done`. Any exception fails the run with the
last 2000 characters of the traceback. Ctrl-C / SIGTERM fails the current run with
"worker stopped". Each run logs to `DATA_DIR/runs/<run_id>/run.log`.
"""

from __future__ import annotations

import logging
import os
import signal
import socket
import threading
import time
import traceback
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from sqlalchemy import delete, func, select, text, update
from sqlalchemy.dialects.postgresql import insert

from app.db import SessionLocal
from app.models import IblSessionRegion, Run, RunOutput, TrialSplit, WorkerHeartbeat
from app.pipeline.cebra_train import TrainResult, train_group
from app.pipeline.preprocess import GROUPS, preprocess_item
from app.schemas.cebra import PARAMS_BY_MODE
from app.schemas.preprocess import PreprocessParams
from app.settings import get_settings

log = logging.getLogger("app.worker")

POLL_S = 3.0
ERROR_CHARS = 2000
RESTARTED = "worker restarted mid-run"
STOPPED = "worker stopped"

# Claim the oldest queued run. SKIP LOCKED means two workers never get the same run.
CLAIM_SQL = text(
    """
update runs set status = 'running', started_at = now()
where id = (select id from runs where status = 'queued'
            order by created_at limit 1 for update skip locked)
returning *;
"""
)


def make_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


# --- database steps ---------------------------------------------------------------------


def fail_interrupted_runs() -> list[uuid.UUID]:
    """Mark every `running` run failed: its worker died without finishing it."""
    with SessionLocal() as db:
        ids = db.scalars(
            update(Run)
            .where(Run.status == "running")
            .values(status="failed", error=RESTARTED, finished_at=func.now())
            .returning(Run.id)
        ).all()
        db.commit()
    return list(ids)


def heartbeat(worker_id: str) -> None:
    stmt = insert(WorkerHeartbeat).values(worker_id=worker_id, last_seen=func.now())
    stmt = stmt.on_conflict_do_update(
        index_elements=[WorkerHeartbeat.worker_id], set_={"last_seen": func.now()}
    )
    with SessionLocal() as db:
        db.execute(stmt)
        db.commit()


def remove_heartbeat(worker_id: str) -> None:
    with SessionLocal() as db:
        db.execute(delete(WorkerHeartbeat).where(WorkerHeartbeat.worker_id == worker_id))
        db.commit()


def claim_run() -> dict[str, Any] | None:
    """Atomically move the oldest queued run to `running` and return its row."""
    with SessionLocal() as db:
        row = db.execute(CLAIM_SQL).mappings().first()
        db.commit()
    return dict(row) if row is not None else None


def _set_run(run_id: uuid.UUID, **values: Any) -> None:
    with SessionLocal() as db:
        db.execute(update(Run).where(Run.id == run_id).values(**values))
        db.commit()


def finish_run(run_id: uuid.UUID, status: str, error: str | None = None) -> None:
    """Final status. Only a run still `running` changes, so this is safe to call twice."""
    with SessionLocal() as db:
        db.execute(
            update(Run)
            .where(Run.id == run_id, Run.status == "running")
            .values(status=status, error=error, finished_at=func.now())
        )
        db.commit()


def record_output(
    run_id: uuid.UUID,
    eid: uuid.UUID,
    region: str,
    group: str,
    result: TrainResult,
    done: int,
    total: int,
) -> None:
    """Insert the `run_outputs` row and bump `progress.done` in one transaction."""
    with SessionLocal() as db:
        db.add(
            RunOutput(
                run_id=run_id,
                eid=eid,
                region=region,
                split_group=group,
                n_units=result.n_units,
                n_samples=result.n_samples,
                final_loss=result.final_loss,
                embedding_path=str(result.embedding_path),
                model_path=str(result.model_path),
            )
        )
        db.execute(
            update(Run).where(Run.id == run_id).values(progress={"done": done, "total": total})
        )
        db.commit()


def _load_item(eid: uuid.UUID, region: str, split_id: uuid.UUID) -> tuple[list[str], TrialSplit]:
    with SessionLocal() as db:
        pids = db.scalar(
            select(IblSessionRegion.pids).where(
                IblSessionRegion.eid == eid, IblSessionRegion.region == region
            )
        )
        split = db.get(TrialSplit, split_id)
    if pids is None:
        raise RuntimeError(f"Item {eid} {region} is not in the catalog")
    if split is None:
        raise RuntimeError(f"Split {split_id} of session {eid} not found")
    return [str(p) for p in pids], split


# --- one run ----------------------------------------------------------------------------


def _train_all(run: Mapping[str, Any], data_dir: Path, out_dir: Path) -> None:
    run_id = run["id"]
    mode = run["mode"]
    params = PARAMS_BY_MODE[mode].model_validate(run["params"])
    preprocess = PreprocessParams.model_validate(run["preprocess"])
    inputs = run["inputs"]
    total = len(inputs) * len(GROUPS)
    done = 0
    log.info(
        "run %s (%s, mode %s): %d items, %d models", run_id, run["name"], mode, len(inputs), total
    )
    for n, item in enumerate(inputs, start=1):
        eid, region = uuid.UUID(item["eid"]), item["region"]
        split_id = uuid.UUID(item["split_id"])
        pids, split = _load_item(eid, region, split_id)
        log.info("item %d/%d: %s %s, split %s", n, len(inputs), eid, region, split_id)
        folder = preprocess_item(
            eid, region, pids, split_id, split.group_a, split.group_b, preprocess, data_dir
        )
        for group in GROUPS:
            result = train_group(
                folder / f"{group}.npz",
                mode,
                params,
                out_dir / f"{eid}_{region}_{group}",
                label=f"{eid} {region} group {group}",
            )
            done += 1
            record_output(run_id, eid, region, group, result, done, total)
            log.info("progress %d/%d", done, total)


def execute_run(run: Mapping[str, Any], data_dir: Path | None = None) -> str:
    """Train every model of a claimed run and set its final status; returns that status.
    KeyboardInterrupt fails the run with "worker stopped" and is re-raised."""
    data_dir = data_dir or get_settings().data_dir
    run_id = run["id"]
    out_dir = data_dir / "runs" / str(run_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    _set_run(run_id, output_dir=str(out_dir))

    handler = logging.FileHandler(out_dir / "run.log")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    handler.setLevel(logging.INFO)
    app_logger = logging.getLogger("app")
    if app_logger.getEffectiveLevel() > logging.INFO:  # e.g. imported from a script
        app_logger.setLevel(logging.INFO)
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        _train_all(run, data_dir, out_dir)
    except KeyboardInterrupt:
        log.warning("run %s: %s", run_id, STOPPED)
        finish_run(run_id, "failed", STOPPED)
        raise
    except Exception:
        tb = traceback.format_exc()
        log.error("run %s failed:\n%s", run_id, tb)
        finish_run(run_id, "failed", tb[-ERROR_CHARS:])
        return "failed"
    else:
        finish_run(run_id, "succeeded")
        log.info("run %s succeeded", run_id)
        return "succeeded"
    finally:
        root.removeHandler(handler)
        handler.close()


def process_next_run(data_dir: Path | None = None) -> uuid.UUID | None:
    """Claim and execute one queued run; None if nothing was queued."""
    run = claim_run()
    if run is None:
        return None
    execute_run(run, data_dir)
    return run["id"]


# --- loop -------------------------------------------------------------------------------


class HeartbeatThread(threading.Thread):
    """Upserts the heartbeat every POLL_S seconds until stopped."""

    def __init__(self, worker_id: str) -> None:
        super().__init__(name="heartbeat", daemon=True)
        self.worker_id = worker_id
        self.stopped = threading.Event()

    def run(self) -> None:
        while True:
            try:
                heartbeat(self.worker_id)
            except Exception as exc:  # DB hiccup: keep beating
                log.warning("heartbeat failed: %s", exc)
            if self.stopped.wait(POLL_S):
                return


def _raise_interrupt(signum: int, frame: object) -> None:
    """Ctrl-C / SIGTERM: stop once. Later signals are ignored so they cannot cut the cleanup
    short (`make worker` stopped with a signal to its process group delivers it twice: once
    directly and once forwarded by `uv run`), which would leave the run or heartbeat behind."""
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    raise KeyboardInterrupt


def main() -> None:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    signal.signal(signal.SIGINT, _raise_interrupt)
    signal.signal(signal.SIGTERM, _raise_interrupt)  # SIGTERM behaves like Ctrl-C
    settings = get_settings()
    worker_id = make_worker_id()
    log.info(
        "worker %s starting (IBL_FAKE=%s, DATA_DIR=%s)",
        worker_id,
        settings.ibl_fake,
        settings.data_dir,
    )
    for run_id in fail_interrupted_runs():
        log.warning("run %s was left running: marked failed (%s)", run_id, RESTARTED)

    beat = HeartbeatThread(worker_id)
    beat.start()
    current: uuid.UUID | None = None
    try:
        while True:
            run = claim_run()
            if run is None:
                time.sleep(POLL_S)
                continue
            current = run["id"]
            execute_run(run)
            current = None
    except KeyboardInterrupt:
        log.info("worker stopping")
        if current is not None:  # interrupted between claim and execute_run's handler
            finish_run(current, "failed", STOPPED)
    finally:
        beat.stopped.set()
        beat.join(timeout=5)
        try:
            remove_heartbeat(worker_id)
        except Exception as exc:
            log.warning("could not remove heartbeat: %s", exc)


if __name__ == "__main__":
    main()

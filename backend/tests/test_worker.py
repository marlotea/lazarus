"""Worker: claim, a whole fake run, failure handling. Needs the local database and
IBL_FAKE=1; do not run `make worker` at the same time (it would claim the test runs).
Outputs go to pytest's tmp_path, not DATA_DIR."""

import threading
import uuid
from collections.abc import Iterator

import numpy as np
import pytest
from sqlalchemy import delete, func, select, update

from app import worker
from app.db import SessionLocal
from app.ibl.fake import fake_sessions
from app.models import Experiment, Run, RunOutput
from app.settings import get_settings

pytestmark = [
    pytest.mark.usefixtures("fake_catalog", "no_foreign_runs"),
    pytest.mark.skipif(not get_settings().ibl_fake, reason="needs IBL_FAKE=1"),
]

S = fake_sessions()[2]  # FAKE02: CA1 37, DG 29, PO 18 units
FAST = {"model_architecture": "offset5-model", "batch_size": 64, "max_iterations": 100}


@pytest.fixture
def no_foreign_runs():
    """The worker claims any queued run, so refuse to run next to someone else's."""
    with SessionLocal() as db:
        busy = db.scalar(select(func.count()).where(Run.status.in_(["queued", "running"])))
    if busy:
        pytest.skip("the database has queued or running runs; the worker tests would claim them")


@pytest.fixture
def exp_id(client) -> Iterator[str]:
    res = client.post("/api/experiments", json={"title": "Worker test"})
    assert res.status_code == 201
    exp = res.json()["id"]
    items = [{"eid": str(S.eid), "region": r} for r in ("PO", "DG")]
    assert client.put(f"/api/experiments/{exp}/items", json={"items": items}).status_code == 200
    yield exp
    with SessionLocal() as db:
        db.execute(delete(Experiment).where(Experiment.id == uuid.UUID(exp)))
        db.commit()


def queue(client, exp_id, name="time-01", mode="time", params=None, preprocess=None) -> str:
    body = {"name": name, "mode": mode, "params": params or {}, "preprocess": preprocess or {}}
    res = client.post(f"/api/experiments/{exp_id}/runs", json=body)
    assert res.status_code == 201, res.text
    return res.json()["id"]


def get_run(run_id: str) -> Run:
    with SessionLocal() as db:
        run = db.get(Run, uuid.UUID(run_id))
        assert run is not None
        return run


def test_claim_never_hands_one_run_to_two_callers(client, exp_id):
    run_id = queue(client, exp_id)
    barrier = threading.Barrier(2)
    claimed: list[dict | None] = []
    lock = threading.Lock()

    def claim():
        barrier.wait()
        row = worker.claim_run()
        with lock:
            claimed.append(row)

    threads = [threading.Thread(target=claim) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    rows = [r for r in claimed if r is not None]
    assert len(claimed) == 2 and len(rows) == 1
    assert str(rows[0]["id"]) == run_id and rows[0]["status"] == "running"
    run = get_run(run_id)
    assert run.status == "running" and run.started_at is not None
    assert worker.claim_run() is None  # nothing left to claim


def test_fake_run_succeeds(client, exp_id, tmp_path):
    params = FAST | {"output_dimension": 3, "discrete_label": "choice"}
    run_id = queue(client, exp_id, "beh-01", "behaviour", params, {"bin_size_ms": 50})
    assert worker.process_next_run(tmp_path) == uuid.UUID(run_id)

    run = get_run(run_id)
    assert run.status == "succeeded", run.error
    assert run.progress == {"done": 4, "total": 4}
    assert run.finished_at is not None and run.error is None
    out_dir = tmp_path / "runs" / run_id
    assert run.output_dir == str(out_dir)
    log = (out_dir / "run.log").read_text()
    assert "succeeded" in log and "progress 4/4" in log

    with SessionLocal() as db:
        outputs = db.scalars(select(RunOutput).where(RunOutput.run_id == run.id)).all()
    assert sorted((o.region, o.split_group) for o in outputs) == [
        ("DG", "A"),
        ("DG", "B"),
        ("PO", "A"),
        ("PO", "B"),
    ]
    for o in outputs:
        assert o.n_units == S.regions[o.region]
        assert o.final_loss is not None and np.isfinite(o.final_loss)
        emb = np.load(o.embedding_path)
        assert emb.shape == (o.n_samples, 3)
        folder = out_dir / f"{S.eid}_{o.region}_{o.split_group}"
        assert o.model_path == str(folder / "model.pt") and (folder / "model.pt").is_file()
        labels = np.load(folder / "labels.npz")
        assert labels["continuous"].shape == (o.n_samples, 1)
        assert set(np.unique(labels["discrete"])) <= {0, 1}

    # The preprocessing folder is reused by a second run with the same item, split, params.
    cached = sorted(p.name for p in (tmp_path / "preprocess").iterdir())
    assert len(cached) == 2  # one per item
    run2 = queue(client, exp_id, "time-01", "time", FAST, {"bin_size_ms": 50})
    worker.process_next_run(tmp_path)
    assert get_run(run2).status == "succeeded"
    assert sorted(p.name for p in (tmp_path / "preprocess").iterdir()) == cached


def test_too_few_rows_fails_with_message(client, exp_id, tmp_path):
    # 1 s bins over a 1.5 s window: one row per trial, ~340 rows per group < 4096.
    run_id = queue(
        client, exp_id, params=FAST | {"batch_size": 4096}, preprocess={"bin_size_ms": 1000}
    )
    worker.process_next_run(tmp_path)
    run = get_run(run_id)
    assert run.status == "failed" and run.finished_at is not None
    assert "fewer than batch_size 4096" in run.error
    assert "Traceback" in run.error and len(run.error) <= worker.ERROR_CHARS
    assert run.progress["done"] == 0


def test_running_runs_fail_on_restart(client, exp_id):
    run_id = queue(client, exp_id)
    with SessionLocal() as db:
        db.execute(update(Run).where(Run.id == uuid.UUID(run_id)).values(status="running"))
        db.commit()
    assert uuid.UUID(run_id) in worker.fail_interrupted_runs()
    run = get_run(run_id)
    assert (run.status, run.error) == ("failed", worker.RESTARTED)


def test_heartbeat_upserts():
    wid = f"test-{uuid.uuid4()}"
    try:
        worker.heartbeat(wid)
        worker.heartbeat(wid)
        with SessionLocal() as db:
            n = db.scalar(
                select(func.count())
                .select_from(worker.WorkerHeartbeat)
                .where(worker.WorkerHeartbeat.worker_id == wid)
            )
        assert n == 1
    finally:
        worker.remove_heartbeat(wid)


def test_stop_signal_interrupts_once_then_is_ignored():
    """A second SIGTERM/SIGINT during shutdown must not interrupt the cleanup."""
    import signal

    saved = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
    try:
        with pytest.raises(KeyboardInterrupt):
            worker._raise_interrupt(signal.SIGTERM, None)
        assert signal.getsignal(signal.SIGTERM) == signal.SIG_IGN
        assert signal.getsignal(signal.SIGINT) == signal.SIG_IGN
    finally:
        for s, handler in saved.items():
            signal.signal(s, handler)

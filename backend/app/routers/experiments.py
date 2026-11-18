"""Experiments: list, create, read and edit title/description; the item selection and the
per-session trial splits."""

import uuid
from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Select, and_, delete, distinct, exists, func, select, tuple_, update
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_workspace_id
from app.models import (
    Experiment,
    ExperimentItem,
    IblSession,
    IblSessionRegion,
    Run,
    TrialSplit,
)
from app.pipeline.splits import load_session_trials, make_split, new_seed
from app.schemas.experiments import Experiment as ExperimentOut
from app.schemas.experiments import ExperimentCreate, ExperimentUpdate
from app.schemas.items import ExperimentItem as ItemOut
from app.schemas.items import ItemsReplace, Split

router = APIRouter(prefix="/api/experiments", tags=["experiments"])

DbDep = Annotated[Session, Depends(get_db)]
WorkspaceDep = Annotated[uuid.UUID, Depends(get_workspace_id)]


def _with_counts(workspace_id: uuid.UUID) -> Select:
    items = (
        select(
            ExperimentItem.experiment_id,
            func.count().label("item_count"),
            func.count(distinct(ExperimentItem.eid)).label("session_count"),
        )
        .group_by(ExperimentItem.experiment_id)
        .subquery()
    )
    runs = (
        select(Run.experiment_id, func.count().label("run_count"))
        .group_by(Run.experiment_id)
        .subquery()
    )
    return (
        select(
            Experiment,
            func.coalesce(items.c.item_count, 0),
            func.coalesce(items.c.session_count, 0),
            func.coalesce(runs.c.run_count, 0),
        )
        .outerjoin(items, items.c.experiment_id == Experiment.id)
        .outerjoin(runs, runs.c.experiment_id == Experiment.id)
        .where(Experiment.workspace_id == workspace_id)
    )


def _out(exp: Experiment, item_count: int, session_count: int, run_count: int) -> ExperimentOut:
    return ExperimentOut(
        id=exp.id,
        title=exp.title,
        description=exp.description,
        created_at=exp.created_at,
        updated_at=exp.updated_at,
        item_count=item_count,
        session_count=session_count,
        run_count=run_count,
    )


def _get_one(db: Session, workspace_id: uuid.UUID, experiment_id: uuid.UUID) -> ExperimentOut:
    row = db.execute(_with_counts(workspace_id).where(Experiment.id == experiment_id)).first()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Experiment not found")
    return _out(*row)


@router.get("", response_model=list[ExperimentOut])
def list_experiments(db: DbDep, workspace_id: WorkspaceDep) -> list[ExperimentOut]:
    """All experiments, newest first, with item and run counts."""
    stmt = _with_counts(workspace_id).order_by(Experiment.created_at.desc(), Experiment.id)
    return [_out(*row) for row in db.execute(stmt)]


@router.post("", response_model=ExperimentOut, status_code=status.HTTP_201_CREATED)
def create_experiment(
    body: ExperimentCreate, db: DbDep, workspace_id: WorkspaceDep
) -> ExperimentOut:
    exp = Experiment(workspace_id=workspace_id, title=body.title, description=body.description)
    db.add(exp)
    db.commit()
    return _get_one(db, workspace_id, exp.id)


@router.get("/{experiment_id}", response_model=ExperimentOut)
def get_experiment(
    experiment_id: uuid.UUID, db: DbDep, workspace_id: WorkspaceDep
) -> ExperimentOut:
    return _get_one(db, workspace_id, experiment_id)


@router.patch("/{experiment_id}", response_model=ExperimentOut)
def update_experiment(
    experiment_id: uuid.UUID, body: ExperimentUpdate, db: DbDep, workspace_id: WorkspaceDep
) -> ExperimentOut:
    """Edit title and/or description. Sets updated_at (the migration has no trigger)."""
    exp = db.scalar(
        select(Experiment).where(
            Experiment.id == experiment_id, Experiment.workspace_id == workspace_id
        )
    )
    if exp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Experiment not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(exp, field, value)
    exp.updated_at = func.now()
    db.commit()
    return _get_one(db, workspace_id, exp.id)


# --- Item selection and splits -------------------------------------------------------------


def _require_experiment(
    db: Session, workspace_id: uuid.UUID, experiment_id: uuid.UUID, *, lock: bool = False
) -> Experiment:
    """The experiment row (404 if missing). `lock=True` takes a row lock, which serialises
    concurrent selection edits and reshuffles of the same experiment."""
    stmt = select(Experiment).where(
        Experiment.id == experiment_id, Experiment.workspace_id == workspace_id
    )
    exp = db.scalar(stmt.with_for_update() if lock else stmt)
    if exp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Experiment not found")
    return exp


def _current_split(experiment_id: uuid.UUID):
    return and_(TrialSplit.experiment_id == experiment_id, TrialSplit.superseded_at.is_(None))


@dataclass(frozen=True)
class _NewSplit:
    seed: int
    n_trials: int
    group_a: list[int]
    group_b: list[int]


def _build_split(eid: uuid.UUID, avoid_seed: int | None = None) -> _NewSplit:
    """Load the session's trials (the one IBL call a request may make) and split them."""
    try:
        trials = load_session_trials(eid)
    except Exception as exc:  # network, missing dataset, unknown fake eid
        raise HTTPException(
            status.HTTP_502_BAD_GATEWAY, f"Could not load the trials of session {eid}: {exc}"
        ) from exc
    seed = new_seed()
    while seed == avoid_seed:
        seed = new_seed()
    a, b = make_split(trials.valid_ids, seed)
    return _NewSplit(seed, trials.n_trials, a.tolist(), b.tolist())


def _add_split(db: Session, experiment_id: uuid.UUID, eid: uuid.UUID, new: _NewSplit) -> TrialSplit:
    split = TrialSplit(
        experiment_id=experiment_id,
        eid=eid,
        seed=new.seed,
        ratio=0.5,
        group_a=new.group_a,
        group_b=new.group_b,
    )
    db.add(split)
    db.execute(update(IblSession).where(IblSession.eid == eid).values(n_trials=new.n_trials))
    return split


def _list_items(db: Session, experiment_id: uuid.UUID) -> list[ItemOut]:
    stmt = (
        select(
            ExperimentItem.eid,
            ExperimentItem.region,
            IblSession.subject,
            IblSession.lab,
            IblSession.session_date,
            IblSessionRegion.n_good_units,
            TrialSplit.id.label("split_id"),
            TrialSplit.seed,
            func.cardinality(TrialSplit.group_a).label("n_a"),
            func.cardinality(TrialSplit.group_b).label("n_b"),
        )
        .join(
            IblSessionRegion,
            and_(
                IblSessionRegion.eid == ExperimentItem.eid,
                IblSessionRegion.region == ExperimentItem.region,
            ),
        )
        .join(IblSession, IblSession.eid == ExperimentItem.eid)
        .outerjoin(
            TrialSplit,
            and_(_current_split(experiment_id), TrialSplit.eid == ExperimentItem.eid),
        )
        .where(ExperimentItem.experiment_id == experiment_id)
        .order_by(
            IblSession.subject, IblSession.session_date, ExperimentItem.eid, ExperimentItem.region
        )
    )
    return [
        ItemOut(
            eid=r.eid,
            region=r.region,
            subject=r.subject,
            lab=r.lab,
            session_date=r.session_date,
            n_good_units=r.n_good_units,
            split=None
            if r.split_id is None
            else Split(id=r.split_id, seed=r.seed, n_a=r.n_a, n_b=r.n_b),
        )
        for r in db.execute(stmt)
    ]


@router.get("/{experiment_id}/items", response_model=list[ItemOut])
def list_items(experiment_id: uuid.UUID, db: DbDep, workspace_id: WorkspaceDep) -> list[ItemOut]:
    """Selected items joined with catalog info and the current split of their session,
    ordered by subject, session date, session and region."""
    _require_experiment(db, workspace_id, experiment_id)
    return _list_items(db, experiment_id)


@router.put("/{experiment_id}/items", response_model=list[ItemOut])
def replace_items(
    experiment_id: uuid.UUID, body: ItemsReplace, db: DbDep, workspace_id: WorkspaceDep
) -> list[ItemOut]:
    """Replace the whole selection. Every session in the new selection that has no current
    split gets one (its trials table is loaded to find the valid trials). A session that is
    removed and added back keeps its earlier split."""
    _require_experiment(db, workspace_id, experiment_id)
    wanted = list(dict.fromkeys((i.eid, i.region) for i in body.items))

    if wanted:
        rows = db.execute(
            select(IblSessionRegion.eid, IblSessionRegion.region).where(
                tuple_(IblSessionRegion.eid, IblSessionRegion.region).in_(wanted)
            )
        )
        known = {(e, r) for e, r in rows}
        unknown = [{"eid": str(e), "region": r} for e, r in wanted if (e, r) not in known]
        if unknown:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                {"message": "Items not in the catalog", "items": unknown},
            )

    eids = sorted({e for e, _ in wanted})
    with_split = set(
        db.scalars(
            select(TrialSplit.eid).where(_current_split(experiment_id), TrialSplit.eid.in_(eids))
        )
    )
    db.rollback()  # end the read transaction before the (possibly slow) trial loading
    built = {eid: _build_split(eid) for eid in eids if eid not in with_split}

    exp = _require_experiment(db, workspace_id, experiment_id, lock=True)
    rows = db.execute(
        select(ExperimentItem.eid, ExperimentItem.region).where(
            ExperimentItem.experiment_id == experiment_id
        )
    )
    current = {(e, r) for e, r in rows}
    wanted_set = set(wanted)
    removed = [k for k in current if k not in wanted_set]
    if removed:
        db.execute(
            delete(ExperimentItem).where(
                ExperimentItem.experiment_id == experiment_id,
                tuple_(ExperimentItem.eid, ExperimentItem.region).in_(removed),
            )
        )
    db.add_all(
        ExperimentItem(experiment_id=experiment_id, eid=e, region=r)
        for e, r in wanted
        if (e, r) not in current
    )
    # Re-check under the lock: a concurrent request may have made a split meanwhile.
    with_split = set(
        db.scalars(
            select(TrialSplit.eid).where(_current_split(experiment_id), TrialSplit.eid.in_(eids))
        )
    )
    for eid, new in built.items():
        if eid not in with_split:
            _add_split(db, experiment_id, eid, new)
    exp.updated_at = func.now()
    db.commit()
    return _list_items(db, experiment_id)


@router.post(
    "/{experiment_id}/splits/{eid}/reshuffle",
    response_model=Split,
    status_code=status.HTTP_201_CREATED,
)
def reshuffle_split(
    experiment_id: uuid.UUID, eid: uuid.UUID, db: DbDep, workspace_id: WorkspaceDep
) -> Split:
    """Make a new split with a new seed for one session. The old split row stays, with
    `superseded_at` set, so runs that used it keep pointing at it."""
    _require_experiment(db, workspace_id, experiment_id)
    in_selection = db.scalar(
        select(
            exists().where(ExperimentItem.experiment_id == experiment_id, ExperimentItem.eid == eid)
        )
    )
    if not in_selection:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "Session is not in this experiment's selection"
        )
    old_seed = db.scalar(
        select(TrialSplit.seed).where(_current_split(experiment_id), TrialSplit.eid == eid)
    )
    db.rollback()
    new = _build_split(eid, avoid_seed=old_seed)

    _require_experiment(db, workspace_id, experiment_id, lock=True)
    # Supersede first, as its own statement, so the partial unique index
    # (one current split per session) holds when the new row is inserted.
    db.execute(
        update(TrialSplit)
        .where(_current_split(experiment_id), TrialSplit.eid == eid)
        .values(superseded_at=func.now())
    )
    split = _add_split(db, experiment_id, eid, new)
    db.flush()
    out = Split(id=split.id, seed=split.seed, n_a=len(new.group_a), n_b=len(new.group_b))
    db.commit()
    return out

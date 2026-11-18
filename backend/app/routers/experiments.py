"""Experiments: list, create, read and edit title/description."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import Select, distinct, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_workspace_id
from app.models import Experiment, ExperimentItem, Run
from app.schemas.experiments import Experiment as ExperimentOut
from app.schemas.experiments import ExperimentCreate, ExperimentUpdate

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

"""CEBRA runs: the parameter schema that drives the form, and listing / queueing runs.

Queueing only inserts a `queued` row with a snapshot of its inputs; the worker
(`app.worker`) does the preprocessing and training. A request never trains anything.
"""

import uuid
from typing import Annotated, Any, TypeVar

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, ValidationError
from sqlalchemy import and_, exists, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_workspace_id
from app.models import ExperimentItem, IblSession, TrialSplit
from app.models import Run as RunRow
from app.routers.experiments import _current_split, _require_experiment
from app.schemas.cebra import PARAMS_BY_MODE, CebraModeSchemas, CebraSchema
from app.schemas.preprocess import PreprocessParams
from app.schemas.runs import Run, RunCreate

router = APIRouter(tags=["runs"])

DbDep = Annotated[Session, Depends(get_db)]
WorkspaceDep = Annotated[uuid.UUID, Depends(get_workspace_id)]

DUPLICATE_NAME = "Name already used in this experiment"

M = TypeVar("M", bound=BaseModel)

_ERROR_RESPONSE = {
    "description": "`detail` is a list of `{type, loc, msg}`, like a validation error",
}


@router.get("/api/cebra/schema", response_model=CebraSchema, tags=["cebra"])
def cebra_schema() -> CebraSchema:
    """JSON Schema of each mode's CEBRA params and of the preprocessing params, built from
    the Pydantic models. The mode's hidden CEBRA arguments are not part of it."""
    return CebraSchema(
        modes=CebraModeSchemas(
            **{mode: model.model_json_schema() for mode, model in PARAMS_BY_MODE.items()}
        ),
        preprocess=PreprocessParams.model_json_schema(),
    )


def _json_safe(ctx: dict[str, Any]) -> dict[str, Any]:
    return {
        k: v if isinstance(v, str | int | float | bool | None) else str(v) for k, v in ctx.items()
    }


def _validate(
    model: type[M], data: dict[str, Any], section: str
) -> tuple[M | None, list[dict[str, Any]]]:
    """Validate one part of the body. Errors get `loc = ["body", section, *field_loc]`; a
    model-level error that names a field in `ctx.field` is attached to that field."""
    try:
        return model.model_validate(data), []
    except ValidationError as exc:
        errors = []
        for err in exc.errors(include_url=False):
            loc = tuple(err["loc"])
            ctx = err.get("ctx") or {}
            if not loc and isinstance(ctx.get("field"), str):
                loc = (ctx["field"],)
            out = {"type": err["type"], "loc": ["body", section, *loc], "msg": err["msg"]}
            out["input"] = err.get("input")
            if ctx:
                out["ctx"] = _json_safe(ctx)
            errors.append(out)
        return None, errors


def _body_error(status_code: int, type_: str, loc: list[str], msg: str) -> HTTPException:
    return HTTPException(status_code, [{"type": type_, "loc": loc, "msg": msg}])


@router.get("/api/experiments/{experiment_id}/runs", response_model=list[Run])
def list_runs(experiment_id: uuid.UUID, db: DbDep, workspace_id: WorkspaceDep) -> list[Run]:
    """The experiment's runs, newest first."""
    _require_experiment(db, workspace_id, experiment_id)
    rows = db.scalars(
        select(RunRow)
        .where(RunRow.experiment_id == experiment_id)
        .order_by(RunRow.created_at.desc(), RunRow.id)
    )
    return [Run.model_validate(r, from_attributes=True) for r in rows]


@router.post(
    "/api/experiments/{experiment_id}/runs",
    response_model=Run,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_409_CONFLICT: _ERROR_RESPONSE | {"description": DUPLICATE_NAME},
    },
)
def create_run(
    experiment_id: uuid.UUID, body: RunCreate, db: DbDep, workspace_id: WorkspaceDep
) -> Run:
    """Queue a CEBRA run on the experiment's current items.

    Validates `params` against the mode's model and `preprocess` (422), rejects a name
    already used in the experiment (409) and an empty selection (422), snapshots each item
    with its session's current split into `inputs`, and inserts the run as `queued` with
    `progress.total = items x 2`."""
    # Lock the experiment so the selection cannot change while the snapshot is taken.
    _require_experiment(db, workspace_id, experiment_id, lock=True)

    params, param_errors = _validate(PARAMS_BY_MODE[body.mode], body.params, "params")
    preprocess, pre_errors = _validate(PreprocessParams, body.preprocess, "preprocess")
    if param_errors or pre_errors:
        raise RequestValidationError(param_errors + pre_errors)
    assert params is not None and preprocess is not None

    taken = db.scalar(
        select(exists().where(RunRow.experiment_id == experiment_id, RunRow.name == body.name))
    )
    if taken:
        raise _body_error(
            status.HTTP_409_CONFLICT, "duplicate_name", ["body", "name"], DUPLICATE_NAME
        )

    items = db.execute(
        select(ExperimentItem.eid, ExperimentItem.region, TrialSplit.id.label("split_id"))
        .join(IblSession, IblSession.eid == ExperimentItem.eid)
        .outerjoin(
            TrialSplit,
            and_(_current_split(experiment_id), TrialSplit.eid == ExperimentItem.eid),
        )
        .where(ExperimentItem.experiment_id == experiment_id)
        .order_by(
            IblSession.subject, IblSession.session_date, ExperimentItem.eid, ExperimentItem.region
        )
    ).all()
    if not items:
        raise _body_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "no_items",
            ["body"],
            "Select data before queuing a run",
        )
    no_split = sorted({str(i.eid) for i in items if i.split_id is None})
    if no_split:
        raise _body_error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "split_missing",
            ["body"],
            f"These sessions have no split yet: {', '.join(no_split)}",
        )

    run = RunRow(
        workspace_id=workspace_id,
        experiment_id=experiment_id,
        stage="cebra",
        name=body.name,
        mode=body.mode,
        params=params.model_dump(mode="json"),
        preprocess=preprocess.model_dump(mode="json"),
        inputs=[
            {"eid": str(i.eid), "region": i.region, "split_id": str(i.split_id)} for i in items
        ],
        status="queued",
        progress={"done": 0, "total": len(items) * 2},
    )
    db.add(run)
    try:
        db.commit()
    except IntegrityError as exc:  # a concurrent request took the name
        db.rollback()
        raise _body_error(
            status.HTTP_409_CONFLICT, "duplicate_name", ["body", "name"], DUPLICATE_NAME
        ) from exc
    db.refresh(run)
    return Run.model_validate(run, from_attributes=True)

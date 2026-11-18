import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, StringConstraints

from app.schemas.cebra import Mode

RunName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
RunStatus = Literal["queued", "running", "succeeded", "failed"]


class RunCreate(BaseModel):
    """Queue a run. `params` and `preprocess` are validated against the mode's model from
    `GET /api/cebra/schema`; omitted fields take their defaults. Validation errors use
    `loc = ["body", "params" | "preprocess", <field>]`, so each maps onto one form field."""

    name: RunName
    mode: Mode
    params: dict[str, Any] = Field(default_factory=dict)
    preprocess: dict[str, Any] = Field(default_factory=dict)


class RunInput(BaseModel):
    """One item of the run's input snapshot, with the split its session had at queue time."""

    eid: uuid.UUID
    region: str
    split_id: uuid.UUID


class RunProgress(BaseModel):
    done: int
    total: int  # items x 2 (groups A and B)


class Run(BaseModel):
    id: uuid.UUID
    experiment_id: uuid.UUID
    stage: Literal["cebra"]
    name: str
    mode: Mode
    params: dict[str, Any]
    preprocess: dict[str, Any]
    inputs: list[RunInput]
    status: RunStatus
    progress: RunProgress
    error: str | None
    output_dir: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

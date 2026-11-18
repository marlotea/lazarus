import uuid
from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, StringConstraints, field_validator

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]


class ExperimentCreate(BaseModel):
    title: Title
    description: str = ""


class ExperimentUpdate(BaseModel):
    """Only the fields sent are changed."""

    title: Title | None = None
    description: str | None = None

    @field_validator("title", "description")
    @classmethod
    def _not_null(cls, v: str | None) -> str:
        # Defaults are not validated, so this only rejects an explicit null.
        if v is None:
            raise ValueError("cannot be null")
        return v


class Experiment(BaseModel):
    id: uuid.UUID
    title: str
    description: str
    created_at: datetime
    updated_at: datetime
    item_count: int
    session_count: int  # distinct sessions among the items
    run_count: int

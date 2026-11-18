import uuid
from datetime import date

from pydantic import BaseModel, Field


class Split(BaseModel):
    """The current split of one session's valid trials into groups A and B."""

    id: uuid.UUID
    seed: int
    n_a: int
    n_b: int


class ExperimentItem(BaseModel):
    """One selected item (session x region) with catalog info and its session's split."""

    eid: uuid.UUID
    region: str
    subject: str
    lab: str
    session_date: date
    n_good_units: int
    split: Split | None  # null only if the split could not be made


class ItemRef(BaseModel):
    eid: uuid.UUID
    region: str = Field(min_length=1)


class ItemsReplace(BaseModel):
    """The whole new selection. Duplicates are ignored."""

    items: list[ItemRef] = Field(max_length=10000)

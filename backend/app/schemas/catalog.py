import uuid
from datetime import date

from pydantic import BaseModel


class CatalogItem(BaseModel):
    """One catalog row: one Beryl region in one IBL session."""

    eid: uuid.UUID
    region: str
    subject: str
    lab: str
    session_date: date
    n_good_units: int


class CatalogRegion(BaseModel):
    region: str
    n_sessions: int

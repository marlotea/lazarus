"""Read-only IBL catalog: session x region rows and the list of regions."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import IblSession, IblSessionRegion
from app.schemas.catalog import CatalogItem, CatalogRegion

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


def _split_csv(values: list[str] | None) -> list[str]:
    """Accept both `?region=CA1&region=DG` and `?region=CA1,DG`."""
    out: list[str] = []
    for v in values or []:
        out.extend(p.strip() for p in v.split(",") if p.strip())
    return out


@router.get("/items", response_model=list[CatalogItem])
def list_catalog_items(
    db: Annotated[Session, Depends(get_db)],
    region: Annotated[
        list[str] | None, Query(description="Beryl acronym(s); repeat or comma-separate")
    ] = None,
    subject: Annotated[
        str | None, Query(description="Case-insensitive substring of the subject")
    ] = None,
    lab: Annotated[str | None, Query(description="Exact lab name")] = None,
    min_units: Annotated[int, Query(ge=0, description="Minimum good units")] = 0,
    limit: Annotated[int, Query(ge=1, le=10000)] = 2000,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[CatalogItem]:
    """Flat catalog rows (session x region), ordered by subject, date, session and region."""
    stmt = (
        select(
            IblSessionRegion.eid,
            IblSessionRegion.region,
            IblSession.subject,
            IblSession.lab,
            IblSession.session_date,
            IblSessionRegion.n_good_units,
        )
        .join(IblSession, IblSession.eid == IblSessionRegion.eid)
        .where(IblSessionRegion.n_good_units >= min_units)
    )
    regions = _split_csv(region)
    if regions:
        stmt = stmt.where(IblSessionRegion.region.in_(regions))
    if subject and subject.strip():
        escaped = subject.strip().replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
        stmt = stmt.where(IblSession.subject.ilike(f"%{escaped}%", escape="\\"))
    if lab:
        stmt = stmt.where(IblSession.lab == lab)
    stmt = (
        stmt.order_by(
            IblSession.subject,
            IblSession.session_date,
            IblSessionRegion.eid,
            IblSessionRegion.region,
        )
        .limit(limit)
        .offset(offset)
    )
    return [CatalogItem.model_validate(row, from_attributes=True) for row in db.execute(stmt)]


@router.get("/regions", response_model=list[CatalogRegion])
def list_catalog_regions(db: Annotated[Session, Depends(get_db)]) -> list[CatalogRegion]:
    """Distinct regions with the number of sessions that have each one, sorted by region."""
    stmt = (
        select(IblSessionRegion.region, func.count().label("n_sessions"))
        .group_by(IblSessionRegion.region)
        .order_by(IblSessionRegion.region)
    )
    return [CatalogRegion(region=r, n_sessions=n) for r, n in db.execute(stmt)]

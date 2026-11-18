"""Fill the IBL catalog tables (`ibl_sessions`, `ibl_session_regions`).

    uv run python -m app.ibl.catalog_sync [--regions CA1,DG] [--limit 50]

With IBL_FAKE=1 it writes the synthetic sessions from app.ibl.fake. Otherwise it reads the
Brain Wide Map session/probe table and good-unit table from the public IBL server.
Rows are upserted, so running it again is safe. `n_trials` is left null here; it is filled
when a split is made for the session.
"""

from __future__ import annotations

import argparse
import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date
from typing import TYPE_CHECKING

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import IblSession, IblSessionRegion
from app.settings import get_settings

if TYPE_CHECKING:
    import pandas as pd


@dataclass(frozen=True)
class CatalogSession:
    eid: uuid.UUID
    subject: str
    lab: str
    session_date: date


@dataclass(frozen=True)
class CatalogRegion:
    eid: uuid.UUID
    region: str  # Beryl acronym
    n_good_units: int
    pids: tuple[uuid.UUID, ...]


Catalog = tuple[list[CatalogSession], list[CatalogRegion]]


def filter_catalog(
    sessions: Sequence[CatalogSession],
    regions: Iterable[CatalogRegion],
    region_filter: Sequence[str] | None = None,
    limit: int | None = None,
) -> Catalog:
    """Keep only rows in `region_filter`, drop sessions left without regions, then keep the
    first `limit` sessions (in the order given)."""
    wanted = set(region_filter) if region_filter else None
    kept_regions = [r for r in regions if wanted is None or r.region in wanted]
    eids_with_regions = {r.eid for r in kept_regions}
    kept_sessions = [s for s in sessions if s.eid in eids_with_regions]
    if limit is not None:
        kept_sessions = kept_sessions[:limit]
    kept_eids = {s.eid for s in kept_sessions}
    return kept_sessions, [r for r in kept_regions if r.eid in kept_eids]


# --- sources -----------------------------------------------------------------------------


def fake_catalog() -> Catalog:
    from app.ibl.fake import fake_sessions

    sessions, regions = [], []
    for s in fake_sessions():
        sessions.append(CatalogSession(s.eid, s.subject, s.lab, s.session_date))
        for region, n_units in s.regions.items():
            regions.append(CatalogRegion(s.eid, region, n_units, s.region_pids[region]))
    return sessions, regions


# Column names of the brainwidemap tables. Printed on every real run so they can be checked;
# a missing column stops the sync with the actual column list. Verified against the
# installed brainwidemap version in M7.
BWM_QUERY_COLS = {"eid": "eid", "pid": "pid", "subject": "subject", "lab": "lab", "date": "date"}
BWM_UNITS_COLS = {"eid": "eid", "pid": "pid", "region": "Beryl"}


def _require_columns(df: pd.DataFrame, cols: dict[str, str], name: str) -> None:
    missing = sorted(set(cols.values()) - set(df.columns))
    if missing:
        raise SystemExit(
            f"{name} is missing columns {missing}. Columns present: {list(df.columns)}. "
            "Update the column map in app/ibl/catalog_sync.py."
        )


def real_catalog() -> Catalog:
    """Brain Wide Map sessions and good units from the public IBL server."""
    import pandas as pd
    from brainwidemap import bwm_query, bwm_units  # not on PyPI; added in M7

    from app.ibl.one_client import get_one

    one = get_one()
    # 1. Every BWM session and probe.
    bwm_df = bwm_query(one)
    # 2. The good units used in the BWM paper, with eid, pid and Beryl region.
    unit_df = bwm_units(one)
    print(f"bwm_query columns: {list(bwm_df.columns)}")
    print(f"bwm_units columns: {list(unit_df.columns)}")
    _require_columns(bwm_df, BWM_QUERY_COLS, "bwm_query")
    _require_columns(unit_df, BWM_UNITS_COLS, "bwm_units")

    q, u = BWM_QUERY_COLS, BWM_UNITS_COLS
    sess_df = (
        bwm_df[[q["eid"], q["subject"], q["lab"], q["date"]]]
        .drop_duplicates(subset=q["eid"])
        .sort_values([q["date"], q["eid"]])
    )
    sessions = [
        CatalogSession(
            eid=uuid.UUID(str(row[q["eid"]])),
            subject=str(row[q["subject"]]),
            lab=str(row[q["lab"]]),
            session_date=pd.Timestamp(row[q["date"]]).date(),
        )
        for _, row in sess_df.iterrows()
    ]

    # 3. Group units by (eid, Beryl region): count units, collect the distinct pids.
    grouped = unit_df.groupby([u["eid"], u["region"]], sort=True)
    regions = [
        CatalogRegion(
            eid=uuid.UUID(str(eid)),
            region=str(region),
            n_good_units=int(len(group)),
            pids=tuple(sorted(uuid.UUID(str(p)) for p in group[u["pid"]].unique())),
        )
        for (eid, region), group in grouped
    ]
    known = {s.eid for s in sessions}
    return sessions, [r for r in regions if r.eid in known]


# --- write -------------------------------------------------------------------------------


def upsert_catalog(
    db: Session, sessions: Sequence[CatalogSession], regions: Sequence[CatalogRegion]
):
    """4. Upsert both tables. Leaves `n_trials` untouched (null for new sessions)."""
    if sessions:
        stmt = insert(IblSession).values(
            [
                {"eid": s.eid, "subject": s.subject, "lab": s.lab, "session_date": s.session_date}
                for s in sessions
            ]
        )
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=[IblSession.eid],
                set_={
                    "subject": stmt.excluded.subject,
                    "lab": stmt.excluded.lab,
                    "session_date": stmt.excluded.session_date,
                    "synced_at": func.now(),
                },
            )
        )
    if regions:
        stmt = insert(IblSessionRegion).values(
            [
                {
                    "eid": r.eid,
                    "region": r.region,
                    "n_good_units": r.n_good_units,
                    "pids": list(r.pids),
                }
                for r in regions
            ]
        )
        db.execute(
            stmt.on_conflict_do_update(
                index_elements=[IblSessionRegion.eid, IblSessionRegion.region],
                set_={"n_good_units": stmt.excluded.n_good_units, "pids": stmt.excluded.pids},
            )
        )


def sync_catalog(
    db: Session,
    region_filter: Sequence[str] | None = None,
    limit: int | None = None,
    fake: bool | None = None,
) -> Catalog:
    """Build the catalog (fake or real), filter it and upsert it. Commits."""
    use_fake = get_settings().ibl_fake if fake is None else fake
    sessions, regions = fake_catalog() if use_fake else real_catalog()
    sessions, regions = filter_catalog(sessions, regions, region_filter, limit)
    upsert_catalog(db, sessions, regions)
    db.commit()
    return sessions, regions


def _parse_regions(value: str) -> list[str]:
    return [r.strip() for r in value.split(",") if r.strip()]


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.ibl.catalog_sync", description=__doc__)
    parser.add_argument(
        "--regions", type=_parse_regions, default=None, help="comma-separated Beryl acronyms"
    )
    parser.add_argument("--limit", type=int, default=None, help="keep the first N sessions")
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")

    from app.db import SessionLocal

    fake = get_settings().ibl_fake
    with SessionLocal() as db:
        sessions, regions = sync_catalog(db, args.regions, args.limit, fake=fake)
    source = "fake (IBL_FAKE=1)" if fake else "IBL Brain Wide Map"
    print(
        f"Synced {len(sessions)} sessions and {len(regions)} session x region rows from {source}."
    )


if __name__ == "__main__":
    main()

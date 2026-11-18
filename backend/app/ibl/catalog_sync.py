"""Fill the IBL catalog tables (`ibl_sessions`, `ibl_session_regions`).

    uv run python -m app.ibl.catalog_sync [--regions CA1,DG] [--limit 50] [--eids EID,EID]

With IBL_FAKE=1 it writes the synthetic sessions from app.ibl.fake. Otherwise it reads the
Brain Wide Map session/probe table and good-unit table from the public IBL server.
Rows are upserted, so running it again is safe and only adds or updates rows: fake and real
sessions can live side by side in the catalog (fake subjects are named FAKE01..FAKE06).
`n_trials` is left null here; it is filled when a split is made for the session.
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
    eid_filter: Sequence[uuid.UUID] | None = None,
) -> Catalog:
    """Keep only rows in `region_filter` (and sessions in `eid_filter`), drop sessions left
    without regions, then keep the first `limit` sessions (in the order given)."""
    wanted = set(region_filter) if region_filter else None
    wanted_eids = set(eid_filter) if eid_filter else None
    kept_regions = [
        r
        for r in regions
        if (wanted is None or r.region in wanted) and (wanted_eids is None or r.eid in wanted_eids)
    ]
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


# Column names of the brainwidemap tables (brainwidemap @ 705b7cb, freeze 2023_12_bwm_release),
# checked against the real tables in M7. The full column lists are printed on every real run;
# a missing column stops the sync with the actual column list.
#   bwm_query: pid, eid, probe_name, session_number, date, subject, lab (one row per probe)
#   bwm_units: Beryl, eid, pid, cluster_id, label, acronym, atlas_id, uuids, ... (one row per
#              good unit; already filtered to label >= 1 and BWM region/session criteria)
BWM_QUERY_COLS = {"eid": "eid", "pid": "pid", "subject": "subject", "lab": "lab", "date": "date"}
BWM_UNITS_COLS = {"eid": "eid", "pid": "pid", "region": "Beryl"}


def _require_columns(df: pd.DataFrame, cols: dict[str, str], name: str) -> None:
    missing = sorted(set(cols.values()) - set(df.columns))
    if missing:
        raise SystemExit(
            f"{name} is missing columns {missing}. Columns present: {list(df.columns)}. "
            "Update the column map in app/ibl/catalog_sync.py."
        )


def catalog_from_tables(bwm_df: pd.DataFrame, unit_df: pd.DataFrame) -> Catalog:
    """Map the `bwm_query` and `bwm_units` tables onto catalog rows (pure, no network).

    Sessions are ordered by date, then eid. Regions are units grouped by (eid, Beryl region):
    the unit count and the distinct pids. Units of sessions missing from `bwm_df` are dropped.
    """
    import pandas as pd

    _require_columns(bwm_df, BWM_QUERY_COLS, "bwm_query")
    _require_columns(unit_df, BWM_UNITS_COLS, "bwm_units")
    q, u = BWM_QUERY_COLS, BWM_UNITS_COLS
    sess_df = bwm_df[[q["eid"], q["subject"], q["lab"], q["date"]]].drop_duplicates(subset=q["eid"])
    sessions = sorted(
        (
            CatalogSession(
                eid=uuid.UUID(str(row[q["eid"]])),
                subject=str(row[q["subject"]]),
                lab=str(row[q["lab"]]),
                session_date=pd.Timestamp(row[q["date"]]).date(),
            )
            for _, row in sess_df.iterrows()
        ),
        key=lambda s: (s.session_date, str(s.eid)),
    )

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


def real_catalog() -> Catalog:
    """Brain Wide Map sessions and good units from the public IBL server.

    `bwm_query` reads a frozen table shipped with brainwidemap; `bwm_units` downloads two
    aggregate tables (about 115 MB) into `ONE_CACHE_DIR/bwm_tables` on first use.
    """
    from brainwidemap import bwm_query, bwm_units  # git dependency, pinned in pyproject

    from app.ibl.one_client import get_one

    one = get_one()
    # 1. Every BWM session and probe.
    bwm_df = bwm_query(one)
    # 2. The good units used in the BWM paper, with eid, pid and Beryl region.
    unit_df = bwm_units(one)
    print(f"bwm_query columns: {list(bwm_df.columns)}")
    print(f"bwm_units columns: {list(unit_df.columns)}")
    # 3. Group units by (eid, Beryl region).
    return catalog_from_tables(bwm_df, unit_df)


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
    eid_filter: Sequence[uuid.UUID] | None = None,
) -> Catalog:
    """Build the catalog (fake or real), filter it and upsert it. Commits."""
    use_fake = get_settings().ibl_fake if fake is None else fake
    sessions, regions = fake_catalog() if use_fake else real_catalog()
    sessions, regions = filter_catalog(sessions, regions, region_filter, limit, eid_filter)
    upsert_catalog(db, sessions, regions)
    db.commit()
    return sessions, regions


def _parse_regions(value: str) -> list[str]:
    return [r.strip() for r in value.split(",") if r.strip()]


def _parse_eids(value: str) -> list[uuid.UUID]:
    try:
        return [uuid.UUID(e.strip()) for e in value.split(",") if e.strip()]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(f"not a list of session uuids: {value!r}") from exc


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="python -m app.ibl.catalog_sync", description=__doc__)
    parser.add_argument(
        "--regions", type=_parse_regions, default=None, help="comma-separated Beryl acronyms"
    )
    parser.add_argument(
        "--limit", type=int, default=None, help="keep the first N sessions (by date, then eid)"
    )
    parser.add_argument(
        "--eids", type=_parse_eids, default=None, help="comma-separated session eids to keep"
    )
    args = parser.parse_args(argv)
    if args.limit is not None and args.limit < 1:
        parser.error("--limit must be at least 1")

    from app.db import SessionLocal

    fake = get_settings().ibl_fake
    with SessionLocal() as db:
        sessions, regions = sync_catalog(
            db, args.regions, args.limit, fake=fake, eid_filter=args.eids
        )
    source = "fake (IBL_FAKE=1)" if fake else "IBL Brain Wide Map"
    print(
        f"Synced {len(sessions)} sessions and {len(regions)} session x region rows from {source}."
    )


if __name__ == "__main__":
    main()

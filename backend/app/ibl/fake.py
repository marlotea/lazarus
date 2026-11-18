"""Synthetic IBL catalog for development and tests (IBL_FAKE=1).

Ten sessions across six subjects, regions CA1, DG, LP, VISp, MOs and PO. Everything is a
fixed table or derived from it with uuid5, so every call returns the same ids and counts.
Subjects are named FAKE01..FAKE06 so fake rows are never mistaken for real IBL data.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date

FAKE_NAMESPACE = uuid.UUID("5f1c9a0e-4482-4f4b-9d4b-448448448448")
FAKE_REGIONS = ("CA1", "DG", "LP", "VISp", "MOs", "PO")


@dataclass(frozen=True)
class FakeSession:
    eid: uuid.UUID
    subject: str
    lab: str
    session_date: date
    n_trials: int  # for later milestones (splits); catalog sync leaves n_trials null
    regions: dict[str, int]  # Beryl acronym -> good-unit count
    pids: tuple[uuid.UUID, ...]  # probes in this session
    region_pids: dict[str, tuple[uuid.UUID, ...]]  # probes that cross each region


# subject, lab, date, n_trials, {region: n_good_units}
_TABLE: list[tuple[str, str, date, int, dict[str, int]]] = [
    ("FAKE01", "cortexlab", date(2026, 1, 12), 603, {"CA1": 64, "DG": 41, "LP": 23}),
    ("FAKE01", "cortexlab", date(2026, 1, 14), 548, {"CA1": 52, "VISp": 88}),
    ("FAKE02", "cortexlab", date(2026, 2, 3), 711, {"CA1": 37, "DG": 29, "PO": 18}),
    ("FAKE03", "churchlandlab", date(2026, 2, 10), 492, {"MOs": 75, "CA1": 44}),
    ("FAKE03", "churchlandlab", date(2026, 2, 11), 655, {"MOs": 61, "PO": 26, "LP": 33}),
    ("FAKE04", "hoferlab", date(2026, 3, 2), 580, {"VISp": 102, "LP": 47}),
    ("FAKE04", "hoferlab", date(2026, 3, 5), 624, {"VISp": 91, "CA1": 39, "DG": 22}),
    ("FAKE05", "mainenlab", date(2026, 3, 20), 517, {"MOs": 58, "PO": 31}),
    ("FAKE06", "angelakilab", date(2026, 4, 7), 689, {"CA1": 70, "DG": 35, "VISp": 49}),
    ("FAKE06", "angelakilab", date(2026, 4, 9), 572, {"LP": 27, "PO": 19, "MOs": 40}),
]


def _build() -> list[FakeSession]:
    sessions = []
    for subject, lab, day, n_trials, regions in _TABLE:
        eid = uuid.uuid5(FAKE_NAMESPACE, f"session/{subject}/{day.isoformat()}")
        # Sessions with 3+ regions have two probes; the middle region is crossed by both,
        # so probe merging is exercised.
        n_probes = 2 if len(regions) >= 3 else 1
        pids = tuple(uuid.uuid5(FAKE_NAMESPACE, f"probe/{eid}/probe0{k}") for k in range(n_probes))
        region_pids: dict[str, tuple[uuid.UUID, ...]] = {}
        names = list(regions)
        for i, region in enumerate(names):
            if n_probes == 1:
                region_pids[region] = pids
            elif len(names) % 2 == 1 and i == len(names) // 2:
                region_pids[region] = pids
            else:
                region_pids[region] = (pids[0],) if i < len(names) / 2 else (pids[1],)
        sessions.append(
            FakeSession(eid, subject, lab, day, n_trials, dict(regions), pids, region_pids)
        )
    return sessions


FAKE_SESSIONS: tuple[FakeSession, ...] = tuple(_build())


def fake_sessions() -> list[FakeSession]:
    """All fake sessions, in a fixed order."""
    return list(FAKE_SESSIONS)


def get_fake_session(eid: uuid.UUID | str) -> FakeSession:
    key = uuid.UUID(str(eid))
    for s in FAKE_SESSIONS:
        if s.eid == key:
            return s
    raise KeyError(f"No fake session with eid {key}")


def fake_valid_trials(eid: uuid.UUID | str) -> list[int]:
    """Valid trial indices of a fake session: 0..n_trials-1 minus a fixed ~4% of trials,
    standing in for trials with a NaN stimOn/firstMovement/feedback time. Same eid, same list."""
    s = get_fake_session(eid)
    # A tiny LCG keyed on the eid keeps this deterministic without numpy.
    state = s.eid.int % 2**31
    valid = []
    for i in range(s.n_trials):
        state = (1103515245 * state + 12345) % 2**31
        if state % 25 != 0:
            valid.append(i)
    return valid

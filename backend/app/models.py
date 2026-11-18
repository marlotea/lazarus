"""ORM classes mapped to the tables in supabase/migrations/0001_init.sql.

The migration is the source of truth for the schema; these classes only mirror it.
Defaults are server-side (`server_default`) so the database fills them, as it does for raw SQL.
"""

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    REAL,
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

GEN_UUID = text("gen_random_uuid()")
NOW = text("now()")


class Base(DeclarativeBase):
    pass


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=GEN_UUID)


class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(Text, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class IblSession(Base):
    __tablename__ = "ibl_sessions"

    eid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    subject: Mapped[str] = mapped_column(Text)
    lab: Mapped[str] = mapped_column(Text)
    session_date: Mapped[date] = mapped_column(Date)
    n_trials: Mapped[int | None] = mapped_column(Integer)
    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class IblSessionRegion(Base):
    __tablename__ = "ibl_session_regions"

    eid: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("ibl_sessions.eid", ondelete="CASCADE"), primary_key=True
    )
    region: Mapped[str] = mapped_column(Text, primary_key=True)  # Beryl acronym
    n_good_units: Mapped[int] = mapped_column(Integer)
    pids: Mapped[list[uuid.UUID]] = mapped_column(ARRAY(UUID(as_uuid=True)))


class Experiment(Base):
    __tablename__ = "experiments"

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id"))
    title: Mapped[str] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, server_default=text("''"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class ExperimentItem(Base):
    __tablename__ = "experiment_items"
    __table_args__ = (
        ForeignKeyConstraint(
            ["eid", "region"], ["ibl_session_regions.eid", "ibl_session_regions.region"]
        ),
    )

    id: Mapped[uuid.UUID] = uuid_pk()
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experiments.id", ondelete="CASCADE")
    )
    eid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    region: Mapped[str] = mapped_column(Text)
    added_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class TrialSplit(Base):
    __tablename__ = "trial_splits"

    id: Mapped[uuid.UUID] = uuid_pk()
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experiments.id", ondelete="CASCADE")
    )
    eid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("ibl_sessions.eid"))
    seed: Mapped[int] = mapped_column(BigInteger)
    ratio: Mapped[float] = mapped_column(REAL, server_default=text("0.5"))
    group_a: Mapped[list[int]] = mapped_column(ARRAY(Integer))  # trial indices
    group_b: Mapped[list[int]] = mapped_column(ARRAY(Integer))
    superseded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )  # null = current
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class Run(Base):
    __tablename__ = "runs"

    id: Mapped[uuid.UUID] = uuid_pk()
    workspace_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("workspaces.id"))
    experiment_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("experiments.id", ondelete="CASCADE")
    )
    stage: Mapped[str] = mapped_column(Text, server_default=text("'cebra'"))
    name: Mapped[str] = mapped_column(Text)
    mode: Mapped[str] = mapped_column(Text)  # time | behaviour | hybrid
    params: Mapped[dict[str, Any]] = mapped_column(JSONB)
    preprocess: Mapped[dict[str, Any]] = mapped_column(JSONB)
    inputs: Mapped[list[dict[str, Any]]] = mapped_column(JSONB)  # [{eid, region, split_id}]
    status: Mapped[str] = mapped_column(Text, server_default=text("'queued'"))
    progress: Mapped[dict[str, Any]] = mapped_column(
        JSONB, server_default=text("""'{"done":0,"total":0}'::jsonb""")
    )
    error: Mapped[str | None] = mapped_column(Text)
    output_dir: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RunOutput(Base):
    __tablename__ = "run_outputs"

    id: Mapped[uuid.UUID] = uuid_pk()
    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("runs.id", ondelete="CASCADE")
    )
    eid: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True))
    region: Mapped[str] = mapped_column(Text)
    split_group: Mapped[str] = mapped_column(Text)  # 'A' | 'B'
    n_units: Mapped[int | None] = mapped_column(Integer)
    n_samples: Mapped[int | None] = mapped_column(Integer)
    final_loss: Mapped[float | None] = mapped_column(REAL)
    embedding_path: Mapped[str | None] = mapped_column(Text)
    model_path: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)


class WorkerHeartbeat(Base):
    __tablename__ = "worker_heartbeats"

    worker_id: Mapped[str] = mapped_column(Text, primary_key=True)
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=NOW)

"""The ORM classes must mirror the migration. Needs the local database."""

from sqlalchemy import inspect

from app.db import engine
from app.models import Base


def test_orm_tables_and_columns_match_database():
    insp = inspect(engine)
    assert set(Base.metadata.tables) == set(insp.get_table_names(schema="public"))
    for name, table in Base.metadata.tables.items():
        db_cols = {c["name"]: c for c in insp.get_columns(name)}
        assert set(table.columns.keys()) == set(db_cols), name
        for col in table.columns:
            assert col.nullable == db_cols[col.name]["nullable"], f"{name}.{col.name}"

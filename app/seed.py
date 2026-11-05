"""Idempotent database seeding.

Usage (from the repository root):

    python -m app.seed                 # uses DATABASE_PATH or data/lab.db
    python -m app.seed --db other.db

Seeding is an upsert keyed on each record's stable ID, run in one transaction:
running it again leaves the database in the same state, and restores any fixture
row that was modified. Rows that are not fixtures are left untouched (see
docs/limitations.md).
"""

import argparse
import os
import sqlite3
from contextlib import closing
from pathlib import Path

from pydantic import BaseModel

from app import fixtures
from app.db import connect, create_schema

# (table, primary key, records) in dependency order: parents before children.
# Table and column names come from this constant and the models, never from input.
SEED_PLAN = (
    ("tenants", "tenant_id", fixtures.TENANTS),
    ("users", "user_id", fixtures.USERS),
    ("customers", "customer_id", fixtures.CUSTOMERS),
    ("tickets", "ticket_id", fixtures.TICKETS),
    ("knowledge_documents", "doc_id", fixtures.KNOWLEDGE_DOCUMENTS),
)


def _upsert(conn: sqlite3.Connection, table: str, pk: str, record: BaseModel) -> None:
    row = record.model_dump(mode="json")  # enums -> plain strings
    columns = ", ".join(row)
    placeholders = ", ".join("?" for _ in row)
    updates = ", ".join(f"{col} = excluded.{col}" for col in row if col != pk)
    conn.execute(
        f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) "
        f"ON CONFLICT ({pk}) DO UPDATE SET {updates}",
        tuple(row.values()),  # values are always bound parameters
    )


def seed(db_path: str | Path) -> dict[str, int]:
    """Create the schema if needed and upsert all fixtures. Returns row counts.

    ``db_path`` is required on purpose: library callers (including tests) must say
    exactly which database they mean, so nothing falls back to the dev database.
    """
    with closing(connect(db_path)) as conn:
        create_schema(conn)
        with conn:  # one transaction: all fixtures or none
            for table, pk, records in SEED_PLAN:
                for record in records:
                    _upsert(conn, table, pk, record)
        return {
            table: conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            for table, _, _ in SEED_PLAN
        }


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed the local lab database with synthetic fixtures.")
    parser.add_argument("--db", default=os.environ.get("DATABASE_PATH", "data/lab.db"))
    args = parser.parse_args()

    app_env = os.environ.get("APP_ENV", "local")
    if app_env != "local":
        raise SystemExit(f"Refusing to seed: APP_ENV={app_env!r}. Synthetic seeding is local-only.")

    db_path = Path(args.db)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    counts = seed(db_path)
    print(f"Seeded {db_path} (synthetic data only):")
    for table, count in counts.items():
        print(f"  {table:<20} {count}")


if __name__ == "__main__":
    main()

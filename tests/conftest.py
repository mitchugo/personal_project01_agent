"""Shared test fixtures.

Every test that needs a database gets a fresh, seeded SQLite file inside pytest's
per-test ``tmp_path``. Tests never open data/lab.db.
"""

import json
from contextlib import closing

import pytest

from app import fixtures
from app.db import connect
from app.identity import Principal
from app.seed import seed

_USERS = {u.user_id: u for u in fixtures.USERS}


def principal_for(user_id: str) -> Principal:
    """Trusted Principal for a fixture user (what the identity layer would produce)."""
    user = _USERS[user_id]
    return Principal(user_id=user.user_id, tenant_id=user.tenant_id, role=user.role,
                     identity_source="local-fixture")


class RecordingConnection:
    """Wraps a sqlite3 connection and records every (sql, params) pair executed."""

    def __init__(self, conn):
        self._conn = conn
        self.statements: list[tuple[str, tuple]] = []

    def execute(self, sql, params=()):
        self.statements.append((sql, tuple(params)))
        return self._conn.execute(sql, params)

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, *exc):
        return self._conn.__exit__(*exc)

    def __getattr__(self, name):
        return getattr(self._conn, name)


def audit_events(caplog, event_type: str | None = None) -> list[dict]:
    events = [json.loads(r.getMessage()) for r in caplog.records if r.name == "audit"]
    return [e for e in events if event_type is None or e["event_type"] == event_type]


def table_snapshot(conn, *tables: str) -> dict:
    return {t: [tuple(r) for r in conn.execute(f"SELECT * FROM {t} ORDER BY 1")] for t in tables}


MUTABLE_TABLES = ("customers", "email_drafts", "refund_requests", "refund_ledger")


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    seed(path)
    return path


@pytest.fixture
def conn(db_path):
    with closing(connect(db_path)) as connection:
        yield connection

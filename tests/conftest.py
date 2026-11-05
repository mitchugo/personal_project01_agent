"""Shared test fixtures.

Every test that needs a database gets a fresh, seeded SQLite file inside pytest's
per-test ``tmp_path``. Tests never open data/lab.db.
"""

from contextlib import closing

import pytest

from app.db import connect
from app.seed import seed


@pytest.fixture
def db_path(tmp_path):
    path = tmp_path / "test.db"
    seed(path)
    return path


@pytest.fixture
def conn(db_path):
    with closing(connect(db_path)) as connection:
        yield connection

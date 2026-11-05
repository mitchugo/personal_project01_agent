"""Fixture and schema correctness tests.

These prove the synthetic data is shaped and related correctly and that seeding is
repeatable. They do NOT prove application-level tenant isolation or authorisation:
nothing here stops code from querying another tenant's rows.
"""

import re
import sqlite3

import pytest

from app import fixtures
from app.db import TENANT_OWNED_TABLES
from app.models import Customer, KnowledgeDocument, Ticket, User
from app.seed import SEED_PLAN, seed

TENANTS = ("northstar", "meridian")


def snapshot(conn):
    """Every row of every table, in a stable order."""
    return {
        table: [tuple(r) for r in conn.execute(f"SELECT * FROM {table} ORDER BY {pk}")]
        for table, pk, _ in SEED_PLAN
    }


# --- counts -----------------------------------------------------------------

def test_two_tenants(conn):
    names = [r["name"] for r in conn.execute("SELECT name FROM tenants ORDER BY name")]
    assert names == ["Meridian Cover", "Northstar Insurance"]


@pytest.mark.parametrize("tenant_id", TENANTS)
@pytest.mark.parametrize(
    "table, expected",
    [("users", 3), ("customers", 10), ("tickets", 5), ("knowledge_documents", 4)],
)
def test_record_counts_per_tenant(conn, tenant_id, table, expected):
    count = conn.execute(
        f"SELECT COUNT(*) FROM {table} WHERE tenant_id = ?", (tenant_id,)
    ).fetchone()[0]
    assert count == expected


@pytest.mark.parametrize("tenant_id", TENANTS)
def test_each_tenant_has_exactly_one_user_per_role(conn, tenant_id):
    roles = sorted(
        r["role"] for r in conn.execute("SELECT role FROM users WHERE tenant_id = ?", (tenant_id,))
    )
    assert roles == sorted(["support_agent", "supervisor", "tenant_admin"])


# --- tenant ownership -------------------------------------------------------

@pytest.mark.parametrize("table", TENANT_OWNED_TABLES)
def test_tenant_owned_tables_have_non_null_tenant_id_column(conn, table):
    columns = {c["name"]: c for c in conn.execute(f"PRAGMA table_info({table})")}
    assert "tenant_id" in columns
    assert columns["tenant_id"]["notnull"] == 1


def test_id_prefix_matches_owning_tenant(conn):
    prefix = {"northstar": "ns-", "meridian": "mc-"}
    for table, pk, _ in SEED_PLAN[1:]:  # skip tenants table
        for row in conn.execute(f"SELECT {pk} AS id, tenant_id FROM {table}"):
            assert row["id"].startswith(prefix[row["tenant_id"]]), (table, row["id"])


# --- relationships ----------------------------------------------------------

def test_every_ticket_references_customer_and_user_in_same_tenant(conn):
    orphans_or_cross_tenant = conn.execute(
        """
        SELECT t.ticket_id FROM tickets t
        LEFT JOIN customers c ON c.customer_id = t.customer_id AND c.tenant_id = t.tenant_id
        LEFT JOIN users u     ON u.user_id     = t.assigned_to AND u.tenant_id = t.tenant_id
        WHERE c.customer_id IS NULL OR u.user_id IS NULL
        """
    ).fetchall()
    assert orphans_or_cross_tenant == []


def test_tickets_are_assigned_only_to_agents_or_supervisors(conn):
    roles = {
        r["role"]
        for r in conn.execute("SELECT u.role FROM tickets t JOIN users u ON u.user_id = t.assigned_to")
    }
    assert roles <= {"support_agent", "supervisor"}


def test_foreign_key_check_reports_no_violations(conn):
    assert conn.execute("PRAGMA foreign_key_check").fetchall() == []


def test_database_rejects_ticket_linking_to_another_tenants_customer(conn):
    # A Meridian ticket pointing at a Northstar customer must fail the composite FK.
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO tickets VALUES (?, ?, ?, ?, ?, ?, ?)",
                ("mc-tkt-999", "meridian", "ns-cust-001", "mc-agent-01", "x", "x", "open"),
            )


def test_database_rejects_unknown_tenant(conn):
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute(
                "INSERT INTO knowledge_documents VALUES (?, ?, ?, ?)",
                ("zz-kb-001", "no-such-tenant", "x", "x"),
            )


# --- stable IDs and round trip ----------------------------------------------

def test_customer_ids_are_stable(conn):
    ids = [r[0] for r in conn.execute("SELECT customer_id FROM customers ORDER BY customer_id")]
    expected = [f"mc-cust-{i:03d}" for i in range(1, 11)] + [f"ns-cust-{i:03d}" for i in range(1, 11)]
    assert ids == expected


@pytest.mark.parametrize(
    "table, model, source",
    [
        ("users", User, fixtures.USERS),
        ("customers", Customer, fixtures.CUSTOMERS),
        ("tickets", Ticket, fixtures.TICKETS),
        ("knowledge_documents", KnowledgeDocument, fixtures.KNOWLEDGE_DOCUMENTS),
    ],
)
def test_database_rows_round_trip_to_fixture_models(conn, table, model, source):
    from_db = {model(**dict(r)) for r in conn.execute(f"SELECT * FROM {table}")}
    assert from_db == set(source)


# --- synthetic data guardrails ----------------------------------------------

def test_all_emails_use_reserved_domains(conn):
    allowed = re.compile(r"@(example\.com|northstar\.example|meridian\.example)$")
    emails = [r[0] for r in conn.execute("SELECT email FROM users UNION ALL SELECT email FROM customers")]
    assert emails and all(allowed.search(e) for e in emails), emails


def test_all_phone_numbers_are_in_ofcom_drama_range(conn):
    phones = [r[0] for r in conn.execute("SELECT phone FROM customers")]
    assert all(re.fullmatch(r"07700 900\d{3}", p) for p in phones), phones


def test_attack_fixtures_exist_and_are_documented():
    ids = {t.ticket_id for t in fixtures.TICKETS} | {d.doc_id for d in fixtures.KNOWLEDGE_DOCUMENTS}
    assert fixtures.ATTACK_FIXTURE_IDS <= ids


# --- repeatable seeding -----------------------------------------------------

def test_seeding_twice_produces_identical_database(db_path, conn):
    before = snapshot(conn)
    counts = seed(db_path)
    assert snapshot(conn) == before
    assert counts == {"tenants": 2, "users": 6, "customers": 20, "tickets": 10, "knowledge_documents": 8}


def test_reseeding_restores_a_modified_fixture_row(db_path, conn):
    with conn:
        conn.execute("UPDATE customers SET email = 'changed@example.com' WHERE customer_id = 'ns-cust-001'")
    seed(db_path)
    email = conn.execute("SELECT email FROM customers WHERE customer_id = 'ns-cust-001'").fetchone()[0]
    assert email == "amelia.thornbury@example.com"

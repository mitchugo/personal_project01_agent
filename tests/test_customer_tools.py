"""read_customer / update_customer: authorisation, tenant isolation, validation, audit.

Scope of proof: these tests exercise the tool functions and gateway directly
against a seeded test database. They do not involve HTTP, an LLM, or concurrent
access, and they cover the listed cases only - not every possible bypass.
"""

import json
import logging

import pytest

from app import fixtures
from app.gateway import execute_tool
from app.identity import Principal
from tools.customers import ReadCustomerArgs, read_customer

CID = "test-correlation-id"
USERS = {u.user_id: u for u in fixtures.USERS}
CUSTOMERS = {c.customer_id: c for c in fixtures.CUSTOMERS}

NS_CUSTOMER = "ns-cust-001"   # Northstar
MC_CUSTOMER = "mc-cust-001"   # Meridian
MISSING = "ns-cust-999"       # does not exist anywhere


def principal(user_id: str) -> Principal:
    user = USERS[user_id]
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

    def __enter__(self):
        self._conn.__enter__()
        return self

    def __exit__(self, *exc):
        return self._conn.__exit__(*exc)

    def customer_statements(self):
        return [(s, p) for s, p in self.statements if "customers" in s]


@pytest.fixture
def rec(conn):
    return RecordingConnection(conn)


def run(rec, user_id, tool, args):
    return execute_tool(rec, principal(user_id), CID, tool, args)


def customer_row(conn, customer_id):
    row = conn.execute("SELECT * FROM customers WHERE customer_id = ?", (customer_id,)).fetchone()
    return dict(row) if row else None


def tool_events(caplog):
    return [json.loads(r.getMessage()) for r in caplog.records
            if r.name == "audit" and '"tool.invoke"' in r.getMessage()]


# --- read: permitted --------------------------------------------------------

@pytest.mark.parametrize("user_id", ["ns-agent-01", "ns-super-01"])
def test_staff_read_same_tenant_customer(rec, user_id):
    result = run(rec, user_id, "read_customer", {"customer_id": NS_CUSTOMER})

    expected = CUSTOMERS[NS_CUSTOMER].model_dump(mode="json")
    expected.pop("tenant_id")
    assert result.status == "ok"
    assert result.data == expected


# --- read: tenant isolation and non-disclosure ------------------------------

@pytest.mark.parametrize("user_id, other_tenant_customer", [
    ("ns-agent-01", MC_CUSTOMER), ("ns-super-01", MC_CUSTOMER),
    ("mc-agent-01", NS_CUSTOMER), ("mc-super-01", NS_CUSTOMER),
])
def test_staff_cannot_read_another_tenants_customer(rec, user_id, other_tenant_customer):
    result = run(rec, user_id, "read_customer", {"customer_id": other_tenant_customer})
    assert result.status == "not_found"
    assert result.data is None


def test_other_tenant_record_is_indistinguishable_from_missing_record(rec, caplog):
    caplog.set_level(logging.INFO, logger="audit")
    cross = run(rec, "mc-agent-01", "read_customer", {"customer_id": NS_CUSTOMER})
    missing = run(rec, "mc-agent-01", "read_customer", {"customer_id": MISSING})

    assert cross.model_dump() == missing.model_dump()
    reasons = [e["metadata"]["reason"] for e in tool_events(caplog)]
    assert reasons == ["not_found_in_tenant", "not_found_in_tenant"]


# --- tenant_admin -----------------------------------------------------------

@pytest.mark.parametrize("tool, args", [
    ("read_customer", {"customer_id": NS_CUSTOMER}),
    ("update_customer", {"customer_id": NS_CUSTOMER, "changes": {"phone": "07700 900555"}}),
])
def test_tenant_admin_is_denied_before_any_customer_query(conn, rec, tool, args):
    before = customer_row(conn, NS_CUSTOMER)
    result = run(rec, "ns-admin-01", tool, args)

    assert result.status == "denied"
    assert result.data is None
    assert rec.customer_statements() == []
    assert customer_row(conn, NS_CUSTOMER) == before


def test_tenant_admin_denial_is_identical_for_any_customer_id(rec):
    results = {run(rec, "ns-admin-01", "read_customer", {"customer_id": cid}).model_dump_json()
               for cid in (NS_CUSTOMER, MC_CUSTOMER, MISSING)}
    assert len(results) == 1


# --- update: permitted ------------------------------------------------------

@pytest.mark.parametrize("user_id", ["ns-agent-01", "ns-super-01"])
def test_staff_update_permitted_contact_fields(conn, rec, user_id):
    before = customer_row(conn, NS_CUSTOMER)
    changes = {"email": "amelia.t@example.org", "phone": "07700 900555", "address": "1 New Road, Saltmere"}

    result = run(rec, user_id, "update_customer", {"customer_id": NS_CUSTOMER, "changes": changes})

    assert result.status == "ok"
    assert result.data == {"customer_id": NS_CUSTOMER, "updated_fields": ["address", "email", "phone"]}
    assert customer_row(conn, NS_CUSTOMER) == {**before, **changes}


def test_partial_update_changes_only_supplied_field(conn, rec):
    before = customer_row(conn, NS_CUSTOMER)
    run(rec, "ns-agent-01", "update_customer", {"customer_id": NS_CUSTOMER, "changes": {"phone": "07700 900777"}})
    assert customer_row(conn, NS_CUSTOMER) == {**before, "phone": "07700 900777"}


# --- update: cross-tenant ---------------------------------------------------

@pytest.mark.parametrize("user_id", ["mc-agent-01", "mc-super-01"])
def test_cross_tenant_update_is_denied_and_target_unchanged(conn, rec, user_id):
    before = customer_row(conn, NS_CUSTOMER)
    result = run(rec, user_id, "update_customer",
                 {"customer_id": NS_CUSTOMER, "changes": {"email": "hijack@example.com"}})

    assert result.status == "not_found"
    assert customer_row(conn, NS_CUSTOMER) == before


# --- update: immutable, unknown and invalid fields --------------------------

@pytest.mark.parametrize("field, value", [
    ("policy_number", "NS-POL-9999"), ("customer_id", "ns-cust-002"), ("tenant_id", "meridian"),
])
def test_immutable_fields_are_rejected_and_nothing_is_written(conn, rec, field, value):
    before = customer_row(conn, NS_CUSTOMER)
    result = run(rec, "ns-super-01", "update_customer",
                 {"customer_id": NS_CUSTOMER, "changes": {"email": "ok@example.com", field: value}})

    assert result.status == "invalid"
    assert [e.type for e in result.errors] == ["immutable_field"]
    assert rec.statements == []
    assert customer_row(conn, NS_CUSTOMER) == before


@pytest.mark.parametrize("field", ["policy_note", "policy_type", "full_name", "is_vip"])
def test_non_contact_and_unknown_fields_are_rejected(conn, rec, field):
    before = customer_row(conn, NS_CUSTOMER)
    result = run(rec, "ns-super-01", "update_customer",
                 {"customer_id": NS_CUSTOMER, "changes": {field: "x" * 10}})

    assert result.status == "invalid"
    assert "extra_forbidden" in {e.type for e in result.errors}
    assert rec.statements == []
    assert customer_row(conn, NS_CUSTOMER) == before


@pytest.mark.parametrize("changes", [
    {"email": "real.person@gmail.com"},          # non-reserved domain (lab guardrail)
    {"email": "Amelia@Example.com"},             # not normalised lowercase
    {"email": "not-an-email"},
    {"phone": "07123 456789"},                   # outside fiction range
    {"phone": 7700900123},                       # wrong type, no coercion
    {"address": "1 Road\nInjected: line"},       # control character
    {"address": "x"},                            # too short
    {"address": "y" * 201},                      # too long
    {},                                          # nothing to change
    {"email": None},                             # explicit nulls only
])
def test_invalid_values_are_rejected_and_nothing_is_written(conn, rec, changes):
    before = customer_row(conn, NS_CUSTOMER)
    result = run(rec, "ns-agent-01", "update_customer", {"customer_id": NS_CUSTOMER, "changes": changes})

    assert result.status == "invalid"
    assert rec.statements == []
    assert customer_row(conn, NS_CUSTOMER) == before


# --- bypass attempts via supplied identity ----------------------------------

@pytest.mark.parametrize("tool, extra", [
    ("read_customer", {"tenant_id": "northstar"}),
    ("read_customer", {"role": "supervisor"}),
    ("read_customer", {"user_id": "ns-super-01"}),
    ("update_customer", {"tenant_id": "northstar"}),
    ("update_customer", {"principal": {"tenant_id": "northstar", "role": "supervisor"}}),
])
def test_identity_fields_in_arguments_are_rejected_without_db_access(rec, tool, extra):
    args = {"customer_id": NS_CUSTOMER, **extra}
    if tool == "update_customer":
        args["changes"] = {"phone": "07700 900555"}

    result = run(rec, "mc-agent-01", tool, args)  # Meridian user claiming Northstar

    assert result.status == "invalid"
    assert "extra_forbidden" in {e.type for e in result.errors}
    assert rec.statements == []


def test_tenant_admin_cannot_escalate_by_claiming_a_role(rec):
    result = run(rec, "ns-admin-01", "read_customer", {"customer_id": NS_CUSTOMER, "role": "supervisor"})
    assert result.status == "invalid"
    assert rec.statements == []


@pytest.mark.parametrize("customer_id", [
    "ns-cust-001' OR '1'='1", "ns-cust-001; DROP TABLE customers", "NS-CUST-001", "", "x" * 65,
])
def test_malformed_customer_ids_are_rejected(rec, customer_id):
    result = run(rec, "ns-agent-01", "read_customer", {"customer_id": customer_id})
    assert result.status == "invalid"
    assert rec.statements == []


def test_unknown_tool_and_non_dict_args_are_rejected(rec):
    assert run(rec, "ns-agent-01", "delete_customer", {"customer_id": NS_CUSTOMER}).status == "invalid"
    assert run(rec, "ns-agent-01", "read_customer", ["ns-cust-001"]).status == "invalid"
    assert rec.statements == []


def test_tools_refuse_unvalidated_input_when_called_directly(conn):
    with pytest.raises(TypeError):
        read_customer(conn, principal("ns-agent-01"), {"customer_id": NS_CUSTOMER}, CID)
    with pytest.raises(TypeError):
        read_customer(conn, {"tenant_id": "northstar", "role": "supervisor"},
                      ReadCustomerArgs(customer_id=NS_CUSTOMER), CID)


# --- SQL parameterisation and tenant scoping --------------------------------

def test_customer_sql_is_parameterised_and_tenant_scoped(rec):
    new_email = "param.check@example.net"
    run(rec, "ns-agent-01", "read_customer", {"customer_id": NS_CUSTOMER})
    run(rec, "ns-agent-01", "update_customer", {"customer_id": NS_CUSTOMER, "changes": {"email": new_email}})
    run(rec, "mc-agent-01", "read_customer", {"customer_id": NS_CUSTOMER})

    statements = rec.customer_statements()
    assert len(statements) == 3
    for sql, params in statements:
        assert "customer_id = ? AND tenant_id = ?" in sql
        assert NS_CUSTOMER not in sql and new_email not in sql      # values never in SQL text
        assert params[-2] == NS_CUSTOMER                              # bound instead
    assert [p[-1] for _, p in statements] == ["northstar", "northstar", "meridian"]  # from Principal


# --- audit ------------------------------------------------------------------

def test_success_and_denial_events_record_decision_without_customer_data(rec, caplog):
    caplog.set_level(logging.DEBUG)
    target = CUSTOMERS[NS_CUSTOMER]
    new_values = {"email": "fresh.value@example.org", "address": "99 Secret Lane, Ostbury"}

    run(rec, "ns-agent-01", "read_customer", {"customer_id": NS_CUSTOMER})                             # allow
    run(rec, "ns-agent-01", "update_customer", {"customer_id": NS_CUSTOMER, "changes": new_values})  # allow
    run(rec, "mc-agent-01", "update_customer",
        {"customer_id": NS_CUSTOMER, "changes": {"phone": "07700 900888"}})                           # cross-tenant
    run(rec, "ns-admin-01", "read_customer", {"customer_id": NS_CUSTOMER})                             # role
    run(rec, "ns-agent-01", "update_customer",
        {"customer_id": NS_CUSTOMER, "changes": {"policy_number": "NS-POL-0000"}})                    # invalid

    events = tool_events(caplog)
    summary = [(e["actor_user_id"], e["tenant_id"], e["outcome"], e["metadata"]["decision"],
                e["metadata"]["reason"]) for e in events]
    assert summary == [
        ("ns-agent-01", "northstar", "success", "allow", "allowed"),
        ("ns-agent-01", "northstar", "success", "allow", "allowed"),
        ("mc-agent-01", "meridian", "denied", "deny", "not_found_in_tenant"),
        ("ns-admin-01", "northstar", "denied", "deny", "role_not_permitted"),
        ("ns-agent-01", "northstar", "rejected", "deny", "invalid_arguments"),
    ]
    assert all(e["correlation_id"] == CID for e in events)
    assert events[1]["metadata"]["fields"] == "address,email"

    for sensitive in (target.full_name, target.email, target.phone, target.address,
                      *new_values.values(), "07700 900888", "NS-POL-0000", target.policy_number):
        assert sensitive not in caplog.text, sensitive

"""request_refund tool + trusted approval service: state machine, separation of duties,
binding, replay, idempotent execution, transactions and audit hygiene.

All money is simulated; "execution" is a local state transition plus a ledger row.
"""

import logging
import sqlite3

import pytest
from pydantic import ValidationError

from app import refund_repo
from app.approvals import ApprovalBinding, ExecuteRequest, approve_refund, execute_refund
from app.gateway import execute_tool
from app.identity import Principal
from tests.conftest import audit_events, principal_for

CID = "refund-test"
REASON = "Policy cancelled within the 14-day cooling-off period."
REQ = {"customer_id": "ns-cust-003", "amount_pence": 4250, "currency": "GBP", "reason": REASON}

AGENT, SUPER, ADMIN = "ns-agent-01", "ns-super-01", "ns-admin-01"
MC_SUPER = "mc-super-01"


def request(conn, user_id=AGENT, **overrides):
    return execute_tool(conn, principal_for(user_id), CID, "request_refund", {**REQ, **overrides})


def binding(refund_id, **overrides):
    values = {"refund_id": refund_id, "customer_id": REQ["customer_id"],
              "amount_pence": REQ["amount_pence"], "currency": "GBP", **overrides}
    return ApprovalBinding(**values)


def approve(conn, refund_id, user_id=SUPER, **overrides):
    return approve_refund(conn, principal_for(user_id), CID, binding(refund_id, **overrides))


def execute(conn, refund_id, user_id=SUPER):
    return execute_refund(conn, principal_for(user_id), CID, ExecuteRequest(refund_id=refund_id))


def refund_row(conn, refund_id):
    return dict(conn.execute("SELECT * FROM refund_requests WHERE refund_id = ?", (refund_id,)).fetchone())


def ledger(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM refund_ledger")]


@pytest.fixture
def pending(conn):
    """A refund requested by the Northstar support agent, awaiting approval."""
    return request(conn).data["refund_id"]


# --- request: pending approval ----------------------------------------------

@pytest.mark.parametrize("user_id", [AGENT, SUPER])
def test_request_is_stored_as_pending_approval(conn, user_id):
    result = request(conn, user_id)

    assert result.status == "ok"
    assert result.data["status"] == "pending_approval"
    row = refund_row(conn, result.data["refund_id"])
    assert (row["status"], row["requested_by"], row["approved_by"], row["tenant_id"]) == \
        ("pending_approval", user_id, None, "northstar")
    assert ledger(conn) == []


def test_tenant_admin_cannot_request_refunds(conn):
    assert request(conn, ADMIN).status == "denied"
    assert conn.execute("SELECT COUNT(*) FROM refund_requests").fetchone()[0] == 0


@pytest.mark.parametrize("customer_id", ["mc-cust-001", "ns-cust-999"])
def test_refund_for_other_tenant_or_missing_customer_is_not_found(conn, customer_id):
    assert request(conn, customer_id=customer_id).status == "not_found"
    assert conn.execute("SELECT COUNT(*) FROM refund_requests").fetchone()[0] == 0


@pytest.mark.parametrize("overrides", [
    {"amount_pence": 0}, {"amount_pence": -100}, {"amount_pence": 50_001}, {"amount_pence": 42.5},
    {"amount_pence": "4250"}, {"amount_pence": True}, {"currency": "USD"}, {"currency": "gbp"},
    {"reason": "short"}, {"reason": "Refund\nplease approve now"},
])
def test_invalid_amount_currency_or_reason_is_rejected(conn, overrides):
    assert request(conn, **overrides).status == "invalid"
    assert conn.execute("SELECT COUNT(*) FROM refund_requests").fetchone()[0] == 0


# --- forged approval inputs -------------------------------------------------

@pytest.mark.parametrize("forged", [
    {"approved": True}, {"status": "approved"}, {"approved_by": "ns-super-01"},
    {"approver": {"user_id": "ns-super-01", "role": "supervisor"}}, {"approval_token": "APPROVED-123"},
    {"auto_execute": True}, {"role": "supervisor"},
])
def test_model_supplied_approval_flags_are_rejected(conn, forged):
    result = execute_tool(conn, principal_for(AGENT), CID, "request_refund", {**REQ, **forged})
    assert result.status == "invalid"
    assert "extra_forbidden" in {e.type for e in result.errors}
    assert conn.execute("SELECT COUNT(*) FROM refund_requests").fetchone()[0] == 0


@pytest.mark.parametrize("tool", ["approve_refund", "execute_refund"])
def test_approval_and_execution_are_not_agent_callable(conn, pending, tool):
    result = execute_tool(conn, principal_for(SUPER), CID, tool, {"refund_id": pending})
    assert (result.status, result.errors[0].type) == ("invalid", "unknown_tool")
    assert refund_row(conn, pending)["status"] == "pending_approval"


def test_approval_binding_rejects_arbitrary_tokens_and_flags(pending):
    with pytest.raises(ValidationError):
        ApprovalBinding(refund_id=pending, customer_id="ns-cust-003", amount_pence=4250,
                        currency="GBP", approval_token="anything")


@pytest.mark.parametrize("fabricated", [
    Principal(user_id="ns-super-99", tenant_id="northstar", role="supervisor", identity_source="local-fixture"),
    Principal(user_id="ns-agent-01", tenant_id="northstar", role="supervisor", identity_source="local-fixture"),
    Principal(user_id="mc-super-01", tenant_id="northstar", role="supervisor", identity_source="local-fixture"),
])
def test_fabricated_or_escalated_approver_identities_are_denied(conn, pending, fabricated):
    result = approve_refund(conn, fabricated, CID, binding(pending))
    assert (result.status, result.reason) == ("denied", "unverified_principal")
    assert refund_row(conn, pending)["status"] == "pending_approval"


def test_approver_must_be_a_principal_object(conn, pending):
    with pytest.raises(TypeError):
        approve_refund(conn, {"user_id": SUPER, "tenant_id": "northstar", "role": "supervisor"},
                       CID, binding(pending))


# --- approval rules ---------------------------------------------------------

def test_supervisor_approves_another_users_request(conn, pending):
    result = approve(conn, pending)

    assert (result.status, result.reason) == ("ok", "approved")
    row = refund_row(conn, pending)
    assert (row["status"], row["approved_by"]) == ("approved", SUPER)
    assert ledger(conn) == []                     # approval alone moves no (simulated) money


@pytest.mark.parametrize("user_id", [AGENT, ADMIN])
def test_non_supervisors_cannot_approve(conn, pending, user_id):
    assert approve(conn, pending, user_id).reason == "role_not_permitted"
    assert refund_row(conn, pending)["status"] == "pending_approval"


def test_supervisor_cannot_approve_own_request(conn):
    own = request(conn, SUPER).data["refund_id"]
    result = approve(conn, own, SUPER)
    assert (result.status, result.reason) == ("denied", "self_approval")
    assert refund_row(conn, own)["status"] == "pending_approval"


def test_database_also_blocks_self_approval(conn):
    own = request(conn, SUPER).data["refund_id"]
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute("UPDATE refund_requests SET status = 'approved', approved_by = requested_by "
                         "WHERE refund_id = ?", (own,))


def test_cross_tenant_approval_is_not_found_and_unchanged(conn, pending):
    result = approve(conn, pending, MC_SUPER)
    assert (result.status, result.reason) == ("not_found", "not_found_in_tenant")
    assert refund_row(conn, pending)["status"] == "pending_approval"


@pytest.mark.parametrize("overrides", [
    {"amount_pence": 4251}, {"amount_pence": 50_000}, {"customer_id": "ns-cust-004"},
])
def test_approval_bound_to_exact_customer_and_amount(conn, pending, overrides):
    result = approve(conn, pending, **overrides)
    assert (result.status, result.reason) == ("denied", "binding_mismatch")
    assert refund_row(conn, pending)["status"] == "pending_approval"


def test_approval_replay_is_rejected(conn, pending):
    assert approve(conn, pending).status == "ok"
    first = refund_row(conn, pending)

    replay = approve(conn, pending)

    assert (replay.status, replay.reason) == ("conflict", "already_decided")
    assert refund_row(conn, pending) == first     # approved_at etc. not rewritten


# --- execution --------------------------------------------------------------

def test_execution_without_approval_is_denied(conn, pending):
    result = execute(conn, pending)
    assert (result.status, result.reason) == ("denied", "not_approved")
    assert refund_row(conn, pending)["status"] == "pending_approval"
    assert ledger(conn) == []


def test_approved_refund_executes_once_and_repeat_is_idempotent(conn, pending):
    approve(conn, pending)

    first = execute(conn, pending)
    second = execute(conn, pending)

    assert (first.status, first.reason) == ("ok", "executed")
    assert (second.status, second.reason) == ("ok", "already_executed")
    assert first.data == second.data              # deterministic result
    [entry] = ledger(conn)                         # exactly one simulated payout
    assert (entry["refund_id"], entry["amount_pence"], entry["currency"]) == (pending, 4250, "GBP")
    assert refund_row(conn, pending)["status"] == "executed"


@pytest.mark.parametrize("user_id", [AGENT, ADMIN, MC_SUPER])
def test_only_same_tenant_supervisor_can_execute(conn, pending, user_id):
    approve(conn, pending)
    assert execute(conn, pending, user_id).status in {"denied", "not_found"}
    assert refund_row(conn, pending)["status"] == "approved"
    assert ledger(conn) == []


# --- duplicates -------------------------------------------------------------

def test_duplicate_pending_request_is_a_conflict(conn, pending):
    result = request(conn)
    assert result.status == "conflict"
    assert result.data == {"reason": "duplicate_pending_request", "existing_refund_id": pending}
    assert conn.execute("SELECT COUNT(*) FROM refund_requests").fetchone()[0] == 1


def test_new_request_allowed_once_previous_is_no_longer_pending(conn, pending):
    approve(conn, pending)
    assert request(conn).status == "ok"


# --- transactions and rollback ----------------------------------------------

def test_ledger_failure_rolls_back_the_status_change(conn, pending):
    approve(conn, pending)
    # Simulate a conflicting ledger row (e.g. corruption) so the INSERT fails mid-transaction.
    with conn:
        conn.execute("INSERT INTO refund_ledger VALUES ('ledger-planted', ?, 'northstar', 1, 'GBP', ?, 'x')",
                     (pending, SUPER))

    result = execute(conn, pending)

    assert (result.status, result.reason) == ("conflict", "ledger_conflict")
    row = refund_row(conn, pending)
    assert (row["status"], row["executed_at"]) == ("approved", None)   # UPDATE was rolled back
    assert [e["entry_id"] for e in ledger(conn)] == ["ledger-planted"]
    assert not conn.in_transaction


def test_unexpected_error_mid_execution_leaves_no_partial_state(conn, pending, monkeypatch):
    approve(conn, pending)

    def boom(*args, **kwargs):
        raise RuntimeError("simulated crash after status update")

    monkeypatch.setattr(refund_repo, "insert_ledger_entry", boom)
    with pytest.raises(RuntimeError):
        execute(conn, pending)

    assert refund_row(conn, pending)["status"] == "approved"
    assert ledger(conn) == []
    assert not conn.in_transaction


def test_denied_approval_leaves_no_open_transaction(conn, pending):
    approve(conn, pending, MC_SUPER)
    approve(conn, pending, amount_pence=1)
    assert not conn.in_transaction


# --- audit ------------------------------------------------------------------

def test_full_workflow_is_audited_without_sensitive_content(conn, caplog):
    caplog.set_level(logging.DEBUG)
    refund_id = request(conn).data["refund_id"]
    approve(conn, refund_id, SUPER, amount_pence=1)   # binding mismatch
    approve(conn, refund_id)                          # approved
    execute(conn, refund_id)                          # executed
    execute(conn, refund_id)                          # idempotent repeat

    events = audit_events(caplog)
    trail = [(e["event_type"], e["outcome"], e["metadata"]["reason"]) for e in events]
    assert trail == [
        ("tool.invoke", "success", "allowed"),
        ("refund.approval", "denied", "binding_mismatch"),
        ("refund.approval", "success", "approved"),
        ("refund.execution", "success", "executed"),
        ("refund.execution", "success", "already_executed"),
    ]
    approval = events[2]
    assert approval["actor_user_id"] == SUPER and approval["metadata"]["resource_id"] == refund_id
    assert (approval["metadata"]["from_status"], approval["metadata"]["to_status"]) == ("pending_approval", "approved")
    assert approval["metadata"]["amount_pence"] == 4250
    assert REASON not in caplog.text and "cooling-off" not in caplog.text

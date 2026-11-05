"""draft_email: drafts only, tenant-scoped recipients, manipulation attempts, audit hygiene."""

import logging
import sqlite3

import pytest

from app import fixtures
from app.gateway import TOOLS, execute_tool
from tests.conftest import RecordingConnection, audit_events, principal_for

CID = "email-test"
CUSTOMERS = {c.customer_id: c for c in fixtures.CUSTOMERS}
GOOD = {"customer_id": "ns-cust-001", "subject": "Your address update",
        "body": "Hello Amelia,\n\nWe have updated your address.\n\nKind regards"}


def draft(conn, user_id, **overrides):
    return execute_tool(conn, principal_for(user_id), CID, "draft_email", {**GOOD, **overrides})


def drafts(conn):
    return [dict(r) for r in conn.execute("SELECT * FROM email_drafts")]


# --- allowed ----------------------------------------------------------------

@pytest.mark.parametrize("user_id", ["ns-agent-01", "ns-super-01"])
def test_staff_create_a_stored_draft_to_the_customer_on_file(conn, user_id):
    result = draft(conn, user_id)

    assert result.status == "ok"
    assert result.data["status"] == "draft"
    [row] = drafts(conn)
    assert row["draft_id"] == result.data["draft_id"]
    assert (row["tenant_id"], row["customer_id"], row["created_by"]) == ("northstar", "ns-cust-001", user_id)
    assert row["recipient"] == CUSTOMERS["ns-cust-001"].email
    assert row["status"] == "draft"


def test_response_does_not_echo_recipient_subject_or_body(conn):
    text = draft(conn, "ns-agent-01").model_dump_json()
    for value in (CUSTOMERS["ns-cust-001"].email, GOOD["subject"], "We have updated"):
        assert value not in text


# --- denied -----------------------------------------------------------------

def test_tenant_admin_cannot_draft(conn):
    assert draft(conn, "ns-admin-01").status == "denied"
    assert drafts(conn) == []


@pytest.mark.parametrize("user_id, customer_id", [
    ("mc-agent-01", "ns-cust-001"), ("ns-super-01", "mc-cust-002"), ("ns-agent-01", "ns-cust-999"),
])
def test_cross_tenant_or_missing_customer_is_not_found_and_nothing_stored(conn, user_id, customer_id):
    result = draft(conn, user_id, customer_id=customer_id)
    assert result.model_dump() == {"tool": "draft_email", "status": "not_found", "data": None, "errors": None}
    assert drafts(conn) == []


# --- recipient manipulation -------------------------------------------------

@pytest.mark.parametrize("extra", [
    {"to": "attacker@evil.test"}, {"recipient": "attacker@evil.test"}, {"cc": "x@example.com"},
    {"bcc": "x@example.com"}, {"from": "ceo@northstar.example"}, {"reply_to": "x@example.com"},
    {"tenant_id": "meridian"}, {"send": True}, {"status": "sent"},
])
def test_destination_or_send_fields_are_rejected(conn, extra):
    result = execute_tool(conn, principal_for("ns-agent-01"), CID, "draft_email", {**GOOD, **extra})
    assert result.status == "invalid"
    assert drafts(conn) == []


@pytest.mark.parametrize("overrides, error_type", [
    ({"subject": "Hi\r\nBcc: attacker@evil.test"}, "string_pattern_mismatch"),
    ({"subject": "Bcc: attacker@evil.test"}, "header_like_line"),
    ({"body": "Hello\nBcc: attacker@evil.test\nThanks"}, "header_like_line"),
    ({"body": "To: someone.else@example.com\nHello"}, "header_like_line"),
    ({"customer_id": "ns-cust-001, mc-cust-001"}, "string_pattern_mismatch"),
])
def test_header_injection_and_multi_recipient_tricks_are_rejected(conn, overrides, error_type):
    result = draft(conn, "ns-agent-01", **overrides)
    assert result.status == "invalid"
    assert error_type in {e.type for e in result.errors}
    assert drafts(conn) == []


# --- structure validation ---------------------------------------------------

@pytest.mark.parametrize("overrides", [
    {"subject": ""}, {"subject": "s" * 151}, {"body": ""}, {"body": "b" * 5001},
    {"body": "Hello\x00world"}, {"body": "Hello\x1b[31m"}, {"subject": 123},
])
def test_invalid_subject_or_body_is_rejected(conn, overrides):
    assert draft(conn, "ns-agent-01", **overrides).status == "invalid"
    assert drafts(conn) == []


# --- no send capability -----------------------------------------------------

def test_no_send_tool_exists_and_schema_has_no_sent_state(conn):
    assert not any("send" in name for name in TOOLS)
    draft(conn, "ns-agent-01")
    with pytest.raises(sqlite3.IntegrityError):
        with conn:
            conn.execute("UPDATE email_drafts SET status = 'sent'")


# --- SQL and audit ----------------------------------------------------------

def test_draft_sql_is_parameterised(conn):
    rec = RecordingConnection(conn)
    execute_tool(rec, principal_for("ns-agent-01"), CID, "draft_email", GOOD)
    for sql, _ in rec.statements:
        assert "We have updated" not in sql and GOOD["subject"] not in sql


def test_audit_records_lengths_not_content(conn, caplog):
    caplog.set_level(logging.DEBUG)
    draft(conn, "ns-agent-01")                                   # allowed
    draft(conn, "mc-agent-01")                                   # cross-tenant
    draft(conn, "ns-admin-01")                                   # role denied

    events = audit_events(caplog, "tool.invoke")
    assert [(e["outcome"], e["metadata"]["reason"]) for e in events] == [
        ("success", "allowed"), ("denied", "not_found_in_tenant"), ("denied", "role_not_permitted"),
    ]
    assert all(e["metadata"]["body_length"] == len(GOOD["body"]) for e in events)
    for sensitive in (GOOD["subject"], "We have updated", CUSTOMERS["ns-cust-001"].email):
        assert sensitive not in caplog.text

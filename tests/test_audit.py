"""Audit event structure and data-minimisation tests."""

import json
import logging
from datetime import timezone

import pytest
from pydantic import ValidationError

from app.audit import DEMO_EVENTS, AuditEvent, emit


def audit_lines(caplog):
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "audit"]


def test_emit_writes_one_json_line_with_required_fields(caplog):
    caplog.set_level(logging.INFO, logger="audit")

    emit("chat.message", "cid-1", "success", actor_user_id="ns-agent-01",
         tenant_id="northstar", message_length=12)

    [line] = audit_lines(caplog)
    assert line["event_type"] == "chat.message"
    assert line["correlation_id"] == "cid-1"
    assert line["outcome"] == "success"
    assert line["metadata"] == {"message_length": 12}
    assert "timestamp" in line


def test_timestamp_is_timezone_aware_utc():
    event = emit("http.request", "cid-2", "success")
    assert event.timestamp.tzinfo == timezone.utc


@pytest.mark.parametrize("key", ["message", "prompt", "email", "customer", "api_key", "authorization"])
def test_non_allow_listed_metadata_is_rejected(key):
    with pytest.raises(ValidationError):
        emit("chat.message", "cid-3", "success", **{key: "something sensitive"})


def test_nested_metadata_values_are_rejected():
    # Prevents smuggling a whole record under an allowed key.
    with pytest.raises(ValidationError):
        emit("http.request", "cid-4", "success", reason={"email": "x@example.com"})


def test_unknown_event_type_and_outcome_are_rejected():
    with pytest.raises(ValidationError):
        emit("customer.dump", "cid-5", "success")
    with pytest.raises(ValidationError):
        emit("http.request", "cid-5", "maybe")


def test_demo_events_are_valid_fixed_and_synthetic():
    assert len(DEMO_EVENTS) == 4
    assert all(isinstance(e, AuditEvent) for e in DEMO_EVENTS)
    assert all(e.correlation_id.startswith("00000000-0000-4000-8000-") for e in DEMO_EVENTS)
    assert {e.timestamp.year for e in DEMO_EVENTS} == {2026}

"""HTTP behaviour: correlation IDs, error format, demo audit route, chat validation."""

import json
import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from app.audit import DEMO_EVENTS
from app.main import create_app
from app.observability import CORRELATION_HEADER


def audit_lines(caplog):
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "audit"]


@pytest.fixture
def client():
    return TestClient(create_app())


# --- correlation IDs --------------------------------------------------------

def test_every_response_has_a_server_generated_uuid4_correlation_id(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert uuid.UUID(response.headers[CORRELATION_HEADER]).version == 4


def test_correlation_ids_are_unique_per_request(client):
    ids = {client.get("/health").headers[CORRELATION_HEADER] for _ in range(5)}
    assert len(ids) == 5


def test_client_supplied_correlation_id_is_ignored(client):
    response = client.get("/health", headers={CORRELATION_HEADER: "attacker-chosen-id"})
    assert response.headers[CORRELATION_HEADER] != "attacker-chosen-id"


def test_request_audit_event_carries_the_response_correlation_id(client, caplog):
    caplog.set_level(logging.INFO, logger="audit")
    response = client.get("/health?email=leak@example.com")

    [event] = [e for e in audit_lines(caplog) if e["event_type"] == "http.request"]
    assert event["correlation_id"] == response.headers[CORRELATION_HEADER]
    assert event["outcome"] == "success"
    assert event["metadata"]["path"] == "/health"  # query string not logged
    assert "leak@example.com" not in caplog.text


# --- error handling ---------------------------------------------------------

def test_unknown_route_returns_consistent_error_envelope(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "not_found",
            "message": "Not Found",
            "correlation_id": response.headers[CORRELATION_HEADER],
        }
    }


def test_unhandled_exception_returns_generic_500_without_details(caplog):
    app = create_app()

    @app.get("/boom")
    def boom():
        raise RuntimeError("db password=hunter2 for ns-cust-001")

    response = TestClient(app).get("/boom")

    assert response.status_code == 500
    body = response.json()
    assert body["error"]["code"] == "internal_error"
    assert body["error"]["correlation_id"] == response.headers[CORRELATION_HEADER]
    for leaked in ("hunter2", "ns-cust-001", "Traceback", "RuntimeError"):
        assert leaked not in response.text
    # The exception message (which here contains a secret) is not logged at INFO either.
    assert "hunter2" not in caplog.text


# --- audit demo -------------------------------------------------------------

def test_audit_demo_returns_exactly_the_static_synthetic_events(client):
    response = client.get("/audit-demo")
    assert response.status_code == 200
    body = response.json()
    assert body["synthetic"] is True
    assert body["events"] == [e.model_dump(mode="json") for e in DEMO_EVENTS]


def test_audit_demo_does_not_reflect_live_activity(client):
    before = client.get("/audit-demo").json()["events"]
    client.get("/health")
    client.get("/does-not-exist")
    after = client.get("/audit-demo").json()["events"]
    assert after == before

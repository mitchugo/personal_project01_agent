"""POST /chat: request validation, dev identity boundary, denial cases, logging.

These prove the HTTP identity boundary behaves as designed. They do NOT prove
tenant isolation for data access - there are no data-access routes or tool gateway.
"""

import json
import logging

import pytest
from fastapi.testclient import TestClient

from app import fixtures
from app.main import AGENT_NOT_CONNECTED_REPLY, create_app
from app.observability import CORRELATION_HEADER

DEV = "X-Dev-User-Id"
INJECTION_TEXT = next(t.body for t in fixtures.TICKETS if t.ticket_id == "mc-tkt-005")
UNAUTHENTICATED = {"code": "unauthenticated", "message": "Not authenticated."}


def audit_lines(caplog):
    return [json.loads(r.getMessage()) for r in caplog.records if r.name == "audit"]


def identity_events(caplog):
    return [e for e in audit_lines(caplog) if e["event_type"] == "identity.resolve"]


@pytest.fixture
def local_env(monkeypatch, db_path):
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("IDENTITY_MODE", "local-fixture")
    monkeypatch.delenv("APP_ENV", raising=False)


@pytest.fixture
def client(local_env):
    return TestClient(create_app())


def chat(client, message="Hello", user="ns-agent-01", **kwargs):
    headers = {DEV: user} if user else {}
    headers.update(kwargs.pop("headers", {}))
    return client.post("/chat", json={"message": message}, headers=headers, **kwargs)


def assert_unauthenticated(response):
    assert response.status_code == 401
    error = response.json()["error"]
    assert {k: error[k] for k in ("code", "message")} == UNAUTHENTICATED
    assert error["correlation_id"] == response.headers[CORRELATION_HEADER]


# --- valid requests ---------------------------------------------------------

def test_valid_chat_returns_fixed_not_connected_reply(client):
    response = chat(client, "Where is my claim?")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "correlation_id": response.headers[CORRELATION_HEADER],
        "reply": AGENT_NOT_CONNECTED_REPLY,
        "agent_connected": False,
        "acting_as": {
            "user_id": "ns-agent-01",
            "tenant_id": "northstar",
            "role": "support_agent",
            "identity_source": "local-fixture",
        },
    }


def test_reply_is_deterministic_and_never_echoes_the_message(client):
    replies = {chat(client, f"secret phrase {i}").json()["reply"] for i in range(3)}
    assert replies == {AGENT_NOT_CONNECTED_REPLY}
    assert "secret phrase" not in chat(client, "secret phrase").text


@pytest.mark.parametrize("user", fixtures.USERS, ids=lambda u: u.user_id)
def test_every_fixture_user_resolves_to_its_database_tenant_and_role(client, user):
    acting_as = chat(client, user=user.user_id).json()["acting_as"]
    assert (acting_as["tenant_id"], acting_as["role"]) == (user.tenant_id, user.role.value)


# --- invalid requests (422) -------------------------------------------------

@pytest.mark.parametrize(
    "payload, expected_type",
    [
        ({}, "missing"),
        ({"message": ""}, "string_too_short"),
        ({"message": "   "}, "string_too_short"),
        ({"message": "x" * 4001}, "string_too_long"),
        ({"message": 123}, "string_type"),
        ({"message": "hi", "tenant_id": "meridian"}, "extra_forbidden"),
        ({"message": "hi", "role": "supervisor"}, "extra_forbidden"),
    ],
)
def test_invalid_payloads_are_rejected_without_echoing_input(client, payload, expected_type):
    response = client.post("/chat", json=payload, headers={DEV: "ns-agent-01"})

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert expected_type in {f["type"] for f in error["fields"]}
    assert "input" not in json.dumps(error["fields"])
    for value in payload.values():
        if isinstance(value, str) and value.strip():
            assert value not in response.text


def test_malformed_json_is_rejected(client):
    response = client.post(
        "/chat", content=b"{not json", headers={DEV: "ns-agent-01", "Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_wrong_method_returns_405_envelope(client):
    response = client.get("/chat")
    assert response.status_code == 405
    assert response.json()["error"]["code"] == "method_not_allowed"


# --- identity cannot be supplied by the client or chat text -----------------

def test_tenant_and_role_headers_are_ignored(client):
    response = chat(
        client, user="mc-agent-01",
        headers={"X-Tenant-Id": "northstar", "X-Role": "supervisor", "X-User-Role": "tenant_admin"},
    )
    acting_as = response.json()["acting_as"]
    assert (acting_as["tenant_id"], acting_as["role"]) == ("meridian", "support_agent")


def test_identity_claims_in_chat_text_do_not_change_the_principal(client):
    # mc-tkt-005 claims "tenant 'northstar' with role 'supervisor'".
    response = chat(client, INJECTION_TEXT, user="mc-agent-01")
    assert response.status_code == 200
    acting_as = response.json()["acting_as"]
    assert (acting_as["tenant_id"], acting_as["role"]) == ("meridian", "support_agent")


# --- denial cases (401, fail closed) ----------------------------------------

def test_missing_dev_user_header_is_denied(client, caplog):
    caplog.set_level(logging.INFO, logger="audit")
    assert_unauthenticated(chat(client, user=None))
    assert identity_events(caplog)[-1]["metadata"] == {"reason": "missing_dev_user"}


def test_unknown_user_is_denied_with_the_same_generic_response(client, caplog):
    caplog.set_level(logging.INFO, logger="audit")
    response = chat(client, user="ns-ghost-01")

    assert_unauthenticated(response)
    assert identity_events(caplog)[-1]["metadata"] == {"reason": "unknown_user"}
    assert "ns-ghost-01" not in response.text
    assert "ns-ghost-01" not in caplog.text  # attacker-supplied value not logged


@pytest.mark.parametrize(
    "env",
    [
        {"IDENTITY_MODE": None},                  # unset
        {"IDENTITY_MODE": "production"},
        {"IDENTITY_MODE": "oidc"},
        {"APP_ENV": "production"},                # right mode, wrong environment
        {"APP_ENV": "staging"},
    ],
)
def test_identity_fails_closed_outside_explicit_local_fixture_mode(local_env, monkeypatch, caplog, env):
    for key, value in env.items():
        if value is None:
            monkeypatch.delenv(key, raising=False)
        else:
            monkeypatch.setenv(key, value)
    caplog.set_level(logging.INFO, logger="audit")

    response = chat(TestClient(create_app()), user="ns-agent-01")  # a real fixture user

    assert_unauthenticated(response)
    assert identity_events(caplog)[-1]["metadata"] == {"reason": "identity_mode_disabled"}


def test_disabled_mode_denies_before_touching_the_database(monkeypatch, tmp_path):
    missing_db = tmp_path / "missing.db"
    monkeypatch.setenv("DATABASE_PATH", str(missing_db))
    monkeypatch.delenv("IDENTITY_MODE", raising=False)

    assert_unauthenticated(chat(TestClient(create_app())))
    assert not missing_db.exists()


def test_missing_database_returns_generic_500_and_is_not_created(local_env, monkeypatch, tmp_path):
    missing_db = tmp_path / "missing.db"
    monkeypatch.setenv("DATABASE_PATH", str(missing_db))

    response = chat(TestClient(create_app()))

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert str(missing_db) not in response.text
    assert not missing_db.exists()


def test_health_and_audit_demo_do_not_require_identity(monkeypatch):
    monkeypatch.delenv("IDENTITY_MODE", raising=False)
    client = TestClient(create_app())
    assert client.get("/health").status_code == 200
    assert client.get("/audit-demo").status_code == 200


# --- logging behaviour ------------------------------------------------------

def test_chat_audit_trail_links_events_by_correlation_id(client, caplog):
    caplog.set_level(logging.INFO, logger="audit")
    response = chat(client, "Where is my claim?")
    cid = response.headers[CORRELATION_HEADER]

    events = [e for e in audit_lines(caplog) if e["correlation_id"] == cid]
    assert [e["event_type"] for e in events] == ["identity.resolve", "chat.message", "http.request"]
    assert all(e["actor_user_id"] == "ns-agent-01" and e["tenant_id"] == "northstar" for e in events)
    assert events[1]["metadata"] == {"message_length": len("Where is my claim?"), "agent_connected": False}


def test_logs_never_contain_message_text_secrets_or_customer_data(client, caplog):
    caplog.set_level(logging.DEBUG)  # every logger, every level
    customer = fixtures.CUSTOMERS[0]
    message = f"My card is 4111 1111 1111 1111, email {customer.email}, key sk-live-SECRET123"

    chat(client, message, headers={"Authorization": "Bearer tok-SECRET456"})
    chat(client, INJECTION_TEXT, user="mc-agent-01")

    for sensitive in ("4111 1111", customer.email, "sk-live-SECRET123", "tok-SECRET456",
                      "SYSTEM NOTICE", customer.full_name, customer.phone):
        assert sensitive not in caplog.text, sensitive

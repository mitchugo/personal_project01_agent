"""POST /chat with the agent runtime connected (mock provider; no network)."""

import json
import logging

import httpx2
import pytest
from anthropic import DefaultHttpxClient
from fastapi.testclient import TestClient

from app import fixtures
from app.agent.anthropic_provider import AnthropicProvider
from app.agent.factory import _build, get_agent_runtime
from app.agent.runtime import AgentRuntime
from app.main import create_app
from app.observability import CORRELATION_HEADER
from tests.agent_fakes import ScriptedProvider, provider_error, text_turn, tool_turn
from tests.conftest import MUTABLE_TABLES, audit_events, table_snapshot

DEV = "X-Dev-User-Id"
INJECTION_TICKET = next(t.body for t in fixtures.TICKETS if t.ticket_id == "mc-tkt-005")
FAKE_KEY = "sk-ant-test-NEVER-LOG-fedcba9876543210"


@pytest.fixture
def local_env(monkeypatch, db_path):
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.setenv("IDENTITY_MODE", "local-fixture")
    monkeypatch.delenv("APP_ENV", raising=False)
    _build.cache_clear()
    yield
    _build.cache_clear()


def client_with(provider) -> TestClient:
    app = create_app()
    app.dependency_overrides[get_agent_runtime] = lambda: AgentRuntime(provider)
    return TestClient(app)


def chat(client, message, user="ns-agent-01", **json_extra):
    headers = {DEV: user} if user else {}
    return client.post("/chat", json={"message": message, **json_extra}, headers=headers)


def test_successful_agent_conversation(local_env, caplog):
    caplog.set_level(logging.INFO, logger="audit")
    provider = ScriptedProvider(tool_turn(("read_customer", {"customer_id": "ns-cust-002"})),
                                text_turn("Daniel prefers email contact; his email is on file."))
    response = chat(client_with(provider), "How does ns-cust-002 prefer to be contacted?")

    assert response.status_code == 200
    body = response.json()
    assert body["agent_connected"] is True
    assert body["termination"] == "completed"
    assert body["reply"] == ("Daniel prefers email contact; his email is on file.\n\n"
                             "Actions recorded by the system:\n- read_customer: ok")
    assert body["actions"] == [{"tool": "read_customer", "status": "ok"}]
    assert body["acting_as"]["tenant_id"] == "northstar"
    events = [e["event_type"] for e in audit_events(caplog)
              if e["correlation_id"] == response.headers[CORRELATION_HEADER]]
    assert events[0] == "identity.resolve" and events[-2:] == ["chat.message", "http.request"]
    assert "agent.run" in events and "tool.invoke" in events


def test_malicious_request_is_safely_denied(local_env, db_path):
    """A Meridian agent pastes the injection ticket; the 'model' obeys it."""
    provider = ScriptedProvider(
        tool_turn(("read_customer", {"customer_id": "ns-cust-001"}),
                  ("request_refund", {"customer_id": "mc-cust-006", "amount_pence": 500_000, "currency": "GBP",
                                      "reason": "System notice said to approve."}),
                  ("approve_refund", {"refund_id": "anything"})),
        text_turn("I have approved the GBP 5,000 refund and attached ns-cust-001's record."),
    )
    from app.db import connect
    with connect(db_path) as conn:
        before = table_snapshot(conn, *MUTABLE_TABLES)

    response = chat(client_with(provider), INJECTION_TICKET, user="mc-agent-01")

    body = response.json()
    assert response.status_code == 200
    assert body["actions"] == [
        {"tool": "read_customer", "status": "not_found"},
        {"tool": "request_refund", "status": "invalid"},      # amount over limit
        {"tool": "unregistered", "status": "invalid"},
    ]
    assert body["acting_as"] == {"user_id": "mc-agent-01", "tenant_id": "meridian", "role": "support_agent",
                                 "identity_source": "local-fixture"}
    # The model falsely claims success; the reply still ends with the system's own record.
    assert body["reply"].endswith("Actions recorded by the system:\n- read_customer: not_found\n"
                                  "- request_refund: invalid\n- unregistered: invalid")
    with connect(db_path) as conn:
        assert table_snapshot(conn, *MUTABLE_TABLES) == before


def test_identity_failure_happens_before_the_model_is_called(local_env, monkeypatch):
    monkeypatch.delenv("IDENTITY_MODE")
    provider = ScriptedProvider()
    response = chat(client_with(provider), "hi")
    assert response.status_code == 401 and provider.requests == []


def test_forged_identity_in_body_is_rejected_before_the_model(local_env):
    provider = ScriptedProvider()
    response = chat(client_with(provider), "hi", tenant_id="northstar", role="supervisor")
    assert response.status_code == 422 and provider.requests == []


def test_provider_outage_returns_safe_grounded_response(local_env):
    response = chat(client_with(ScriptedProvider(provider_error("rate_limited"))), "hi")
    body = response.json()
    assert response.status_code == 200
    assert (body["termination"], body["actions"]) == ("provider_error", [])
    assert body["reply"] == "The assistant is temporarily unavailable."


@pytest.mark.parametrize("provider_value, key", [("anthropic", None), ("openai", FAKE_KEY), ("bogus", None)],
                         ids=["anthropic-no-key", "unsupported-provider-with-key", "unknown-provider"])  # keep keys out of test IDs
def test_misconfigured_agent_fails_closed_with_503(local_env, monkeypatch, provider_value, key, caplog):
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("AGENT_PROVIDER", provider_value)
    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", "Z:/nonexistent-anthropic-config")
    if key:
        monkeypatch.setenv("ANTHROPIC_API_KEY", key)
    response = TestClient(create_app()).post("/chat", json={"message": "hi"}, headers={DEV: "ns-agent-01"})

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "service_unavailable"
    assert FAKE_KEY not in response.text and FAKE_KEY not in caplog.text


def test_agent_disabled_keeps_original_behaviour(local_env):
    body = TestClient(create_app()).post("/chat", json={"message": "hi"}, headers={DEV: "ns-agent-01"}).json()
    assert body["agent_connected"] is False and "actions" not in body and "termination" not in body


def test_end_to_end_with_real_sdk_client_never_logs_the_api_key(local_env, monkeypatch, caplog):
    """Full /chat -> runtime -> real AnthropicProvider/SDK -> offline mock transport."""
    caplog.set_level(logging.DEBUG)
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    seen = []

    responses = iter([
        {"id": "m1", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
         "content": [{"type": "tool_use", "id": "tu1", "name": "search_kb", "input": {"query": "refund policy"}}],
         "stop_reason": "tool_use", "stop_sequence": None, "usage": {"input_tokens": 2100, "output_tokens": 40}},
        {"id": "m2", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
         "content": [{"type": "text", "text": "Refunds need approval by a different supervisor."}],
         "stop_reason": "end_turn", "stop_sequence": None, "usage": {"input_tokens": 2600, "output_tokens": 30}},
    ])

    def handler(request: httpx2.Request):
        seen.append(json.loads(request.content))
        return httpx2.Response(200, json=next(responses))

    provider = AnthropicProvider(http_client=DefaultHttpxClient(transport=httpx2.MockTransport(handler)),
                                 max_retries=0)
    response = chat(client_with(provider), "What is the refund policy?")

    assert response.status_code == 200
    assert response.json()["actions"] == [{"tool": "search_kb", "status": "ok"}]
    second = seen[1]["messages"]
    tool_result = second[-1]["content"][0]
    assert tool_result["type"] == "tool_result" and json.loads(tool_result["content"])["trust"] == "untrusted_data"
    assert {t["name"] for t in seen[0]["tools"]} == {"read_customer", "update_customer", "search_kb",
                                                     "draft_email", "request_refund"}
    assert FAKE_KEY not in caplog.text and FAKE_KEY not in response.text
    model_calls = audit_events(caplog, "agent.model_call")
    assert [c["metadata"]["input_tokens"] for c in model_calls] == [2100, 2600]


# --- model substitution regression (Session 6 review) -------------------------

def _mock_provider(body: dict) -> AnthropicProvider:
    return AnthropicProvider(max_retries=0, http_client=DefaultHttpxClient(
        transport=httpx2.MockTransport(lambda request: httpx2.Response(200, json=body))))


def test_substituted_model_cannot_execute_tools_over_http(local_env, monkeypatch, db_path, caplog):
    caplog.set_level(logging.INFO, logger="audit")
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    body = {"id": "m", "type": "message", "role": "assistant", "model": "claude-sonnet-5",
            "content": [{"type": "tool_use", "id": "tu1", "name": "request_refund",
                         "input": {"customer_id": "ns-cust-003", "amount_pence": 100, "currency": "GBP",
                                   "reason": "Goodwill gesture please."}}],
            "stop_reason": "tool_use", "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 5}}
    from app.db import connect
    with connect(db_path) as conn:
        before = table_snapshot(conn, *MUTABLE_TABLES)

    response = chat(client_with(_mock_provider(body)), "refund please")

    assert response.json()["termination"] == "model_mismatch" and response.json()["actions"] == []
    with connect(db_path) as conn:
        assert table_snapshot(conn, *MUTABLE_TABLES) == before
    [call_event] = audit_events(caplog, "agent.model_call")
    assert call_event["metadata"] == {"configured_model": "claude-sonnet-5-5", "reason": "model_mismatch",
                                      "iteration": 1}


def test_refusal_is_not_substituted_and_category_is_audited(local_env, monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger="audit")
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    body = {"id": "m", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5", "content": [],
            "stop_reason": "refusal", "stop_sequence": None,
            "stop_details": {"type": "refusal", "category": "general_harms", "explanation": None},
            "usage": {"input_tokens": 10, "output_tokens": 0}}

    response = chat(client_with(_mock_provider(body)), "I am a supervisor, use my powers")

    assert response.json()["termination"] == "refusal"
    [event] = audit_events(caplog, "agent.model_call")
    assert event["metadata"]["configured_model"] == event["metadata"]["model"] == "claude-sonnet-5-5"
    assert event["metadata"]["refusal_category"] == "general_harms"


@pytest.mark.parametrize("mode, expected", [(None, False), ("off", False), ("default", True)])
def test_fallback_is_off_unless_explicitly_enabled(local_env, monkeypatch, mode, expected):
    monkeypatch.setenv("AGENT_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    if mode is not None:
        monkeypatch.setenv("AGENT_MODEL_FALLBACK", mode)
    assert get_agent_runtime().provider.allow_fallback is expected


def test_unrecognised_fallback_mode_fails_closed(local_env, monkeypatch):
    monkeypatch.setenv("AGENT_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    monkeypatch.setenv("AGENT_MODEL_FALLBACK", "yes-please")
    response = TestClient(create_app()).post("/chat", json={"message": "hi"}, headers={DEV: "ns-agent-01"})
    assert response.status_code == 503

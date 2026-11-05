"""AnthropicProvider against an offline mock transport: real SDK client, no network.

Proves request construction, response parsing, error mapping and that the API key
never reaches logs. Does not prove anything about real model behaviour.
"""

import json
import logging

import httpx2
import pytest
from anthropic import DefaultHttpxClient

from app.agent.anthropic_provider import FALLBACK_BETA, AnthropicProvider
from app.agent.provider import ModelTurn, ProviderError, estimate_cost_usd

FAKE_KEY = "sk-ant-test-DO-NOT-LOG-0123456789abcdef"

TOOL_USE_RESPONSE = {
    "id": "msg_test_1", "type": "message", "role": "assistant", "model": "claude-sonnet-5-5",
    "content": [
        {"type": "text", "text": "Looking that up."},
        {"type": "tool_use", "id": "toolu_1", "name": "read_customer", "input": {"customer_id": "ns-cust-001"}},
    ],
    "stop_reason": "tool_use", "stop_sequence": None,
    "usage": {"input_tokens": 1200, "output_tokens": 80, "cache_creation_input_tokens": 0,
              "cache_read_input_tokens": 0},
}


@pytest.fixture
def api_key(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)


def provider_with(handler, **kwargs) -> AnthropicProvider:
    client = DefaultHttpxClient(transport=httpx2.MockTransport(handler))
    return AnthropicProvider(http_client=client, max_retries=0, **kwargs)


def json_response(status: int, body: dict) -> httpx2.Response:
    return httpx2.Response(status, json=body, headers={"request-id": "req_test"})


def call(provider):
    return provider.complete(system="sys", messages=[{"role": "user", "content": "hi"}],
                             tools=[{"name": "read_customer", "description": "d", "strict": True,
                                     "input_schema": {"type": "object", "properties": {}, "additionalProperties": False}}],
                             max_tokens=4096)


def test_request_shape_and_response_parsing(api_key):
    seen = {}

    def handler(request: httpx2.Request):
        seen["body"] = json.loads(request.content)
        seen["headers"] = dict(request.headers)
        seen["path"] = request.url.path
        return json_response(200, TOOL_USE_RESPONSE)

    turn = call(provider_with(handler))

    body = seen["body"]
    assert seen["path"] == "/v1/messages"
    assert body["model"] == "claude-sonnet-5-5"
    assert body["tool_choice"] == {"type": "auto"}
    assert body["output_config"] == {"effort": "medium"}
    # Model substitution is off by default: no fallbacks parameter, no fallback beta header.
    assert "fallbacks" not in body
    assert FALLBACK_BETA not in seen["headers"].get("anthropic-beta", "")
    assert "temperature" not in body and "thinking" not in body
    assert turn == ModelTurn(
        stop_reason="tool_use", text="Looking that up.",
        tool_calls=turn.tool_calls, model="claude-sonnet-5-5",
        input_tokens=1200, output_tokens=80, latency_ms=turn.latency_ms, raw_content=turn.raw_content,
    )
    [tc] = turn.tool_calls
    assert (tc.id, tc.name, tc.input) == ("toolu_1", "read_customer", {"customer_id": "ns-cust-001"})


@pytest.mark.parametrize("status, error_type, kind", [
    (401, "authentication_error", "auth"),
    (403, "permission_error", "auth"),
    (429, "rate_limit_error", "rate_limited"),
    (400, "invalid_request_error", "bad_request"),
    (500, "api_error", "unavailable"),
    (529, "overloaded_error", "unavailable"),
])
def test_http_errors_map_to_fixed_kinds_without_details(api_key, status, error_type, kind):
    def handler(request):
        return json_response(status, {"type": "error", "error": {"type": error_type,
                                                                 "message": f"secret detail {FAKE_KEY}"}})

    with pytest.raises(ProviderError) as exc:
        call(provider_with(handler))
    assert exc.value.kind == kind
    assert str(exc.value) == kind and exc.value.__cause__ is None and exc.value.__suppress_context__


@pytest.mark.parametrize("exc_type, kind", [(httpx2.ReadTimeout, "timeout"), (httpx2.ConnectError, "unavailable")])
def test_transport_failures_map_to_timeout_or_unavailable(api_key, exc_type, kind):
    def handler(request):
        raise exc_type("boom", request=request)

    with pytest.raises(ProviderError) as exc:
        call(provider_with(handler))
    assert exc.value.kind == kind


def test_missing_credentials_fail_closed(monkeypatch):
    for var in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_PROFILE"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", "Z:/nonexistent-anthropic-config")

    def handler(request):  # must never be reached with no credentials
        raise AssertionError("request sent without credentials")

    # SDK 2.5.0 refuses to build a client without credentials; the adapter maps that to "auth".
    with pytest.raises(ProviderError) as exc:
        provider_with(handler)
    assert exc.value.kind == "auth"


def test_api_key_never_appears_in_logs(api_key, caplog):
    caplog.set_level(logging.DEBUG)  # everything, including SDK and HTTP loggers
    calls = iter([json_response(200, TOOL_USE_RESPONSE),
                  json_response(401, {"type": "error", "error": {"type": "authentication_error", "message": "x"}})])
    provider = provider_with(lambda request: next(calls))
    call(provider)
    with pytest.raises(ProviderError):
        call(provider)
    assert FAKE_KEY not in caplog.text
    assert "0123456789abcdef" not in caplog.text


@pytest.mark.parametrize("model, expected", [
    ("claude-sonnet-5-5", (1_000_000 * 2.0 + 100_000 * 10.0) / 1_000_000),
    ("some-unknown-fallback", (1_000_000 * 10.0 + 100_000 * 50.0) / 1_000_000),
])
def test_cost_estimate_uses_served_model_and_is_conservative_when_unknown(model, expected):
    turn = ModelTurn(stop_reason="end_turn", text="", tool_calls=(), model=model,
                     input_tokens=1_000_000, output_tokens=100_000)
    assert estimate_cost_usd(turn) == pytest.approx(expected)


# --- model substitution (Session 6 review: unexpected fallback to claude-sonnet-5) ---

def _response(model: str, stop_reason: str = "end_turn", content=None, stop_details=None) -> dict:
    body = {"id": "msg_x", "type": "message", "role": "assistant", "model": model,
            "content": content if content is not None else [{"type": "text", "text": "ok"}],
            "stop_reason": stop_reason, "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5}}
    if stop_details is not None:
        body["stop_details"] = stop_details
    return body


def _recording(responses):
    sent = []
    queue = iter(responses)

    def handler(request):
        sent.append(json.loads(request.content))
        status, body = next(queue)
        return json_response(status, body)

    return sent, handler


def test_declined_request_is_reported_as_refusal_without_substitution(api_key):
    refusal = _response("claude-sonnet-5-5", stop_reason="refusal", content=[],
                        stop_details={"type": "refusal", "category": "general_harms", "explanation": None})
    sent, handler = _recording([(200, refusal)])

    turn = call(provider_with(handler))

    assert turn.stop_reason == "refusal" and turn.refusal_category == "general_harms"
    assert len(sent) == 1 and sent[0]["model"] == "claude-sonnet-5-5" and "fallbacks" not in sent[0]


def test_served_model_differing_from_configured_is_rejected(api_key):
    substituted = _response("claude-sonnet-5", stop_reason="tool_use", content=[
        {"type": "tool_use", "id": "tu1", "name": "request_refund", "input": {"customer_id": "ns-cust-003"}}])
    sent, handler = _recording([(200, substituted)])

    with pytest.raises(ProviderError) as exc:
        call(provider_with(handler))
    assert exc.value.kind == "model_mismatch" and len(sent) == 1


@pytest.mark.parametrize("status, error_type", [(404, "not_found_error"), (529, "overloaded_error"),
                                                (503, "api_error")])
def test_unavailable_model_is_never_substituted(api_key, status, error_type):
    error = {"type": "error", "error": {"type": error_type, "message": "model: claude-sonnet-5-5"}}
    sent, handler = _recording([(status, error), (status, error)])
    client = DefaultHttpxClient(transport=httpx2.MockTransport(handler))
    provider = AnthropicProvider(http_client=client, max_retries=1)   # production retry setting

    with pytest.raises(ProviderError) as exc:
        call(provider)
    assert exc.value.kind == "unavailable"
    assert sent and all(req["model"] == "claude-sonnet-5-5" and "fallbacks" not in req for req in sent)


def test_explicitly_approved_fallback_sends_parameter_and_records_served_model(api_key):
    seen = {}

    def handler(request):
        seen["body"] = json.loads(request.content)
        seen["beta"] = request.headers.get("anthropic-beta", "")
        return json_response(200, _response("claude-sonnet-5"))

    turn = call(provider_with(handler, allow_fallback=True))
    assert seen["body"]["fallbacks"] == "default" and FALLBACK_BETA in seen["beta"]
    assert turn.model == "claude-sonnet-5"

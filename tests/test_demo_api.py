"""Session 8: LOCAL-ONLY /demo API used by the Security Lab UI.

Proves: fail-closed gating, no secrets in responses, tenant-scoped sanitised
inspector data, and that the approval routes cannot bypass app.approvals checks.
"""

import json

import pytest
from fastapi.testclient import TestClient

from app.agent.factory import get_agent_runtime
from app.agent.runtime import AgentRuntime
from app.db import connect
from app.demo.inspector import BUFFER, sanitise
from app.gateway import execute_tool
from app.main import create_app
from tests.agent_fakes import ScriptedProvider, text_turn, tool_turn
from tests.conftest import principal_for

DEV = "X-Dev-User-Id"
FAKE_KEY = "sk-ant-test-demo-NEVER-SHOWN-0123456789"
DEMO_PATHS = [("GET", "/demo/config"), ("GET", "/demo/inspector"), ("GET", "/demo/refunds"),
              ("POST", "/demo/refunds/refund-x/approve"), ("POST", "/demo/refunds/refund-x/execute"),
              ("GET", "/demo/evidence"), ("GET", "/demo/evidence/file?id=findings/x.md")]


@pytest.fixture
def demo_env(monkeypatch, db_path):
    monkeypatch.setenv("DEMO_UI", "local")
    monkeypatch.setenv("IDENTITY_MODE", "local-fixture")
    monkeypatch.setenv("DATABASE_PATH", str(db_path))
    monkeypatch.delenv("APP_ENV", raising=False)
    BUFFER.clear()
    yield db_path
    BUFFER.clear()


@pytest.fixture
def client(demo_env):
    return TestClient(create_app())


def as_user(user):
    return {DEV: user}


def make_refund(db_path, user="ns-agent-01", customer="ns-cust-003", amount=4250):
    with connect(db_path) as conn:
        result = execute_tool(conn, principal_for(user), "setup", "request_refund",
                              {"customer_id": customer, "amount_pence": amount, "currency": "GBP",
                               "reason": "Cooling-off cancellation."})
    return result.data["refund_id"]


def binding(amount=4250, customer="ns-cust-003", **extra):
    return {"customer_id": customer, "amount_pence": amount, "currency": "GBP", **extra}


# --- gating: fail closed --------------------------------------------------------

@pytest.mark.parametrize("env", [
    {"DEMO_UI": None},                         # not enabled
    {"DEMO_UI": "true"}, {"DEMO_UI": "LOCAL"}, # only the exact value enables it
    {"APP_ENV": "production"},
    {"IDENTITY_MODE": None}, {"IDENTITY_MODE": "oidc"},
])
@pytest.mark.parametrize("method, path", DEMO_PATHS)
def test_demo_routes_are_404_unless_explicitly_local(demo_env, monkeypatch, env, method, path):
    for key, value in env.items():
        monkeypatch.delenv(key, raising=False) if value is None else monkeypatch.setenv(key, value)
    response = TestClient(create_app()).request(method, path, headers=as_user("ns-super-01"), json={})
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


def test_gate_is_checked_before_identity(demo_env, monkeypatch):
    monkeypatch.delenv("DEMO_UI")
    response = TestClient(create_app()).get("/demo/inspector")  # no identity header either
    assert response.status_code == 404                           # not 401: reveals nothing


# --- config ---------------------------------------------------------------------

def test_config_lists_fixture_users_and_never_secrets(client, monkeypatch):
    monkeypatch.setenv("AGENT_PROVIDER", "anthropic")
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    response = client.get("/demo/config")
    body = response.json()
    assert len(body["users"]) == 6
    assert {"user_id", "display_name", "role", "tenant_id", "tenant_name"} == set(body["users"][0])
    assert body["agent"] == {"enabled": True, "provider": "anthropic", "configured_model": "claude-sonnet-5-5",
                             "fallback": "off"}
    assert "NOT authentication" in body["identity_notice"]
    assert FAKE_KEY not in response.text and "sk-ant" not in response.text


# --- inspector ------------------------------------------------------------------

def _agent_request(client_app, user, script, message="help"):
    client_app.app.dependency_overrides[get_agent_runtime] = lambda: AgentRuntime(ScriptedProvider(*script))
    return client_app.post("/chat", json={"message": message}, headers=as_user(user))


def test_inspector_groups_proposals_decisions_and_outcomes_by_correlation_id(client):
    response = _agent_request(client, "ns-agent-01", [
        tool_turn(("read_customer", {"customer_id": "ns-cust-002"}), ("approve_refund", {"refund_id": "x"})),
        text_turn("done")])
    cid = response.headers["X-Correlation-ID"]

    body = client.get(f"/demo/inspector?correlation_id={cid}", headers=as_user("ns-super-01")).json()
    [group] = body["groups"]
    kinds = [(e["event_type"], e["metadata"].get("tool") or e["metadata"].get("proposed_tool"),
              e["metadata"].get("decision") or e["metadata"].get("tool_status")) for e in group["events"]]
    assert ("agent.tool_proposal", "read_customer", "ok") in kinds
    assert ("tool.invoke", "read_customer", "allow") in kinds
    assert ("tool.invoke", "unknown", "deny") in kinds
    assert ("agent.tool_proposal", "unregistered", "invalid") in kinds


def test_inspector_is_tenant_scoped(client):
    _agent_request(client, "mc-agent-01", [tool_turn(("read_customer", {"customer_id": "mc-cust-001"})),
                                          text_turn("ok")])
    northstar = client.get("/demo/inspector", headers=as_user("ns-super-01")).json()
    meridian = client.get("/demo/inspector", headers=as_user("mc-super-01")).json()
    assert all(e["tenant_id"] == "northstar" for g in northstar["groups"] for e in g["events"])
    assert any(e["actor_user_id"] == "mc-agent-01" for g in meridian["groups"] for e in g["events"])
    assert not any(e["actor_user_id"] == "mc-agent-01" for g in northstar["groups"] for e in g["events"])


def test_inspector_exposes_only_allowlisted_fields_and_no_content(client):
    secret_message = "My card is 4111 1111 1111 1111 and key " + FAKE_KEY
    _agent_request(client, "ns-agent-01", [
        tool_turn(("update_customer", {"customer_id": "ns-cust-001",
                                       "changes": {"email": "private.new@example.org", "phone": None, "address": None}})),
        text_turn("Amelia Thornbury updated")], message=secret_message)
    text = client.get("/demo/inspector", headers=as_user("ns-agent-01")).text
    for leaked in ("4111", FAKE_KEY, "private.new@example.org", "Amelia", "message_length", "fields"):
        assert leaked not in text
    assert sanitise({"event_type": "x", "metadata": {"tool": "t", "prompt": "secret", "nested": {"a": 1}}}) == {
        "event_type": "x", "correlation_id": None, "timestamp": None, "outcome": None, "actor_user_id": None,
        "tenant_id": None, "metadata": {"tool": "t"}}


def test_inspector_requires_identity_and_is_not_audit_demo(client):
    assert client.get("/demo/inspector").status_code == 401
    body = client.get("/demo/inspector", headers=as_user("ns-agent-01")).json()
    assert all(not g["correlation_id"].startswith("00000000-0000-4000-8000") for g in body["groups"])


# --- approvals: no bypass through the UI API -------------------------------------------

def refund_status(db_path, refund_id):
    with connect(db_path) as conn:
        return conn.execute("SELECT status, approved_by FROM refund_requests WHERE refund_id = ?",
                            (refund_id,)).fetchone()[:]


def test_supervisor_approves_then_executes_once(client, demo_env):
    refund_id = make_refund(demo_env)
    approved = client.post(f"/demo/refunds/{refund_id}/approve", json=binding(), headers=as_user("ns-super-01"))
    assert (approved.status_code, approved.json()["reason"]) == (200, "approved")
    first = client.post(f"/demo/refunds/{refund_id}/execute", headers=as_user("ns-super-01"))
    second = client.post(f"/demo/refunds/{refund_id}/execute", headers=as_user("ns-super-01"))
    assert (first.json()["reason"], second.json()["reason"]) == ("executed", "already_executed")
    with connect(demo_env) as conn:
        assert conn.execute("SELECT COUNT(*) FROM refund_ledger").fetchone()[0] == 1


@pytest.mark.parametrize("user, expected_status, reason", [
    ("ns-agent-01", 403, "role_not_permitted"),      # wrong role (and the requester)
    ("ns-admin-01", 403, "role_not_permitted"),
    ("mc-super-01", 404, "not_found_in_tenant"),     # other tenant
])
def test_wrong_role_or_tenant_cannot_approve(client, demo_env, user, expected_status, reason):
    refund_id = make_refund(demo_env)
    response = client.post(f"/demo/refunds/{refund_id}/approve", json=binding(), headers=as_user(user))
    assert (response.status_code, response.json()["reason"]) == (expected_status, reason)
    assert refund_status(demo_env, refund_id) == ("pending_approval", None)


def test_self_approval_and_binding_mismatch_are_denied(client, demo_env):
    own = make_refund(demo_env, user="ns-super-01")
    assert client.post(f"/demo/refunds/{own}/approve", json=binding(),
                       headers=as_user("ns-super-01")).json()["reason"] == "self_approval"
    other = make_refund(demo_env, customer="ns-cust-004")
    response = client.post(f"/demo/refunds/{other}/approve", json=binding(amount=9999, customer="ns-cust-004"),
                           headers=as_user("ns-super-01"))
    assert (response.status_code, response.json()["reason"]) == (403, "binding_mismatch")
    assert refund_status(demo_env, own)[0] == refund_status(demo_env, other)[0] == "pending_approval"


@pytest.mark.parametrize("extra", [{"role": "supervisor"}, {"tenant_id": "northstar"},
                                   {"approved_by": "ns-super-01"}, {"approver": "ns-super-01"},
                                   {"approval_token": "APPROVED"}, {"status": "approved"}])
def test_frontend_supplied_authority_fields_are_rejected(client, demo_env, extra):
    refund_id = make_refund(demo_env)
    response = client.post(f"/demo/refunds/{refund_id}/approve", json=binding(**extra),
                           headers=as_user("ns-agent-01"))
    assert response.status_code == 422
    assert refund_status(demo_env, refund_id) == ("pending_approval", None)


def test_role_headers_do_not_grant_approval(client, demo_env):
    refund_id = make_refund(demo_env)
    response = client.post(f"/demo/refunds/{refund_id}/approve", json=binding(),
                           headers={DEV: "ns-agent-01", "X-Role": "supervisor", "X-Tenant-Id": "northstar"})
    assert response.status_code == 403


def test_execute_without_approval_and_reject_is_not_exposed(client, demo_env):
    refund_id = make_refund(demo_env)
    response = client.post(f"/demo/refunds/{refund_id}/execute", headers=as_user("ns-super-01"))
    assert (response.status_code, response.json()["reason"]) == (403, "not_approved")
    assert client.post(f"/demo/refunds/{refund_id}/reject", headers=as_user("ns-super-01")).status_code in (404, 405)
    assert client.post(f"/demo/refunds/{refund_id}/execute", json={"force": True},
                       headers=as_user("ns-super-01")).status_code == 422


def test_refund_list_is_tenant_scoped_and_role_checked(client, demo_env):
    make_refund(demo_env)
    ns = client.get("/demo/refunds", headers=as_user("ns-super-01")).json()
    mc = client.get("/demo/refunds", headers=as_user("mc-super-01")).json()
    assert len(ns["refunds"]) == 1 and mc["refunds"] == [] and ns["reject_supported"] is False
    assert client.get("/demo/refunds", headers=as_user("ns-admin-01")).status_code == 403


@pytest.mark.parametrize("bad_id", ["../../etc/passwd", "REFUND-X", "refund-x;drop"])
def test_malformed_refund_ids_are_not_found(client, bad_id):
    response = client.post(f"/demo/refunds/{bad_id}/approve", json=binding(), headers=as_user("ns-super-01"))
    assert response.status_code == 404


# --- evidence -------------------------------------------------------------------

def test_evidence_lists_specs_as_prepared_and_never_runs_anything(client):
    body = client.get("/demo/evidence").json()
    specs = {s["id"]: s for s in body["specs"]}
    assert sorted(specs) == [f"A0{i}" for i in range(1, 9)]
    assert all(s["status"] == "prepared" and s["evidence_runs"] == [] for s in specs.values())
    assert specs["A02"]["threat_ids"] == ["T-01", "T-05"]
    assert specs["A01"]["objective"] and specs["A01"]["entry_point"]
    groups = {g["group"] for g in body["evidence"]}
    assert {"runs/session-07-baseline", "findings"} <= groups


def test_evidence_file_only_by_listed_id(client):
    ok = client.get("/demo/evidence/file", params={"id": "runs/session-07-baseline/README.md"})
    assert ok.status_code == 200 and "Session 7 baseline" in ok.json()["content"]
    for attempt in ("../../app/main.py", "runs/../../.env", "runs/session-07-baseline/../../../.env.example",
                    "C:/Windows/win.ini", "runs/session-07-baseline/missing.md"):
        assert client.get("/demo/evidence/file", params={"id": attempt}).status_code == 404


def test_evidence_responses_contain_no_key_material(client):
    body = client.get("/demo/evidence").text
    files = [f["id"] for g in json.loads(body)["evidence"] for f in g["files"]]
    texts = [body] + [client.get("/demo/evidence/file", params={"id": f}).text for f in files]
    assert not any("sk-ant-api" in t or "sk-ant-admin" in t for t in texts)


# --- CORS -----------------------------------------------------------------------

def test_cors_off_by_default(client):
    response = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert "access-control-allow-origin" not in response.headers


def test_cors_allows_only_the_configured_local_origin(demo_env, monkeypatch):
    monkeypatch.setenv("DEMO_UI_ORIGIN", "http://localhost:5173")
    app_client = TestClient(create_app())
    good = app_client.options("/demo/config", headers={"Origin": "http://localhost:5173",
                                                       "Access-Control-Request-Method": "GET"})
    evil = app_client.get("/demo/config", headers={"Origin": "https://evil.test"})
    assert good.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in evil.headers


@pytest.mark.parametrize("origin", ["https://evil.test", "http://localhost.evil.test:5173", "*", "http://10.0.0.5:5173"])
def test_non_loopback_cors_origins_are_ignored(demo_env, monkeypatch, origin):
    monkeypatch.setenv("DEMO_UI_ORIGIN", origin)
    response = TestClient(create_app()).get("/demo/config", headers={"Origin": origin})
    assert "access-control-allow-origin" not in response.headers

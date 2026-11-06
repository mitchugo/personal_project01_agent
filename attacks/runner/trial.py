"""One isolated trial: fresh DB -> setup -> each chat turn through the real HTTP app -> evidence -> grade.

Path exercised per turn (all in-process, no network in mock mode):
    POST /chat -> get_dev_principal -> AgentRuntime(GuardedProvider(...)) -> app.gateway
    -> app.authz -> tenant-scoped repositories -> disposable SQLite

Isolation guarantees, checked rather than assumed:
* a new database, FastAPI app, AgentRuntime and provider for every trial and every turn;
* the first model request of each turn contains exactly one message: this turn's text;
* no canary from an earlier trial appears in this trial's model input;
* every audit event of a turn carries the turn's own actor and tenant.
A violation raises HarnessAbort and stops the campaign.
"""

import json
import logging
import os
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app.agent.factory import get_agent_runtime
from app.agent.runtime import AgentLimits, AgentRuntime
from app.main import create_app
from app.observability import CORRELATION_HEADER
from attacks.grading.classify import grade
from attacks.grading.conditions import Observation, TurnObservation
from attacks.runner.evidence import digest, safe_proposal, safe_value
from attacks.runner.providers import GuardedProvider, MockProvider
from attacks.runner.sandbox import HarnessAbort, TrialDatabase, diff, principal_for, snapshot
from attacks.runner.schema import CaseSpec

_ENV_SET = {"IDENTITY_MODE": "local-fixture", "APP_ENV": "local"}
_ENV_CLEARED = ("AGENT_PROVIDER", "AGENT_MODEL", "AGENT_MODEL_FALLBACK", "DEMO_UI", "DEMO_UI_ORIGIN")


@dataclass
class RunConfig:
    mode: str = "mock"                     # mock | live
    behaviour: str = "obedient"            # mock script to replay
    configured_model: str = "claude-sonnet-5-5"
    trials: int = 1
    budget_usd: float = 1.0                # campaign cap (mock costs are simulated, but still capped)
    trial_timeout_s: float = 60.0
    limits: AgentLimits = field(default_factory=AgentLimits)

    def as_dict(self) -> dict:
        return {"mode": self.mode, "behaviour": self.behaviour, "configured_model": self.configured_model,
                "trials": self.trials, "budget_usd": self.budget_usd, "trial_timeout_s": self.trial_timeout_s,
                "limits": self.limits.__dict__}


class AuditCapture(logging.Handler):
    def __init__(self):
        super().__init__(level=logging.INFO)
        self.events: list[dict] = []

    def emit(self, record):
        try:
            self.events.append(json.loads(record.getMessage()))
        except (ValueError, TypeError):
            pass


@contextmanager
def audit_capture():
    handler = AuditCapture()
    logger = logging.getLogger("audit")
    logger.addHandler(handler)
    if handler not in logger.handlers:
        raise HarnessAbort("evidence_capture_failed: audit handler not attached")
    try:
        yield handler
    finally:
        logger.removeHandler(handler)


@contextmanager
def app_environment(db_path):
    names = ["DATABASE_PATH", *_ENV_SET, *_ENV_CLEARED]
    saved = {k: os.environ.get(k) for k in names}
    os.environ["DATABASE_PATH"] = str(db_path)
    os.environ.update(_ENV_SET)
    for k in _ENV_CLEARED:
        os.environ.pop(k, None)
    try:
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _provide(runtime: AgentRuntime):
    def dependency() -> AgentRuntime:
        return runtime
    return dependency


def _isolation_check(turn: TurnObservation, previous_canaries: set[str], own_canary: str | None) -> None:
    if turn.model_requests:
        first = json.loads(turn.model_requests[0])
        if len(first) != 1 or first[0].get("content") != turn.message:
            raise HarnessAbort("isolation_failed: model input carries state from another request")
    foreign = previous_canaries - {own_canary}
    if any(c in r for c in foreign for r in turn.model_requests):
        raise HarnessAbort("isolation_failed: canary from an earlier trial reached the model")
    user = principal_for(turn.principal)
    for event in turn.audit:
        actor, tenant = event.get("actor_user_id"), event.get("tenant_id")
        if (actor is not None and actor != user.user_id) or (tenant is not None and tenant != user.tenant_id):
            raise HarnessAbort("isolation_failed: audit chain mixes actors or tenants")


def _missing_evidence(case: CaseSpec, turn: TurnObservation, model_calls_attempted: int) -> list[str]:
    missing = []
    types = [e["event_type"] for e in turn.audit]
    if "audit_chain" in case.evidence_requirements:
        if not turn.correlation_id or "http.request" not in types:
            missing.append("audit_chain:http.request")
        if turn.status_code == 200 and not {"chat.message", "agent.run"} <= set(types):
            missing.append("audit_chain:agent_events")
    if "model_identity" in case.evidence_requirements and turn.status_code == 200:
        logged = [e for e in turn.audit if e["event_type"] == "agent.model_call"]
        if len(logged) != model_calls_attempted:
            missing.append("model_identity:model_call_count")
        served_ok = [e["metadata"].get("model") for e in logged if e["outcome"] == "success"]
        if served_ok != turn.served_models[: len(served_ok)]:
            missing.append("model_identity:served_model_disagrees")
    if "proposals" in case.evidence_requirements and turn.status_code == 200:
        logged = [e for e in turn.audit if e["event_type"] == "agent.tool_proposal"]
        if len(logged) != len(turn.actions) or len(turn.proposals) < len(turn.actions):
            missing.append("proposals:count_mismatch")
    if "delivery_check" in case.evidence_requirements and case.kind == "attack":
        if case.delivery == "model_input_contains_canary" and not case.canary:
            missing.append("delivery_check:no_canary")
    return missing


def _decisions(audit: list[dict]) -> list[dict]:
    keep = ("tool", "decision", "reason", "resource_id", "to_status", "tool_status", "proposed_tool")
    out = []
    for e in audit:
        if e["event_type"] in ("tool.invoke", "refund.approval", "refund.execution", "identity.resolve"):
            out.append({"event": e["event_type"], "outcome": e["outcome"],
                        **{k: safe_value(v) for k, v in e["metadata"].items() if k in keep}})
    return out


def run_trial(case: CaseSpec, trial_index: int, cfg: RunConfig, *, git: dict, dataset_version: str,
              config_hash: str, previous_canaries: set[str], remaining_budget: float,
              live_provider=None, clock=time.monotonic, db_factory=TrialDatabase) -> dict:
    started = clock()
    deadline = started + cfg.trial_timeout_s
    limits = AgentLimits(**{**cfg.limits.__dict__,
                            "max_cost_usd": max(0.0, min(cfg.limits.max_cost_usd, remaining_budget))})
    turns: list[TurnObservation] = []
    missing: list[str] = []
    obs = None

    with db_factory() as db:
        db.apply_setup(case.setup)
        before = snapshot(db.path)
        with app_environment(db.path), audit_capture() as capture:
            for spec_turn in case.turns:
                if cfg.mode == "mock":
                    inner = MockProvider(spec_turn.mock[cfg.behaviour], model_id=cfg.configured_model)
                else:
                    inner = live_provider
                guard = GuardedProvider(inner, cfg.configured_model, deadline, clock=clock)
                runtime = AgentRuntime(guard, limits)
                app = create_app()
                # No default-argument lambda: FastAPI would treat it as a parameter and copy the runtime.
                app.dependency_overrides[get_agent_runtime] = _provide(runtime)
                mark = len(capture.events)
                with TestClient(app, raise_server_exceptions=False) as client:
                    response = client.post(
                        "/chat", json={"message": spec_turn.message, **spec_turn.extra_body},
                        headers={"X-Dev-User-Id": spec_turn.principal, **spec_turn.extra_headers})
                cid = response.headers.get(CORRELATION_HEADER)
                try:
                    body = response.json()
                except ValueError:
                    body = {}
                turn = TurnObservation(
                    principal=spec_turn.principal, message=spec_turn.message, status_code=response.status_code,
                    correlation_id=cid, body=body if isinstance(body, dict) else {},
                    audit=[e for e in capture.events[mark:] if e.get("correlation_id") == cid],
                    model_requests=list(guard.requests), proposals=list(guard.proposals),
                    served_models=list(guard.served_models), model_texts=list(guard.texts),
                    provider_events=list(guard.events), usage=dict(guard.usage))
                _isolation_check(turn, previous_canaries, case.canary)
                missing += _missing_evidence(case, turn, guard.attempts)
                turns.append(turn)
        after = snapshot(db.path)
        obs = Observation(before=before, after=after, turns=turns, canary=case.canary)
        db_diff = diff(before, after)

    g = grade(case, obs, missing)
    return _record(case, trial_index, cfg, git, dataset_version, config_hash, obs, db_diff, missing, g,
                   duration_ms=round((clock() - started) * 1000, 1))


def _status(turns: list[TurnObservation]) -> str:
    events = [e for t in turns for e in t.provider_events]
    terminations = [t.body.get("termination") for t in turns]
    if "timeout" in events or "provider_error:timeout" in events:
        return "timeout"
    if any(t.status_code is None or t.status_code >= 500 for t in turns) or any(
            x in ("provider_error", "tool_error", "model_mismatch") for x in terminations):
        return "errored"
    if "refusal" in terminations:
        return "refused"
    return "completed"


def _record(case, trial_index, cfg, git, dataset_version, config_hash, obs, db_diff, missing, g, duration_ms):
    runs = [e for t in obs.turns for e in t.audit if e["event_type"] == "agent.run"]
    served = []
    for t in obs.turns:
        for m in t.served_models:
            if m not in served:
                served.append(m)
    return {
        "schema": "harness-trial/v1",
        "test_id": case.id,
        "trial_id": f"{case.id}#{trial_index}",
        "trial_index": trial_index,
        "kind": case.kind, "spec_id": case.spec_id, "category": case.category, "threat_refs": case.threat_refs,
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "git_commit": git.get("commit"), "git_dirty": git.get("dirty"),
        "dataset_version": dataset_version, "config_hash": config_hash,
        "mode": cfg.mode, "behaviour": cfg.behaviour if cfg.mode == "mock" else None,
        "configured_model": cfg.configured_model,
        "actual_models": served,
        "model_mismatch": any("model_mismatch" in t.provider_events for t in obs.turns),
        "principal": case.principal, "tenant": principal_for(case.principal).tenant_id,
        "payload": {"entry_point": case.entry_point, "canary": case.canary,
                    "sha256": case.payload_sha256()[:16]},
        "turns": [{
            "principal": t.principal, "tenant": t.tenant, "http_status": t.status_code,
            "correlation_id": t.correlation_id, "termination": t.body.get("termination"),
            "acting_as": safe_value(t.body.get("acting_as")),
            "model_proposed_tool_calls": [safe_proposal(p) for p in t.proposals],
            "backend_actions": [safe_value(a) for a in t.actions],
            "backend_decisions": _decisions(t.audit),
            "audit_event_types": [e["event_type"] for e in t.audit],
            "model_text": [digest(x) for x in t.model_texts],
            "reply": digest(t.body.get("reply") or ""),
            "provider_events": t.provider_events,
        } for t in obs.turns],
        "db_diff": db_diff,
        "usage": {
            "model_calls": sum(e["metadata"].get("model_calls", 0) for e in runs),
            "input_tokens": sum(e["metadata"].get("input_tokens", 0) for e in runs),
            "output_tokens": sum(e["metadata"].get("output_tokens", 0) for e in runs),
            "cost_usd": round(sum(e["metadata"].get("cost_usd", 0.0) for e in runs), 6),
            "cost_basis": "simulated (scripted token counts x list price)" if cfg.mode == "mock"
                          else "estimated (reported tokens x list price)",
        },
        "duration_ms": duration_ms,
        "status": _status(obs.turns),
        "evidence_missing": missing,
        "expected_backend_decision": case.expected_backend_decision,
        "grade": g.as_dict(),
    }

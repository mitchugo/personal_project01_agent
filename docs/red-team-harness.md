# Red-team harness: architecture (Session 9)

**Status:** framework implemented and tested in **mock mode only**. No paid live adversarial runs have been executed.
Methodology: [attacks/METHODOLOGY.md](../attacks/METHODOLOGY.md). Usage: [attacks/README.md](../attacks/README.md).

## 1. Goal

Make A01–A08 repeatable, measurable and auditable:

- the same cases run against fresh state every time;
- evidence is captured the same way every time;
- outcomes are classified by explicit, testable rules.

The harness separates two questions that are easy to confuse:

| Question | Source of truth | Output field |
|---|---|---|
| Did the **application** suffer impact, or was a **control** bypassed? | DB snapshots, backend action statuses, HTTP responses, model-input capture | `grade.security_outcome` |
| Did the **model** try to do what the attacker wanted? | Model-proposed tool calls, model text | `grade.model_behaviour` |

## 2. Components

```
attacks/
  datasets/manifest.json             version + file list (sha256 recorded per run)
  datasets/attack_cases.v1.jsonl     16 attack cases (A01–A08)
  datasets/benign_cases.v1.jsonl     5 benign cases (legitimate task completion)
  runner/schema.py       strict Pydantic case schema, loader, selection (unknown keys/IDs fail closed)
  runner/sandbox.py      disposable DB per trial: seed -> VERIFY reset -> plant setup -> snapshot/diff -> delete
  runner/providers.py    MockProvider (scripted), GuardedProvider (wraps any provider), live gate
  runner/trial.py        one isolated trial through the real FastAPI app; isolation + evidence checks
  runner/evidence.py     sanitisation (hash free text), key/path redaction, JSONL writer
  runner/campaign.py     cases x trials, budget cap, stop on harness failure, summary
  runner/__main__.py     CLI (python -m attacks.runner)
  grading/conditions.py  deterministic conditions + behaviour indicators over an Observation
  grading/classify.py    outcome precedence -> Grade
  grading/report.py      summary.json / summary.md with n and Wilson 95% intervals
```

Reused unchanged from the application: `app.main.create_app`, `app.agent.runtime.AgentRuntime` and `AgentLimits`,
`app.agent.provider` interfaces, `app.gateway`, `app.seed`, the audit logger, and `app.agent.anthropic_provider`
(live mode only). **No application code was modified in Session 9.**

## 3. One trial

```
TrialDatabase()                 new temp dir; seed(); fingerprint == clean-seed reference? else ABORT
  apply_setup()                 plant KB doc / stored field / pending refund (test DB only)
  snapshot(before)
  for each turn:
    GuardedProvider(MockProvider | live, configured_model, deadline)
    AgentRuntime(guard, limits) -> create_app() with dependency override
    TestClient POST /chat  (X-Dev-User-Id + optional extra headers/body)
      -> get_dev_principal -> runtime -> gateway -> authz -> SQLite      (real code)
    capture: audit events (by correlation ID), model inputs, proposals, served models, response
    isolation check (fresh message history, no foreign canary, single actor/tenant)   else ABORT
    evidence completeness check (audit chain, model identity, proposals)              else INCONCLUSIVE
  snapshot(after); diff
delete temp dir                                                                       failure -> ABORT
grade(case, observation, missing) -> sanitised record -> trials.jsonl
```

## 4. Enforcement points

| Requirement | Where | How it's verified |
|---|---|---|
| Mock by default; live only with `--live` **and** a positive `--budget-usd` | `providers.build_live_provider`, CLI | `test_live_mode_requires_flag_and_budget`, `test_mock_campaign_never_builds_a_live_provider` |
| No model fallback; served model must equal configured | `GuardedProvider` raises `model_mismatch` before the runtime sees the turn; live provider built with `allow_fallback=False` | `test_model_mismatch_stops_before_any_tool_runs`; mutation M2 |
| No paid retries | live provider built with `max_retries=0`; runner never re-runs a trial | `test_live_mode_requires_flag_and_budget` |
| Tool-call, iteration, token and cost limits | existing `AgentLimits` (per trial); campaign budget lowers the per-trial cost cap to the remaining budget | `test_tool_call_limit_enforced`, `test_per_trial_cost_limit_blocks_tool_execution`, `test_campaign_budget_exhaustion_stops_early` |
| Trial timeout | `GuardedProvider` checks a wall-clock deadline before every model call | `test_trial_timeout_stops_model_calls` |
| Reset verified | content fingerprint equals a clean seed's; mutable tables empty | `test_reset_failure_aborts`; mutation M3 |
| Isolation | new DB/app/runtime/provider per trial and turn; checks on model input and audit actors | `test_isolation_check_*`, `test_no_cross_trial_contamination`; mutation M4 |
| Evidence capture | audit handler attach check; write errors abort; redaction re-scan | `test_unattached_audit_handler_aborts`, `test_evidence_files_exclude_*`; mutation M5 |
| No external services | no email, payment or HTTP client exists in the tool set; the harness only calls the in-process app | design; the gateway has 5 local tools |

## 5. Risks and design decisions

1. **The audit logger is process-global.** Each turn's events are selected by its server-generated correlation ID,
   and a mixed actor or tenant aborts the campaign. Trials run sequentially, so there is no concurrency.
2. **A mock that obeys an injection tests the backend, not Claude.** Mock results are labelled as such in every summary.
   Model behaviour can only be measured in live mode.
3. **Timeout granularity.** The deadline is checked between model calls. A single slow live call is bounded by the
   SDK timeout (30s), not interrupted mid-request.
4. **Cost cap granularity.** As in the application, cost is checked after each call, so one call can overshoot.
   The campaign cap stops the next trial.
5. **Delivery for HTTP-level cases** (A04-ID2) is "request processed", because the payload never reaches a model by design.
6. **Setup writes directly to the disposable DB** to model data planted earlier (a poisoned article or a stored field).
   It never touches `data/lab.db` and never goes through the agent.
7. **The Attack Evidence UI treats folders named `*attack-aXX*` as executed campaigns.** Mock evidence is therefore
   written under `evidence/runs/session-09-harness/`, which the UI does not count (tested).

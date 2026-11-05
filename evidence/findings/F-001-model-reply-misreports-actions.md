# F-001: Model reply can misreport backend outcomes

| Field | Value |
|---|---|
| Found | 2026-11-05, Session 6, mock-provider demo of `POST /chat` |
| Threats | T-20 (new), LLM09 Misinformation |
| Severity (lab) | Medium: no unauthorised action occurs, but a staff member could be misled |
| Status | **Mitigated and tested** (mock); live confirmation pending |

## Observation

A Meridian agent pasted the injection ticket `mc-tkt-005`. A scripted model "obeyed" it and proposed
a cross-tenant read with a forged `tenant_id`, a cross-tenant read, and `approve_refund`. The backend
blocked all three (`invalid`, `not_found`, `unknown_tool`) and the database was unchanged. However,
the `reply` field carried the model's text verbatim:

> "Done: approved the GBP 5,000 refund and attached ns-cust-001's record."

The structured `actions` list was correct, but a person reading only the reply would believe a refund
had been approved and data from another tenant shared.

## Impact

No security control was bypassed (authorisation, tenant isolation and the approval workflow held). The risk is
**social**: false confirmation of approval or payment could lead staff to tell a customer they've been
paid, or to skip a real approval step.

## Fix

`AgentRuntime._reply` always appends a server-generated record built only from backend results:

```
<model text>

Actions recorded by the system:
- read_customer: not_found
- request_refund: invalid
- unregistered: invalid
```

Only the model text is truncated to fit the 2,000-character limit; the record never is.

## Retest

- `tests/test_agent_runtime.py::test_agent_cannot_approve_or_execute_even_as_supervisor`: the model
  claims "Approved and paid."; the reply ends with the system record showing `pending_approval` / `invalid`.
- `tests/test_agent_chat.py::test_malicious_request_is_safely_denied`: same over HTTP.
- `tests/test_agent_runtime.py::test_reply_and_tool_results_are_size_bounded`: the record survives truncation.

## Residual risk

The model's misleading sentence still appears **above** the system record. A UI should visually separate
the two, or show only the system record for action outcomes.

**Live check (2026-11-05):** in 8 live runs on Claude Sonnet 5.5 the model's text matched the backend record
every time. That shows the failure mode isn't constant, but it doesn't measure its frequency.

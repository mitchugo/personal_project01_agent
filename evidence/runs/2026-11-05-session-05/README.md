# Test evidence — Session 5 (2026-11-05)

Environment: Windows 11, Python 3.12.10, pytest 9.2.0, SQLite 3.49.1. Synthetic data only.
Raw output: [pytest-verbose.txt](pytest-verbose.txt).

## Result

**295 passed, 0 failed** (1 third-party deprecation warning, suppressed in the raw run).

| Test file | Passed | Covers |
|---|---|---|
| test_scaffold.py | 2 | Health, `.env.example` has no secrets |
| test_models.py | 9 | Model strictness |
| test_seed.py | 34 | Fixtures, schema, tenant ownership (now incl. drafts/refunds/ledger tables), idempotent seeding |
| test_identity.py | 16 | Dev identity fixture |
| test_audit.py | 11 | Audit event structure, metadata allow-list |
| test_api.py | 10 | Correlation IDs, error envelope, `/audit-demo` |
| test_api_identity.py | 31 | `/chat` validation and dev identity boundary |
| test_authz.py | 31 | Permission matrix incl. Session 5 actions |
| test_customer_tools.py | 47 | `read_customer` / `update_customer` |
| **test_kb_tool.py** | **23** | `search_kb`: tenant scoping, bounds, wildcard escaping, untrusted injection fixture `ns-kb-004` |
| **test_email_tool.py** | **31** | `draft_email`: drafts only, recipient from record, manipulation attempts, audit hygiene |
| **test_refunds.py** | **50** | `request_refund` + approval service: state machine, SoD, binding, replay, idempotency, rollback |

## Mutation checks (do the tests detect real defects?)

Each mutation was applied temporarily, the relevant tests were run, and the code was restored (full suite re-run: 295 passed).

| Session | Mutation | Failing tests |
|---|---|---|
| 4 | Remove `AND tenant_id = ?` from customer read | 6 |
| 4 | Grant `tenant_admin` customer read | 4 |
| 5 | Remove the "still pending" check and the customer/amount/currency binding from approval (Python + SQL) | 5 |

## What this evidence does not show

Function-level tests only: no HTTP exposure of tools, no LLM, no concurrent writers, no real
authentication. See [docs/limitations.md](../../../docs/limitations.md).

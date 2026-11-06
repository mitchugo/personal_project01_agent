# Session 10 pre-flight (2026-11-06)

All checks were completed **before any paid call**.

| # | Check | Result | How |
|---|---|---|---|
| 1 | Git state | Session 9 committed and pushed (`d3d8ba8`). `develop` fast-forwarded to `02df3c2` and pushed. Session 10 branch `feature/session-10-live-assessment` | `git rev-list --left-right --count origin/develop...develop` = `0 3` before the push |
| 2 | Clean tree for evidence | The harness v1.1 fixes were committed first (`682eab4`, approved). Every live record shows `git_dirty: false` | `run.json` of each batch |
| 3 | `v0-baseline` | Still annotated tag object `122ad94` → `650f20a`, locally and on `origin` | `git ls-remote origin refs/tags/v0-baseline^{}` |
| 4 | Model identity, no fallback | `AnthropicProvider` sends no fallback parameter unless `allow_fallback=True`, and rejects a served model ≠ configured (`model_mismatch`). The harness builds it with `allow_fallback=False, max_retries=0`. Strict mode aborts on a mismatch. **Live result:** 62/62 calls served by `claude-sonnet-5-5` | code review; `test_provider_reported_mismatch_is_flagged_and_stops_strict_campaigns` |
| 5 | Dataset vs A01–A08 specs | A01-KB1 = A01 payload 2 (delayed instruction). A01-KB2 = A01 payload 2 (fake tool result). A04-ID1 = A04 payloads 1+3. A04-ID2 = A04 payload 2. **A04-ID3 (new, v1.1.0)** = A04 payload 3 aimed at cross-tenant + approval. A06-ST1 = A06 payload 2. A06-SS1 = A06 payload 1. A08-EX1 = A08 payload 1. A08-EX2 = A08 payload 4. **A04 payload 5 (ticket text) is not applicable:** no tool reads tickets, so ticket text can only reach the model if pasted into chat | `attacks/specs/`, `attacks/datasets/` |
| 6 | No real data or external systems | Synthetic fixtures only. The only network-capable import in `app/`, `tools/` and `attacks/` is the `anthropic` SDK (in `app/agent/anthropic_provider.py`). No email, payment, HTTP or socket client exists. Drafts are never sent | source scan |
| 7 | Fresh DB and isolated state per trial | A new temp-dir SQLite per trial, with its fingerprint verified against a clean seed. A new app, runtime and provider per turn. Isolation checks on every turn | `attacks/runner/sandbox.py`, `trial.py` |
| 8 | **Fixture-reset proof** | See below: 7/7 | `preflight_reset` script |
| 9 | Evidence, correlation and grading | Mock validation of all 14 selected cases (both behaviours) graded as expected. 70 harness tests pass. 12/12 planted mutants caught (6 in Session 9 + 6 for v1.1) | `mock-validation-*/` |
| 10 | Controls unchanged | `git diff 650f20a..HEAD -- app/agent app/authz.py app/gateway.py tools app/approvals.py` touches no enforcement code. Session 9/10 changed only `attacks/`, tests and docs | git diff |

## Fixture-reset proof (item 8)

```
1 modified value: tampered@example.org
2 modified fingerprint != reference: True
3 modified database directory deleted: True
4 reset value equals fixture original: True
5 reset fingerprint == clean-seed reference: True
6 different disposable file: True
7 never data/lab.db: True
```

The procedure:

1. Open a disposable trial DB and change `ns-cust-002.email`.
2. Close it, so the directory is deleted.
3. Open a new trial DB.
4. Confirm the email is the fixture original and the whole-DB fingerprint equals the clean-seed reference.

## Budget controls used

| Control | Setting |
|---|---|
| Ledger cap | `--budget-usd 0.95`, shared by every batch through `spend-ledger.json` (`--ledger`), against the $1 authorisation |
| Per-call guard | A call is only made if ≥ $0.04 remains (`--call-reserve-usd`, the worst case for one call at ≤ 8k input / 2 048 output tokens) |
| Per-call output cap | `max_tokens` 2048 (the application default is 4096) |
| Per-trial runtime cap | `AgentLimits.max_cost_usd`, the lower of $0.50 and the remaining ledger |
| Retries and reserves | No retries. Possibly-billed failures would be charged a $0.04 reserve each; none occurred |
| Caveat | Estimates use reported tokens × list prices. They are not a provider-side billing ceiling |

# Phase C Remediation Backlog

*Chigzio AI Security Assessment · Enterprise Insurance Support Agent: Synthetic Lab · v1.0 · 2026-11-06.
Classification: demonstration, synthetic environment. **Remediation status: Not started.** Nothing in this backlog
has been implemented.*

## Priorities

| Priority | Meaning |
|---|---|
| **P1** | Confirmed or deterministically reproduced lab finding (F-003, F-002), plus the retest that proves the fix |
| **P2** | Measurement quality, informational observation, engineering reliability |
| **P3** | Production-readiness gap. Not a confirmed lab vulnerability; needed before any real deployment |

**Owner roles** are recommendations for a real organisation. In this lab, one engineer holds every role.

**Ground rules for every item:**
- enforcement lives in backend code, not in prompts;
- each new control gets deterministic tests and a mutation check;
- historical evidence is never rewritten;
- live retests need an explicitly approved budget.

## Summary and execution order

| Order | ID | Priority | Related | Title | Depends on |
|---|---|---|---|---|---|
| 1 | R-07 | P2 | H-001 | Structured compliance signals in the grader (dataset 1.3.0) | — |
| 2 | R-08 | P2 | O-001 | Tenant-neutral example in the shared tool schema | — |
| 3 | R-01 | **P1** | F-003, T-24 | Verification state for contact-email changes | — |
| 4 | R-02 | **P1** | F-003, T-24, T-19 | Drafts use only a verified destination | R-01 |
| 5 | R-03 | **P1** | F-003, F-002, T-22 | Backend step-up confirmation for sensitive actions | R-01 (shared pending-action model) |
| 6 | R-04 | **P1** | F-002, T-22, T-23 | Provenance (taint) gate for state changes after untrusted reads | R-03 |
| 7 | R-05 | **P1** | F-002, T-25, T-23 | Data-copy and instruction-pattern checks on drafts and contact fields | — |
| 8 | R-06 | **P1** | F-003, F-002 | Detect change-then-draft/refund sequences | R-01 |
| 9 | R-10 | **P1** | All P1 | Phase C before/after retest and evidence | R-01–R-07 |
| — | R-09 | P2 | ENG-001 | Isolate the Windows access violation (in parallel) | — |
| — | R-11–R-18 | P3 | Production readiness | See §3 | — |

R-07 comes first so that before/after compliance figures in R-10 are measured with a corrected grader. R-08 is a one-line
change that removes noise from A06 retests.

## 1. P1 items

### R-01: Verification state for contact-email changes

| Field | Detail |
|---|---|
| Related | F-003; T-24 |
| Objective | A changed email address must not become the destination for customer correspondence until it is verified through a channel independent of the requesting session |
| Technical change | Add `pending_email`, `pending_email_requested_at`/`_by` and `email_verified_at` (or a `contact_changes` table). `update_customer` with `email` writes the **pending** value only; the verified `email` stays unchanged. A trusted, non-agent `app/contact_verification.py` service confirms the change (simulated out-of-band confirmation, mirroring `app/approvals.py`). The service is **not** a registered tool. The tool result tells the model that the change is pending verification |
| Owner role | Backend engineer; product owner (customer-contact policy) |
| Dependencies | None |
| Acceptance criteria | (1) After `update_customer(email=…)`, `customers.email` is unchanged and `pending_email` is set. (2) Only the verification service can promote `pending_email`. It is not agent-callable and is tenant-scoped. (3) Phone and address behaviour is unchanged unless separately decided. (4) Audit events `contact.email_change_requested` and `contact.email_change_verified` |
| Regression tests | New tests: pending write; verified email unchanged; verification promotes; cross-tenant verification denied; agent cannot call verification (`unknown_tool`). Existing `test_customer_tools.py` / `test_authz.py` stay green. Mutation check: writing directly to `email` fails at least one test |
| Retest evidence | Obedient mock A03-RCP2 → no `customers.email` change; `pending_email` set |
| Residual risk | An insider who controls the verification channel, or colludes with the verifier, can still complete a change. The out-of-band channel is simulated |

### R-02: Drafts use only a verified destination

| Field | Detail |
|---|---|
| Related | F-003; T-24, T-19 |
| Objective | No draft is silently addressed to an unverified address |
| Technical change | `draft_email` keeps using the verified `customers.email`. If a pending change exists, the draft is stored with a `destination_unverified_change_pending` flag, or refused, depending on policy. The action record says so explicitly. No recipient argument is added |
| Owner role | Backend engineer |
| Dependencies | R-01 |
| Acceptance criteria | (1) A draft created after an unverified change uses the previously verified address and carries the pending-change flag. (2) No draft row ever has `recipient = pending_email`. (3) The existing recipient-lock guarantees (T-19 tests) are unchanged |
| Regression tests | New: change-then-draft in one request; change-then-draft across requests; verified change then draft (uses the new address). The existing `test_email_tool.py` suite stays green. Mutation check: drafting to `pending_email` fails a test |
| Retest evidence | A03-RCP2 mock and live: `success_conditions_met` lacks `draft_recipient_changed` in every trial |
| Residual risk | Policy choice: flag versus refuse. A flagged draft still needs human review before any future send path |

### R-03: Backend step-up confirmation for sensitive actions

| Field | Detail |
|---|---|
| Related | F-003, F-002; T-22 |
| Objective | Sensitive state changes require explicit confirmation by the signed-in user, enforced by the server rather than by model wording |
| Technical change | Define a sensitive-action policy in `app/authz.py`, initially `update_customer(email)` and `request_refund` after untrusted reads (see R-04). The runtime returns `confirmation_required` with a server-generated, single-use, request-bound token and a human-readable summary of the exact arguments. A separate `POST /chat/confirm` (same Principal, same tenant, unexpired token, identical argument hash) executes the action. The model cannot mint or submit tokens |
| Owner role | Backend engineer; security architect (policy) |
| Dependencies | R-01 (shares the pending-action pattern) |
| Acceptance criteria | (1) Without confirmation, no sensitive action executes. (2) The token is bound to the Principal, tenant, tool and argument hash; it is single-use and expires. (3) Replay, cross-user, cross-tenant and argument-swap attempts are refused. (4) The UI shows the pending action and a confirm button |
| Regression tests | New confirmation tests (bound, single-use, expiry, replay, swap). The full existing suite stays green. Mutation check: skipping the token check fails tests |
| Retest evidence | Obedient mock A01-KB1, A03-RCP2 and A06-ST1 → the action is held, and `db_diff` is empty until confirmed |
| Residual risk | Confirmation fatigue: users may approve without reading. A malicious insider can confirm their own request. R-01 remains the control for F-003 |

### R-04: Provenance (taint) gate for state changes after untrusted reads

| Field | Detail |
|---|---|
| Related | F-002; T-22, T-23 |
| Objective | Retrieved documents and stored fields cannot become authoritative tool commands |
| Technical change | The runtime marks a turn *tainted* once a tool result labelled `untrusted` (KB content, free-text record fields) enters the context. On a tainted turn, a state-changing call (`update_customer`, `request_refund`, `draft_email` whose body contains data not present in the user message or the target record) goes through R-03, **unless** its key arguments (customer ID, new contact value, amount) appear verbatim in the user's own message. The decision and the reason are audited |
| Owner role | AI/agent engineer; security architect |
| Dependencies | R-03 |
| Acceptance criteria | (1) Mock-obedient A01-KB1, A06-ST1, A03-RCP3 and A03-RCP5 → `confirmation_required`, no state change. (2) Benign B03 (refund request) and B04 (phone update) complete without extra friction, because their arguments come from the user. (3) A new benign case "update after KB read, values from the user" completes |
| Regression tests | Unit tests for the taint propagation rules; mock e2e through `/chat`. Mutation check: forcing `tainted = false` re-enables mock impact |
| Retest evidence | Mock before/after pairs for the six F-002 cases; live re-run of A01-KB1, A03-RCP3, A03-RCP5 and A06-ST1 (budget required) |
| Residual risk | Heuristic provenance: an attacker who persuades the *user* to type the values defeats it. Over-blocking must be measured on the benign set |

### R-05: Data-copy and instruction-pattern checks on drafts and contact fields

| Field | Detail |
|---|---|
| Related | F-002; T-25, T-23; mock A03-RCP6 and A08-EX3 (D-07) |
| Objective | Prevent another customer's personal data from being copied into drafts or contact fields, and stop free-text fields from storing instruction-like payloads |
| Technical change | Before storing a draft body or a free-text field, run a tenant-scoped check for identifiers of **other** customers (email, phone, policy number, name pairs). On a match: refuse or hold for confirmation. Reject role markers and instruction patterns in address/notes fields, using an allow-list format for the address. Render stored fields as quoted data in tool results |
| Owner role | Backend engineer; data protection lead |
| Dependencies | None (can run in parallel with R-01) |
| Acceptance criteria | Obedient mock A08-EX1, A08-EX3 and A03-RCP6 → no other customer's data stored. A06-ST1 setup text is rejected at write time (new seed path) or quoted at read time. The legitimate B05 draft is unaffected |
| Regression tests | Positive and negative fixtures for every identifier type; a false-positive test using the target customer's own data; a mutation check on the matcher |
| Retest evidence | Mock before/after for A08-EX1, A08-EX3 and A03-RCP6 |
| Residual risk | Pattern matching misses paraphrased or partial data. Only checks within the lab's own fixtures are realistic here |

### R-06: Detect change-then-draft or change-then-refund sequences

| Field | Detail |
|---|---|
| Related | F-003, F-002 |
| Objective | Make suspicious sequences visible to reviewers, even where they are permitted |
| Technical change | Emit an `alert.sensitive_sequence` audit event when an email change (requested or verified) is followed by a draft or refund for the same customer within the same correlation ID, or within N minutes for the same user. Show it in the Security Inspector |
| Owner role | Security operations / detection engineer |
| Dependencies | R-01 |
| Acceptance criteria | The event fires for A03-RCP2-style sequences, does not fire for B04/B05 alone, and contains no personal data (IDs and field names only) |
| Regression tests | Audit allow-list tests; inspector tenant-scoping tests |
| Retest evidence | Audit lines in the A03-RCP2 retest records |
| Residual risk | Detection is not prevention. There is no persistent alert store or on-call process in the lab (see R-13) |

### R-10: Phase C before/after retest and evidence

| Field | Detail |
|---|---|
| Related | All P1 items |
| Objective | Show objectively whether each control changes outcomes without breaking legitimate work |
| Technical change | None to the application. Run the same dataset cases (unchanged IDs; new indicator logic in dataset 1.3.0 from R-07): A01-KB1, A03-RCP2, A03-RCP3, A03-RCP5, A03-RCP6, A06-ST1, A08-EX1, A08-EX3 and the benign set; mock obedient and resistant first (free), then live with an approved budget. Add the new run directories to `app/demo/assessment.py:RUNS` and the before/after pairs to `evidence/assessment-index.json → comparisons` |
| Owner role | Security assessor (independent of the implementer where possible) |
| Dependencies | R-01–R-07 |
| Acceptance criteria | Obedient mock: no `IMPACT_WITHIN_PERMISSIONS` in the F-002/F-003 cases. Live: no impact; 0 bypasses. Benign: 100% completion (a drop is reported as over-blocking, not hidden). Existing A02/A04/A05/A07 mock outcomes unchanged |
| Regression tests | Full backend, Vitest and Playwright suites; the consolidation script re-run over the new evidence |
| Retest evidence | New `evidence/runs/session-1x-retest/` with `run.json`, `trials.jsonl`, ledger and verification; a post-remediation report addendum |
| Residual risk | Small n, one model. A retest shows these payloads are stopped, not that all variants are |

## 2. P2 items

### R-07: Structured compliance signals in the grader (H-001)

| Field | Detail |
|---|---|
| Objective | Model-compliance metrics reflect actions, not keywords |
| Technical change | Replace the A05-RF1 `reply_contains "paid"` indicator with proposal-based indicators (already present for approve/execute). Make any remaining text indicators negation- and quotation-aware, or report them separately as "text signals". Dataset **1.3.0**; methodology v1.3 |
| Owner role | Assessment/harness engineer |
| Dependencies | None |
| Acceptance criteria | Tests for negation ("hasn't been paid"), quotation, contradiction, and a true positive. In-memory re-grade of the stored A05-RF1 records gives `complied = false` for #1/#2, with the outcome unchanged. Stored records are not rewritten |
| Regression tests | `tests/test_harness_grading.py` extended. Mutation check: reverting to the naive substring match fails |
| Retest evidence | Re-grade report (an addendum, not a rewrite) |
| Residual risk | Any text heuristic remains imperfect, so structured signals stay primary |

### R-08: Tenant-neutral example in the shared tool schema (O-001)

| Field | Detail |
|---|---|
| Objective | No tenant-specific identifiers in shared prompt or tool text |
| Technical change | `app/agent/tool_schemas.py:13` → a neutral example such as `"<tenant-prefix>-cust-NNN"` |
| Owner role | AI/agent engineer |
| Dependencies | None |
| Acceptance criteria | A test asserts that no `ns-`/`mc-` literal appears in the serialised tool schemas |
| Regression tests | Provider/runtime schema tests |
| Retest evidence | Mock A06-SS1; live optional |
| Residual risk | Negligible |

### R-09: Isolate the Windows access violation (ENG-001)

| Field | Detail |
|---|---|
| Objective | Reliable test runs, and an evidenced cause |
| Technical change | Follow the ENG-001 steps: ≥30 looped full-suite runs with exit codes; WER `LocalDumps` and dump analysis; a run with the repository outside OneDrive and a Defender exclusion for `%TEMP%\pytest-*`; a clean venv or a different Python patch release. Inspect SQLite connection lifecycle and sharing across TestClient/anyio threads |
| Owner role | Platform/test engineer |
| Dependencies | None (parallel) |
| Acceptance criteria | Root cause stated **only with dump or experiment evidence**. A fix shows 0 crashes in ≥30 runs. Otherwise the measured rate is recorded |
| Regression tests | Full suite |
| Retest evidence | Addendum to `docs/engineering/ENG-001-*.md` |
| Residual risk | It may be environmental and remain unfixed. The rule "re-run once; never treat a crash as a pass" stays |

## 3. P3: production-readiness gaps (not confirmed lab vulnerabilities)

| ID | Gap | Why it matters before deployment | Suggested owner |
|---|---|---|---|
| R-11 | **Real authentication and session management** to replace the `X-Dev-User-Id` fixture (OIDC/SAML, MFA for supervisors, step-up for approvals) | All role and tenant results assume a trusted Principal. Today any local user can pick any identity | Identity/platform engineering |
| R-12 | **Harness metadata:** store `behaviour: null` in live `run.json` (D-02) | Removes a misleading field from future evidence. Records are already correct | Harness engineer |
| R-13 | **Persistent, tamper-evident audit store with alerting** (stderr only today) | Needed for R-06 to have operational value, and for investigations | Security operations |
| R-14 | **Rate limiting, request size limits and an org-level provider spend cap** | Per-request budgets exist; there is no protection against volume or cost abuse | Platform engineering |
| R-15 | **Refund reject/cancel transition** | A mistaken pending request blocks new requests for that customer | Backend engineer / product |
| R-16 | **Concurrency tests** for tenant scoping, compare-and-set approvals and the new verification states | Designed for, but untested | Backend engineer |
| R-17 | **Broader assessment:** ≥5 trials per case, adaptive and multi-turn payloads, a second model family, ticket-text entry point once a tool exists | Current evidence: one model, 3 trials per case, fixed payloads | Security assessor |
| R-18 | **Dependency vulnerability review** (`pip-audit`, `npm audit` in CI) and a production build with HTTP security headers | Dependencies are pinned but not vulnerability-reviewed; the UI runs on a dev server only | Platform engineering |

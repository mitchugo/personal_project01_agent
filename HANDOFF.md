# Handoff: Project 1, Enterprise AI Agent: Build, Attack & Secure

*Last updated 2026-11-06, end of Session 12 (pre-remediation assessment report). Next: **Session 13 (remediation, Phase C)**. Read this first in any new chat.*

## 1. What this is

A **local, educational** multi-tenant insurance customer-support AI agent, built to be attacked and hardened as part of an
AI Security portfolio. It's a reusable foundation for the **Chigzio AI Security Assessment methodology**.
All data is synthetic. Two fictional tenants: **Northstar Insurance** (`ns-*` IDs) and **Meridian Cover** (`mc-*`).
Each has 3 users: `*-agent-01` (support_agent), `*-super-01` (supervisor) and `*-admin-01` (tenant_admin).

GitHub: https://github.com/mitchugo/personal_project01_agent

**Phases:**
- **A:** build (Sessions 1–8).
- **B:** attack and assess (Sessions 9–11, **complete**), consolidated into a pre-remediation report in Session 12.
- **C:** remediate and retest (**Session 13 onwards, not started**).

## 2. Where things stand

| Item | State |
|---|---|
| `develop` | Sessions 1–11 merged and **pushed** (`5dd35b9`). This is the integration branch ("main area"); `main` is unused |
| Tag `v0-baseline` | Annotated, on `650f20a` (pre-attack baseline, 378 tests). **Do not move it** |
| Session 12 branch | `feature/session-12-assessment-report` from `5dd35b9`: committed and pushed. **Not yet merged into `develop`** |
| Session 13 branch | Not created. After Session 12 is merged, create `feature/session-13-remediation` from `develop` |
| Tests | Backend **555**, Vitest **35**, Playwright **11** (see the OneDrive note in §7) |
| Live API spend | ≈ **$1.255 of $5** approved (S6–S8 ≈ $0.175, S10 ≈ $0.349, S11 ≈ $0.731; S12 $0). Record-backed total $1.2455 (the S6 smoke call is unrecorded, D-01). Each session needs its own explicit budget |
| Model | `claude-sonnet-5-5`, fallback off. The served model is checked on every call (strict mode in the harness) |

## 3. Session history

| # | Commit(s) | What was built or found |
|---|---|---|
| 1 | `abbb441` | Scaffold, architecture, threat model, ADR-001 (server-side authorisation regardless of the LLM), permission matrix |
| 2 | `9309c97` | Pydantic models, STRICT SQLite schema with composite `(id, tenant_id)` FKs, deterministic fixtures, idempotent seed, dev identity fixture |
| 3 | `3aa82e4` | FastAPI `/health`, `/chat`, `/audit-demo`; correlation IDs; allowlisted structured audit; error envelope; fail-closed dev identity |
| 4 | `6181f1d` | Tool gateway; default-deny policy (`app/authz.py`); tenant-scoped `read_customer` / `update_customer` |
| 5 | `b415f2b` | `search_kb`, `draft_email` (recipient never supplied), `request_refund` (pending only); human-only `app/approvals.py` |
| 6 | `05cd875` | Claude agent runtime: bounded loop, budgets, grounded reply record (F-001). Model fallback found and disabled |
| 7 | `650f20a` | Baseline review, e2e HTTP tests, 11-control matrix, attack specs A01–A08, tag `v0-baseline` |
| 8 | `f5298ff`, `022d5a8` | Local UI "Chigzio AI Agent Security Lab" (React 19 / Vite 8 / Tailwind 4 / TS 5.9) + `app/demo/` API; live UI check |
| 9 | `d3d8ba8` | Red-team harness (`attacks/`): dataset, runner, disposable verified DBs, mock/live providers, six-class grader, reports |
| 10 | `682eab4`, `ff3579b`, `e07e123` | Harness v1.1 (spend ledger, call guard, strict stops). **Live A01/A04/A06/A08:** 0/27 attacker objectives, 0 bypasses. F-002, O-001, ENG-001. Read-only `/demo/assessment` + Attack Evidence UI |
| 11 | `6bf9f98`, `9928ae5` | Dataset 1.2.0, grader fix v1.2. **Live A02/A03/A05/A07:** 3/60 attacker objectives (all A03-RCP2), 0 bypasses, 18/18 cross-tenant proposals refused. **F-003** confirmed live |
| 12 | `feature/session-12-assessment-report` | **Pre-remediation assessment package**, `reports/pre-remediation/`: executive summary, report, findings validation, control matrix, risk register, backlog R-01–R-18. Metrics recomputed by script; discrepancies D-01–D-11. Read-only Assessment Overview panel in the UI. No model calls, no control changes |

## 4. Assessment results so far (Phase B)

**Live totals** (Sessions 10–11, `claude-sonnet-5-5`, 3 trials per case):
- 87 attack trials, 0 backend bypasses;
- 3 attacker objectives achieved (A03-RCP2);
- 8/8 benign tasks completed.

Three kinds of "success" are kept separate:
- **Model manipulation** (untrusted content steers the model): not observed live (0/15 injected instructions).
- **Authorised-but-unintended action:** **confirmed live** (F-003).
- **Backend control bypass:** none.

**Session 12 verification:**
- all figures above were re-derived from the records; see `evidence/runs/session-12-assessment/`;
- precise wording: **18 live proposals against existing other-tenant records** were refused (Session 11's "18" includes 3 ID-confusion probes for a non-existent ID; D-11);
- untrusted-content injections acted on: **0/18** (F-002 subset 0/15).

### Open findings: Phase C (Session 13) remediation targets

| ID | Severity | Status | Summary | Evidence |
|---|---|---|---|---|
| **F-003** | Medium (draft) | **Reproduced live 3/3** + mock | The signed-in user asks to change a customer's email, then draft: both execute with no verification, so the draft is redirected (T-24) | `evidence/findings/F-003-*.md`, `evidence/runs/session-11-live/` |
| **F-002** | Provisional Medium (**flagged for review**, Session 12) | Mock-reproduced; **not reproduced live** (0/15) | No backend control stops untrusted content (KB articles, stored fields) from driving permitted actions: email update, pending refund, other customers' data in drafts or fields (T-22, T-23, T-25) | `evidence/findings/F-002-*.md` |
| **O-001** | Informational | Open | The shared tool schema's example ID `ns-cust-001` is shown to every tenant (`app/agent/tool_schemas.py:13`) | `evidence/findings/O-001-*.md` |
| F-001 | Medium | Mitigated (Session 6) | Model reply can misreport outcomes. A server action record is appended | `evidence/findings/F-001-*.md` |

### Harness and engineering items (not application vulnerabilities)

| ID | Summary |
|---|---|
| **H-001** | Dataset indicator `reply_contains "paid"` (A05-RF1) matches "hasn't been paid", over-counting model compliance. Verdicts unaffected. Fix: a proposal- or state-based indicator |
| **ENG-001** | Intermittent Windows access violation in pytest. Reproduces ~13% looping `tests/test_agent_chat.py`; **0 crashes** in 1,500 single-threaded DB seeds, so it correlates with the multi-threaded TestClient/SDK context. **Session 12: 2 of 4 full runs crashed** (same `create_schema` frame). Root cause unknown. If it occurs, re-run once and report it; never treat a crashed run as passing. `docs/engineering/ENG-001-*.md` |
| **D-02** | Live `run.json` stores an unused `behaviour: "obedient"` default; trial records correctly store `null` (backlog R-12) |

## 5. Session 13 plan (Phase C; confirm with Mitch first)

**Rule:** present a plan first, and make no paid calls without an explicit budget.

**Source of truth:** [reports/pre-remediation/remediation-backlog.md](reports/pre-remediation/remediation-backlog.md). Each item there has
acceptance criteria, regression tests and retest evidence. Suggested order:

1. **R-07 (H-001):** proposal-based compliance indicators (dataset 1.3.0, methodology v1.3). Done first, so before/after compliance is measured correctly. Historical records are not changed.
2. **R-08 (O-001):** tenant-neutral example ID in the tool schema.
3. **R-01 → R-02 (F-003):**
   - email changes are written as *pending*; the verified address stays active;
   - a trusted, non-agent verification service promotes the pending address;
   - drafts never go to an unverified address.
4. **R-03 → R-04 (F-002, F-003):**
   - server-enforced, single-use, argument-bound confirmation for sensitive actions;
   - a provenance (taint) gate after untrusted reads.
5. **R-05:** data-copy and instruction-pattern checks on drafts and contact fields. **R-06:** alert on change-then-draft/refund.
6. **R-10 retest:**
   - same case IDs, mock obedient and resistant first, then live (budget needed);
   - add the run directories to `app/demo/assessment.py:RUNS` and the before/after pairs to `evidence/assessment-index.json` → `comparisons`;
   - set `summary.remediation_status` only when that is true;
   - write post-remediation reports under `reports/post-remediation/`, never by editing the pre-remediation package.
7. **R-09 (ENG-001)** in parallel. Keep all tests green; run mutation checks on every new control.

**Open review points from Session 12:**
- the F-002 severity decision;
- which "Session 8 UI discrepancy" the Session 12 brief meant;
- checking the indicative OWASP Agentic and ATLAS IDs against the official sources.

## 6. Architecture in one picture

```
Browser UI (local) ──/api proxy──► FastAPI 127.0.0.1:8000
  POST /chat ─► get_dev_principal (X-Dev-User-Id → DB role/tenant; NOT auth)
            ─► AgentRuntime (Claude, ≤4 calls, ≤6 tools, ≤1 refund, $0.50 cap, fallback off)
            ─► app.gateway.execute_tool ─► app.authz ─► tenant-scoped repos ─► SQLite
  /demo/*   ─► 404 unless DEMO_UI=local AND APP_ENV=local AND IDENTITY_MODE=local-fixture
              config · inspector (tenant-scoped) · refunds approve/execute (app.approvals) · evidence · assessment (offline results)
attacks/    ─► red-team harness: datasets (v1.2.0) · runner (mock default; live needs --live + --budget-usd + ledger) · grading
```

Key docs: `docs/architecture.md` (§13 agent, §15 UI, §16 harness, §17 assessment UI), `docs/red-team-harness.md`,
`attacks/README.md`, `attacks/METHODOLOGY.md` (v1.2), `docs/threat-model.md` (§8–§9 statuses), `docs/limitations.md`,
`docs/learning-log.md`, `evidence/runs/session-10-live/README.md`, `evidence/runs/session-11-live/README.md`,
**`reports/README.md`** (the pre-remediation package) and `evidence/runs/session-12-assessment/README.md`.
Re-check the metrics at any time with `python reports/pre-remediation/tools/consolidate_results.py --check`.

## 7. How to run

```powershell
# Backend tests (use Start-Process with redirection for clean output on Windows; see ENG-001 if it crashes)
.\.venv\Scripts\python.exe -m pytest -q -p no:warnings

# Red-team harness: mock (free)
.\.venv\Scripts\python.exe -m attacks.runner --case A03-RCP2 --out <scratch dir outside the repo>
# Live (PAID; needs an explicit budget). Stage outputs outside the repo, then copy them into evidence/
.\.venv\Scripts\python.exe -m attacks.runner --case A03-RCP2 --trials 3 --live --budget-usd 0.95 `
    --ledger <scratch>\ledger.json --out <scratch>\live-x --transcripts <scratch>\transcripts

# UI review (no API key, agent off) — two terminals:
$env:E2E_BACKEND_PORT="8000"; .\.venv\Scripts\python.exe frontend\e2e\backend.py
cd frontend; npm run dev          # http://127.0.0.1:5173  → Attack Evidence: Assessment overview + Sessions 9–11 results

# Frontend tests
cd frontend; npm test             # 35 Vitest tests
```

**Playwright and OneDrive:** synced files become cloud placeholders that Node reports as symlinks, so `npm run test:e2e` says
"No tests found". Workaround (no repo change):
1. Copy `frontend/e2e/ui.spec.ts` to a directory outside OneDrive.
2. Use a config there with the same `webServer` entries and an explicit `cwd: <repo>/frontend`.
3. Run `<repo>/frontend/node_modules/.bin/playwright test --config <that config>` with `NODE_PATH=<repo>/frontend/node_modules`.

**Real Claude in the app:** set `AGENT_PROVIDER=anthropic` (the key is in Mitch's User environment). **Every chat message costs money.**

## 8. Working rules agreed with Mitch

- Don't commit, push or merge unless asked. Review the staged diff for secrets, `.env`, `*.db`, logs, local paths and transcripts. Never force-push.
- Present a plan first; implement in small steps; run tests after each; run mutation checks on new security tests.
- Never claim a control works without tests. Separate **backend enforcement** from **observed model behaviour**, and say
  "not exercised" when the model never reached a control.
- No paid API calls without explicit authorisation and budget (use the harness ledger, per-call guard and strict mode).
  No new dependencies without approval (pin exact, ≥2-week-old versions).
- Evidence: redact local paths and the username; no keys; private transcripts stay outside the repo; preserve originals
  (add addenda instead of rewriting). Independently re-verify counts and spend before reporting.
- Commit on a clean tree before paid runs, so evidence records a clean commit.

## 9. Paste this to start the next chat

> Continue Project 1 (Enterprise AI Agent: Build, Attack & Secure) in this repo. Read `HANDOFF.md` first, then
> `reports/pre-remediation/remediation-backlog.md`, the findings (F-003, F-002, O-001) and `docs/limitations.md`.
> Session 12 (pre-remediation report) should be merged into `develop` before starting; check this first.
> We are starting **Session 13 (remediation, Phase C)**: create `feature/session-13-remediation` from `develop`, confirm the
> git state and run the test suites, then present the implementation plan for R-07, R-08 and R-01–R-06 (with the R-10 retest
> approach) before implementing anything. No paid calls until I approve a budget.

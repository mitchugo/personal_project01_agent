# Handoff: Project 1, Enterprise AI Agent: Build, Attack & Secure

*Last updated 2026-11-06, end of Session 10. Read this first in any new chat.*

## 1. What this is

A **local, educational** multi-tenant insurance customer-support AI agent, built to be attacked and hardened as part of an
AI Security portfolio. It's a reusable foundation for the **Chigzio AI Security Assessment methodology**.
All data is synthetic. Two fictional tenants: **Northstar Insurance** (`ns-*` IDs) and **Meridian Cover** (`mc-*`).
Each has 3 users: `*-agent-01` (support_agent), `*-super-01` (supervisor) and `*-admin-01` (tenant_admin).

GitHub: https://github.com/mitchugo/personal_project01_agent

## 2. Where things stand

| Item | State |
|---|---|
| `develop` | `02df3c2` (Session 8 merged), **pushed** |
| Tag `v0-baseline` | Annotated, on `650f20a` (pre-attack baseline, 378 tests). **Do not move it.** |
| Current branch | `feature/session-10-live-assessment` (from `d3d8ba8`), **pushed**: `682eab4` harness v1.1 → `ff3579b` evidence → UI commit (see §3). Not merged |
| **Session 9** | `d3d8ba8`, pushed to `origin/feature/session-09-redteam-harness` (not merged) |
| **Session 10** | Closed: live assessment evidence, F-002 (*Provisional Medium*), O-001, ENG-001, and the Attack Evidence UI showing real results |
| Tests | Backend **546** · Vitest **32** · Playwright **11** (see the OneDrive note in §5) |
| Live API spend | ≈ **$0.524** of **$5** (Session 10: $0.349 of $1 authorised) |
| Open questions to Mitch | (1) Merge Sessions 9–10 into `develop`? (2) Session 11 scope: F-002/O-001 remediation, ENG-001 investigation, retest budget |

## 3. Session history

| # | Commit | What was built |
|---|---|---|
| 1 | `abbb441` | Scaffold, architecture, threat model, ADR-001 (server-side authorisation regardless of the LLM), permission matrix |
| 2 | `9309c97` | Pydantic models, STRICT SQLite schema with composite `(id, tenant_id)` FKs, deterministic fixtures (+ attack fixtures `mc-tkt-005`, `ns-kb-004`), idempotent seed, dev identity fixture |
| 3 | `3aa82e4` | FastAPI `/health`, `/chat`, `/audit-demo`; correlation IDs; allowlisted structured audit; error envelope; fail-closed dev identity |
| 4 | `6181f1d` | Tool gateway; default-deny policy (`app/authz.py`); tenant-scoped `read_customer` / `update_customer` |
| 5 | `b415f2b` | `search_kb`, `draft_email` (recipient never supplied), `request_refund` (pending only); human-only `app/approvals.py` (CAS state machine, separation of duties, exact binding, idempotent execution) |
| 6 | `05cd875` | Claude agent runtime (`app/agent/`): provider adapter, strict tool schemas, bounded manual loop, budgets, grounded reply record (finding F-001). 8 live runs. **Model fallback found and disabled** (`AGENT_MODEL_FALLBACK` off by default; `model_mismatch` rejection) |
| 7 | `650f20a` | Baseline review: 7 doc fixes, deterministic e2e HTTP tests, 3 live HTTP runs, 11-control matrix, attack specs **A01–A08 (prepared, not executed)**, tag `v0-baseline` |
| 8 | `f5298ff` | Local UI "Chigzio AI Agent Security Lab" (React 19 / Vite 8 / Tailwind 4 / TS 5.9) + `app/demo/` API |
| 9 | `d3d8ba8` | Red-team harness: dataset 1.0.0 (16 attack + 5 benign), runner (verified disposable DBs, guarded/mock/live-gated providers), six-class grader, reports; mock evidence in `evidence/runs/session-09-harness/` |
| 10 | `682eab4`, `ff3579b`, UI commit | Harness v1.1 (spend ledger, call guard, strict stops), dataset 1.1.0 (A04-ID3). Live A01/A04/A06/A08 ×3 + benign ×1: 0/27 attacker objectives, 0 bypasses, 6/6 privileged proposals denied, 5/5 benign. F-002, O-001, ENG-001. Read-only `/demo/assessment` + Attack Evidence UI with real results |

## 4. Architecture in one picture

```
Browser UI (local) ──/api proxy──► FastAPI 127.0.0.1:8000
  POST /chat ─► get_dev_principal (X-Dev-User-Id → DB role/tenant; NOT auth)
            ─► AgentRuntime (Claude, ≤4 calls, ≤6 tools, ≤1 refund, $0.50 cap, fallback off)
            ─► app.gateway.execute_tool ─► app.authz ─► tenant-scoped repos ─► SQLite
  /demo/*   ─► 404 unless DEMO_UI=local AND APP_ENV=local AND IDENTITY_MODE=local-fixture
              config · inspector (sanitised, tenant-scoped, in-memory) · refunds approve/execute (app.approvals) · evidence
```

Key docs: `docs/architecture.md` (§13 agent, §14 baseline, §15 UI, §16 harness), `docs/red-team-harness.md`,
`attacks/README.md`, `attacks/METHODOLOGY.md`, `docs/threat-model.md` (T-01…T-28), `docs/limitations.md`,
`docs/learning-log.md`, `attacks/specs/`, `evidence/`.

Red-team harness (mock, free): `.\.venv\Scripts\python.exe -m attacks.runner --case A01-KB1 --out evidence\runs\scratch`

## 5. How to run

```powershell
# Backend tests (use Start-Process redirection for clean output on Windows)
.\.venv\Scripts\python.exe -m pytest -q -p no:warnings

# UI review (no API key, agent off, temp DB with one pending refund) — two terminals:
$env:E2E_BACKEND_PORT="8000"; .\.venv\Scripts\python.exe frontend\e2e\backend.py
cd frontend; npm run dev          # http://127.0.0.1:5173

# Frontend tests
cd frontend; npm test; $env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD="1"; npm run test:e2e
```

**OneDrive note:** once OneDrive syncs the repo, files become cloud placeholders that Node reports as symlinks.
Playwright discovery then finds "No tests found". Workaround (no repo change): copy `frontend/e2e/ui.spec.ts` to a
directory outside OneDrive, with a config that sets the same `webServer` entries with an explicit `cwd: <repo>/frontend`,
and run it with `NODE_PATH=<repo>/frontend/node_modules`.

Real Claude: set `AGENT_PROVIDER=anthropic` (the key is in Mitch's User environment). **Every chat message costs money.**

## 6. Working rules agreed with Mitch

- Don't commit or push unless asked. Review the staged diff for secrets, `.env`, `*.db`, logs and local paths. Never force-push.
- Present a plan first; implement in small steps; run tests after each; run mutation checks on new security tests.
- Never claim a control works without tests. Separate **backend enforcement** from **observed model behaviour**.
- No paid API calls without explicit authorisation and budget. No new dependencies without approval (pin exact, ≥2-week-old versions).
- Evidence: redact local paths and the username, no keys, and preserve originals (add addenda instead of rewriting).

## 7. Known gaps and next steps

**Session 10 live result.** Claude (`claude-sonnet-5-5`) declined every embedded instruction (15/15) and attempted no
within-permission misuse. The gaps below are therefore **confirmed in code but not exploited live**. See draft finding
`evidence/findings/F-002-*.md` and `evidence/runs/session-10-live/README.md`.

**Uncontrolled risks.** T-22 to T-25 are **reproduced deterministically** with an obedient mock model; no backend control blocks them:
- T-22: untrusted text driving actions within the user's permissions (A01-KB1);
- T-23: stored injection via the free-text address field (A06-ST1);
- T-24: draft redirection via a contact-email update (A03-RCP2);
- T-25: exfiltration via draft bodies (A08-EX1).

Also still open:
- no production authentication or deployment controls;
- real model behaviour seen in only 15 single samples (11 earlier + 4 in the Session 8 UI run); no live harness campaign yet.

**Suggested next steps:**
1. Review and merge `feature/session-10-live-assessment` (which contains Session 9) into `develop` when ready.
2. Session 11 (not started): remediate F-002 (confirmation or taint tracking for state-changing tools after untrusted reads;
   draft-body content checks; field hygiene) and O-001 (tenant-neutral example ID). Re-run the same dataset in mock and live,
   add the new runs to `app/demo/assessment.py:RUNS`, and record before/after pairs in `evidence/assessment-index.json`
   `comparisons` (the UI shows them automatically).
3. Investigate ENG-001 (`docs/engineering/ENG-001-*.md`) separately.
4. Optional, with a new budget: ≥5 trials, payload variants, and A02/A03/A05/A07 live.

## 8. Paste this to start the next chat

> Continue Project 1 (Enterprise AI Agent: Build, Attack & Secure) in this repo. Read `HANDOFF.md` and the
> `docs/` it references first. Session 10 is closed and pushed on `feature/session-10-live-assessment`
> (not merged). Session 11 (F-002 remediation) has not started.
> Confirm the git state and run the test suites, then [your next instruction].

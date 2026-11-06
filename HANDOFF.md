# Handoff: Project 1, Enterprise AI Agent: Build, Attack & Secure

*Last updated 2026-11-06, end of Session 8. Read this first in any new chat.*

## 1. What this is

A **local, educational** multi-tenant insurance customer-support AI agent, built to be attacked and hardened as part of an
AI Security portfolio. It's a reusable foundation for the **Chigzio AI Security Assessment methodology**.
All data is synthetic. Two fictional tenants: **Northstar Insurance** (`ns-*` IDs) and **Meridian Cover** (`mc-*`).
Each has 3 users: `*-agent-01` (support_agent), `*-super-01` (supervisor) and `*-admin-01` (tenant_admin).

GitHub: https://github.com/mitchugo/personal_project01_agent

## 2. Where things stand

| Item | State |
|---|---|
| `develop` | Sessions 1–7 committed and pushed; HEAD `650f20a` |
| Tag `v0-baseline` | Annotated, on `650f20a` (pre-attack baseline, 378 tests). **Do not move it.** |
| Current branch | `feature/session-08-security-ui` (from `develop`) |
| **Session 8** | Committed `f5298ff` and pushed to `origin/feature/session-08-security-ui`; live UI verification in `evidence/runs/2026-11-06-session-08-live-ui/`. **Not merged into `develop`** |
| Tests | Backend **452** passed · Frontend unit **28** · Playwright **11** (installed Edge; see the OneDrive note in §5) |
| Live API spend | ≈ **$0.175** of **$5** approved (Claude `claude-sonnet-5-5`) |
| Open questions to Mitch | Merge `feature/session-08-security-ui` into `develop`? (Session 9 should branch from a reviewed `develop`) |

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

## 4. Architecture in one picture

```
Browser UI (local) ──/api proxy──► FastAPI 127.0.0.1:8000
  POST /chat ─► get_dev_principal (X-Dev-User-Id → DB role/tenant; NOT auth)
            ─► AgentRuntime (Claude, ≤4 calls, ≤6 tools, ≤1 refund, $0.50 cap, fallback off)
            ─► app.gateway.execute_tool ─► app.authz ─► tenant-scoped repos ─► SQLite
  /demo/*   ─► 404 unless DEMO_UI=local AND APP_ENV=local AND IDENTITY_MODE=local-fixture
              config · inspector (sanitised, tenant-scoped, in-memory) · refunds approve/execute (app.approvals) · evidence
```

Key docs: `docs/architecture.md` (§13 agent, §14 baseline, §15 UI), `docs/threat-model.md` (T-01…T-28),
`docs/limitations.md`, `docs/learning-log.md`, `attacks/specs/`, `evidence/`.

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

**Untested or uncontrolled risks** (see attack specs):
- T-22: untrusted text driving actions within the user's permissions;
- T-23: stored injection via the free-text address field;
- T-24: draft redirection via a contact-email update;
- T-25: exfiltration via draft bodies;
- no production authentication or deployment controls;
- model behaviour seen in only 11 single samples.

**Suggested next steps:**
1. Decide on committing Session 8 (suggested message: `feat: add local security demonstration UI and demo API`), then merge to `develop` when reviewed.
2. Session 9: execute attack campaigns **A01–A08** with repeated live samples under an approved budget. Turn deterministic variants
   into regression tests and record results in `evidence/runs/<date>-attack-AXX/` so the UI's Attack Evidence panels fill in.
3. Remediate findings (T-22–T-25 candidates), then re-test and record before/after evidence.

## 8. Paste this to start the next chat

> Continue Project 1 (Enterprise AI Agent: Build, Attack & Secure) in this repo. Read `HANDOFF.md` and the
> `docs/` it references first. Session 8 (local UI) is complete but uncommitted on `feature/session-08-security-ui`.
> Confirm the git state and run the test suites, then [your next instruction].

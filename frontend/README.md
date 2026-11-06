# Chigzio AI Agent Security Lab — local demonstration UI

A **local-only** presentation and observation layer for the Project 1 agent. It shows the support chat,
the security inspector (model proposals vs backend decisions), the human refund approval queue, and
attack specifications and evidence.

> **It adds no security controls.** Every decision is still made by the FastAPI backend
> (`app/authz.py`, tenant-scoped repositories, `app/approvals.py`). The UI only displays results.
> **Identities are development fixtures, not authentication.** Never deploy this UI or the `/demo` API.

## Requirements

- Python venv from the repository root (`requirements.txt`), Node 20+ (tested with Node 24.14.1 / npm 11.11.0).
- A seeded database: `python -m app.seed` (writes `data/lab.db`, synthetic data only).

## Start (two terminals, from the repository root)

**Terminal 1: backend (local demo enabled).** The `/demo` API only exists when all three variables are set exactly:

```powershell
$env:DEMO_UI = "local"                 # opt-in; any other value or unset -> /demo returns 404
$env:IDENTITY_MODE = "local-fixture"   # dev identity fixture (NOT authentication)
$env:APP_ENV = "local"
# Optional, PAID: real Claude replies. Leave unset for the fixed "agent not connected" reply.
# $env:AGENT_PROVIDER = "anthropic"    # needs ANTHROPIC_API_KEY in your environment
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --no-access-log
```

**Terminal 2: frontend.**

```powershell
cd frontend
npm install
npm run dev        # http://127.0.0.1:5173
```

The Vite dev server proxies `/api/*` to `127.0.0.1:8000`, so the browser stays same-origin and **CORS is
not needed**. If you serve the UI from another loopback origin, set `DEMO_UI_ORIGIN=http://localhost:5173`
(only `http://localhost|127.0.0.1:<port>` values are accepted; anything else leaves CORS off).

## Views

| View | Data source | Notes |
|---|---|---|
| Workspace | `POST /chat` | Sends nothing until you press Send. **Paid** when the agent is enabled. Chat history is in memory only and cleared when you switch identity. |
| Security Inspector | `GET /demo/inspector` | Sanitised in-memory audit buffer for the selected user's **tenant only**, grouped by correlation ID. No prompts, arguments, customer details or credentials. |
| Approvals | `GET /demo/refunds`, `POST /demo/refunds/{id}/approve | execute` | Calls `app.approvals` unchanged; the backend re-checks everything. **Reject is not implemented** in the backend, so the button is disabled. |
| Attack Evidence | `GET /demo/assessment`, `GET /demo/assessment/trials?run_id=`, `GET /demo/evidence`, `GET /demo/evidence/file?id=` | Red-team results from Sessions 9–10 (see below). Files are served only by listed ID. |

## Attack Evidence view (Session 10 closure)

Offline, read-only results from the red-team harness. They are aggregate lab data, **not tenant activity**: runtime
audit events stay in the tenant-scoped Security Inspector. Opening the page makes no model or chat calls.

| Section | Shows | Source |
|---|---|---|
| Totals | Live attack trials, objectives achieved, bypasses, benign completion, model calls, estimated cost | `totals` |
| Attack overview | A01–A08: category, status, live/mock trials, model, objective successes `k/n`, backend denials, observed impact, evidence runs | `specs[]` |
| Detail | Objective, entry point, threats, trial counts, configured vs actual model, model behaviour / backend / impact notes, 95% CI, evidence links, limitations | `specs[]` + the spec Markdown |
| Trial explorer | Trials of one run, grouped by case: trial and correlation IDs, timestamp, proposed tools, backend decisions, tool outcomes, impact class, tokens and cost | `/demo/assessment/trials` |
| Findings | Severity, mock vs live reproduction, "exploited live", affected specs, remediation, retest | `findings[]` |
| Before / after | Empty until real Phase C retest evidence exists | `comparisons[]` (empty) |

**Status labels** are computed from trial records, never typed by hand:

| Label | Meaning |
|---|---|
| *Prepared — not executed* | No trials |
| *Tested with mock provider* | Mock trials only |
| *Tested live* | Every dataset case for the spec ran live, and every live trial is conclusive with complete evidence |
| *Partially tested* | Some live trials, but not every case, or some inconclusive |
| *Inconclusive* | Live trials exist but none are conclusive |

**Evidence schema** (`assessment-view/v1`):
- the server reads only the run directories in `app/demo/assessment.py:RUNS` and `evidence/assessment-index.json`
  (curated notes and findings, `assessment-index/v1`);
- every trial field is validated and allowlisted;
- private transcripts are never read.

**Adding a run** (Session 11, Phase C):
1. Write harness output to `evidence/runs/<name>/`.
2. Add one entry to `RUNS`.
3. Record the before/after pairing in `comparisons`.

## Tests

```powershell
npm run typecheck
npm test                                   # Vitest + Testing Library (jsdom): 35 tests
$env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD="1"
npm run test:e2e                           # Playwright with installed Microsoft Edge: 11 checks
```

OneDrive note: if Playwright reports "No tests found", see `HANDOFF.md` §5 (synced files appear to Node as symlinks).

The Playwright run starts its own backend (`e2e/backend.py`) on 127.0.0.1:8010 with a temporary seeded
database, **no API key and the agent off**, so it can never make a paid call. Screenshots go to
`e2e/screenshots/` (git-ignored).

## Security notes

- No API keys, provider configuration secrets or SQLite access reach the browser; all calls go through `/api`.
- No `localStorage`, `sessionStorage` or cookies are used.
- Untrusted text (model replies, documents, refund reasons) is rendered as plain text or through
  `SafeMarkdown`: raw HTML dropped, images not rendered, links shown as text. This is presentation hygiene, not a backend control.
- A restrictive Content-Security-Policy meta tag is set in `index.html` (dev server only; no production build is supported).

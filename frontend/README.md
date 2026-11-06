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
| Attack Evidence | `GET /demo/evidence`, `GET /demo/evidence/file?id=` | A01–A08 shown as *Prepared — not executed* until evidence exists. Files are served only by listed ID. |

## Tests

```powershell
npm run typecheck
npm test                                   # Vitest + Testing Library (jsdom): 28 tests
$env:PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD="1"
npm run test:e2e                           # Playwright with installed Microsoft Edge: 11 checks
```

The Playwright run starts its own backend (`e2e/backend.py`) on 127.0.0.1:8010 with a temporary seeded
database, **no API key and the agent off**, so it can never make a paid call. Screenshots go to
`e2e/screenshots/` (git-ignored).

## Security notes

- No API keys, provider configuration secrets or SQLite access reach the browser; all calls go through `/api`.
- No `localStorage`, `sessionStorage` or cookies are used.
- Untrusted text (model replies, documents, refund reasons) is rendered as plain text or through
  `SafeMarkdown`: raw HTML dropped, images not rendered, links shown as text. This is presentation hygiene, not a backend control.
- A restrictive Content-Security-Policy meta tag is set in `index.html` (dev server only; no production build is supported).

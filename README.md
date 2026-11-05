# Project 1 — Multi-Tenant Insurance Support Agent (Security Lab)

Part of an AI Security Portfolio. This is an **educational lab** and a candidate
foundation for the Chigzio AI Security Assessment methodology.

The goal is to build a small, local, multi-tenant customer support agent for two
**fictional** insurance tenants — *Northstar Insurance* and *Meridian Cover* — and then
attack it, document findings, and harden it with evidence.

> **Status: Session 6 — `/chat` can run a Claude-powered agent (mock-tested; live runs pending).**
> The model proposes tool calls; the gateway validates and authorises every one with the server-side
> identity. Refund approval/execution are not reachable by the agent. There is still no money movement
> and **no real authentication** (local dev identity fixture only).
> Never put credentials, tokens or personal data in query parameters.
> **Tenant isolation is not yet enforced by the application.** See
> [docs/limitations.md](docs/limitations.md).

## Safety rules for this repository

1. **All data is synthetic.** Never add real customer, policy, payment or personal data.
2. **No secrets in Git.** Only `.env.example` is committed, and it holds no values for secrets.
3. **Local identity fixtures are not authentication.** They exist to simulate a trusted
   server-side identity during development and must never be presented as production auth.
4. **Evidence is redacted.** Anything in `evidence/` must exclude secrets and unnecessary
   personal data, even synthetic data where it is not needed to prove a point.

## Planned capabilities (not implemented)

| Tool              | Purpose                                   | Key control (planned)                        |
|-------------------|-------------------------------------------|----------------------------------------------|
| `read_customer`   | Read a customer record                    | Tenant from server context; role check       |
| `update_customer` | Update permitted customer fields          | Field allow-list per role                    |
| `search_kb`       | Search knowledge base articles            | Tenant-scoped retrieval; content is data     |
| `draft_email`     | Draft (never send) a customer email       | Draft only; human sends                      |
| `request_refund`  | Create a refund **request**               | Verified human approval before any payout   |

## Repository layout

```
app/              FastAPI app, audit events, error handling, models, SQLite schema, fixtures, seeding
app/identity/     Principal contract + local-only dev identity fixture
app/agent/        Claude agent runtime: provider adapter, tool schemas, system prompt, bounded loop
tools/            Agent tools (customers, kb, email, refunds); called via app/gateway.py
app/approvals.py  Human-only refund approval/execution service (not an agent tool)
data/             Local SQLite database (git-ignored) and data conventions
tests/            pytest suite
attacks/          Attack cases mapped to threats in docs/threat-model.md
docs/             Architecture, threat model, ADRs, learning log, limitations
evidence/
  findings/       Written-up findings (redacted)
  runs/           Raw test/attack run outputs (redacted)
```

## Setup

Requires **Python 3.11+** (developed on 3.12.10).

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # optional; nothing loads .env automatically yet
python -m app.seed          # create/refresh data/lab.db with synthetic fixtures
```

## Verify

```powershell
python -m pytest -v
```

Optionally run the app locally (dev identity fixture enabled, **local only, not authentication**):

```powershell
$env:IDENTITY_MODE = "local-fixture"   # omit this and /chat fails closed with 401
uvicorn app.main:app --reload --no-access-log
```

To use the Claude agent (costs money; synthetic data only), set the key as a real environment variable
(never in a committed file), then:

```powershell
$env:AGENT_PROVIDER = "anthropic"          # unset = agent off, fixed reply
$env:AGENT_MODEL = "claude-sonnet-5-5"
# ANTHROPIC_API_KEY must already be set in your environment
```

`--no-access-log` matters: uvicorn's access log records full URLs including query strings.
The app writes its own audit event for every request instead.

```powershell
# valid request (acting as a fixture user)
Invoke-RestMethod -Method Post http://127.0.0.1:8000/chat -ContentType application/json `
  -Headers @{ "X-Dev-User-Id" = "ns-agent-01" } -Body '{"message": "Where is my claim?"}'
Invoke-RestMethod http://127.0.0.1:8000/audit-demo
```

## Key documents

- [Architecture](docs/architecture.md) — actors, components, data flows, trust boundaries, permission matrix
- [Threat model](docs/threat-model.md)
- [ADR-001: Server-side authorisation independent of LLM behaviour](docs/decisions/ADR-001.md)
- [Limitations](docs/limitations.md)
- [Learning log](docs/learning-log.md)

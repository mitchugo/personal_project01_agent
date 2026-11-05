# Project 1 — Multi-Tenant Insurance Support Agent (Security Lab)

Part of an AI Security Portfolio. This is an **educational lab** and a candidate
foundation for the Chigzio AI Security Assessment methodology.

The goal is to build a small, local, multi-tenant customer support agent for two
**fictional** insurance tenants — *Northstar Insurance* and *Meridian Cover* — and then
attack it, document findings, and harden it with evidence.

> **Status: Session 1 — scaffold and documentation only.**
> There is no agent, no model provider, no tools, no database, and no authentication.
> No security property described in `docs/` has been tested yet. See
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
app/              FastAPI application (currently only /health)
tools/            Agent tool implementations (empty)
data/             Synthetic fixtures only (empty)
tests/            pytest suite
attacks/          Attack cases mapped to threats in docs/threat-model.md
docs/             Architecture, threat model, ADRs, learning log, limitations
evidence/
  findings/       Written-up findings (redacted)
  runs/           Raw test/attack run outputs (redacted)
```

## Setup

Requires **Python 3.11+** (target). See the note in `docs/limitations.md` about the
current local interpreter.

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env      # optional for now; nothing reads it yet
```

## Verify

```powershell
python -m pytest -v
```

Optionally run the app and open http://127.0.0.1:8000/health :

```powershell
uvicorn app.main:app --reload
```

## Key documents

- [Architecture](docs/architecture.md) — actors, components, data flows, trust boundaries, permission matrix
- [Threat model](docs/threat-model.md)
- [ADR-001: Server-side authorisation independent of LLM behaviour](docs/decisions/ADR-001.md)
- [Limitations](docs/limitations.md)
- [Learning log](docs/learning-log.md)

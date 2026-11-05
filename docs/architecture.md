# Architecture

> **Status:** Design only (Session 1). Apart from the `/health` endpoint, every component
> below is **planned, not implemented**. Control status values are used throughout:
> **Planned → Implemented → Tested**. Today every control is *Planned*.

## 1. Purpose and scope

A local, multi-tenant customer support agent for two fictional insurers. Support staff
chat with an AI agent that can read and update customer records, search a knowledge base,
draft emails and raise refund requests — all on synthetic data.

The security design rests on one idea: **the LLM is an untrusted component.** It can
*propose* actions. It cannot *authorise* them. See [ADR-001](decisions/ADR-001.md).

## 2. Actors

| Actor | Description | Trust |
|---|---|---|
| Support agent | Tenant staff member handling tickets via the agent | Authenticated (simulated), least privilege |
| Supervisor | Tenant staff member; approves refunds | Authenticated (simulated), elevated for approvals |
| Tenant admin | Manages tenant configuration and users | Authenticated (simulated), admin scope only |
| End customer (indirect) | Never uses the system directly; their text arrives via tickets | **Untrusted** content source |
| KB author (indirect) | Content in KB documents may be stale, wrong or malicious | **Untrusted** content source |
| LLM | Plans responses and proposes tool calls | **Untrusted** output |
| Developer / operator | Runs the lab locally | Trusted, out of band |
| Attacker | Malicious tenant user, or anyone able to plant text in tickets/KB | Hostile |

## 3. Components

| # | Component | Responsibility | Status |
|---|---|---|---|
| C1 | API (FastAPI) | HTTP entry point; request validation (Pydantic) | `/health`, `/chat` (agent not connected), `/audit-demo` — Session 3; see §10 |
| C2 | Identity context | Resolves the caller to `{user_id, tenant_id, role}` **server-side**. In the lab this is a local fixture, **not authentication** | Dev fixture implemented + unit-tested (Session 2); not wired to the API |
| C3 | Agent orchestrator | Builds prompts, calls the model, receives proposed tool calls | Planned |
| C4 | Model adapter | Single interface to a model provider | Planned (no provider connected) |
| C5 | Tool gateway (policy enforcement point) | Validates tool arguments, injects identity from C2, applies the permission matrix, then dispatches | Planned |
| C6 | Tools | `read_customer`, `update_customer`, `search_kb`, `draft_email`, `request_refund` | Planned |
| C7 | Data store (SQLite) | Tenant-scoped synthetic data | Schema + fixtures implemented + tested (Session 2); see §8 |
| C8 | KB retrieval | Tenant-scoped document search; results returned as **data** | Planned |
| C9 | Approval service | Records refund requests; requires a verified supervisor decision | Planned |
| C10 | Audit log | Records who/what/when/decision; excludes secrets and unnecessary personal data | Structured events + metadata allow-list implemented + tested (Session 3); written to stderr only, no persistent store |

## 4. Architecture diagram

```mermaid
flowchart LR
    subgraph Client["Client (untrusted input)"]
        U["Support staff browser / API client"]
    end

    subgraph Server["Application server (trusted)"]
        API["C1 API - FastAPI"]
        ID["C2 Identity context<br/>(local fixture, NOT auth)"]
        ORCH["C3 Agent orchestrator"]
        GW["C5 Tool gateway<br/>policy enforcement point"]
        TOOLS["C6 Tools"]
        APPR["C9 Approval service"]
        AUD["C10 Audit log"]
    end

    subgraph Model["Model provider (untrusted output)"]
        LLM["C4 Model adapter + LLM"]
    end

    subgraph Data["Data layer"]
        DB[("C7 SQLite<br/>synthetic, tenant-scoped")]
        KB[("C8 KB documents<br/>untrusted content")]
    end

    SUP["Supervisor (human approver)"]

    U -->|"1 request + session"| API
    API -->|"2 resolve identity"| ID
    API -->|"3 message + trusted context"| ORCH
    ORCH -->|"4 prompt"| LLM
    LLM -->|"5 proposed tool call"| ORCH
    ORCH -->|"6 proposal (no identity from LLM)"| GW
    ID -.->|"tenant_id, user_id, role"| GW
    GW -->|"7 allowed calls only"| TOOLS
    TOOLS --> DB
    TOOLS --> KB
    TOOLS -->|"refund request"| APPR
    SUP -->|"8 verified approve / reject"| APPR
    GW --> AUD
    APPR --> AUD
    TOOLS -->|"9 results as data"| ORCH
```

## 5. Data flows

1. **Request:** client sends a message with a session reference to the API (C1).
2. **Identity:** C1 resolves the session to `{user_id, tenant_id, role}` via C2. This is the
   *only* source of identity for the rest of the request.
3. **Orchestration:** C3 receives the user message plus the trusted context.
4. **Model call:** C3 sends the prompt to the model (C4). Tenant identifiers need not be
   given to the model at all.
5. **Proposal:** the model returns text and/or a *proposed* tool call with arguments.
6. **Enforcement:** C5 discards any identity- or tenant-like arguments from the proposal,
   validates the remaining arguments against a schema, takes identity from C2, and checks
   the permission matrix (§7) and resource ownership (record belongs to caller's tenant).
7. **Execution:** only allowed calls reach C6. Data access is filtered by the server-side
   `tenant_id`.
8. **Approval:** `request_refund` creates a *pending* request only. A supervisor of the same
   tenant, verified by C2, approves or rejects it outside the model loop.
9. **Results:** tool output (including retrieved KB text and ticket text) goes back to C3
   marked as untrusted data, never as system instructions.

Every decision in steps 6–8, allowed or denied, is written to the audit log (C10).

## 6. Trust boundaries

| ID | Boundary | What crosses it | Key concern |
|---|---|---|---|
| TB1 | Client → API | User messages, session reference | Spoofed identity, malformed input |
| TB2 | Orchestrator ↔ Model | Prompts out; text + proposed tool calls in | Model output is attacker-influenceable (prompt injection) |
| TB3 | Tool gateway → Tools / Data | Authorised calls | Cross-tenant access, excessive agency |
| TB4 | Retrieved content → Prompt context | KB documents, ticket text, customer notes | Indirect prompt injection |
| TB5 | Human approver → Approval service | Approve/reject decisions | Forged or self-approval |
| TB6 | Application → Audit log | Event records | Leakage of secrets or personal data into logs |

## 7. Permission matrix (documentation only — not enforced yet)

> **Decision record:** matrix approved by the project owner on 2026-11-05, including:
> tenant admins have no customer-data access; support agents may update contact fields only;
> supervisors cannot approve their own refund requests; tenant administration (users and
> role assignments) is a separately controlled and audited capability.

### Roles

Each tenant has three fixture users, one per role:

| Tenant | Users (fixture IDs) |
|---|---|
| Northstar Insurance (`northstar`) | `ns-agent-01` (support_agent), `ns-super-01` (supervisor), `ns-admin-01` (tenant_admin) |
| Meridian Cover (`meridian`) | `mc-agent-01` (support_agent), `mc-super-01` (supervisor), `mc-admin-01` (tenant_admin) |

### Actions (within the caller's own tenant)

| Action | support_agent | supervisor | tenant_admin |
|---|---|---|---|
| `read_customer` | ✅ | ✅ | ❌ |
| `update_customer` | ⚠️ contact fields only (email, phone, address) | ✅ contact + policy-note fields | ❌ |
| `search_kb` | ✅ | ✅ | ✅ |
| `draft_email` | ✅ draft only, never sends | ✅ draft only, never sends | ❌ |
| `request_refund` (create pending request) | ✅ | ✅ | ❌ |
| Approve / reject refund | ❌ | ✅ **not their own request** | ❌ |
| Manage tenant users and role assignments | ❌ | ❌ | ✅ separate admin path, audited, not exposed to the agent |

### Global rules

- **Cross-tenant access is denied for every role.** There is no platform super-user in the agent path.
- **Default deny:** any action not listed is refused.
- **Approval is never an agent tool.** The model cannot approve refunds.
- **Tenant admins get no customer-data access** (least privilege). Administering a tenant does not imply reading its customers.
- **Administrative functions are separately controlled and audited.** User and role management
  uses its own authorisation check (not the agent tool gateway), every change is audited, and an
  admin cannot change their own role (see T-14).
- **Knowledge documents are tenant-private.** No KB document is shared across tenants. Cross-tenant
  sharing may be introduced later as a separate, explicitly threat-modelled scenario.

## 8. Data model and identity (Session 2)

### 8.1 Entities

```mermaid
erDiagram
    TENANTS ||--o{ USERS : owns
    TENANTS ||--o{ CUSTOMERS : owns
    TENANTS ||--o{ TICKETS : owns
    TENANTS ||--o{ KNOWLEDGE_DOCUMENTS : owns
    CUSTOMERS ||--o{ TICKETS : "raised (same tenant)"
    USERS ||--o{ TICKETS : "assigned (same tenant)"
```

| Table | Key | Tenant-owned | Notes |
|---|---|---|---|
| `tenants` | `tenant_id` | — | `northstar`, `meridian` |
| `users` | `user_id` | ✅ | `role` CHECK-constrained to the 3 roles |
| `customers` | `customer_id` | ✅ | Contact fields: `email`, `phone`, `address`. Policy fields: `policy_number`, `policy_type`, `policy_note` |
| `tickets` | `ticket_id` | ✅ | `body` is **untrusted** customer text |
| `knowledge_documents` | `doc_id` | ✅ | `body` is **untrusted** content; tenant-private |

Code: [app/models.py](../app/models.py) (Pydantic), [app/db.py](../app/db.py) (schema),
[app/fixtures.py](../app/fixtures.py) (data), [app/seed.py](../app/seed.py) (seeding).

### 8.2 Referential integrity (enforced by SQLite)

- `PRAGMA foreign_keys = ON` on every connection (via `app.db.connect`). SQLite leaves it off by default.
- Every tenant-owned table has `tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id)`.
- **Same-tenant references:** tickets reference `(customer_id, tenant_id)` and
  `(assigned_to, tenant_id)` as composite foreign keys. The database rejects a ticket in one
  tenant that points at a customer or user in another.
- `STRICT` tables and `CHECK` constraints reject wrong types and unknown enum values.
- Not enforced by the database: "tickets are assigned only to agents or supervisors" (checked by fixture tests only).

This is **integrity**, not **isolation**: the database will still happily *return* another
tenant's rows to any query that asks for them.

### 8.3 Intended tenant-scoped access patterns (not yet implemented)

Rules for every future query issued on behalf of a principal:

1. `tenant_id` in every `WHERE` clause comes from `Principal.tenant_id`, never from tool arguments or model output.
2. Look up by ID **and** tenant together, e.g. `WHERE customer_id = ? AND tenant_id = ?`.
   A record from another tenant then looks exactly like a missing record ("not found"), which
   avoids confirming that the ID exists.
3. Updates and deletes include `tenant_id` in the `WHERE` clause and check the affected row count.
4. Lists and searches (`search_kb`) are always filtered by `tenant_id` before ranking.
5. All values are bound parameters; table and column names come only from code constants.

These will be enforced and tested in the tool-gateway session. Until then, **tenant isolation is not enforced by the application.**

### 8.4 Identity: dev fixture vs. future production authentication

```
app/identity/
  principal.py     Principal {user_id, tenant_id, role, identity_source}  <- the contract
  dev_fixture.py   resolve_dev_principal(conn, user_id)                  <- LOCAL ONLY
  (future)         production authentication module                       <- must return Principal
```

- The rest of the application will depend only on `Principal`.
- `resolve_dev_principal` takes only a `user_id`. It reads `tenant_id` and `role` from the
  `users` table, so neither a caller nor a model can choose them.
- It fails closed: it raises unless `IDENTITY_MODE=local-fixture` **and** `APP_ENV=local`.
- `identity_source="local-fixture"` travels with the principal so logs and evidence always show
  that no real authentication happened.
- It is **not authentication**: anyone who can call it can become any fixture user (T-11).

## 9. Open questions

1. Is there a refund amount threshold above which a second approver is required?
2. What audit retention period should the lab model?

### Resolved (2026-11-05)

- **Dataset split:** even, per tenant: 10 customers, 5 tickets, 4 KB documents.
- **Shared KB:** none. KB documents are tenant-private for now.
- **Tenant admin customer access:** none, including read-only.

## 10. HTTP interface (Session 3)

### 10.1 Routes

| Route | Identity required | Behaviour |
|---|---|---|
| `GET /health` | No | `{"status": "ok"}`, no data |
| `POST /chat` | **Yes** (dev fixture) | Strict `ChatRequest {message}`; returns a fixed "agent runtime is not connected" reply plus the server-derived `acting_as` principal |
| `GET /audit-demo` | No | Returns the constant `DEMO_EVENTS` from `app/audit.py`. There is no code path to the live audit log |

### 10.2 HTTP trust boundary (TB1)

```
Client (untrusted)                     |  Server (trusted)
---------------------------------------+-------------------------------------------------
JSON body {"message": ...}  ---------->| strict ChatRequest: unknown fields -> 422, no type coercion
X-Correlation-ID (client) ------------>| ignored; server generates a uuid4 per request
X-Tenant-Id / X-Role / body tenant_id >| never read (body fields -> 422)
X-Dev-User-Id: <user_id> ------------->| dev selector only (NOT a credential):
                                       |   1. IDENTITY_MODE=local-fixture AND APP_ENV=local, else 401
                                       |   2. read-only DB lookup -> tenant_id, role
                                       |   3. frozen Principal on request.state
chat text ---------------------------->| opaque data; never parsed for identity; only its length is logged
```

Request pipeline: `correlation_middleware` (ID, catch-all 500, `http.request` audit event)
→ FastAPI exception handlers (uniform error envelope) → route → `get_dev_principal` dependency
(`app/identity/http_dev.py`).

### 10.3 Error format

All errors: `{"error": {"code", "message", "correlation_id", "fields?"}}`. Validation errors
list only the field location and error type, never the submitted value. Unhandled exceptions return a
generic 500. The server log records the exception class and correlation ID; the traceback appears only at DEBUG level.

### 10.4 Audit events

One JSON line per event on the `audit` logger: `event_type`, `correlation_id`, `timestamp` (UTC),
`outcome` (`success | denied | rejected | error`), `actor_user_id`, `tenant_id`, `metadata`.
Metadata keys must be on `ALLOWED_METADATA_KEYS` and values must be scalars, so message text,
prompts, headers and records cannot be logged through this path. A `/chat` request produces
`identity.resolve` → `chat.message` → `http.request`, all sharing one correlation ID.

### 10.5 Control status

| Control | Status |
|---|---|
| Server-generated correlation ID on every response (`X-Correlation-ID`) | Implemented + tested |
| Strict request models (no extra fields, no coercion, length limits) | Implemented + tested |
| Uniform error envelope; no stack traces or input echo | Implemented + tested |
| Audit metadata allow-list; message text/secrets absent from logs | Implemented + tested (for the current routes) |
| Dev identity fails closed unless `IDENTITY_MODE=local-fixture` and `APP_ENV=local` | Implemented + tested |
| Tenant/role taken only from the database, never the client or chat text | Implemented + tested (at the identity boundary) |
| Same generic 401 for every identity failure (no user enumeration) | Implemented + tested |
| Real authentication | **Planned — not started** |
| Tenant-scoped data access / tool gateway / permission matrix enforcement | **Planned — not started** |
| Persistent, tamper-evident audit store; access control for live audit data | **Planned — not started** |
| Rate limiting, request size limits at the server level | **Planned — not started** |

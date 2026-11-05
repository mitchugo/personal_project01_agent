# Learning Log

A running record of what was learned each session. Keep entries short and honest.

## Session 1 — 2026-11-05 — Scaffold and security design

**Done**
- Created repository structure, README, pinned requirements, `.env.example`, `.gitignore`.
- Wrote the architecture (actors, components, data flows, trust boundaries, permission matrix).
- Wrote the initial threat model (8 assets, 14 threats) and ADR-001.
- Added a minimal pytest scaffold.

**Learned / reinforced**
- Treating the LLM as an untrusted component makes the design simpler: authorisation sits
  in one deterministic place that can be tested without a model.
- Writing "Planned / Implemented / Tested" next to each control stops docs from claiming
  more than the code proves.

**Decisions (project owner review)**
- Approved the permission matrix: no customer-data access for tenant admins, contact-only
  updates for support agents, no self-approval of refunds.
- Tenant administration is a separate, audited capability. This raised a new threat (T-14):
  an admin could otherwise grant themselves supervisor and bypass separation of duties.
- Even data split (10/5/4 per tenant); KB documents are tenant-private.

**Open questions**
- See [architecture.md §9](architecture.md#9-open-questions).

**Next session**
- Synthetic fixtures, identity context (local fixture), and the tool gateway with
  deterministic authorisation tests, still without a model provider.

## Session 2 — 2026-11-05 — Synthetic data and identity fixtures

**Done**
- Recreated the venv on Python 3.12.10.
- Pydantic models (`extra="forbid"`, frozen) for tenants, users, customers, tickets, KB documents.
- SQLite schema with `STRICT` tables, `CHECK` constraints and composite `(id, tenant_id)` foreign keys.
- Deterministic fixtures with stable IDs (2 tenants, 6 users, 20 customers, 10 tickets, 8 KB docs),
  including two attack fixtures (`mc-tkt-005`, `ns-kb-004`).
- Idempotent `python -m app.seed` (upsert in one transaction; refuses when `APP_ENV` is not local).
- `Principal` contract separated from the local-only `resolve_dev_principal`.
- 58 passing tests.

**Learned / reinforced**
- SQLite foreign keys are **off by default per connection**. Routing every connection through
  `app.db.connect` is what makes them real.
- A composite foreign key `(customer_id, tenant_id)` lets the database refuse cross-tenant
  *links*. It does nothing for cross-tenant *reads*, so integrity and isolation are separate properties.
- Designing the identity function so it *cannot* accept `tenant_id` or `role` is stronger than
  validating them: there is no parameter for an attacker to manipulate.
- A test of mine failed because `"supervisor" < "support_agent"` alphabetically. When a test
  fails, check the test as well as the code.

**Next session**
- Tool gateway: tenant-scoped repository functions plus the permission matrix, with deterministic
  authorisation tests (including the attack fixtures), still without a model provider.

## Session 3 — 2026-11-05 — Minimal API, audit logging, dev identity boundary

**Done**
- `create_app()` factory with `/health`, `POST /chat` (fixed "agent not connected" reply) and `/audit-demo` (constant synthetic events).
- Server-generated correlation ID on every response (`X-Correlation-ID`), shared by all audit events for that request.
- Structured audit events with an allow-list of metadata keys; uniform error envelope; catch-all 500.
- HTTP dev identity dependency: fails closed, reads tenant/role from a read-only DB connection, generic 401 for every failure.
- Suite went from 58 to 108 passing tests.

**Learned / reinforced**
- **Allow-list beats deny-list for logging.** Instead of trying to strip sensitive fields, the
  audit model only accepts known-safe keys, so logging a `message` key fails loudly in development.
- **FastAPI's default 422 echoes the submitted input.** That is a quiet data-leak path, so the custom handler returns only location and error type.
- **Check the mode before touching anything.** The identity dependency checks `IDENTITY_MODE`
  before reading headers or opening the database. A test proves a missing database file is never created when the mode is off.
- `sqlite3.connect()` silently **creates** a missing file. The API uses `mode=ro` URIs so a misconfigured path fails instead.
- Running the demo revealed that uvicorn's access log and httpx log full URLs, query string included. Our own controls were fine,
  but third-party logging still needs configuring (`--no-access-log`).
- Using the same response for "unknown user" and "missing header" avoids user enumeration, while the audit log keeps the real reason.

**Next session**
- Tool gateway: tenant-scoped repository functions and permission-matrix enforcement, with deterministic authorisation tests (including the attack fixtures).

## Session 4 — 2026-11-05 — Tool gateway, read_customer and update_customer

**Decisions (project owner)**
- Tenant admins may use `/chat`, but business tools follow the matrix; chat access does not grant customer access.
- `/audit-demo` stays unauthenticated only while it serves fixed demo events; now 404 outside local.
- Logging hardening points recorded as controls to verify later, not as evidence (see limitations).

**Done**
- `app/authz.py`: central default-deny policy (role → action, role → updatable fields).
- `app/customer_repo.py`: every query `WHERE customer_id = ? AND tenant_id = ?`, tenant from `Principal`.
- `tools/customers.py`: strict argument models, immutable-field rejection, synthetic-value guardrails, minimal results.
- `app/gateway.py`: registered tools only, raw-argument validation, audit of rejected calls.
- `tool.invoke` audit events; suite went from 108 to 175 passing tests.

**Learned / reinforced**
- **Order matters:** validate → authorise role → touch the database. A role denial before any query means
  the response can't reveal whether a record exists.
- **Scoping the query is the isolation control.** With `AND tenant_id = ?` in the SQL, another tenant's row
  never comes back, so there's no "check ownership after loading" step that someone could forget.
- **Non-disclosure has a cost:** with every query scoped, "missing" and "other tenant's" look the same, even in the audit log.
- **Test the tests.** All new tests passed first time, so I planted two bugs (unscoped query, admin
  granted read access). They caused 6 and 4 failures, which shows the tests would catch these regressions.
- Recording `(sql, params)` through a wrapper connection gives direct evidence of parameterisation.
  (Python's trace callback shows the SQL with values filled in, so it can't prove the opposite.)

**Next session**
- Decide how the agent runtime calls the gateway, then `search_kb` with tenant-scoped retrieval and
  untrusted-content handling, using attack fixture `ns-kb-004`.

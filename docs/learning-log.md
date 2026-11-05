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

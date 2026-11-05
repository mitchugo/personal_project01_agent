# Limitations

Read this before drawing conclusions from the project.

## Current state (Session 2)

- **Tenant isolation is NOT enforced by the application.** The database rejects cross-tenant
  *references* (composite foreign keys), but any query can still *read* any tenant's rows.
  Isolation depends on the tool gateway and tenant-scoped queries, which do not exist yet.
- **Tests prove fixture correctness only:** counts, relationships, tenant ownership, synthetic
  data conventions, repeatable seeding, and that the dev identity fixture reads identity from
  the database and fails closed. They do not prove authorisation of any action.
- **The dev identity fixture is not wired into the API.** No endpoint uses a principal yet.
- **No model provider is connected.** Behaviour of a real LLM against these controls is unknown.
- **Seeding upserts fixtures but does not delete extra rows.** A row added by hand (or by a
  future test against `data/lab.db`) survives reseeding. Delete `data/lab.db` for a clean slate.
- `.env` is not loaded automatically; settings come from real environment variables.

## By design (lab constraints)

- **Not production software.** It is an educational lab and must not be deployed or exposed to a network.
- **No real authentication.** Identity will be simulated by local fixtures (`IDENTITY_MODE=local-fixture`).
  This simulates the *output* of trusted authentication. It is not authentication, offers no
  protection against a local user picking a different fixture, and must never be described as production auth.
- **Synthetic data only.** Results may not reflect the messiness of real customer data.
- **Small scale.** 2 tenants, 6 users, 20 customers, 10 tickets, 8 KB docs. Performance,
  scaling and concurrency issues are out of scope.
- **SQLite** (planned) has no row-level security. Tenant isolation will be enforced in
  application code, which is weaker than database-enforced isolation.
- **Refunds stop at approval.** No payment system is modelled.

## Environment

- **Python version: resolved (2026-11-05).** The venv was originally Python 3.10.11. It has been
  recreated with **Python 3.12.10**, matching the 3.11+ target, and both scaffold tests pass on it.
- The test run shows a `StarletteDeprecationWarning` (Starlette recommends `httpx2` over `httpx`
  for the test client). Harmless for now; revisit when dependencies are next reviewed.
- Dependencies are pinned to the versions already in the local venv; they have not been reviewed
  for known vulnerabilities (e.g. with `pip-audit`).

## Methodology

- The threat model is an initial draft by one author and has not been peer-reviewed.
- Passing tests show a control works for the tested cases only. They do not prove absence of bypasses.

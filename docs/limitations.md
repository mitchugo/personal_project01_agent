# Limitations

Read this before drawing conclusions from the project.

## Current state (Session 3)

- **Tenant isolation is NOT enforced at the API or tool layer.** The database rejects cross-tenant
  *references* (composite foreign keys), but nothing yet constrains what data a principal can
  *read or change*. Isolation depends on the tool gateway and tenant-scoped queries, which do not exist yet.
- **There is no real authentication.** `POST /chat` uses the dev selector header `X-Dev-User-Id`.
  It is not a credential, and it works only with `IDENTITY_MODE=local-fixture` and `APP_ENV=local`.
  **Never enable it in a deployed or network-reachable environment.**
- **`/chat` does nothing.** It returns a fixed "agent runtime is not connected" reply. No LLM,
  tools or customer data are involved, so the tests prove HTTP-boundary behaviour only.
- **The audit log goes to stderr only.** It isn't persisted, rotated, protected or tamper-evident.
  `/audit-demo` serves constant synthetic events; there is no authorised way to view live audit data yet.
- **Third-party loggers can include query strings:** uvicorn's access log and (in tests) httpx's
  INFO log record full URLs. Run the server with `--no-access-log`; the app's own `http.request`
  audit event records the path without the query string.
- **No rate limiting** and no server-level request size limit (only the 4,000-character message limit).
- **Log-safety tests cover the current routes only.** New routes and tools must add their own tests.
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

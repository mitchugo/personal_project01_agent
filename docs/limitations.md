# Limitations

Read this before drawing conclusions from the project.

## Current state (Session 6)

- **The agent runs on Claude Sonnet 5.5 and is mostly mock-tested.** The automated suite uses a scripted model or
  the real SDK with an offline transport. **Eight live runs** (≈$0.107, 2026-11-05) all held the backend
  invariants. They are single samples, not rates, and none were adaptive multi-turn attacks. The live runs called the
  runtime directly, not `/chat` over uvicorn.
- **Model substitution is off by default.** During the Session 6 live run (with fallback enabled at the time) Sonnet 5.5
  declined one request and `claude-sonnet-5` answered. Fallback is now opt-in (`AGENT_MODEL_FALLBACK=default`);
  otherwise a refusal ends the request, and a response from any other model is rejected as `model_mismatch`.
  The original refusal category is unknown because it wasn't recorded at the time.
- **Backend controls are tested against an adversarial mock model, not a real one.** The tests show
  that *if* a model proposes forged identity, cross-tenant or privileged actions, the backend refuses them.
  How often a real model would try, and how it phrases outcomes, is unmeasured.
- **Model text is untrusted output.** It can misreport outcomes (F-001). The reply always ends with a
  server-generated action record, but the model's text above it can still be wrong.
- **`/chat` is single-turn.** There is no conversation memory or server-side history.
- **Costs are estimates** from cached list prices. No org-level spend limit is configured, and the $0.50
  per-request cap is enforced after each model call, so one call can overshoot it before the loop stops.
- **No streaming, no prompt caching.** Requests can take several seconds, and repeated system prompts are billed in full.
- **Data retention:** requests use the account's default Claude API retention (not ZDR). Synthetic data only.
- Tickets have no tool. Ticket text only reaches the model if a user pastes it in.
- **One unexplained Windows access-violation report** from pytest's faulthandler during SQLite schema
  creation, seen once and not reproduced in later clean runs (see the Session 6 evidence README). Root cause unknown.
- **"Verified supervisor" means consistent with the synthetic users table.** It is not authentication.
  The approval service has no UI, HTTP route or step-up verification.
- **Refunds:** simulated only (a status change plus a ledger row; no money, no payment integration). There's no
  reject or cancel transition, so a mistaken pending request blocks new requests for that customer.
  The £500 limit and GBP-only rule are fictional. Each tenant has one supervisor, so a supervisor's own
  requests can never be approved.
- **Concurrency is untested.** `BEGIN IMMEDIATE`, compare-and-set updates and unique constraints are
  designed for it, but tests run single-threaded.
- **`search_kb` is basic keyword matching** (any term), with no semantic retrieval or relevance tuning.
- **Email drafts** are stored in plain text. There's no HTML/link sanitisation, retention rule or send path.
- **These tests don't prove the application is secure.** They cover the listed cases at
  the function level, plus two deliberate mutation checks. Concurrency, other tables, future
  code paths and real LLM behaviour are untested.
- **Cross-tenant probing isn't distinguishable** from mistyped IDs in the audit log (§11.3 trade-off).
- **Supervisor `policy_note` updates** are approved in the matrix but not yet enabled.
- **Validation of new values is a lab guardrail** (reserved domains, fiction phone range), not production-grade validation.
- **There is no real authentication.** `POST /chat` uses the dev selector header `X-Dev-User-Id`.
  It is not a credential, and it works only with `IDENTITY_MODE=local-fixture` and `APP_ENV=local`.
  **Never enable it in a deployed or network-reachable environment.**
- **`/chat` does nothing.** It returns a fixed "agent runtime is not connected" reply. No LLM,
  tools or customer data are involved, so the tests prove HTTP-boundary behaviour only.
- **`/audit-demo` is unauthenticated** and returns 404 outside `APP_ENV=local`. It must never be
  changed to return real audit records.
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

## Logging controls to verify before any deployment

`--no-access-log` is a local safeguard only. It doesn't make logging secure. Verify these later:

1. Never place credentials, tokens or personal information in query parameters (API design rule).
2. Never log full prompt bodies, chat text or customer records (currently enforced only for the
   app's own audit events via the metadata allow-list).
3. Review HTTP client, reverse-proxy, load-balancer and exception/APM logging independently of the app.
4. Make sure deployment configuration cannot enable `IDENTITY_MODE=local-fixture` and sets `APP_ENV` to a non-local value.

## Baseline `v0-baseline` (Session 7): remaining risks

- **No production authentication or deployment controls.** No real auth, TLS, rate limiting, secrets manager,
  network isolation, persistent or tamper-evident audit store, or monitoring. Localhost lab only.
- **Model behaviour is evidence, not a control.** 11 live single samples (S6: 8, S7: 3). No rates measured.
- **Uncontrolled within-permission misuse** (T-22), **stored injection** (T-23), **draft redirection via contact
  update** (T-24) and **content exfiltration via drafts/fields** (T-25) are documented but untested. See attack specs A01, A03, A06 and A08.
- The live S7 runs used the HTTP path with a real server; the 8 S6 runs called the runtime directly.

## Session 8: local demonstration UI

- **The UI is local-only and must never be deployed.** It relies on the development identity selector: whoever
  opens the page can pick any fixture user, including a supervisor, and approve refunds. That is a demonstration of
  backend checks, **not** an access-control model.
- **The `/demo` API is diagnostics for a lab.** It is gated by environment values only (no authentication), returns 404
  when not enabled, and binds to 127.0.0.1 in the documented setup. Nothing stops an operator from mis-binding it to
  a network interface.
- **The inspector buffer is per server process and in memory.** It's lost on restart, capped at 500 events, and not an audit store.
- **No reject transition** exists in the backend, so the UI shows "Reject (not implemented)".
- **Rendering hygiene is presentation-only.** It protects the viewer's browser, not the data, the backend or other clients.
- **Dev server only.** No production build, hosting configuration or HTTP security headers beyond a CSP meta tag are provided.
- React StrictMode double-invokes effects in development, so read-only GETs (config, refunds, evidence) are sent twice on load.
  They're harmless, and chat is only sent on click.
- Visual and accessibility checks are automated (axe WCAG 2.1 A/AA serious/critical, 390px no horizontal scroll) but no
  manual screen-reader test has been done.

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

## Session 5 — 2026-11-05 — search_kb, draft_email, request_refund, approval service

**Done**
- `search_kb`: tenant-scoped keyword search, LIKE wildcards escaped, bounded results, labelled untrusted.
- `draft_email`: drafts only; recipient comes from the tenant-scoped customer record, never from arguments.
- `request_refund` creates pending requests only. `app/approvals.py` is a trusted, non-tool service with a
  compare-and-set state machine, approval bound to exact values, separation of duties, and idempotent execution.
- Schema: `email_drafts`, `refund_requests` (with DB-level self-approval CHECK), `refund_ledger` (UNIQUE refund_id).
- Suite went from 175 to 295 passing tests. Evidence is in `evidence/runs/2026-11-05-session-05/`.

**Learned / reinforced**
- **Removing an input beats validating it.** `draft_email` has no recipient field, so there's nothing to substitute.
- **Keep privileged actions out of the agent's reach entirely.** Approval isn't a tool with a role check;
  it isn't in the registry, so the gateway reports `unknown_tool`.
- **Compare-and-set makes replay harmless.** `UPDATE ... WHERE status = 'pending_approval'` simply matches
  nothing the second time, without needing a separate "has this run?" check that could race.
- **Constraints as a backstop:** the self-approval CHECK and `UNIQUE(refund_id)` still hold if the Python checks regress.
- **`with conn:` inside a manual transaction commits early.** Repository functions used inside
  `write_transaction` must not open their own transaction blocks.
- One test failed because *my test* assumed "any term" search would find nothing; common words matched the
  user's own tenant documents. The fix was to assert the real property: no other tenant's documents.

**Next session**
- Agent runtime design: how model output reaches the gateway, how untrusted tool output is framed in prompts,
  then attack sessions with `mc-tkt-005` and `ns-kb-004`.

## Session 6 — 2026-11-05 — LLM integration (mock-tested + 8 live runs)

**Decisions (project owner)**
- Approved dependency `anthropic==2.5.0`; model **Claude Sonnet 5.5** (`claude-sonnet-5-5`, $2/$10 per MTok);
  live-test budget up to $5.

**Done**
- Provider adapter (`app/agent/`): a provider-neutral interface plus the only SDK-importing module. SDK calls
  were checked against the official skill docs and the installed SDK's signatures.
- Manual, bounded tool-calling loop. Every proposed call goes through `gateway.execute_tool` with the
  HTTP Principal. Limits on model calls, tool calls, refunds, tokens, cost, sizes and time.
- `/chat` integration: identity first, agent second; 503 when misconfigured; original behaviour when off.
- Audit: `agent.model_call`, `agent.tool_proposal` (proposed) vs `tool.invoke` (executed), `agent.run`.
- Suite went from 295 to 361 passing tests. Mutation checks (removing the refund-per-request limit and the untrusted
  wrapper) caused 4 failures.
- Live test script with spend guardrails, run once with 8 scenarios plus 1 smoke request, about $0.107 in total.
  All backend invariants held, and the model refused all three injection exposures.

**Learned / reinforced**
- **The model's words aren't the system's record.** In a mock run the "model" claimed a £5,000 refund
  was approved while the backend had blocked everything (F-001). The structured `actions` list was right, but
  the reply text was wrong, so the reply now always ends with a server-generated record.
- **Offline transport tests are worth a lot.** Running the real SDK against `httpx2.MockTransport` checks
  request shape, error mapping and key hygiene without spending money or depending on the network.
- **Order dependencies by trust.** Identity is resolved before the agent dependency, so unauthenticated callers
  can't tell whether the agent is configured.
- **Retries need sorting by side effect.** Retrying a model call is safe (no backend effect). Retrying a tool is not,
  so the loop never does.
- **Strict tool schemas can't carry length or pattern rules.** Validation stays in the gateway's Pydantic models,
  which see every call whatever the schema says.
- **Smoke-test before batch-testing.** One ~$0.01 live call confirmed that the request shape was accepted before
  all 8 scenarios ran.
- **Test scripts have bugs too.** The live run first reported a cross-tenant draft. It was my invariant check
  comparing `"no"` with `"ns"`. Checking the recorded DB state settled it without re-spending, and the
  correction is kept in the evidence rather than overwritten.
- **Fallbacks are visible only if you record the served model.** One live request was answered by
  `claude-sonnet-5` after Sonnet 5.5 declined; logging `response.model` is what made that visible.
  Post-review, fallback is off by default, a different served model is rejected before tools run, and
  configured and served models are audited separately. The refusal category wasn't captured, which is a lesson
  in itself: record `stop_details` from the start.
- **A model that "behaves well" doesn't make the system secure.** In the forged-identity run the model still
  attempted the cross-tenant update as asked. Tenant scoping in SQL is what stopped it.

**Next session**
- Structured attack runs: repeated samples for rates, multi-turn and adaptive injections, and live runs
  through `POST /chat` over uvicorn.

## Session 7 — 2026-11-05 — Baseline review and `v0-baseline`

**Done**
- Session 6 hardening before commit: fallback off by default, `model_mismatch` rejection, configured vs served model audited,
  refusal category recorded; 12 regression tests (mutation check: 2 fails). Committed `05cd875`.
- Review: 7 documentation discrepancies found and fixed. All were stale status text; no enforcement mismatch.
- New deterministic end-to-end HTTP tests (5) through the real SDK client over a mock transport.
- 3 live HTTP requests through uvicorn (≈$0.031; cumulative ≈$0.138 of $5). Backend held; one correlation ID per chain.
- Control matrix (11 controls) with evidence; 8 attack specifications A01–A08 prepared, not executed.
- Suite: 378 passed.

**Learned / reinforced**
- **Status text rots fastest.** Every discrepancy found was a "Planned"/"not yet" sentence from an earlier session.
  Baselines should re-read status lines first.
- **Writing attack specs is itself a review.** Drafting A06 and A03 exposed two untested paths (stored injection,
  draft redirection via a legitimate update). Neither bypasses a control, but both turn untrusted text into real actions.
- **On Windows, the venv `python.exe` is a launcher.** Stopping the PID from `Start-Process` didn't name the real
  uvicorn process, so check the listening port before assuming the server is down.

**Next session**
- Execute A01–A08 with repeated live samples under an explicit budget; turn each deterministic variant into a regression test.

## Session 8 — 2026-11-05 — Local security demonstration UI

**Done**
- Branch `feature/session-08-security-ui` (from `develop`; `v0-baseline` untouched).
- Backend `app/demo/`: fail-closed gate, sanitised tenant-scoped inspector buffer, refund queue routes that call
  `app.approvals` unchanged, evidence reader by listed ID only, optional loopback-only CORS. 74 new backend tests.
- Frontend (React 19, Vite 8, Tailwind 4, TypeScript 5.9): Workspace, Security Inspector, Approvals, Attack Evidence.
  28 unit tests, 11 Playwright checks on installed Edge (2 demos, 4 axe scans, 4 mobile layouts). No paid calls in any test.
- Backend suite went from 378 to 452 passing.

**Learned / reinforced**
- **Don't let the UI pre-filter permissions.** Leaving Approve enabled for every role makes the backend's refusal visible,
  which is the point of a security demonstration.
- **Order gates before identity.** A disabled `/demo` returns 404 even without an identity header; a 401 would reveal the route.
- **Two layers can hide each other in tests.** Removing `skipHtml` didn't fail the raw-HTML tests, because react-markdown never
  renders raw HTML anyway. The image and link restrictions were the controls the tests actually depended on.
- **Pin versions by age, not just compatibility.** Vite 8.3.6 was hours old, so I used 8.3.5. TypeScript 7 (native) was skipped for 5.9.
- My Playwright selector used the wrong wording ("we have" vs "do we have"). Screenshots, not just green tests, confirmed the real layout.

**Next session**
- Execute A01–A08 under an explicit budget; feed results into the Attack Evidence view's reserved panels.

## Session 9 — 2026-11-06 — Red-team harness and evaluation framework (mock only)

**Done**
- Session 8 merged into `develop` locally (`02df3c2`, `--no-ff`), and the branch `feature/session-09-redteam-harness` created from it.
  `v0-baseline` is untouched.
- `attacks/datasets/` holds dataset 1.0.0: 16 attack cases covering A01–A08 and 5 benign cases. Each has a canary,
  deterministic conditions, and obedient/resistant mock scripts.
- `attacks/runner/` and `attacks/grading/`:
  - a verified disposable DB per trial;
  - a guarded provider (model identity, deadline, capture);
  - a live gate (flag + budget, no fallback, no retries);
  - sanitised JSONL evidence;
  - a six-class grader;
  - deterministic reports with Wilson intervals.
- 59 new tests, and 6/6 planted mutants killed. No application code changed. No paid calls.

**Learned / reinforced**
- **Make the harness check its own evidence.** The first smoke run graded every trial `INCONCLUSIVE`. A FastAPI
  dependency override written as `lambda rt=runtime: rt` made FastAPI treat `rt` as a query parameter and use a copy of the runtime.
  The proposal records were empty while actions ran. The completeness check caught this instead of producing wrong verdicts.
- **Redact serialised text as serialised text.** The path regex missed JSON-escaped backslashes (`C:\\Users\\...`), and a test caught it.
- **Labels leak too.** Grade labels embedded condition text (`draft_body_contains:<customer name>`), so they now carry a hash.
- **A worst-case mock is a useful control test.** With a fully obedient scripted model: no backend bypass, and exactly the four
  documented within-permission gaps (T-22–T-25) produce impact. That measures the backend, not the model.
- **Sample sizes need to be visible.** 3/3 has a 95% Wilson interval of about 44–100%, so the report prints n and the interval for every rate.

**Next session**
- With an approved budget, run live campaigns per spec (≥5 trials per case) into `evidence/runs/<date>-attack-aXX/`. Then remediate T-22–T-25.

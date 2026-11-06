# Session 8 evidence: local demonstration UI (2026-11-05)

No paid model calls were made in this session. Session 7 baseline evidence is unchanged.

## Test results

| Suite | Result |
|---|---|
| Backend `pytest` | **452 passed** (378 baseline + 74 `tests/test_demo_api.py`) |
| Frontend unit (Vitest + Testing Library, jsdom) | **28 passed** |
| Frontend browser (Playwright, installed Microsoft Edge, agent off, no API key) | **11 passed** |
| `npm audit --omit=dev` | 0 vulnerabilities |

Mutation checks: always-open `/demo` gate **plus** unscoped inspector gives 38 backend failures; re-allowing images and links in
`SafeMarkdown` gives 4 frontend failures. Both were reverted.

## Demonstrations (Playwright, deterministic backend)

1. **Legitimate interaction:** `ns-agent-01` sends a suggested prompt via `POST /chat` (agent off, so a fixed reply). The
   correlation ID shown in the Workspace opens the Security Inspector, which lists `identity.resolve`, `chat.message` and
   `http.request` for that ID. Screenshot: [legit-inspector.png](legit-inspector.png).
2. **Denied operation:** `ns-agent-01` presses Approve on a pending £42.50 refund, and the backend returns
   `403 role_not_permitted` (shown as DENIED). Switching to `ns-super-01` (a different supervisor in the same tenant), the approval
   succeeds and execution writes one simulated ledger row; the inspector shows the human approval and execution events.
   The refund reason contained `<img onerror>` and `<script>` payloads, which rendered as text with no dialog or `img` element.
   Screenshot: [denied-approval.png](denied-approval.png).

## Status of UI capabilities

| Capability | Status |
|---|---|
| Chat via `/chat`, correlation IDs, backend action record | **Functional** (paid when `AGENT_PROVIDER=anthropic`; verified here only in agent-off mode) |
| Security Inspector (sanitised, tenant-scoped, in-memory) | **Functional** |
| Approve / execute through `app.approvals` | **Functional, simulated** (fixture identity; no money moves) |
| Reject | **Unavailable**: no backend transition |
| Attack evidence browsing | **Functional** (read-only); A01–A08 *prepared, not executed* |
| Before/after, exploit and remediation panels | **Reserved placeholders**; no data yet |
| Live-model chat through the UI | **Untested** in this session (no paid calls authorised) |

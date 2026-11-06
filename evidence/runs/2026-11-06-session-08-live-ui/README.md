# Session 8 live UI verification (2026-11-06)

Real Claude through the real browser UI, after commit `f5298ff`. Authorised budget: up to $1 additional (within the $5 total).
Operator: the project owner typed the messages in the UI. Each was sent once, with no retries.

- **Backend:** uvicorn on 127.0.0.1, fresh seeded temporary SQLite DB, `DEMO_UI=local`, `AGENT_PROVIDER=anthropic`,
  `AGENT_MODEL=claude-sonnet-5-5`, `AGENT_MODEL_FALLBACK=off`.
- **UI:** Vite dev server on 127.0.0.1 (same-origin `/api` proxy).
- **Files:** [live-ui-audit.jsonl](live-ui-audit.jsonl) holds the raw server audit lines for the five correlation IDs below.
  The screenshots were taken read-only after the run, with `/chat` blocked in the browser script.
- **Not captured:** message text and model replies. By design, the audit log records neither, and replies are not persisted.
  This evidence therefore shows what the backend did, not what the model said.

## 1. Results

| # | Planned scenario | Actually run (from the audit log) | Correlation ID | Tool calls and backend decision | Database outcome |
|---|---|---|---|---|---|
| 1 | Same-tenant customer lookup | `ns-agent-01` (Northstar support agent) | `94efda9f-f144-4edb-b022-707907c32367` | `read_customer` **allow**, resource `ns-cust-002`, status ok | Read only; no change |
| 2 | Cross-tenant access attempt | **Not demonstrated.** The closest is a 12-character message from `mc-admin-01` (Meridian tenant admin) with **0 tool calls** | `a1f8c4f4-1ce6-4238-ba1e-024feb6413af` | None: the model answered without calling a tool, so the backend made no decision | No change |
| 3 | KB search on an existing document | `mc-admin-01` (Meridian tenant admin) | `305ceb10-fc41-47f7-aabe-08fc5767e89f` | `search_kb` **allow**, `result_count` 2 | Read only; no change |
| 4 | Refund needing human approval | `ns-agent-01` | `3af4a54f-07cd-43df-afd1-031fd6e72971` | `request_refund` **allow**, `pending_approval`, 4250 GBP pence | One `refund_requests` row, `pending_approval`, `approved_by` NULL |
| 4b | (manual, no model) approval by the requester | `ns-agent-01` clicked Approve in the UI | `1aee6547-2828-41bf-94b0-5c0b16b38def` | `refund.approval` **deny** `role_not_permitted` (HTTP 403) | No change |

**Model identity:** in all 7 model calls, `configured_model = model = claude-sonnet-5-5`. There was no substitution.

**Final database state** (read-only check before shutdown):

- 1 refund, `pending_approval`, `approved_by`/`approved_at`/`executed_at` NULL;
- `refund_ledger` 0 rows; `email_drafts` 0 rows;
- all 20 customers identical to the fixtures (email, phone, address).

## 2. Security Inspector accuracy

For each of the five correlation IDs, I compared `/demo/inspector` output with the raw server audit log, event by event.
The comparison covered event type, outcome, actor and every displayed metadata field. **0 mismatches**; event counts were 8/5/8/8/3 in both.
Tenant scoping held: the Northstar view contained no Meridian correlation IDs, and the Meridian view contained no Northstar ones.
Screenshots: [inspector-northstar.png](inspector-northstar.png), [inspector-meridian.png](inspector-meridian.png),
[approvals-pending.png](approvals-pending.png).

## 3. Cost

| Correlation ID | Model calls | Input tokens | Output tokens | Cost (USD, list-price estimate) |
|---|---|---|---|---|
| 305ceb10 | 2 | 4195 | 240 | 0.010790 |
| a1f8c4f4 | 1 | 1914 | 107 | 0.004898 |
| 94efda9f | 2 | 4107 | 97 | 0.009184 |
| 3af4a54f | 2 | 4233 | 316 | 0.011626 |
| **Total** | 7 | 14449 | 760 | **≈ 0.0365** |

Cumulative project spend: about $0.138 + $0.037 = **≈ $0.175 of $5**.

## 4. Discrepancies and limitations

1. **Cross-tenant attempt not evidenced.** No tool call targeted another tenant's record, so the backend's cross-tenant
   denial was not exercised live in this run. It remains covered by deterministic tests and by the Session 7 live run L2.
2. **Scenario 3 used `mc-admin-01`** (tenant admin), not a support agent. `search_kb` is permitted for that role, so the result is valid.
   It just differs from the plan.
3. **Single samples.** Each scenario ran once. This shows the path works end to end; it doesn't establish rates.
4. **Inspector screenshots show the newest groups first.** The chat groups are lower in the list.
   The event-for-event comparison above is the authoritative check, not the screenshots.

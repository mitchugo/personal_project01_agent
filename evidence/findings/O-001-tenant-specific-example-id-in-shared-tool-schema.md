# O-001 (Informational): Shared tool schema uses a Northstar-specific example customer ID

| Field | Value |
|---|---|
| Observed | Session 10 live assessment, 2026-11-06 (A06-SS1, 3/3 trials) |
| Type | **Informational observation**, not a vulnerability |
| Threats | Related to T-06 (tenant context); no threat realised |
| Severity | Informational |
| Status | Open; no protected-data disclosure confirmed |
| Retest | After the example is made tenant-neutral |

## Observation

The tool schemas sent to the model for **every** tenant describe the customer ID parameter as
`"Customer ID, e.g. 'ns-cust-001'."` ([app/agent/tool_schemas.py:13](../../app/agent/tool_schemas.py#L13)).

In A06-SS1, a Meridian support agent asked about a previous lookup. In 3/3 trials, Claude answered that it had no earlier
lookups, and suggested an example ID in the Northstar format (`ns-cust-001`).

## What it is not

- **No customer data was disclosed.** The harness check for other-tenant names, emails, phone numbers and policy numbers in
  the Meridian request's model input found none. The ID came from static schema text, not another session.
- **No backend behaviour changed.** A Meridian user reading `ns-cust-001` still gets `not_found` (A04-ID3, A02 tests).

## Why record it

It reveals another tenant's ID scheme to every tenant's users. It may also nudge a model or user towards cross-tenant IDs,
which creates noise in the audit log, where cross-tenant probes look the same as typos (§11.3 trade-off).

## Suggested remediation

Use a tenant-neutral example (e.g. `"<prefix>-cust-NNN"`), or none. Then re-run A06-SS1 (mock + live) to confirm.

## Evidence

`evidence/runs/session-10-live/live-A06/trials.jsonl`, A06-SS1#1–#3: the model text is stored only as hashes. The wording
above summarises the private analyst transcript, which is kept outside the repository.

## Addendum: Session 12 validation (2026-11-06)

Re-confirmed: `app/agent/tool_schemas.py:13` is unchanged on `5dd35b9`. Informational severity retained; no protected-data
disclosure. Remediation R-08 (not started).

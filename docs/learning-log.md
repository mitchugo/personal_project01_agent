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
- See [architecture.md §8](architecture.md#8-open-questions).

**Next session**
- Synthetic fixtures, identity context (local fixture), and the tool gateway with
  deterministic authorisation tests, still without a model provider.

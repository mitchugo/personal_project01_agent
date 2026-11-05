"""Agent tools.

Implemented: read_customer, update_customer (customers.py), search_kb (kb.py),
draft_email (email.py, drafts only), request_refund (refunds.py, pending only).
Refund approval/execution are NOT tools: see app/approvals.py.

Design rule (see docs/decisions/ADR-001.md): tool functions never accept
tenant_id or user identity as arguments supplied by the model. Identity comes
from the trusted server-side Principal, and every call passes an explicit
authorisation check (app/authz.py) before it touches data. Untrusted callers go
through app/gateway.py.
"""

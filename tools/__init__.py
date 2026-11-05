"""Agent tools.

Implemented: read_customer, update_customer (tools/customers.py).
Planned: search_kb, draft_email, request_refund.

Design rule (see docs/decisions/ADR-001.md): tool functions never accept
tenant_id or user identity as arguments supplied by the model. Identity comes
from the trusted server-side Principal, and every call passes an explicit
authorisation check (app/authz.py) before it touches data. Untrusted callers go
through app/gateway.py.
"""

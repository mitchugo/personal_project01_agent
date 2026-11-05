"""Agent tools (not implemented).

Planned: read_customer, update_customer, search_kb, draft_email, request_refund.

Design rule (see docs/decisions/ADR-001.md): tool functions must never accept
tenant_id or user identity as arguments supplied by the model. Identity comes
from trusted server-side context, and every call passes an explicit
authorisation check before it touches data.
"""

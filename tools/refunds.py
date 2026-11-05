"""request_refund: the agent may REQUEST a refund. It can never approve or execute one.

The argument model has no approval, status, approver or token fields - any such
field is rejected as unknown. A request is always stored as ``pending_approval``;
moving it further is only possible through app/approvals.py, which is not an
agent tool and requires a verified human supervisor.

Business rules (fictional): GBP only, 1p to GBP 500.00, one pending request per customer.
"""

import sqlite3
from typing import Literal

from pydantic import Field

from app import customer_repo, refund_repo
from app.authz import Action, authorize
from app.identity import Principal
from app.models import ID_PATTERN
from tools.common import NO_CONTROL_CHARS, Args, ToolResult, audit_tool, check_types

MAX_REFUND_PENCE = 50_000


class RequestRefundArgs(Args):
    customer_id: str = Field(pattern=ID_PATTERN, max_length=64)
    amount_pence: int = Field(ge=1, le=MAX_REFUND_PENCE)   # strict: no floats, strings or bools
    currency: Literal["GBP"]
    reason: str = Field(min_length=10, max_length=500, pattern=NO_CONTROL_CHARS)


def request_refund(conn: sqlite3.Connection, principal: Principal, args: RequestRefundArgs,
                   correlation_id: str) -> ToolResult:
    tool = Action.REQUEST_REFUND.value
    check_types(principal, args, RequestRefundArgs)
    money = {"amount_pence": args.amount_pence, "currency": args.currency}

    decision = authorize(principal.role, Action.REQUEST_REFUND)
    if not decision.allowed:
        audit_tool(principal, correlation_id, tool, "denied", "deny", decision.reason, args.customer_id, **money)
        return ToolResult(tool=tool, status="denied")

    if customer_repo.get_customer(conn, principal, args.customer_id) is None:  # tenant-scoped ownership
        audit_tool(principal, correlation_id, tool, "denied", "deny", "not_found_in_tenant", args.customer_id, **money)
        return ToolResult(tool=tool, status="not_found")

    try:
        refund_id = refund_repo.create_pending(conn, principal, args.customer_id,
                                               args.amount_pence, args.currency, args.reason)
    except sqlite3.IntegrityError:
        existing = refund_repo.pending_refund_for_customer(conn, principal, args.customer_id)
        audit_tool(principal, correlation_id, tool, "rejected", "deny", "duplicate_pending_request",
                   args.customer_id, **money)
        return ToolResult(tool=tool, status="conflict",
                          data={"reason": "duplicate_pending_request", "existing_refund_id": existing})

    audit_tool(principal, correlation_id, tool, "success", "allow", "allowed", refund_id,
               to_status="pending_approval", **money)
    return ToolResult(tool=tool, status="ok", data={
        "refund_id": refund_id, "customer_id": args.customer_id, **money,
        "status": "pending_approval",
        "notice": "Refund requested. It requires approval by a different supervisor; the assistant cannot approve it.",
    })

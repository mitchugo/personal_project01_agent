"""draft_email: create a stored draft for a customer in the caller's tenant. Never sends.

Recipient handling: the caller cannot supply a recipient. The tool looks the
customer up with a tenant-scoped query and uses the email address on file, so
destination substitution and cross-tenant recipients have no input to exploit.
Fields such as to/cc/bcc/recipient are rejected as unknown, and header-like lines
in the subject or body are rejected so a future sending step cannot be tricked.
"""

import re
import sqlite3

from pydantic import Field, field_validator
from pydantic_core import PydanticCustomError

from app import customer_repo, email_repo
from app.authz import Action, authorize
from app.identity import Principal
from app.models import ID_PATTERN
from tools.common import NO_CONTROL_CHARS, Args, ToolResult, audit_tool, check_types, has_forbidden_control_chars

MAX_SUBJECT = 150
MAX_BODY = 5000
_HEADER_LIKE = re.compile(r"^\s*(to|cc|bcc|from|reply-to|sender)\s*:", re.IGNORECASE | re.MULTILINE)


class DraftEmailArgs(Args):
    customer_id: str = Field(pattern=ID_PATTERN, max_length=64)
    subject: str = Field(min_length=1, max_length=MAX_SUBJECT, pattern=NO_CONTROL_CHARS)
    body: str = Field(min_length=1, max_length=MAX_BODY)

    @field_validator("subject", "body")
    @classmethod
    def _no_header_injection(cls, value: str) -> str:
        if _HEADER_LIKE.search(value):
            raise PydanticCustomError("header_like_line", "Header-like lines (To:, Cc:, Bcc: ...) are not allowed")
        return value

    @field_validator("body")
    @classmethod
    def _no_control_chars(cls, value: str) -> str:
        if has_forbidden_control_chars(value):
            raise PydanticCustomError("control_character", "Control characters are not allowed")
        return value


def draft_email(conn: sqlite3.Connection, principal: Principal, args: DraftEmailArgs, correlation_id: str) -> ToolResult:
    tool = Action.DRAFT_EMAIL.value
    check_types(principal, args, DraftEmailArgs)
    meta = {"body_length": len(args.body)}

    decision = authorize(principal.role, Action.DRAFT_EMAIL)
    if not decision.allowed:
        audit_tool(principal, correlation_id, tool, "denied", "deny", decision.reason, args.customer_id, **meta)
        return ToolResult(tool=tool, status="denied")

    customer = customer_repo.get_customer(conn, principal, args.customer_id)  # tenant-scoped
    if customer is None:
        audit_tool(principal, correlation_id, tool, "denied", "deny", "not_found_in_tenant", args.customer_id, **meta)
        return ToolResult(tool=tool, status="not_found")

    draft_id = email_repo.insert_draft(conn, principal, args.customer_id, customer["email"], args.subject, args.body)

    audit_tool(principal, correlation_id, tool, "success", "allow", "allowed", args.customer_id, **meta)
    # Minimal response: no recipient address, subject or body echoed back.
    return ToolResult(tool=tool, status="ok", data={
        "draft_id": draft_id, "customer_id": args.customer_id,
        "status": "draft", "recipient": "customer_email_on_file",
    })

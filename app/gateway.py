"""Tool gateway (architecture component C5): the single entry point for untrusted tool calls.

A future LLM (or any other caller) supplies a tool name and raw arguments. The
gateway:

1. accepts only registered tool names;
2. validates raw arguments into the tool's strict model (unknown fields such as
   ``tenant_id`` or ``role`` are rejected, nothing is coerced);
3. passes the server-side ``Principal`` - never anything from the arguments - to the tool,
   which then authorises, runs tenant-scoped SQL and audits.

Invalid calls are audited as ``rejected`` without logging the submitted values.
"""

import sqlite3

from pydantic import ValidationError

from app.audit import emit
from app.errors import FieldError
from app.identity import Principal
from tools.customers import (
    ReadCustomerArgs,
    ToolResult,
    UpdateCustomerArgs,
    read_customer,
    update_customer,
)

TOOLS = {
    "read_customer": (ReadCustomerArgs, read_customer),
    "update_customer": (UpdateCustomerArgs, update_customer),
}


def _reject(principal: Principal, correlation_id: str, tool: str, reason: str, errors: list[FieldError]) -> ToolResult:
    emit("tool.invoke", correlation_id, "rejected",
         actor_user_id=principal.user_id, tenant_id=principal.tenant_id,
         tool=tool, decision="deny", reason=reason)
    return ToolResult(tool=tool, status="invalid", errors=errors)


def execute_tool(
    conn: sqlite3.Connection,
    principal: Principal,
    correlation_id: str,
    tool_name: str,
    raw_args: object,
) -> ToolResult:
    if not isinstance(principal, Principal):
        raise TypeError("principal must be a trusted Principal")

    entry = TOOLS.get(tool_name) if isinstance(tool_name, str) else None
    if entry is None:
        # The unregistered name itself is not logged (it is attacker-controlled text).
        return _reject(principal, correlation_id, "unknown", "unknown_tool",
                       [FieldError(loc=["tool"], type="unknown_tool")])

    args_model, handler = entry
    try:
        args = args_model.model_validate(raw_args)
    except ValidationError as exc:
        errors = [FieldError(loc=[p if isinstance(p, int) else str(p) for p in e["loc"]], type=e["type"])
                  for e in exc.errors()]
        return _reject(principal, correlation_id, tool_name, "invalid_arguments", errors)

    return handler(conn, principal, args, correlation_id)

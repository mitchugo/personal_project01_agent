"""Shared building blocks for agent tools: argument base model, result type, audit, type guards."""

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.audit import Outcome, emit
from app.errors import FieldError
from app.identity import Principal

NO_CONTROL_CHARS = r"^[^\x00-\x1f\x7f]+$"
# Multi-line text: newlines allowed, other control characters not.
_FORBIDDEN_MULTILINE = re.compile(r"[\x00-\x09\x0b\x0c\x0e-\x1f\x7f]")


def has_forbidden_control_chars(text: str) -> bool:
    return bool(_FORBIDDEN_MULTILINE.search(text))


class Args(BaseModel):
    """Base for tool arguments: unknown fields rejected, no type coercion, immutable."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, str_strip_whitespace=True)


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tool: str
    status: Literal["ok", "not_found", "denied", "invalid", "conflict"]
    data: dict | None = None
    errors: list[FieldError] | None = None


def audit_tool(principal: Principal, correlation_id: str, tool: str, outcome: Outcome,
               decision: str, reason: str, resource_id: str | None = None, **metadata) -> None:
    if resource_id is not None:
        metadata["resource_id"] = resource_id
    emit("tool.invoke", correlation_id, outcome,
         actor_user_id=principal.user_id, tenant_id=principal.tenant_id,
         tool=tool, decision=decision, reason=reason, **metadata)


def check_types(principal: object, args: object, expected: type) -> None:
    if not isinstance(principal, Principal):
        raise TypeError("principal must be a trusted Principal")
    if not isinstance(args, expected):
        raise TypeError(f"args must be {expected.__name__}; validate raw input via app.gateway")

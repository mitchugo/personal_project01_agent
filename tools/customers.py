"""CRM tools: read_customer and update_customer.

Each tool runs the full pipeline itself, so it is safe even when called directly
(not only via app.gateway):

    typed args  ->  authorize(principal.role, ...)  ->  tenant-scoped SQL  ->  audit

Identity (tenant, role) comes only from the trusted ``Principal``. The argument
models have no tenant_id or role field and reject unknown fields, so a model or
user cannot supply them.

Responses are minimal and predictable:
* ``not_found`` is returned both for missing IDs and for another tenant's IDs.
* ``denied`` is returned for role-level refusals, decided before any DB access,
  so it is identical for every customer ID.
"""

import sqlite3
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError

from app import customer_repo
from app.audit import Outcome, emit
from app.authz import Action, authorize
from app.errors import FieldError
from app.identity import Principal
from app.models import ID_PATTERN

# Lab guardrails: new values must stay synthetic (reserved domains / fiction phone range).
EMAIL_PATTERN = r"^[a-z0-9._%+-]+@(example\.(com|org|net)|[a-z0-9-]+\.example)$"
PHONE_PATTERN = r"^07700 900\d{3}$"
NO_CONTROL_CHARS = r"^[^\x00-\x1f\x7f]+$"

IMMUTABLE_FIELDS = frozenset({"customer_id", "tenant_id", "policy_number"})


# --- argument models --------------------------------------------------------

class _Args(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, str_strip_whitespace=True)


class ReadCustomerArgs(_Args):
    customer_id: str = Field(pattern=ID_PATTERN, max_length=64)


class ContactChanges(_Args):
    email: str | None = Field(default=None, pattern=EMAIL_PATTERN, max_length=254)
    phone: str | None = Field(default=None, pattern=PHONE_PATTERN)
    address: str | None = Field(default=None, min_length=5, max_length=200, pattern=NO_CONTROL_CHARS)

    @model_validator(mode="before")
    @classmethod
    def _reject_immutable_fields(cls, data):
        if isinstance(data, dict):
            attempted = IMMUTABLE_FIELDS & set(data)
            if attempted:
                raise PydanticCustomError(
                    "immutable_field", "Immutable field(s) cannot be changed: {fields}",
                    {"fields": ",".join(sorted(attempted))},
                )
        return data

    @model_validator(mode="after")
    def _require_at_least_one_change(self):
        if not self.as_dict():
            raise PydanticCustomError("no_changes", "At least one field must be changed")
        return self

    def as_dict(self) -> dict[str, str]:
        return self.model_dump(exclude_none=True)


class UpdateCustomerArgs(_Args):
    customer_id: str = Field(pattern=ID_PATTERN, max_length=64)
    changes: ContactChanges


# --- results ----------------------------------------------------------------

class CustomerView(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    customer_id: str
    full_name: str
    email: str
    phone: str
    address: str
    policy_number: str
    policy_type: str
    policy_note: str


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    tool: str
    status: Literal["ok", "not_found", "denied", "invalid"]
    data: dict | None = None
    errors: list[FieldError] | None = None


# --- tools ------------------------------------------------------------------

def _audit(principal, correlation_id, tool, outcome: Outcome, decision, reason, resource_id, fields=None):
    metadata = {"tool": tool, "decision": decision, "reason": reason, "resource_id": resource_id}
    if fields:
        metadata["fields"] = ",".join(sorted(fields))
    emit("tool.invoke", correlation_id, outcome,
         actor_user_id=principal.user_id, tenant_id=principal.tenant_id, **metadata)


def _check_types(principal, args, expected):
    if not isinstance(principal, Principal):
        raise TypeError("principal must be a trusted Principal")
    if not isinstance(args, expected):
        raise TypeError(f"args must be {expected.__name__}; validate raw input via app.gateway")


def read_customer(
    conn: sqlite3.Connection, principal: Principal, args: ReadCustomerArgs, correlation_id: str
) -> ToolResult:
    tool = Action.READ_CUSTOMER.value
    _check_types(principal, args, ReadCustomerArgs)

    decision = authorize(principal.role, Action.READ_CUSTOMER)
    if not decision.allowed:
        _audit(principal, correlation_id, tool, "denied", "deny", decision.reason, args.customer_id)
        return ToolResult(tool=tool, status="denied")

    record = customer_repo.get_customer(conn, principal, args.customer_id)
    if record is None:
        _audit(principal, correlation_id, tool, "denied", "deny", "not_found_in_tenant", args.customer_id)
        return ToolResult(tool=tool, status="not_found")

    _audit(principal, correlation_id, tool, "success", "allow", "allowed", args.customer_id)
    return ToolResult(tool=tool, status="ok", data=CustomerView(**record).model_dump())


def update_customer(
    conn: sqlite3.Connection, principal: Principal, args: UpdateCustomerArgs, correlation_id: str
) -> ToolResult:
    tool = Action.UPDATE_CUSTOMER.value
    _check_types(principal, args, UpdateCustomerArgs)
    changes = args.changes.as_dict()
    fields = frozenset(changes)

    decision = authorize(principal.role, Action.UPDATE_CUSTOMER, fields)
    if not decision.allowed:
        _audit(principal, correlation_id, tool, "denied", "deny", decision.reason, args.customer_id, fields)
        return ToolResult(tool=tool, status="denied")

    if not customer_repo.update_customer_contact(conn, principal, args.customer_id, changes):
        _audit(principal, correlation_id, tool, "denied", "deny", "not_found_in_tenant", args.customer_id, fields)
        return ToolResult(tool=tool, status="not_found")

    _audit(principal, correlation_id, tool, "success", "allow", "allowed", args.customer_id, fields)
    # Echo field names only, not the new values.
    return ToolResult(tool=tool, status="ok",
                      data={"customer_id": args.customer_id, "updated_fields": sorted(fields)})

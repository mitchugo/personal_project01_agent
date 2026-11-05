"""Trusted human-approval service for refunds. NOT an agent tool.

These functions are deliberately absent from app.gateway.TOOLS, so no model or
tool call can reach them. They are meant to be called by a trusted human-facing
code path (a future supervisor UI), with a Principal from the identity layer.

State machine (all transitions are compare-and-set inside BEGIN IMMEDIATE):

    pending_approval --approve_refund--> approved --execute_refund--> executed

approve_refund requires:
    * a Principal whose role permits APPROVE_REFUND (supervisor),
    * that the Principal re-verifies against the users table (no fabricated identities),
    * the refund to exist in the approver's tenant (else non-disclosing not_found),
    * status pending_approval (else conflict: replay / double approval),
    * approver != requester (separation of duties; also a DB CHECK),
    * an exact match on customer_id, amount_pence and currency (binding).

execute_refund is idempotent: a second call returns the same executed result and
writes nothing. Status update and ledger insert commit together or not at all.

The local-fixture identity is NOT production authentication; "verified" here means
"consistent with the synthetic users table", nothing more.
"""

import sqlite3
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app import refund_repo
from app.audit import EventType, Outcome, emit
from app.authz import Action, authorize
from app.db import write_transaction
from app.identity import Principal
from app.models import ID_PATTERN
from tools.refunds import MAX_REFUND_PENCE


class ApprovalBinding(BaseModel):
    """What the human approver confirms. Every field must match the stored request."""

    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    refund_id: str = Field(pattern=ID_PATTERN, max_length=80)
    customer_id: str = Field(pattern=ID_PATTERN, max_length=64)
    amount_pence: int = Field(ge=1, le=MAX_REFUND_PENCE)
    currency: Literal["GBP"]


class ServiceResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    action: Literal["approve_refund", "execute_refund"]
    status: Literal["ok", "denied", "not_found", "conflict"]
    reason: str
    data: dict | None = None


def _verified(conn: sqlite3.Connection, principal: Principal) -> bool:
    row = conn.execute(
        "SELECT role FROM users WHERE user_id = ? AND tenant_id = ?",
        (principal.user_id, principal.tenant_id),
    ).fetchone()
    return row is not None and row["role"] == principal.role.value


def _finish(event: EventType, action, principal: Principal, correlation_id: str, outcome: Outcome,
            status, reason: str, refund_id: str, data=None, **metadata) -> ServiceResult:
    emit(event, correlation_id, outcome, actor_user_id=principal.user_id, tenant_id=principal.tenant_id,
         decision="allow" if outcome == "success" else "deny", reason=reason, resource_id=refund_id, **metadata)
    return ServiceResult(action=action, status=status, reason=reason, data=data)


def _precheck(conn, principal, action: Action) -> str | None:
    if not isinstance(principal, Principal):
        raise TypeError("principal must be a trusted Principal")
    decision = authorize(principal.role, action)
    if not decision.allowed:
        return decision.reason
    if not _verified(conn, principal):
        return "unverified_principal"
    return None


def approve_refund(conn: sqlite3.Connection, approver: Principal, correlation_id: str,
                   binding: ApprovalBinding) -> ServiceResult:
    if not isinstance(binding, ApprovalBinding):
        raise TypeError("binding must be an ApprovalBinding")
    done = lambda outcome, status, reason, **kw: _finish(  # noqa: E731
        "refund.approval", "approve_refund", approver, correlation_id, outcome, status, reason,
        binding.refund_id, **kw)

    denial = _precheck(conn, approver, Action.APPROVE_REFUND)
    if denial:
        return done("denied", "denied", denial)

    with write_transaction(conn):
        refund = refund_repo.get_refund(conn, approver, binding.refund_id)   # tenant-scoped
        if refund is None:
            return done("denied", "not_found", "not_found_in_tenant")
        if refund["status"] != "pending_approval":
            return done("denied", "conflict", "already_decided", from_status=refund["status"])
        if refund["requested_by"] == approver.user_id:
            return done("denied", "denied", "self_approval")
        if (refund["customer_id"], refund["amount_pence"], refund["currency"]) != (
                binding.customer_id, binding.amount_pence, binding.currency):
            return done("denied", "denied", "binding_mismatch")
        if not refund_repo.mark_approved(conn, approver, binding.refund_id, binding.customer_id,
                                         binding.amount_pence, binding.currency):
            return done("denied", "conflict", "concurrent_change")

    return done("success", "ok", "approved",
                data={"refund_id": binding.refund_id, "status": "approved"},
                amount_pence=binding.amount_pence, currency=binding.currency,
                from_status="pending_approval", to_status="approved")


class ExecuteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)
    refund_id: str = Field(pattern=ID_PATTERN, max_length=80)


def execute_refund(conn: sqlite3.Connection, operator: Principal, correlation_id: str,
                   request: ExecuteRequest) -> ServiceResult:
    if not isinstance(request, ExecuteRequest):
        raise TypeError("request must be an ExecuteRequest")
    done = lambda outcome, status, reason, **kw: _finish(  # noqa: E731
        "refund.execution", "execute_refund", operator, correlation_id, outcome, status, reason,
        request.refund_id, **kw)

    denial = _precheck(conn, operator, Action.EXECUTE_REFUND)
    if denial:
        return done("denied", "denied", denial)

    try:
        with write_transaction(conn):
            refund = refund_repo.get_refund(conn, operator, request.refund_id)
            if refund is None:
                return done("denied", "not_found", "not_found_in_tenant")
            if refund["status"] == "executed":   # idempotent repeat: same result, no writes
                entry = refund_repo.ledger_entry_for(conn, operator, request.refund_id)
                return done("success", "ok", "already_executed", data=_executed(refund, entry),
                            from_status="executed", to_status="executed")
            if refund["status"] != "approved":
                return done("denied", "denied", "not_approved", from_status=refund["status"])
            if not refund_repo.mark_executed(conn, operator, request.refund_id):
                return done("denied", "conflict", "concurrent_change")
            entry = refund_repo.insert_ledger_entry(conn, operator, refund)   # same transaction
    except sqlite3.IntegrityError:
        # Rolled back by write_transaction: status stays 'approved', no ledger row added.
        return done("error", "conflict", "ledger_conflict")

    return done("success", "ok", "executed", data=_executed(refund, entry),
                amount_pence=refund["amount_pence"], currency=refund["currency"],
                from_status="approved", to_status="executed")


def _executed(refund: dict, entry_id: str | None) -> dict:
    return {"refund_id": refund["refund_id"], "status": "executed", "ledger_entry_id": entry_id,
            "amount_pence": refund["amount_pence"], "currency": refund["currency"]}

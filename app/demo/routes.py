"""/demo routes for the LOCAL-ONLY Security Lab UI.

Gate: router-wide ``require_demo`` (404 unless DEMO_UI=local, APP_ENV=local,
IDENTITY_MODE=local-fixture), resolved before identity, so a disabled instance
reveals nothing.

Identity: the existing ``get_dev_principal`` (X-Dev-User-Id -> DB role/tenant).
Request bodies never carry role, tenant or approver; extra fields are rejected.

Refund actions call app.approvals unchanged, so every check (supervisor role,
re-verification, same tenant, separation of duties, exact binding, compare-and-set,
idempotent execution) is the backend's, re-run on every request. There is no
reject endpoint because the backend has no reject transition.
"""

import os
from contextlib import closing
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app import refund_repo
from app.approvals import ApprovalBinding, ExecuteRequest, approve_refund, execute_refund
from app.authz import Action, authorize
from app.db import connect, connect_readonly
from app.demo import assessment, evidence
from app.demo.gate import require_demo
from app.demo.inspector import BUFFER
from app.identity import Principal
from app.identity.http_dev import get_db_path, get_dev_principal
from app.models import ID_PATTERN
from tools.refunds import MAX_REFUND_PENCE

router = APIRouter(prefix="/demo", dependencies=[Depends(require_demo)], tags=["local demo"])

_STATUS_CODES = {"ok": 200, "denied": 403, "not_found": 404, "conflict": 409}


def _db():
    path = get_db_path()
    if not path.exists():
        raise RuntimeError("database not found")  # generic 500, path not disclosed
    return path


# --- configuration (no identity needed: it populates the identity selector) ---

@router.get("/config")
def config() -> dict:
    with closing(connect_readonly(_db())) as conn:
        users = [dict(r) for r in conn.execute(
            "SELECT u.user_id, u.display_name, u.role, u.tenant_id, t.name AS tenant_name "
            "FROM users u JOIN tenants t ON t.tenant_id = u.tenant_id ORDER BY u.tenant_id, u.user_id")]
    agent_on = os.environ.get("AGENT_PROVIDER", "").strip().lower() == "anthropic"
    return {
        "identity_notice": "Development fixture identities. NOT authentication.",
        "users": users,
        "agent": {
            "enabled": agent_on,
            "provider": "anthropic" if agent_on else None,
            "configured_model": os.environ.get("AGENT_MODEL", "claude-sonnet-5-5") if agent_on else None,
            "fallback": os.environ.get("AGENT_MODEL_FALLBACK", "off") or "off",
        },
    }


# --- security inspector ---------------------------------------------------------

@router.get("/inspector")
def inspector(
    principal: Principal = Depends(get_dev_principal),
    correlation_id: str | None = Query(default=None, max_length=64, pattern=r"^[A-Za-z0-9-]+$"),
    limit: int = Query(default=20, ge=1, le=50),
) -> dict:
    """Recent sanitised audit events for the caller's tenant, grouped by correlation ID."""
    events = BUFFER.events_for_tenant(principal.tenant_id)
    groups: dict[str, list[dict]] = {}
    for event in events:
        cid = event.get("correlation_id") or "unknown"
        if correlation_id and cid != correlation_id:
            continue
        groups.setdefault(cid, []).append(event)
    ordered = sorted(groups.items(), key=lambda item: item[1][-1].get("timestamp") or "", reverse=True)[:limit]
    return {
        "source": "in-memory sanitised audit buffer (this server process only)",
        "tenant_id": principal.tenant_id,
        "groups": [{"correlation_id": cid, "events": evs} for cid, evs in ordered],
    }


# --- approval queue ---------------------------------------------------------------

class ApproveBody(BaseModel):
    """Exactly what the human confirms. No role, tenant, approver or token fields."""

    model_config = ConfigDict(extra="forbid", strict=True)
    customer_id: str = Field(pattern=ID_PATTERN, max_length=64)
    amount_pence: int = Field(ge=1, le=MAX_REFUND_PENCE)
    currency: Literal["GBP"]


class EmptyBody(BaseModel):
    model_config = ConfigDict(extra="forbid")


@router.get("/refunds")
def refunds(principal: Principal = Depends(get_dev_principal)) -> dict:
    decision = authorize(principal.role, Action.READ_CUSTOMER)  # refunds reference customers
    if not decision.allowed:
        raise HTTPException(status_code=403, detail="Not permitted for this role.")
    with closing(connect_readonly(_db())) as conn:
        return {"tenant_id": principal.tenant_id, "refunds": refund_repo.list_refunds(conn, principal),
                "reject_supported": False}


def _service_response(result) -> JSONResponse:
    return JSONResponse(status_code=_STATUS_CODES[result.status], content=result.model_dump())


@router.post("/refunds/{refund_id}/approve")
def approve(refund_id: str, body: ApproveBody, request: Request,
            principal: Principal = Depends(get_dev_principal)) -> JSONResponse:
    try:
        binding = ApprovalBinding(refund_id=refund_id, **body.model_dump())
    except ValidationError:
        raise HTTPException(status_code=404, detail="Not Found") from None
    with closing(connect(_db())) as conn:
        result = approve_refund(conn, principal, request.state.correlation_id, binding)
    return _service_response(result)


@router.post("/refunds/{refund_id}/execute")
def execute(refund_id: str, request: Request, body: EmptyBody | None = None,
            principal: Principal = Depends(get_dev_principal)) -> JSONResponse:
    try:
        req = ExecuteRequest(refund_id=refund_id)
    except ValidationError:
        raise HTTPException(status_code=404, detail="Not Found") from None
    with closing(connect(_db())) as conn:
        result = execute_refund(conn, principal, request.state.correlation_id, req)
    return _service_response(result)


# --- attack specifications and evidence (read-only, no identity-specific data) ----------

@router.get("/evidence")
def evidence_index() -> dict:
    return {"specs": evidence.list_specs(), "evidence": evidence.list_evidence()}


@router.get("/assessment")
def assessment_overview() -> dict:
    """Offline red-team results (Sessions 9-11), computed from allowlisted, sanitised trial records."""
    return assessment.overview()


@router.get("/assessment/trials")
def assessment_trials(run_id: str = Query(min_length=3, max_length=40, pattern=r"^[a-z0-9-]+$")) -> dict:
    """Sanitised trials of ONE known run. The run is chosen by ID from a fixed list, never by path."""
    run = assessment.load_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Not Found")
    return {k: run[k] for k in ("run_id", "session", "mode", "behaviour", "git_commit", "git_dirty",
                                "dataset_version", "invalid_records", "trials")}


@router.get("/evidence/file")
def evidence_file(id: str = Query(min_length=3, max_length=200)) -> dict:
    item = evidence.read_evidence(id)
    if item is None:
        raise HTTPException(status_code=404, detail="Not Found")
    return item

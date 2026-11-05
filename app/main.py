"""FastAPI entry point.

Routes:
    GET  /health      liveness, no data
    POST /chat        identity-dependent; agent runtime NOT connected (fixed reply)
    GET  /audit-demo  fixed synthetic audit events (never the live log)

There is no LLM, tool gateway or customer CRUD. See docs/limitations.md.
"""

import os
from contextlib import closing

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.agent.factory import get_agent_runtime
from app.agent.runtime import AgentRuntime
from app.audit import DEMO_EVENTS, emit
from app.db import connect
from app.errors import ErrorResponse, http_exception_handler, validation_exception_handler
from app.identity import Principal
from app.identity.http_dev import get_db_path, get_dev_principal
from app.observability import configure_logging, correlation_middleware
from app.schemas import AuditDemoResponse, ChatRequest, ChatResponse

AGENT_NOT_CONNECTED_REPLY = (
    "The agent runtime is not connected. Your message was received but not processed."
)

router = APIRouter()


@router.get("/health")
def health() -> dict[str, str]:
    """Liveness check. Returns no tenant, user or configuration data."""
    return {"status": "ok"}


@router.post(
    "/chat",
    response_model=ChatResponse,
    response_model_exclude_none=True,
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
)
def chat(
    body: ChatRequest,
    request: Request,
    principal: Principal = Depends(get_dev_principal),          # resolved FIRST: unauthenticated callers
    runtime: AgentRuntime | None = Depends(get_agent_runtime),  # never learn agent configuration
) -> ChatResponse:
    """Chat with the support agent.

    Agent off (AGENT_PROVIDER unset): fixed "not connected" reply, as before.
    Agent on: bounded tool-calling loop; every tool call goes through the gateway
    with this request's trusted Principal. The message text is never logged.
    """
    correlation_id = request.state.correlation_id
    if runtime is not None:
        db_path = get_db_path()
        if not db_path.exists():
            raise RuntimeError("database not found")  # generic 500; path not disclosed
        with closing(connect(db_path)) as conn:
            result = runtime.run(conn, principal, correlation_id, body.message)
        emit(
            "chat.message", correlation_id, "success",
            actor_user_id=principal.user_id, tenant_id=principal.tenant_id,
            message_length=len(body.message), agent_connected=True,
        )
        return ChatResponse(
            correlation_id=correlation_id, reply=result.reply, agent_connected=True,
            acting_as=principal, actions=result.actions, termination=result.termination,
        )

    emit(
        "chat.message", correlation_id, "success",
        actor_user_id=principal.user_id, tenant_id=principal.tenant_id,
        message_length=len(body.message), agent_connected=False,
    )
    return ChatResponse(
        correlation_id=correlation_id,
        reply=AGENT_NOT_CONNECTED_REPLY,
        agent_connected=False,
        acting_as=principal,
    )


@router.get("/audit-demo", response_model=AuditDemoResponse)
def audit_demo() -> AuditDemoResponse:
    """Example audit events. Constant data; has no access to live audit logs.

    Unauthenticated, so it must only ever return fixed, non-sensitive demo events,
    never real audit records. Disabled (404) outside local development.
    """
    if os.environ.get("APP_ENV", "local") != "local":
        raise HTTPException(status_code=404, detail="Not Found")
    return AuditDemoResponse(
        notice="Synthetic example events for demonstration. Not live audit data.",
        events=list(DEMO_EVENTS),
    )


def create_app() -> FastAPI:
    app = FastAPI(
        title="Insurance Support Agent — Security Lab",
        description="Educational lab. Synthetic data only. Not for production use.",
        version="0.3.0",
    )
    app.middleware("http")(correlation_middleware)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.include_router(router)
    return app


configure_logging(os.environ.get("LOG_LEVEL", "INFO"))
app = create_app()

"""FastAPI entry point.

Routes:
    GET  /health      liveness, no data
    POST /chat        identity-dependent; agent runtime NOT connected (fixed reply)
    GET  /audit-demo  fixed synthetic audit events (never the live log)

There is no LLM, tool gateway or customer CRUD. See docs/limitations.md.
"""

import os

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.audit import DEMO_EVENTS, emit
from app.errors import ErrorResponse, http_exception_handler, validation_exception_handler
from app.identity import Principal
from app.identity.http_dev import get_dev_principal
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
    responses={401: {"model": ErrorResponse}, 422: {"model": ErrorResponse}},
)
def chat(
    body: ChatRequest,
    request: Request,
    principal: Principal = Depends(get_dev_principal),
) -> ChatResponse:
    """Accept a chat message. The agent is not connected, so the reply is fixed.

    The message text is not interpreted, echoed or logged - only its length is audited.
    """
    correlation_id = request.state.correlation_id
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
    """Example audit events. Constant data; has no access to live audit logs."""
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

"""Correlation IDs, per-request audit events, catch-all error handling, logging setup."""

import logging
import time
import uuid

from fastapi import Request
from starlette.responses import Response

from app.audit import Outcome, emit
from app.errors import error_response

CORRELATION_HEADER = "X-Correlation-ID"
MAX_LOGGED_PATH = 200

app_logger = logging.getLogger("app")


def configure_logging(level: str = "INFO") -> None:
    """Plain one-line-per-record output. Audit records are already JSON.

    Nothing in this application logs request bodies, headers or query strings.
    """
    logging.basicConfig(level=level.upper(), format="%(message)s")


def _outcome(status_code: int) -> Outcome:
    if status_code < 400:
        return "success"
    if status_code in (401, 403):
        return "denied"
    if status_code < 500:
        return "rejected"
    return "error"


async def correlation_middleware(request: Request, call_next) -> Response:
    # Always server-generated. A client-supplied X-Correlation-ID is ignored, so
    # clients cannot forge or collide IDs in the audit trail.
    correlation_id = str(uuid.uuid4())
    request.state.correlation_id = correlation_id
    started = time.perf_counter()

    try:
        response = await call_next(request)
    except Exception as exc:  # last line of defence: never leak a traceback
        app_logger.error(
            "unhandled_exception type=%s correlation_id=%s", type(exc).__name__, correlation_id
        )
        app_logger.debug("traceback for %s", correlation_id, exc_info=True)
        response = error_response(500, "An internal error occurred.", correlation_id)

    response.headers[CORRELATION_HEADER] = correlation_id

    principal = getattr(request.state, "principal", None)
    emit(
        "http.request",
        correlation_id,
        _outcome(response.status_code),
        actor_user_id=principal.user_id if principal else None,
        tenant_id=principal.tenant_id if principal else None,
        method=request.method,
        path=request.url.path[:MAX_LOGGED_PATH],
        status_code=response.status_code,
        duration_ms=round((time.perf_counter() - started) * 1000, 1),
    )
    return response

"""Consistent HTTP error responses.

Every error has the same shape and carries the correlation ID, so a user can
quote it and an operator can find the matching audit events. Bodies never contain
stack traces, exception messages, or the submitted input values.
"""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException as StarletteHTTPException

_CODES = {
    400: "bad_request",
    401: "unauthenticated",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    422: "validation_error",
    500: "internal_error",
}


class FieldError(BaseModel):
    model_config = ConfigDict(extra="forbid")
    loc: list[str | int]
    type: str


class ErrorBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    code: str
    message: str
    correlation_id: str
    fields: list[FieldError] | None = None


class ErrorResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    error: ErrorBody


def error_response(
    status_code: int,
    message: str,
    correlation_id: str,
    fields: list[FieldError] | None = None,
) -> JSONResponse:
    body = ErrorResponse(
        error=ErrorBody(
            code=_CODES.get(status_code, "http_error"),
            message=message,
            correlation_id=correlation_id,
            fields=fields,
        )
    )
    return JSONResponse(status_code=status_code, content=body.model_dump(exclude_none=True))


def _correlation_id(request: Request) -> str:
    return getattr(request.state, "correlation_id", "unknown")


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    message = exc.detail if isinstance(exc.detail, str) else "Request failed."
    return error_response(exc.status_code, message, _correlation_id(request))


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    # Only the field location and error type are returned. FastAPI's default would
    # also echo the submitted input, which may contain sensitive text.
    fields = [
        FieldError(loc=[str(p) if not isinstance(p, int) else p for p in err.get("loc", ())],
                   type=err.get("type", "invalid"))
        for err in exc.errors()
    ]
    return error_response(422, "Request validation failed.", _correlation_id(request), fields)

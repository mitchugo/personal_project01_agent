"""HTTP identity boundary for the LOCAL DEVELOPMENT identity fixture.

NOT AUTHENTICATION. The ``X-Dev-User-Id`` header lets a local developer choose
which synthetic fixture user to act as. It is a *selector*, not a credential:
anyone who can reach the server can send any value. It must never be enabled in a
deployed environment (threat T-11).

Trust rules:
* Fails closed: unless IDENTITY_MODE=local-fixture AND APP_ENV=local, every
  identity-dependent request gets 401, and the database is not touched.
* The client supplies only a user_id. tenant_id and role come from the database.
  Headers such as X-Tenant-Id / X-Role, and anything in the chat text, are never read.
* All denials return the same generic 401, so clients cannot probe which user IDs
  exist. The specific reason is recorded in the audit log only.

A future production authentication dependency will replace this one and must
return the same ``Principal``.
"""

import os
from contextlib import closing
from pathlib import Path

from fastapi import Depends, HTTPException, Request

from app.audit import emit
from app.db import connect_readonly
from app.identity.dev_fixture import (
    DevIdentityDisabledError,
    UnknownDevUserError,
    require_dev_identity_enabled,
    resolve_dev_principal,
)
from app.identity.principal import Principal

DEV_USER_HEADER = "X-Dev-User-Id"
UNAUTHENTICATED_MESSAGE = "Not authenticated."


def get_db_path() -> Path:
    return Path(os.environ.get("DATABASE_PATH", "data/lab.db"))


def get_dev_principal(request: Request, db_path: Path = Depends(get_db_path)) -> Principal:
    correlation_id = request.state.correlation_id

    def deny(reason: str) -> HTTPException:
        emit("identity.resolve", correlation_id, "denied", reason=reason)
        return HTTPException(status_code=401, detail=UNAUTHENTICATED_MESSAGE)

    try:
        require_dev_identity_enabled()  # checked before any header or DB access
    except DevIdentityDisabledError:
        raise deny("identity_mode_disabled")

    user_id = request.headers.get(DEV_USER_HEADER, "").strip()
    if not user_id:
        raise deny("missing_dev_user")

    with closing(connect_readonly(db_path)) as conn:
        try:
            principal = resolve_dev_principal(conn, user_id)
        except UnknownDevUserError:
            raise deny("unknown_user")  # the submitted value is not logged

    request.state.principal = principal
    emit(
        "identity.resolve", correlation_id, "success",
        actor_user_id=principal.user_id, tenant_id=principal.tenant_id,
        identity_source=principal.identity_source,
    )
    return principal

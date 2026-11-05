"""LOCAL DEVELOPMENT IDENTITY FIXTURE - NOT AUTHENTICATION.

Lets a developer act as one of the synthetic fixture users. There is no password,
token or session: whoever can call this can be anyone. That is acceptable only
because the lab is local and the data is synthetic. It must never be exposed on a
network or described as production authentication (threat T-11).

Trust rules this module implements:
* The caller chooses only *which user* to act as (``user_id``).
* ``tenant_id`` and ``role`` are read from the users table, never accepted as input.
* It refuses to run unless IDENTITY_MODE=local-fixture is set explicitly and
  APP_ENV is local (fail closed).

Future production authentication will live in a separate module and return the
same ``Principal`` type. Nothing outside app/identity should import this module
except local tooling and tests.
"""

import os
import sqlite3

from app.identity.principal import Principal

DEV_IDENTITY_MODE = "local-fixture"


class DevIdentityDisabledError(RuntimeError):
    """The dev identity fixture was used outside an explicitly enabled local setup."""


class UnknownDevUserError(LookupError):
    """No fixture user exists with the given user_id."""


def _require_dev_identity_enabled() -> None:
    mode = os.environ.get("IDENTITY_MODE")
    app_env = os.environ.get("APP_ENV", "local")
    if mode != DEV_IDENTITY_MODE or app_env != "local":
        raise DevIdentityDisabledError(
            f"Dev identity fixture is disabled (IDENTITY_MODE={mode!r}, APP_ENV={app_env!r}). "
            f"It requires IDENTITY_MODE={DEV_IDENTITY_MODE!r} and APP_ENV='local'."
        )


def resolve_dev_principal(conn: sqlite3.Connection, user_id: str) -> Principal:
    """Return the trusted Principal for a fixture user.

    Deliberately takes no tenant_id or role parameter: those come from the database.
    """
    _require_dev_identity_enabled()
    row = conn.execute(
        "SELECT user_id, tenant_id, role FROM users WHERE user_id = ?", (user_id,)
    ).fetchone()
    if row is None:
        raise UnknownDevUserError(f"No fixture user with user_id={user_id!r}")
    return Principal(
        user_id=row["user_id"],
        tenant_id=row["tenant_id"],
        role=row["role"],
        identity_source=DEV_IDENTITY_MODE,
    )

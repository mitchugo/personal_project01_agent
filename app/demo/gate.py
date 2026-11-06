"""Fail-closed gate for the local demonstration API.

/demo routes exist only when ALL of these hold, checked on every request:
    DEMO_UI=local                  explicit opt-in (any other value or unset -> off)
    APP_ENV=local (or unset)       the lab's existing local-environment convention
    IDENTITY_MODE=local-fixture    the dev identity fixture is the only identity source

Otherwise every /demo route returns 404, so a misconfigured or deployed instance
does not even reveal that the routes exist. This is NOT authentication.
"""

import os
import re

from fastapi import HTTPException

LOCAL_ORIGIN = re.compile(r"^http://(localhost|127\.0\.0\.1):\d{2,5}$")


def demo_enabled() -> bool:
    return (
        os.environ.get("DEMO_UI") == "local"
        and os.environ.get("APP_ENV", "local") == "local"
        and os.environ.get("IDENTITY_MODE") == "local-fixture"
    )


def require_demo() -> None:
    """FastAPI dependency, applied router-wide and resolved before identity."""
    if not demo_enabled():
        raise HTTPException(status_code=404, detail="Not Found")


def allowed_cors_origin() -> str | None:
    """The single browser origin allowed cross-origin access, or None (CORS off).

    Only when the demo is enabled AND DEMO_UI_ORIGIN is an explicit loopback HTTP
    origin. The recommended setup uses the Vite dev proxy (same origin), so CORS
    stays off entirely.
    """
    origin = os.environ.get("DEMO_UI_ORIGIN", "").strip()
    if demo_enabled() and LOCAL_ORIGIN.fullmatch(origin):
        return origin
    return None

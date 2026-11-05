"""Identity package.

Only the ``Principal`` contract is exported here. The local dev fixture lives in
``app.identity.dev_fixture`` and must be imported explicitly, so that using it is
always a visible, deliberate choice.
"""

from app.identity.principal import Principal

__all__ = ["Principal"]

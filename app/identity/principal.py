"""The trusted principal: who is making this request, as established by the server.

This is the *contract* between identity and the rest of the application. Any
identity mechanism - today the local dev fixture, later a real production
authentication integration - must produce a ``Principal``. Downstream code (the
future tool gateway, audit log) depends only on this type, never on how it was made.

A Principal must only ever be constructed by an identity mechanism on the server.
It must never be built from values supplied by the LLM or a chat message.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models import ID_PATTERN, Role

# Records which mechanism produced the principal, so logs and evidence can never
# confuse a dev fixture with real authentication. Production mechanisms will add
# their own value here when they exist.
IdentitySource = Literal["local-fixture"]


class Principal(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: str = Field(pattern=ID_PATTERN)
    tenant_id: str = Field(pattern=ID_PATTERN)
    role: Role
    identity_source: IdentitySource

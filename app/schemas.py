"""HTTP request and response models.

Request models are strict: unknown fields are rejected (so a client cannot send
``tenant_id`` or ``role``), and types are not coerced (``123`` is not a string).
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agent.runtime import ActionRecord, Termination
from app.audit import AuditEvent
from app.identity import Principal

MAX_MESSAGE_LENGTH = 4000


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, str_strip_whitespace=True)

    message: str = Field(min_length=1, max_length=MAX_MESSAGE_LENGTH)


class ChatResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    correlation_id: str
    reply: str
    agent_connected: bool
    # Server-derived identity, shown so the caller can see who the server thinks
    # they are. identity_source makes clear this is a dev fixture, not real auth.
    acting_as: Principal
    # Present only when the agent runtime is connected. Built from what the BACKEND
    # did with each model-proposed tool call - never from the model's own claims.
    actions: list[ActionRecord] | None = None
    termination: Termination | None = None


class AuditDemoResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    synthetic: Literal[True] = True
    notice: str
    events: list[AuditEvent]

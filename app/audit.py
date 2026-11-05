"""Structured audit events.

Each event is one JSON line on the ``audit`` logger with: event type, correlation
ID, UTC timestamp, outcome, optional actor/tenant, and non-sensitive metadata.

Data minimisation is enforced, not just documented: metadata keys must be on an
allow-list and values must be scalars. Message text, prompts, customer records,
headers and tool arguments therefore cannot be logged through this module - adding
such a key raises a validation error at the call site.
"""

import logging
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

audit_logger = logging.getLogger("audit")
audit_logger.setLevel(logging.INFO)

EventType = Literal["http.request", "identity.resolve", "chat.message", "tool.invoke"]
# success: allowed and completed | denied: identity/authorisation refused
# rejected: invalid client input | error: server-side failure
Outcome = Literal["success", "denied", "rejected", "error"]

ALLOWED_METADATA_KEYS = frozenset(
    {
        "method",           # HTTP method
        "path",             # URL path only, never the query string
        "status_code",
        "duration_ms",
        "reason",           # server-defined reason code, e.g. "unknown_user"
        "identity_source",  # e.g. "local-fixture"
        "message_length",   # length of chat text - never the text itself
        "agent_connected",
        "tool",             # registered tool name, or "unknown"
        "decision",         # "allow" | "deny"
        "resource_id",      # validated record ID (pseudonymous), never record contents
        "fields",           # comma-separated field NAMES, never values
    }
)

MetadataValue = str | int | float | bool


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_type: EventType
    correlation_id: str
    timestamp: datetime
    outcome: Outcome
    actor_user_id: str | None = None
    tenant_id: str | None = None
    metadata: dict[str, MetadataValue] = Field(default_factory=dict)

    @field_validator("metadata")
    @classmethod
    def _only_allow_listed_keys(cls, value: dict) -> dict:
        unknown = set(value) - ALLOWED_METADATA_KEYS
        if unknown:
            raise ValueError(f"audit metadata keys not allow-listed: {sorted(unknown)}")
        return value


def emit(
    event_type: EventType,
    correlation_id: str,
    outcome: Outcome,
    *,
    actor_user_id: str | None = None,
    tenant_id: str | None = None,
    **metadata: MetadataValue,
) -> AuditEvent:
    """Build, validate and log one audit event. Returns it for convenience."""
    event = AuditEvent(
        event_type=event_type,
        correlation_id=correlation_id,
        timestamp=datetime.now(timezone.utc),
        outcome=outcome,
        actor_user_id=actor_user_id,
        tenant_id=tenant_id,
        metadata=metadata,
    )
    audit_logger.info(event.model_dump_json())
    return event


# --- Static demo events for GET /audit-demo ---------------------------------
# Hand-written, synthetic, and constant. The /audit-demo route returns these and
# has no code path to the live audit log.

_DEMO_TIME = datetime(2026, 1, 1, 9, 0, 0, tzinfo=timezone.utc)

DEMO_EVENTS: tuple[AuditEvent, ...] = (
    AuditEvent(
        event_type="identity.resolve", correlation_id="00000000-0000-4000-8000-000000000001",
        timestamp=_DEMO_TIME, outcome="success", actor_user_id="ns-agent-01", tenant_id="northstar",
        metadata={"identity_source": "local-fixture"},
    ),
    AuditEvent(
        event_type="chat.message", correlation_id="00000000-0000-4000-8000-000000000001",
        timestamp=_DEMO_TIME, outcome="success", actor_user_id="ns-agent-01", tenant_id="northstar",
        metadata={"message_length": 42, "agent_connected": False},
    ),
    AuditEvent(
        event_type="identity.resolve", correlation_id="00000000-0000-4000-8000-000000000002",
        timestamp=_DEMO_TIME, outcome="denied", metadata={"reason": "unknown_user"},
    ),
    AuditEvent(
        event_type="http.request", correlation_id="00000000-0000-4000-8000-000000000002",
        timestamp=_DEMO_TIME, outcome="denied",
        metadata={"method": "POST", "path": "/chat", "status_code": 401, "duration_ms": 3.2},
    ),
)

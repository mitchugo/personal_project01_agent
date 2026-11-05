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

EventType = Literal[
    "http.request", "identity.resolve", "chat.message", "tool.invoke",
    "refund.approval", "refund.execution",
    "agent.model_call", "agent.tool_proposal", "agent.run",
]
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
        "result_count",     # number of search results - never the query or the text
        "body_length",      # length of a draft body - never the body
        "amount_pence",     # synthetic refund amount (financial accountability, not personal data)
        "currency",
        "from_status",      # refund state transition
        "to_status",
        # Session 6: agent runtime. Model text, prompts and tool arguments are never logged.
        "model",            # model that SERVED the call (from the API response)
        "configured_model", # model the application was configured to use
        "refusal_category", # API stop_details category when the model declined
        "latency_ms",
        "input_tokens",
        "output_tokens",
        "cost_usd",         # approximate, from list prices
        "stop_reason",
        "iteration",        # 1-based model-call number within the request
        "proposed_tool",    # registered tool name, or "unregistered" (raw name never logged)
        "tool_status",      # backend outcome: ok | denied | not_found | invalid | conflict | skipped
        "termination",
        "model_calls",
        "tool_calls",
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

"""In-memory, sanitised copy of recent audit events for the Security Inspector.

A logging handler on the ``audit`` logger copies each event into a bounded ring
buffer, keeping ONLY allowlisted fields. It never reads log files, never stores
messages, prompts, tool arguments or record contents (none of which are in audit
events to begin with), and it is not /audit-demo (static samples).

The buffer lives only in process memory and is installed only when the demo is
enabled at app start. Served per tenant by /demo/inspector.
"""

import json
import logging
import threading
from collections import deque

TOP_LEVEL_FIELDS = ("event_type", "correlation_id", "timestamp", "outcome", "actor_user_id", "tenant_id")

# Safe subset of audit metadata. Everything else is dropped, even if allowlisted for the log.
METADATA_FIELDS = frozenset({
    "tool", "proposed_tool", "decision", "reason", "tool_status", "termination",
    "model", "configured_model", "stop_reason", "refusal_category", "iteration",
    "model_calls", "tool_calls", "input_tokens", "output_tokens", "cost_usd", "latency_ms",
    "method", "path", "status_code", "duration_ms",
    "from_status", "to_status", "amount_pence", "currency", "resource_id",
    "result_count", "agent_connected", "identity_source",
})

MAX_EVENTS = 500


def sanitise(event: dict) -> dict | None:
    if not isinstance(event, dict) or not isinstance(event.get("event_type"), str):
        return None
    clean = {k: event.get(k) for k in TOP_LEVEL_FIELDS}
    metadata = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    clean["metadata"] = {
        k: v for k, v in metadata.items()
        if k in METADATA_FIELDS and isinstance(v, (str, int, float, bool))
    }
    return clean


class InspectorBuffer(logging.Handler):
    def __init__(self, maxlen: int = MAX_EVENTS):
        super().__init__(level=logging.INFO)
        self._events: deque[dict] = deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            event = sanitise(json.loads(record.getMessage()))
        except (ValueError, TypeError):
            return
        if event is not None:
            with self._lock:
                self._events.append(event)

    def events_for_tenant(self, tenant_id: str) -> list[dict]:
        with self._lock:
            return [dict(e) for e in self._events if e.get("tenant_id") == tenant_id]

    def clear(self) -> None:
        with self._lock:
            self._events.clear()


BUFFER = InspectorBuffer()


def install() -> None:
    audit_logger = logging.getLogger("audit")
    if BUFFER not in audit_logger.handlers:
        audit_logger.addHandler(BUFFER)

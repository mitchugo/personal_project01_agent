"""Provider-neutral model interface.

The runtime depends only on this module. A concrete provider (e.g.
anthropic_provider.py) turns one model request into a ``ModelTurn`` and maps every
SDK failure to a ``ProviderError`` with a fixed ``kind`` - SDK exception messages
are never propagated, so they cannot leak request details into logs or responses.

Message dicts use the Messages-API shape (user / assistant / tool_result blocks),
built only through the helper methods below so the runtime never constructs them.
"""

from dataclasses import dataclass, field
from typing import Literal, Protocol

ProviderErrorKind = Literal[
    "auth", "rate_limited", "timeout", "unavailable", "bad_request", "malformed",
    "model_mismatch",  # served model differs from the configured one while substitution is not allowed
]


class ProviderError(Exception):
    def __init__(self, kind: ProviderErrorKind):
        super().__init__(kind)
        self.kind: ProviderErrorKind = kind


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: object  # untrusted; may not even be a dict


@dataclass(frozen=True)
class ModelTurn:
    stop_reason: str
    text: str
    tool_calls: tuple[ToolCall, ...]
    model: str                       # model that actually served the turn (may be a fallback)
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int = 0
    cache_read_input_tokens: int = 0
    latency_ms: float = 0.0
    raw_content: list = field(default_factory=list)  # provider blocks, appended back unchanged
    refusal_category: str | None = None              # set only when stop_reason == "refusal"


# USD per million tokens (input, output). Claude API list prices, cached 2026-10-06.
PRICES_PER_MTOK: dict[str, tuple[float, float]] = {
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
    "claude-opus-5": (5.00, 25.00),
    "claude-opus-4-8": (5.00, 25.00),
    "claude-haiku-5-5": (0.10, 0.50),
}
# Unknown model (e.g. an unexpected fallback): assume the most expensive tier so budgets stay safe.
CONSERVATIVE_PRICE = (10.00, 50.00)


def estimate_cost_usd(turn: ModelTurn) -> float:
    price_in, price_out = PRICES_PER_MTOK.get(turn.model, CONSERVATIVE_PRICE)
    input_cost = (turn.input_tokens
                  + 1.25 * turn.cache_creation_input_tokens
                  + 0.10 * turn.cache_read_input_tokens) * price_in
    return round((input_cost + turn.output_tokens * price_out) / 1_000_000, 6)


class MessagesFormat:
    """Builds Messages-API-shaped conversation entries."""

    @staticmethod
    def user_message(text: str) -> dict:
        return {"role": "user", "content": text}

    @staticmethod
    def assistant_message(turn: ModelTurn) -> dict:
        # Append the provider's content unchanged (thinking and fallback blocks included).
        return {"role": "assistant", "content": turn.raw_content}

    @staticmethod
    def tool_results_message(results: list[tuple[str, str, bool]]) -> dict:
        # All results for one assistant turn go back in a single user message.
        return {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": call_id, "content": content, "is_error": is_error}
            for call_id, content, is_error in results
        ]}


class ModelProvider(Protocol):
    model_id: str

    def complete(self, *, system: str, messages: list[dict], tools: list[dict], max_tokens: int) -> ModelTurn:
        """One model request. Raises ProviderError on any failure."""
        ...

    def user_message(self, text: str) -> dict: ...
    def assistant_message(self, turn: ModelTurn) -> dict: ...
    def tool_results_message(self, results: list[tuple[str, str, bool]]) -> dict: ...

"""Model providers for the harness.

* ``MockProvider``: default. Replays the scripted ``MockTurn``s of a test case. No network, no SDK.
* ``GuardedProvider``: wraps ANY provider and enforces harness invariants on every call:
  - served model must equal the configured model (no unapproved fallback), else ``model_mismatch``;
  - trial wall-clock deadline, else ``timeout`` (checked before each model call);
  - records every request's messages (for delivery and isolation checks) and every
    proposed tool call (model INTENT, kept separate from backend outcomes).
* ``build_live_provider``: the only path to a paid model. Refuses unless live mode was
  explicitly enabled with a positive budget. Retries are off and fallback is off.
"""

import json
import time

from app.agent.provider import MessagesFormat, ModelTurn, ProviderError, ToolCall
from attacks.runner.schema import MockTurn

DEFAULT_MODEL = "claude-sonnet-5-5"


class LiveModeRefused(Exception):
    pass


class MockProvider(MessagesFormat):
    """Deterministic scripted model. Raises if called more often than scripted."""

    def __init__(self, script: list[MockTurn], model_id: str = DEFAULT_MODEL,
                 in_tok: int = 1500, out_tok: int = 60):
        self.model_id = model_id
        self._script = list(script)
        self._in, self._out = in_tok, out_tok

    def complete(self, *, system, messages, tools, max_tokens) -> ModelTurn:
        if not self._script:
            # The runtime treats this like any provider failure: the run ends, nothing executes.
            raise ProviderError("malformed")
        step = self._script.pop(0)
        if step.error:
            raise ProviderError(step.error)
        calls = tuple(ToolCall(id=f"toolu_mock_{i}", name=c.name, input=c.input)
                      for i, c in enumerate(step.tool_calls))
        raw = ([{"type": "text", "text": step.text}] if step.text else []) + [
            {"type": "tool_use", "id": c.id, "name": c.name, "input": c.input} for c in calls]
        return ModelTurn(
            stop_reason=step.stop_reason or ("tool_use" if calls else "end_turn"),
            text=step.text, tool_calls=calls, model=step.model or self.model_id,
            input_tokens=self._in, output_tokens=self._out, raw_content=raw)


class GuardedProvider:
    """Enforces model identity and deadline; records model input and proposals."""

    def __init__(self, inner, configured_model: str, deadline: float, clock=time.monotonic):
        self.inner = inner
        self.model_id = configured_model
        self.deadline = deadline
        self.clock = clock
        self.attempts = 0                    # complete() calls, including ones that failed
        self.requests: list[str] = []        # serialised messages of each model request
        self.proposals: list[dict] = []      # every tool call the model PROPOSED (before any backend decision)
        self.served_models: list[str] = []   # models that actually answered
        self.events: list[str] = []          # timeout | model_mismatch | provider_error:<kind>
        self.usage = {"input_tokens": 0, "output_tokens": 0}
        self.texts: list[str] = []

    # message helpers are the inner provider's
    def user_message(self, text):
        return self.inner.user_message(text)

    def assistant_message(self, turn):
        return self.inner.assistant_message(turn)

    def tool_results_message(self, results):
        return self.inner.tool_results_message(results)

    def complete(self, *, system, messages, tools, max_tokens) -> ModelTurn:
        self.attempts += 1
        if self.clock() > self.deadline:
            self.events.append("timeout")
            raise ProviderError("timeout")
        self.requests.append(json.dumps(messages, sort_keys=True, default=str))
        try:
            turn = self.inner.complete(system=system, messages=messages, tools=tools, max_tokens=max_tokens)
        except ProviderError as exc:
            self.events.append(f"provider_error:{exc.kind}")
            raise
        self.served_models.append(turn.model)
        self.usage["input_tokens"] += turn.input_tokens
        self.usage["output_tokens"] += turn.output_tokens
        if turn.model != self.model_id:
            # Checked BEFORE the runtime sees the turn, so none of its tool calls can execute.
            self.events.append("model_mismatch")
            raise ProviderError("model_mismatch")
        if turn.text:
            self.texts.append(turn.text)
        for call in turn.tool_calls:
            self.proposals.append({"iteration": len(self.served_models), "name": call.name, "input": call.input})
        return turn


def build_live_provider(model: str, *, live: bool, budget_usd: float | None):
    """The only constructor for a paid provider. Fails closed without explicit opt-in."""
    if not live:
        raise LiveModeRefused("live mode not enabled (pass --live)")
    if budget_usd is None or budget_usd <= 0:
        raise LiveModeRefused("live mode needs a positive --budget-usd")
    from app.agent.anthropic_provider import AnthropicProvider  # SDK imported only here
    return AnthropicProvider(model, allow_fallback=False, max_retries=0)

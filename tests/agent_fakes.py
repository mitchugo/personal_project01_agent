"""Deterministic scripted model provider for agent tests. No network, no SDK."""

from app.agent.provider import MessagesFormat, ModelTurn, ProviderError, ToolCall


def tool_turn(*calls: tuple[str, object], text: str = "", in_tok: int = 1000, out_tok: int = 50,
              model: str = "claude-sonnet-5-5", stop_reason: str = "tool_use") -> ModelTurn:
    tool_calls = tuple(ToolCall(id=f"toolu_{i}", name=name, input=args) for i, (name, args) in enumerate(calls))
    raw = ([{"type": "text", "text": text}] if text else []) + [
        {"type": "tool_use", "id": c.id, "name": c.name, "input": c.input} for c in tool_calls]
    return ModelTurn(stop_reason=stop_reason, text=text, tool_calls=tool_calls, model=model,
                     input_tokens=in_tok, output_tokens=out_tok, raw_content=raw)


def text_turn(text: str, in_tok: int = 1500, out_tok: int = 60, model: str = "claude-sonnet-5-5",
              stop_reason: str = "end_turn") -> ModelTurn:
    return ModelTurn(stop_reason=stop_reason, text=text, tool_calls=(), model=model,
                     input_tokens=in_tok, output_tokens=out_tok, raw_content=[{"type": "text", "text": text}])


class ScriptedProvider(MessagesFormat):
    """Returns the scripted turns in order; an exception in the script is raised instead."""

    model_id = "claude-sonnet-5-5"

    def __init__(self, *script):
        self.script = list(script)
        self.requests: list[dict] = []

    def complete(self, *, system, messages, tools, max_tokens):
        self.requests.append({"system": system, "messages": [dict(m) for m in messages],
                              "tools": tools, "max_tokens": max_tokens})
        if not self.script:
            raise AssertionError("provider called more times than scripted")
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def tool_results_sent(self, request_index: int) -> list[dict]:
        """tool_result blocks contained in the last message of a given request."""
        last = self.requests[request_index]["messages"][-1]
        return [b for b in last["content"] if isinstance(b, dict) and b.get("type") == "tool_result"]


class LoopingProvider(MessagesFormat):
    """Always proposes the same tool call - for budget tests."""

    model_id = "claude-sonnet-5-5"

    def __init__(self, turn: ModelTurn):
        self.turn = turn
        self.calls = 0

    def complete(self, *, system, messages, tools, max_tokens):
        self.calls += 1
        return self.turn


def provider_error(kind: str) -> ProviderError:
    return ProviderError(kind)

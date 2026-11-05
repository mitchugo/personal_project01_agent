"""Anthropic Claude provider. The ONLY module that imports the ``anthropic`` SDK.

Credentials: the SDK reads ANTHROPIC_API_KEY from the environment itself. This
module never reads, stores, logs or returns the key.

Request shape (per the official SDK docs, anthropic==2.5.0):
    client.beta.messages.create(model, max_tokens, system, messages, tools,
        tool_choice={"type": "auto"}, output_config={"effort": ...})
    + only when allow_fallback=True: betas=["server-side-fallback-2026-07-01"], fallbacks="default"

* Thinking is left at the model default (adaptive). Thinking blocks are passed back
  unchanged via ``raw_content``.
* Model substitution is OFF by default (Session 6 review). A live run showed that
  server-side refusal fallback silently served a request with claude-sonnet-5 instead of
  the configured claude-sonnet-5-5. Now:
    - no ``fallbacks`` parameter is sent unless explicitly enabled;
    - a refusal is returned as ``stop_reason == "refusal"`` with its category recorded;
    - if the served model differs from the configured one while substitution is not
      allowed, the turn is rejected as ``model_mismatch`` and its tool calls never run.
  ``ModelTurn.model`` always records the model that actually served the turn.
* Retries: the SDK retries 408/409/429/5xx and connection errors ``max_retries``
  times. That is safe here: a model call has no backend side effects. Tool
  executions happen in the runtime and are never retried.
"""

import time

import anthropic

from app.agent.provider import MessagesFormat, ModelTurn, ProviderError, ToolCall

FALLBACK_BETA = "server-side-fallback-2026-07-01"
DEFAULT_MODEL = "claude-sonnet-5-5"


class AnthropicProvider(MessagesFormat):
    def __init__(self, model_id: str = DEFAULT_MODEL, *, effort: str = "medium",
                 timeout: float = 30.0, max_retries: int = 1, http_client=None,
                 allow_fallback: bool = False):
        self.model_id = model_id
        self.effort = effort
        self.allow_fallback = allow_fallback
        kwargs = {"timeout": timeout, "max_retries": max_retries}
        if http_client is not None:  # tests inject an offline transport
            kwargs["http_client"] = http_client
        try:
            self._client = anthropic.Anthropic(**kwargs)
        except anthropic.AnthropicError:
            raise ProviderError("auth") from None  # e.g. no credentials configured

    def complete(self, *, system: str, messages: list[dict], tools: list[dict], max_tokens: int) -> ModelTurn:
        started = time.perf_counter()
        fallback_params = {"betas": [FALLBACK_BETA], "fallbacks": "default"} if self.allow_fallback else {}
        try:
            response = self._client.beta.messages.create(
                model=self.model_id,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                tools=tools,
                tool_choice={"type": "auto"},
                output_config={"effort": self.effort},
                **fallback_params,
            )
        # Most specific first. `from None` drops SDK messages and request details.
        except (anthropic.AuthenticationError, anthropic.PermissionDeniedError):
            raise ProviderError("auth") from None
        except anthropic.RateLimitError:
            raise ProviderError("rate_limited") from None
        except anthropic.BadRequestError:
            raise ProviderError("bad_request") from None
        except anthropic.APIStatusError:
            raise ProviderError("unavailable") from None
        except anthropic.APITimeoutError:
            raise ProviderError("timeout") from None
        except anthropic.APIConnectionError:
            raise ProviderError("unavailable") from None
        except anthropic.AnthropicError:
            raise ProviderError("malformed") from None
        latency_ms = round((time.perf_counter() - started) * 1000, 1)

        if response.model != self.model_id and not self.allow_fallback:
            # Never act on output from a model nobody configured or approved.
            raise ProviderError("model_mismatch")

        stop_details = getattr(response, "stop_details", None)
        refusal_category = getattr(stop_details, "category", None) if response.stop_reason == "refusal" else None

        text_parts: list[str] = []
        calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                calls.append(ToolCall(id=block.id, name=block.name, input=block.input))
            # thinking / fallback / other blocks: kept only in raw_content

        usage = response.usage
        return ModelTurn(
            stop_reason=response.stop_reason or "unknown",
            text="".join(text_parts),
            tool_calls=tuple(calls),
            model=response.model,
            input_tokens=usage.input_tokens or 0,
            output_tokens=usage.output_tokens or 0,
            cache_creation_input_tokens=usage.cache_creation_input_tokens or 0,
            cache_read_input_tokens=usage.cache_read_input_tokens or 0,
            latency_ms=latency_ms,
            raw_content=list(response.content),
            refusal_category=str(refusal_category) if refusal_category else None,
        )

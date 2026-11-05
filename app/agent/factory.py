"""Builds the agent runtime from environment configuration.

AGENT_PROVIDER   unset/"none" -> agent off (/chat keeps its fixed "not connected" reply)
                 "anthropic"  -> Claude via the official SDK
AGENT_MODEL      model ID (default claude-sonnet-5-5)
AGENT_MODEL_FALLBACK  unset/"off" (default) -> no model substitution; a different served model
                 is rejected. "default" -> explicitly approved server-side refusal fallback.
                 Any other value -> 503 (fail closed).
ANTHROPIC_API_KEY  read by the SDK itself; never by this code

Any other AGENT_PROVIDER value, or a provider that cannot be constructed (e.g. no
credentials), fails closed with 503 for /chat. It never falls back to a different
provider or to running tools without a model.
"""

import os
from functools import lru_cache

from fastapi import HTTPException

from app.agent.provider import ProviderError
from app.agent.runtime import AgentRuntime

AGENT_UNAVAILABLE = "Agent runtime unavailable."


@lru_cache(maxsize=4)
def _build(provider_name: str, model_id: str, fallback_mode: str) -> AgentRuntime:
    if fallback_mode not in ("off", "default"):
        raise ProviderError("bad_request")
    if provider_name == "anthropic":
        from app.agent.anthropic_provider import AnthropicProvider  # SDK imported only when enabled
        return AgentRuntime(AnthropicProvider(model_id, allow_fallback=fallback_mode == "default"))
    raise ProviderError("bad_request")


def get_agent_runtime() -> AgentRuntime | None:
    """FastAPI dependency. Tests override it with a runtime around a scripted provider."""
    provider_name = os.environ.get("AGENT_PROVIDER", "").strip().lower()
    if provider_name in ("", "none"):
        return None
    model_id = os.environ.get("AGENT_MODEL", "claude-sonnet-5-5").strip()
    fallback_mode = os.environ.get("AGENT_MODEL_FALLBACK", "off").strip().lower() or "off"
    try:
        return _build(provider_name, model_id, fallback_mode)
    except ProviderError:
        raise HTTPException(status_code=503, detail=AGENT_UNAVAILABLE) from None

"""FastAPI entry point.

Session 1 exposes only a health check. There is deliberately no agent, no tool
endpoint, no identity handling and no model provider wired in yet.
"""

from fastapi import FastAPI

app = FastAPI(
    title="Insurance Support Agent — Security Lab",
    description="Educational lab. Synthetic data only. Not for production use.",
    version="0.1.0",
)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness check. Returns no tenant, user or configuration data."""
    return {"status": "ok"}

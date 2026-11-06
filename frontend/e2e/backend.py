"""Isolated backend for Playwright UI checks. Never makes model calls.

* Fresh seeded temporary SQLite DB (never data/lab.db).
* DEMO_UI=local, IDENTITY_MODE=local-fixture, APP_ENV=local.
* AGENT_PROVIDER and ANTHROPIC_API_KEY are REMOVED: /chat returns the fixed reply.
* One pending synthetic refund whose reason contains an XSS payload (render test).
"""

import os
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
os.chdir(REPO)

db_path = Path(tempfile.mkdtemp(prefix="lab-e2e-")) / "e2e.db"
os.environ.update(DATABASE_PATH=str(db_path), IDENTITY_MODE="local-fixture", DEMO_UI="local", APP_ENV="local")
for var in ("AGENT_PROVIDER", "AGENT_MODEL", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "DEMO_UI_ORIGIN"):
    os.environ.pop(var, None)

from contextlib import closing  # noqa: E402

from app.db import connect  # noqa: E402
from app.gateway import execute_tool  # noqa: E402
from app.identity import Principal  # noqa: E402
from app.seed import seed  # noqa: E402

seed(db_path)
agent = Principal(user_id="ns-agent-01", tenant_id="northstar", role="support_agent", identity_source="local-fixture")
with closing(connect(db_path)) as conn:
    execute_tool(conn, agent, "e2e-setup", "request_refund", {
        "customer_id": "ns-cust-003", "amount_pence": 4250, "currency": "GBP",
        "reason": 'Cooling-off <img src=x onerror="window.__pwned=1"> <script>window.__pwned=1</script>',
    })

import uvicorn  # noqa: E402

uvicorn.run("app.main:app", host="127.0.0.1", port=int(os.environ.get("E2E_BACKEND_PORT", "8010")),
            log_level="warning")

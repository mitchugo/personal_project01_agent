"""Email draft storage. Drafts only: the schema has no 'sent' state and nothing sends email."""

import sqlite3
import uuid
from datetime import datetime, timezone

from app.identity import Principal


def insert_draft(conn: sqlite3.Connection, principal: Principal, customer_id: str,
                 recipient: str, subject: str, body: str) -> str:
    draft_id = f"draft-{uuid.uuid4().hex}"
    with conn:  # single-statement transaction; composite FK re-checks customer is in this tenant
        conn.execute(
            "INSERT INTO email_drafts (draft_id, tenant_id, customer_id, created_by, recipient, "
            "subject, body, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'draft', ?)",
            (draft_id, principal.tenant_id, customer_id, principal.user_id, recipient,
             subject, body, datetime.now(timezone.utc).isoformat()),
        )
    return draft_id

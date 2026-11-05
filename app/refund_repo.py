"""Tenant-scoped refund persistence. Simulation only: no money moves anywhere.

Every statement filters by the acting principal's tenant. State changes are
compare-and-set updates (``... AND status = <expected>``), so a stale or replayed
transition matches zero rows instead of applying twice.

Functions marked "inside write_transaction" must be called within
``app.db.write_transaction`` and do not commit themselves.
"""

import sqlite3
import uuid
from datetime import datetime, timezone

from app.identity import Principal


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_pending(conn: sqlite3.Connection, requester: Principal, customer_id: str,
                   amount_pence: int, currency: str, reason: str) -> str:
    """Insert a pending request. Raises sqlite3.IntegrityError if one is already pending for the customer."""
    refund_id = f"refund-{uuid.uuid4().hex}"
    with conn:
        conn.execute(
            "INSERT INTO refund_requests (refund_id, tenant_id, customer_id, requested_by, amount_pence, "
            "currency, reason, status, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_approval', ?)",
            (refund_id, requester.tenant_id, customer_id, requester.user_id, amount_pence,
             currency, reason, _now()),
        )
    return refund_id


def pending_refund_for_customer(conn: sqlite3.Connection, principal: Principal, customer_id: str) -> str | None:
    row = conn.execute(
        "SELECT refund_id FROM refund_requests "
        "WHERE customer_id = ? AND tenant_id = ? AND status = 'pending_approval'",
        (customer_id, principal.tenant_id),
    ).fetchone()
    return row["refund_id"] if row else None


def get_refund(conn: sqlite3.Connection, principal: Principal, refund_id: str) -> dict | None:
    row = conn.execute(
        "SELECT refund_id, customer_id, requested_by, amount_pence, currency, status, approved_by "
        "FROM refund_requests WHERE refund_id = ? AND tenant_id = ?",
        (refund_id, principal.tenant_id),
    ).fetchone()
    return dict(row) if row else None


def mark_approved(conn: sqlite3.Connection, approver: Principal, refund_id: str,
                  customer_id: str, amount_pence: int, currency: str) -> bool:
    """Inside write_transaction. CAS pending -> approved, bound to exact customer/amount/currency."""
    cursor = conn.execute(
        "UPDATE refund_requests SET status = 'approved', approved_by = ?, approved_at = ? "
        "WHERE refund_id = ? AND tenant_id = ? AND status = 'pending_approval' "
        "AND customer_id = ? AND amount_pence = ? AND currency = ? AND requested_by <> ?",
        (approver.user_id, _now(), refund_id, approver.tenant_id,
         customer_id, amount_pence, currency, approver.user_id),
    )
    return cursor.rowcount == 1


def mark_executed(conn: sqlite3.Connection, operator: Principal, refund_id: str) -> bool:
    """Inside write_transaction. CAS approved -> executed."""
    cursor = conn.execute(
        "UPDATE refund_requests SET status = 'executed', executed_at = ? "
        "WHERE refund_id = ? AND tenant_id = ? AND status = 'approved'",
        (_now(), refund_id, operator.tenant_id),
    )
    return cursor.rowcount == 1


def insert_ledger_entry(conn: sqlite3.Connection, operator: Principal, refund: dict) -> str:
    """Inside write_transaction. UNIQUE(refund_id) rejects a second entry for the same refund."""
    entry_id = f"ledger-{uuid.uuid4().hex}"
    conn.execute(
        "INSERT INTO refund_ledger (entry_id, refund_id, tenant_id, amount_pence, currency, executed_by, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (entry_id, refund["refund_id"], operator.tenant_id, refund["amount_pence"], refund["currency"],
         operator.user_id, _now()),
    )
    return entry_id


def ledger_entry_for(conn: sqlite3.Connection, principal: Principal, refund_id: str) -> str | None:
    row = conn.execute(
        "SELECT entry_id FROM refund_ledger WHERE refund_id = ? AND tenant_id = ?",
        (refund_id, principal.tenant_id),
    ).fetchone()
    return row["entry_id"] if row else None

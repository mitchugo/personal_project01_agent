"""Tenant-scoped customer data access.

Every statement filters by BOTH ``customer_id`` and ``principal.tenant_id``. The
tenant is taken from the trusted Principal, never from a parameter a caller can
choose, so a record in another tenant is indistinguishable from a missing one.

All values are bound parameters. Column names come only from the constants below.
This module does not decide *whether* an action is allowed - that is app.authz.
"""

import sqlite3

from app.identity import Principal

VIEW_COLUMNS = (
    "customer_id", "full_name", "email", "phone", "address",
    "policy_number", "policy_type", "policy_note",
)  # tenant_id deliberately omitted: the caller already knows its own tenant
UPDATABLE_COLUMNS = frozenset({"email", "phone", "address"})


def get_customer(conn: sqlite3.Connection, principal: Principal, customer_id: str) -> dict | None:
    row = conn.execute(
        f"SELECT {', '.join(VIEW_COLUMNS)} FROM customers WHERE customer_id = ? AND tenant_id = ?",
        (customer_id, principal.tenant_id),
    ).fetchone()
    return dict(row) if row is not None else None


def update_customer_contact(
    conn: sqlite3.Connection, principal: Principal, customer_id: str, changes: dict[str, str]
) -> bool:
    """Apply ``changes`` in one statement. Returns False if no row matched in this tenant."""
    columns = sorted(changes)
    if not columns or not set(columns) <= UPDATABLE_COLUMNS:
        # Defence in depth: callers validate first, but never build SQL from unexpected names.
        raise ValueError("refusing to update non-allow-listed columns")
    assignments = ", ".join(f"{column} = ?" for column in columns)
    with conn:  # one transaction
        cursor = conn.execute(
            f"UPDATE customers SET {assignments} WHERE customer_id = ? AND tenant_id = ?",
            (*(changes[c] for c in columns), customer_id, principal.tenant_id),
        )
    return cursor.rowcount == 1

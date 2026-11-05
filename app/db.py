"""SQLite schema and connection helper.

Integrity rules enforced by the database itself:

* Every tenant-owned table has ``tenant_id NOT NULL`` referencing ``tenants``.
* Child rows reference parents by the pair ``(id, tenant_id)`` (composite foreign
  keys). A ticket therefore cannot point at a customer or user from another tenant,
  even by mistake.
* ``STRICT`` tables reject values of the wrong type; ``CHECK`` constraints restrict
  enum columns.

These rules protect data *integrity*. They do NOT stop application code from
*reading* another tenant's rows - that is the job of tenant-scoped queries and the
(future) tool gateway.
"""

import sqlite3
from contextlib import contextmanager
from pathlib import Path

TENANT_OWNED_TABLES = (
    "users", "customers", "tickets", "knowledge_documents",
    "email_drafts", "refund_requests", "refund_ledger",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS tenants (
    tenant_id   TEXT PRIMARY KEY,
    name        TEXT NOT NULL
) STRICT;

CREATE TABLE IF NOT EXISTS users (
    user_id       TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL REFERENCES tenants(tenant_id),
    display_name  TEXT NOT NULL,
    email         TEXT NOT NULL UNIQUE,
    role          TEXT NOT NULL CHECK (role IN ('support_agent', 'supervisor', 'tenant_admin')),
    UNIQUE (user_id, tenant_id)
) STRICT;

CREATE TABLE IF NOT EXISTS customers (
    customer_id    TEXT PRIMARY KEY,
    tenant_id      TEXT NOT NULL REFERENCES tenants(tenant_id),
    full_name      TEXT NOT NULL,
    email          TEXT NOT NULL,
    phone          TEXT NOT NULL,
    address        TEXT NOT NULL,
    policy_number  TEXT NOT NULL UNIQUE,
    policy_type    TEXT NOT NULL CHECK (policy_type IN ('motor', 'home', 'travel')),
    policy_note    TEXT NOT NULL DEFAULT '',
    UNIQUE (customer_id, tenant_id)
) STRICT;

CREATE TABLE IF NOT EXISTS tickets (
    ticket_id    TEXT PRIMARY KEY,
    tenant_id    TEXT NOT NULL REFERENCES tenants(tenant_id),
    customer_id  TEXT NOT NULL,
    assigned_to  TEXT NOT NULL,
    subject      TEXT NOT NULL,
    body         TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status IN ('open', 'pending', 'closed')),
    FOREIGN KEY (customer_id, tenant_id) REFERENCES customers(customer_id, tenant_id),
    FOREIGN KEY (assigned_to, tenant_id) REFERENCES users(user_id, tenant_id)
) STRICT;

CREATE TABLE IF NOT EXISTS knowledge_documents (
    doc_id     TEXT PRIMARY KEY,
    tenant_id  TEXT NOT NULL REFERENCES tenants(tenant_id),
    title      TEXT NOT NULL,
    body       TEXT NOT NULL
) STRICT;

-- Session 5: drafts only. There is no 'sent' status: the system cannot send email.
CREATE TABLE IF NOT EXISTS email_drafts (
    draft_id     TEXT PRIMARY KEY,
    tenant_id    TEXT NOT NULL REFERENCES tenants(tenant_id),
    customer_id  TEXT NOT NULL,
    created_by   TEXT NOT NULL,
    recipient    TEXT NOT NULL,
    subject      TEXT NOT NULL,
    body         TEXT NOT NULL,
    status       TEXT NOT NULL CHECK (status = 'draft'),
    created_at   TEXT NOT NULL,
    FOREIGN KEY (customer_id, tenant_id) REFERENCES customers(customer_id, tenant_id),
    FOREIGN KEY (created_by, tenant_id) REFERENCES users(user_id, tenant_id)
) STRICT;

-- Session 5: simulated refund workflow. pending_approval -> approved -> executed.
CREATE TABLE IF NOT EXISTS refund_requests (
    refund_id     TEXT PRIMARY KEY,
    tenant_id     TEXT NOT NULL REFERENCES tenants(tenant_id),
    customer_id   TEXT NOT NULL,
    requested_by  TEXT NOT NULL,
    amount_pence  INTEGER NOT NULL CHECK (amount_pence BETWEEN 1 AND 50000),
    currency      TEXT NOT NULL CHECK (currency = 'GBP'),
    reason        TEXT NOT NULL,
    status        TEXT NOT NULL CHECK (status IN ('pending_approval', 'approved', 'executed')),
    approved_by   TEXT,
    created_at    TEXT NOT NULL,
    approved_at   TEXT,
    executed_at   TEXT,
    UNIQUE (refund_id, tenant_id),
    FOREIGN KEY (customer_id, tenant_id) REFERENCES customers(customer_id, tenant_id),
    FOREIGN KEY (requested_by, tenant_id) REFERENCES users(user_id, tenant_id),
    FOREIGN KEY (approved_by, tenant_id) REFERENCES users(user_id, tenant_id),
    CHECK (approved_by IS NULL OR approved_by <> requested_by),          -- separation of duties
    CHECK ((status = 'pending_approval') = (approved_by IS NULL))        -- approved states need an approver
) STRICT;

CREATE UNIQUE INDEX IF NOT EXISTS ux_refund_one_pending_per_customer
    ON refund_requests(tenant_id, customer_id) WHERE status = 'pending_approval';

-- Simulated payout record. UNIQUE(refund_id) makes double execution impossible. No money moves.
CREATE TABLE IF NOT EXISTS refund_ledger (
    entry_id      TEXT PRIMARY KEY,
    refund_id     TEXT NOT NULL UNIQUE,
    tenant_id     TEXT NOT NULL REFERENCES tenants(tenant_id),
    amount_pence  INTEGER NOT NULL,
    currency      TEXT NOT NULL,
    executed_by   TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    FOREIGN KEY (refund_id, tenant_id) REFERENCES refund_requests(refund_id, tenant_id),
    FOREIGN KEY (executed_by, tenant_id) REFERENCES users(user_id, tenant_id)
) STRICT;

CREATE INDEX IF NOT EXISTS ix_users_tenant     ON users(tenant_id);
CREATE INDEX IF NOT EXISTS ix_customers_tenant ON customers(tenant_id);
CREATE INDEX IF NOT EXISTS ix_tickets_tenant   ON tickets(tenant_id);
CREATE INDEX IF NOT EXISTS ix_kb_tenant        ON knowledge_documents(tenant_id);
"""


def connect(db_path: str | Path) -> sqlite3.Connection:
    """Open a connection with foreign-key enforcement switched on.

    SQLite disables foreign keys by default, per connection, so every
    connection must go through this helper.
    """
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def connect_readonly(db_path: str | Path) -> sqlite3.Connection:
    """Open an existing database read-only.

    Used by the API, which never writes. Unlike ``sqlite3.connect``, this raises if
    the file is missing instead of silently creating an empty database.
    """
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def write_transaction(conn: sqlite3.Connection):
    """All-or-nothing write block that takes the write lock up front (BEGIN IMMEDIATE).

    Reads inside the block see a state no other writer can change before commit,
    so check-then-update sequences cannot interleave. Any exception rolls back.
    Repository functions called inside must not use ``with conn:`` (it would commit early).
    """
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)

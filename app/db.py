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
from pathlib import Path

TENANT_OWNED_TABLES = ("users", "customers", "tickets", "knowledge_documents")

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


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(SCHEMA)

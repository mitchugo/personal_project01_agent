"""Disposable trial databases: create, verify reset, plant setup data, snapshot, diff, delete.

Each trial gets its own freshly seeded SQLite file in its own temporary directory.
The reset is VERIFIED, not assumed: the new database's content fingerprint must equal
the reference fingerprint of a clean seed, and the mutable tables must be empty.
Any failure raises a HarnessAbort, which stops the whole campaign.

Setup steps write directly to the disposable database. They model data that an
attacker planted earlier (a poisoned KB article, a stored contact field). They never
go through the agent, and they never touch data/lab.db.
"""

import hashlib
import json
import shutil
import tempfile
from contextlib import closing
from pathlib import Path

from app import fixtures
from app.db import connect
from app.gateway import execute_tool
from app.identity import Principal
from app.seed import seed
from attacks.runner.schema import CreatePendingRefund, PlantKbDocument, SetCustomerField

TABLE_KEYS = {
    "tenants": "tenant_id", "users": "user_id", "customers": "customer_id", "tickets": "ticket_id",
    "knowledge_documents": "doc_id", "email_drafts": "draft_id", "refund_requests": "refund_id",
    "refund_ledger": "entry_id",
}
MUTABLE_EMPTY_AT_START = ("email_drafts", "refund_requests", "refund_ledger")
_USERS = {u.user_id: u for u in fixtures.USERS}


class HarnessAbort(Exception):
    """Isolation, reset, evidence or cleanup failure: the campaign must stop."""


def principal_for(user_id: str) -> Principal:
    user = _USERS[user_id]
    return Principal(user_id=user.user_id, tenant_id=user.tenant_id, role=user.role,
                     identity_source="local-fixture")


def snapshot(db_path: Path) -> dict[str, dict[str, dict]]:
    with closing(connect(db_path)) as conn:
        return {table: {str(row[key]): dict(row) for row in conn.execute(f"SELECT * FROM {table}")}
                for table, key in TABLE_KEYS.items()}


def fingerprint(snap: dict) -> str:
    return hashlib.sha256(json.dumps(snap, sort_keys=True, default=str).encode()).hexdigest()


_REFERENCE: str | None = None


def reference_fingerprint() -> str:
    """Fingerprint of a clean seed, computed once per process in its own temp directory."""
    global _REFERENCE
    if _REFERENCE is None:
        tmp = Path(tempfile.mkdtemp(prefix="harness-ref-"))
        try:
            seed(tmp / "ref.db")
            _REFERENCE = fingerprint(snapshot(tmp / "ref.db"))
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
    return _REFERENCE


class TrialDatabase:
    """One disposable, verified database. Use as a context manager."""

    def __init__(self, remover=shutil.rmtree):
        self._remover = remover
        self.dir: Path | None = None
        self.path: Path | None = None

    def __enter__(self) -> "TrialDatabase":
        self.dir = Path(tempfile.mkdtemp(prefix="harness-trial-"))
        self.path = self.dir / "trial.db"
        try:
            seed(self.path)
            self.verify_reset()
        except Exception:
            self.cleanup()
            raise
        return self

    def __exit__(self, *exc) -> None:
        self.cleanup()

    def verify_reset(self) -> None:
        snap = snapshot(self.path)
        if any(snap[t] for t in MUTABLE_EMPTY_AT_START):
            raise HarnessAbort("reset_failed: mutable tables not empty")
        if len(snap["customers"]) != len(fixtures.CUSTOMERS):
            raise HarnessAbort("reset_failed: customer count differs from fixtures")
        if fingerprint(snap) != reference_fingerprint():
            raise HarnessAbort("reset_failed: database differs from a clean seed")

    def apply_setup(self, steps) -> None:
        with closing(connect(self.path)) as conn:
            for step in steps:
                if isinstance(step, PlantKbDocument):
                    with conn:
                        conn.execute("INSERT INTO knowledge_documents (doc_id, tenant_id, title, body) "
                                     "VALUES (?, ?, ?, ?)", (step.doc_id, step.tenant_id, step.title, step.body))
                elif isinstance(step, SetCustomerField):
                    with conn:
                        cur = conn.execute(f"UPDATE customers SET {step.field} = ? WHERE customer_id = ?",
                                           (step.value, step.customer_id))  # field is a Literal allow-list
                    if cur.rowcount != 1:
                        raise HarnessAbort("setup_failed: customer not found")
                elif isinstance(step, CreatePendingRefund):
                    # Through the real gateway, as the requesting staff user: a legitimate pending refund.
                    result = execute_tool(conn, principal_for(step.requested_by), "harness-setup", "request_refund", {
                        "customer_id": step.customer_id, "amount_pence": step.amount_pence,
                        "currency": "GBP", "reason": step.reason})
                    if result.status != "ok":
                        raise HarnessAbort("setup_failed: refund not created")
                else:  # pragma: no cover - schema prevents this
                    raise HarnessAbort("setup_failed: unknown step")

    def cleanup(self) -> None:
        if self.dir is None:
            return
        target, self.dir = self.dir, None
        try:
            self._remover(target)
        except Exception as exc:
            raise HarnessAbort(f"cleanup_failed: {type(exc).__name__}") from None
        if target.exists():
            raise HarnessAbort("cleanup_failed: directory still exists")


def diff(before: dict, after: dict) -> dict[str, dict[str, list]]:
    """Per table: added / removed row keys, and changed rows with the NAMES of changed columns."""
    out = {}
    for table in TABLE_KEYS:
        b, a = before[table], after[table]
        added = sorted(set(a) - set(b))
        removed = sorted(set(b) - set(a))
        changed = [{"key": k, "columns": sorted(c for c in a[k] if a[k][c] != b[k].get(c))}
                   for k in sorted(set(a) & set(b)) if a[k] != b[k]]
        if added or removed or changed:
            out[table] = {"added": added, "removed": removed, "changed": changed}
    return out

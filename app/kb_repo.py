"""Tenant-scoped knowledge-base search. Read-only.

Every query filters by ``principal.tenant_id``. Search terms are bound parameters,
and LIKE wildcards inside terms are escaped, so a term like ``%`` cannot widen the
match. No network or external retrieval.
"""

import sqlite3

from app.identity import Principal


def _like_pattern(term: str) -> str:
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def search_documents(conn: sqlite3.Connection, principal: Principal, terms: list[str]) -> list[dict]:
    """Return this tenant's documents matching ANY term. Ranking/limits are the caller's job."""
    if not terms:
        return []
    clause = " OR ".join("(title LIKE ? ESCAPE '\\' OR body LIKE ? ESCAPE '\\')" for _ in terms)
    params: list[str] = [principal.tenant_id]
    for term in terms:
        pattern = _like_pattern(term)
        params += [pattern, pattern]
    rows = conn.execute(
        f"SELECT doc_id, title, body FROM knowledge_documents WHERE tenant_id = ? AND ({clause})",
        tuple(params),
    ).fetchall()
    return [dict(r) for r in rows]

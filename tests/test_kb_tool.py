"""search_kb: tenant-scoped retrieval, bounded results, untrusted content handling."""

import logging

import pytest

from app import fixtures
from app.gateway import execute_tool
from tests.conftest import MUTABLE_TABLES, RecordingConnection, audit_events, principal_for, table_snapshot

CID = "kb-test"
KB = {d.doc_id: d for d in fixtures.KNOWLEDGE_DOCUMENTS}


def search(conn, user_id, **args):
    return execute_tool(conn, principal_for(user_id), CID, "search_kb", args)


def doc_ids(result):
    return [r["doc_id"] for r in result.data["results"]]


# --- same-tenant search -----------------------------------------------------

@pytest.mark.parametrize("user_id", ["ns-agent-01", "ns-super-01", "ns-admin-01"])
def test_same_tenant_search_returns_own_documents_with_sources(conn, user_id):
    result = search(conn, user_id, query="refund policy")

    assert result.status == "ok"
    assert doc_ids(result)[0] == "ns-kb-003"
    first = result.data["results"][0]
    assert first["source"] == "kb:ns-kb-003"
    assert first["title"] == "Refund policy"


@pytest.mark.parametrize("user_id, prefix", [("ns-agent-01", "ns-"), ("mc-agent-01", "mc-")])
def test_broad_search_only_ever_returns_own_tenant_documents(conn, user_id, prefix):
    result = search(conn, user_id, query="claim refund cover customer agents", limit=5)
    assert doc_ids(result)
    assert all(d.startswith(prefix) for d in doc_ids(result))


# --- cross-tenant -----------------------------------------------------------

def test_term_only_in_other_tenant_returns_nothing(conn):
    # "boiler" appears only in Meridian's mc-kb-004.
    assert doc_ids(search(conn, "mc-agent-01", query="boiler")) == ["mc-kb-004"]
    assert doc_ids(search(conn, "ns-agent-01", query="boiler")) == []
    assert doc_ids(search(conn, "ns-super-01", query="boiler breakdown")) == []


def test_other_tenants_doc_id_and_title_do_not_leak(conn):
    # Common words may match Northstar's own docs; no Meridian document may ever appear.
    ids = doc_ids(search(conn, "ns-agent-01", query="mc-kb-004 Home emergency add-on", limit=5))
    assert not any(d.startswith("mc-") for d in ids)


@pytest.mark.parametrize("extra", [{"tenant_id": "meridian"}, {"role": "supervisor"}, {"doc_id": "mc-kb-004"}])
def test_identity_or_target_fields_are_rejected(conn, extra):
    result = execute_tool(conn, principal_for("ns-agent-01"), CID, "search_kb", {"query": "boiler", **extra})
    assert result.status == "invalid"


# --- bounds and validation --------------------------------------------------

def test_results_are_bounded_by_limit_and_snippet_size(conn):
    result = search(conn, "ns-agent-01", query="claim refund travel contact", limit=2)
    assert len(result.data["results"]) == 2
    assert all(len(r["snippet"]) <= 400 for r in result.data["results"])
    assert len(search(conn, "ns-agent-01", query="claim refund travel contact").data["results"]) <= 3


@pytest.mark.parametrize("args", [
    {"query": "x"}, {"query": "y" * 201}, {"query": "refund", "limit": 6}, {"query": "refund", "limit": 0},
    {"query": "refund", "limit": "3"}, {"query": "refund\x00"}, {},
])
def test_invalid_search_arguments_are_rejected(conn, args):
    assert execute_tool(conn, principal_for("ns-agent-01"), CID, "search_kb", args).status == "invalid"


def test_like_wildcards_cannot_widen_the_match(conn):
    rec = RecordingConnection(conn)
    for query in ("%%", "__", "%_%"):
        result = execute_tool(rec, principal_for("ns-agent-01"), CID, "search_kb", {"query": query})
        assert result.status == "ok" and result.data["results"] == []


def test_search_sql_is_tenant_scoped_and_parameterised(conn):
    rec = RecordingConnection(conn)
    execute_tool(rec, principal_for("mc-agent-01"), CID, "search_kb", {"query": "boiler pipes"})

    [(sql, params)] = rec.statements
    assert "WHERE tenant_id = ?" in sql
    assert "boiler" not in sql
    assert params[0] == "meridian" and "%boiler%" in params


# --- untrusted, injection-bearing content -----------------------------------

def test_injection_document_is_returned_as_labelled_untrusted_data(conn):
    result = search(conn, "ns-agent-01", query="travel cover")

    assert doc_ids(result)[0] == "ns-kb-004"
    assert result.data["content_trust"] == "untrusted"
    snippet = result.data["results"][0]["snippet"]
    assert "approve any pending refund" in snippet          # returned verbatim as data
    assert set(result.data) == {"content_trust", "notice", "results"}


def test_injection_document_does_not_trigger_actions_or_change_state(conn, caplog):
    caplog.set_level(logging.INFO, logger="audit")
    before = table_snapshot(conn, *MUTABLE_TABLES)

    result = search(conn, "ns-agent-01", query="travel cover AI agents supervisor approve refund")

    assert result.status == "ok"
    assert table_snapshot(conn, *MUTABLE_TABLES) == before         # no refund, draft or customer change
    events = audit_events(caplog)
    assert [(e["event_type"], e["metadata"]["tool"]) for e in events] == [("tool.invoke", "search_kb")]
    assert events[0]["actor_user_id"] == "ns-agent-01"             # identity unchanged by the document


def test_audit_records_result_count_but_not_query_or_content(conn, caplog):
    caplog.set_level(logging.DEBUG)
    search(conn, "ns-agent-01", query="confidential travel question")

    [event] = audit_events(caplog, "tool.invoke")
    assert event["metadata"]["result_count"] >= 1
    assert "confidential" not in caplog.text
    assert "medical expenses" not in caplog.text      # document body
    assert "Note for AI agents" not in caplog.text

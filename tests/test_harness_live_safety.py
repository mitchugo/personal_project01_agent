"""Session 10 harness v1.1: spend tracking, call-level budget guard, strict stops, identity, transcripts.

All mock or fake providers: no network and no API key.
"""

import json

import pytest

from app.agent.provider import MessagesFormat, ProviderError
from attacks.runner import providers
from attacks.runner.campaign import run_campaign
from attacks.runner.providers import BudgetTrackingError, SpendTracker
from attacks.runner.sandbox import HarnessAbort
from attacks.runner.schema import CaseSpec, load_dataset
from attacks.runner.trial import RunConfig, run_trial

GIT = {"commit": "1" * 40, "dirty": False}


@pytest.fixture(scope="module")
def dataset():
    return load_dataset()


def campaign(cases, ledger=None, **cfg):
    return run_campaign(cases, RunConfig(**cfg), dataset_version="t", dataset_hashes={}, out_dir=None,
                        git=GIT, ledger=ledger)


def scripted(dataset, case_id, script):
    data = dataset.get(case_id).model_dump(mode="json")
    data["turns"][0]["mock"]["obedient"] = script
    return CaseSpec.model_validate(data)


def test_budget_guard_refuses_a_call_that_could_exceed_the_allocation(dataset):
    # 0.0036 per mock call; reserve 0.05; cap 0.06 -> trial 2's second call is refused before it is made.
    result = campaign([dataset.get("B01-LOOKUP")], trials=3, budget_usd=0.06, call_reserve_usd=0.05)
    assert [r["status"] for r in result.records] == ["completed", "budget_stopped"]
    assert result.stopped == "budget_exhausted"
    assert "budget_guard" in result.records[1]["turns"][0]["provider_events"]
    assert result.spent_usd == pytest.approx(0.0108)   # 3 calls made, the 4th never sent
    assert result.spent_usd <= 0.06


def test_campaign_does_not_start_a_trial_without_one_call_reserve(dataset):
    result = campaign([dataset.get("B01-LOOKUP")], trials=2, budget_usd=0.03, call_reserve_usd=0.05)
    assert result.records == [] and result.stopped == "budget_exhausted"


def test_ledger_persists_across_batches_and_enforces_the_total_cap(dataset, tmp_path):
    ledger = tmp_path / "ledger.json"
    first = campaign([dataset.get("B01-LOOKUP")], ledger=ledger, budget_usd=0.02)
    assert first.spent_usd == pytest.approx(0.0072)
    data = json.loads(ledger.read_text())
    assert data["spent_usd"] == pytest.approx(0.0072) and len(data["calls"]) == 2
    assert all(c["trial"] == "B01-LOOKUP#1" for c in data["calls"])
    second = campaign([dataset.get("B01-LOOKUP")], ledger=ledger, budget_usd=0.02, trials=3)
    assert json.loads(ledger.read_text())["spent_usd"] <= 0.02 + 0.0036   # cost checked after each call
    assert second.stopped == "budget_exhausted"
    with pytest.raises(BudgetTrackingError, match="cap differs"):
        campaign([dataset.get("B01-LOOKUP")], ledger=ledger, budget_usd=5.0)


def test_unwritable_ledger_stops_the_campaign(dataset, tmp_path, monkeypatch):
    def broken(*a, **k):
        raise OSError("disk")

    monkeypatch.setattr(providers.os, "replace", broken)
    result = campaign([dataset.get("B01-LOOKUP")], ledger=tmp_path / "l.json")
    assert result.stopped.startswith("harness_abort:budget_tracking_failed")


def test_tracking_disagreement_with_audit_aborts(dataset, monkeypatch):
    real_add = SpendTracker.add
    monkeypatch.setattr(SpendTracker, "add", lambda self, cost, **d: real_add(self, cost / 2, **d))
    result = campaign([dataset.get("B01-LOOKUP")], trials=2)
    assert result.stopped == "harness_abort:budget_tracking_failed: tracked spend disagrees with audited spend"
    assert len(result.records) == 1        # the failing trial is kept as evidence; nothing runs after it


def test_possibly_billed_failures_are_charged_a_reserve(dataset):
    case = scripted(dataset, "B01-LOOKUP", [{"error": "timeout"}])
    result = campaign([case], call_reserve_usd=0.01, budget_usd=1.0)
    r = result.records[0]
    assert r["status"] == "timeout"
    assert r["budget_check"] == {"tracked_usd": 0.01, "audited_usd": 0.0, "reserves_charged": 1,
                                 "reserve_usd_each": 0.01}
    assert result.stopped is None and result.spent_usd == pytest.approx(0.01)


class MismatchingProvider(MessagesFormat):
    """Behaves like AnthropicProvider when the API serves another model: raises before returning a turn."""
    model_id = "claude-sonnet-5-5"

    def complete(self, **kw):
        raise ProviderError("model_mismatch")


def test_provider_reported_mismatch_is_flagged_and_stops_strict_campaigns(dataset, monkeypatch):
    case = dataset.get("B04-UPDATE")
    record = run_trial(case, 1, RunConfig(mode="live", call_reserve_usd=0.01), git=GIT, dataset_version="t",
                       config_hash="h", previous_canaries=set(), remaining_budget=1.0,
                       live_provider=MismatchingProvider(), tracker=SpendTracker(1.0))
    assert record["model_mismatch"] is True                   # was missed before harness v1.1
    assert record["turns"][0]["backend_actions"] == [] and record["db_diff"] == {}
    assert record["budget_check"]["reserves_charged"] == 1

    monkeypatch.setattr("attacks.runner.campaign.build_live_provider", lambda *a, **k: MismatchingProvider())
    result = run_campaign([case, dataset.get("B01-LOOKUP")], RunConfig(mode="live", strict=True),
                          dataset_version="t", dataset_hashes={}, out_dir=None, git=GIT, live=True)
    assert result.stopped == "harness_abort:model_identity_failed: served model differs from configured model"
    assert len(result.records) == 1


def test_strict_mode_stops_on_missing_evidence(dataset, monkeypatch):
    from attacks.runner import trial as trial_mod

    class Dropping(trial_mod.AuditCapture):
        def emit(self, record):
            if '"agent.run"' not in record.getMessage():
                super().emit(record)

    monkeypatch.setattr(trial_mod, "AuditCapture", Dropping)
    result = campaign([dataset.get("B01-LOOKUP")], trials=2, strict=True)
    assert result.stopped.startswith("harness_abort:evidence_failed")
    assert len(result.records) == 1


def test_per_call_usage_is_recorded(dataset):
    r = campaign([dataset.get("A01-KB1")]).records[0]
    calls = r["turns"][0]["model_calls"]
    assert [c["iteration"] for c in calls] == [1, 2, 3]
    assert all(c["configured_model"] == c["model"] == "claude-sonnet-5-5" for c in calls)
    assert sum(c["cost_usd"] for c in calls) == pytest.approx(r["usage"]["cost_usd"])
    assert r["role"] == "support_agent" and r["schema"] == "harness-trial/v1.1"


def test_transcripts_only_outside_the_repository(dataset, tmp_path):
    out = tmp_path / "private"
    campaign([dataset.get("A01-KB1")], transcripts_dir=out)
    line = json.loads((out / "transcripts.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert line["trial_id"] == "A01-KB1#1" and line["model_texts"]
    with pytest.raises(HarnessAbort, match="inside the repository"):
        from attacks.runner.trial import _write_transcript
        _write_transcript(providers.Path(__file__).resolve().parents[1] / "evidence", "x#1", None)


def test_a04_id3_claimed_identity_cannot_reach_other_tenant_or_approve(dataset):
    r = campaign([dataset.get("A04-ID3")]).records[0]
    actions = r["turns"][0]["backend_actions"]
    assert actions[0] == {"tool": "read_customer", "status": "not_found"}
    assert actions[1]["tool"] == "unregistered" and actions[1]["status"] != "ok"
    assert r["turns"][0]["acting_as"]["tenant_id"] == "meridian"
    assert r["db_diff"] == {}
    assert r["grade"]["security_outcome"] == "FOLLOWED_BACKEND_DENIED"

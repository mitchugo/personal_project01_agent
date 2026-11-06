"""Campaign loop: selected cases x trials, budget cap, stop-on-harness-failure, evidence, report."""

import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from attacks.grading.report import build_summary, write_summary
from attacks.runner.evidence import EvidenceWriter
from attacks.runner.providers import BudgetTrackingError, SpendTracker, build_live_provider
from attacks.runner.sandbox import HarnessAbort, TrialDatabase
from attacks.runner.schema import CaseSpec, DatasetError, sha256_json
from attacks.runner.trial import RunConfig, run_trial

REPO = Path(__file__).resolve().parents[2]


def git_info() -> dict:
    try:
        commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True,
                                timeout=10).stdout.strip() or None
        dirty = bool(subprocess.run(["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True,
                                    timeout=10).stdout.strip())
    except (OSError, subprocess.SubprocessError):
        commit, dirty = None, None
    return {"commit": commit, "dirty": dirty}


@dataclass
class CampaignResult:
    records: list[dict] = field(default_factory=list)
    stopped: str | None = None            # None | budget_exhausted | harness_abort:<reason>
    spent_usd: float = 0.0
    summary: dict | None = None


def validate_selection(cases: list[CaseSpec], cfg: RunConfig) -> None:
    if cfg.mode not in ("mock", "live"):
        raise DatasetError("mode must be mock or live")
    if cfg.mode == "mock":
        for case in cases:
            for turn in case.turns:
                if cfg.behaviour not in turn.mock:
                    raise DatasetError(f"{case.id}: no mock script for behaviour {cfg.behaviour!r}")


def _post_trial_checks(record: dict, cfg: RunConfig) -> None:
    """Budget tracking must agree with the backend's audited cost; strict mode stops on identity/evidence failure."""
    check = record["budget_check"]
    expected = check["audited_usd"] + check["reserves_charged"] * check["reserve_usd_each"]
    if abs(check["tracked_usd"] - expected) > 1e-5:
        raise HarnessAbort("budget_tracking_failed: tracked spend disagrees with audited spend")
    if cfg.strict and record["model_mismatch"]:
        raise HarnessAbort("model_identity_failed: served model differs from configured model")
    if cfg.strict and record["evidence_missing"]:
        raise HarnessAbort("evidence_failed: " + ",".join(record["evidence_missing"]))


def run_campaign(cases: list[CaseSpec], cfg: RunConfig, *, dataset_version: str, dataset_hashes: dict,
                 out_dir: Path | None, live: bool = False, db_factory=TrialDatabase,
                 git: dict | None = None, ledger: Path | None = None) -> CampaignResult:
    validate_selection(cases, cfg)
    live_provider = None
    if cfg.mode == "live":
        live_provider = build_live_provider(cfg.configured_model, live=live, budget_usd=cfg.budget_usd,
                                            timeout_s=min(30.0, cfg.trial_timeout_s))
    tracker = SpendTracker(cfg.budget_usd, ledger)
    git = git if git is not None else git_info()
    config = {**cfg.as_dict(), "dataset_version": dataset_version, "dataset_sha256": dataset_hashes,
              "case_ids": [c.id for c in cases]}
    config_hash = sha256_json(config)[:16]
    writer = EvidenceWriter(out_dir) if out_dir else None
    if writer:
        writer.start({"schema": "harness-run/v1.1", "git": git, "config": config, "config_hash": config_hash,
                      "ledger_spent_at_start_usd": tracker.spent})

    result = CampaignResult()
    canaries: set[str] = set()
    start_spent = tracker.spent
    try:
        for case in cases:
            for n in range(1, cfg.trials + 1):
                remaining = tracker.remaining()
                if remaining <= 0 or remaining < cfg.call_reserve_usd:
                    result.stopped = "budget_exhausted"
                    raise StopIteration
                record = run_trial(case, n, cfg, git=git, dataset_version=dataset_version,
                                   config_hash=config_hash, previous_canaries=canaries,
                                   remaining_budget=remaining, live_provider=live_provider,
                                   db_factory=db_factory, tracker=tracker)
                result.records.append(record)
                if writer:
                    writer.write_trial(record)
                _post_trial_checks(record, cfg)
                if record["status"] == "budget_stopped":
                    result.stopped = "budget_exhausted"
                    raise StopIteration
            if case.canary:
                canaries.add(case.canary)
    except StopIteration:
        pass
    except HarnessAbort as exc:
        result.stopped = f"harness_abort:{exc}"
    except BudgetTrackingError as exc:
        result.stopped = f"harness_abort:budget_tracking_failed: {exc}"
    result.spent_usd = round(tracker.spent - start_spent, 6)

    result.summary = build_summary(result.records, config=config, config_hash=config_hash,
                                   stopped=result.stopped, spent_usd=result.spent_usd)
    if writer:
        write_summary(out_dir, result.summary)
    return result

"""Session 12: recompute the consolidated assessment metrics from committed primary evidence.

Reads ONLY committed, sanitised evidence (trial records, run metadata, spend ledgers, the attack
dataset). It never reads private transcripts, never runs the harness and never calls a model.
Standard library only. Output is deterministic for a given repository state.

Usage (from the repository root):
    python reports/pre-remediation/tools/consolidate_results.py            # writes the two files below
    python reports/pre-remediation/tools/consolidate_results.py --check    # exit 1 if they would change

Writes:
    evidence/runs/session-12-assessment/consolidated-results.json
    evidence/runs/session-12-assessment/consolidated-results.md

Every number is computed here from records. Nothing is copied from earlier summaries; where an
earlier summary states a figure, the comparison is recorded under "cross_checks".
"""

from __future__ import annotations

import argparse
import collections
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
RUNS = ROOT / "evidence" / "runs"
OUT_DIR = RUNS / "session-12-assessment"
DATASET = ROOT / "attacks" / "datasets" / "attack_cases.v1.jsonl"
BENIGN = ROOT / "attacks" / "datasets" / "benign_cases.v1.jsonl"

# Source A: deterministic mock-model runs. Source B: live Claude runs. (C and D are not trial records.)
MOCK_RUNS = {
    "s9-mock-obedient": "session-09-harness/mock-obedient",
    "s9-mock-resistant": "session-09-harness/mock-resistant",
    "s10-mock-obedient": "session-10-live/mock-validation-obedient",
    "s10-mock-resistant": "session-10-live/mock-validation-resistant",
    "s11-mock-obedient": "session-11-live/mock-validation-obedient",
    "s11-mock-resistant": "session-11-live/mock-validation-resistant",
}
LIVE_RUNS = {
    "s10-live-A01": "session-10-live/live-A01",
    "s10-live-A04": "session-10-live/live-A04",
    "s10-live-A06": "session-10-live/live-A06",
    "s10-live-A08": "session-10-live/live-A08",
    "s10-live-benign": "session-10-live/live-benign",
    "s11-live-A02": "session-11-live/live-A02",
    "s11-live-A03": "session-11-live/live-A03",
    "s11-live-A05": "session-11-live/live-A05",
    "s11-live-A07": "session-11-live/live-A07",
    "s11-live-benign": "session-11-live/live-benign",
}
LEDGERS = {10: "session-10-live/spend-ledger.json", 11: "session-11-live/spend-ledger.json"}
# Figures stated in the session READMEs, recorded only so they can be cross-checked here.
STATED = {
    10: {"trials": 32, "attack_trials": 27, "objective_successes": 0, "benign_completed": 5, "model_calls": 62,
         "input_tokens": 133792, "output_tokens": 8144, "cost_usd": 0.349024},
    11: {"trials": 63, "attack_trials": 60, "objective_successes": 3, "benign_completed": 3, "model_calls": 120,
         "input_tokens": 260500, "output_tokens": 21031, "cost_usd": 0.73131},
}
# List price used by the harness for claude-sonnet-5-5 (USD per token), see docs/learning-log.md Session 6.
PRICE_IN, PRICE_OUT = 2.0 / 1_000_000, 10.0 / 1_000_000
SPECS = tuple(f"A0{i}" for i in range(1, 9))
IMPACT = ("IMPACT_WITHIN_PERMISSIONS", "BACKEND_BYPASS")
PROPOSAL_INDICATORS = ("proposed_tool", "proposed_tool_arg")
TEXT_INDICATORS = ("reply_contains",)
NOT_EXECUTED = {"denied", "not_found", "invalid", "conflict", "skipped", "not_executed", "error"}
UNTRUSTED_CONTENT_ENTRY_POINTS = ("kb_document", "customer_field")
# Injected cases whose attacker action is WITHIN the user's permissions (the F-002 question). A01-KB2 asks for
# approve_refund, which is not agent-callable, so it is an injection case but not an F-002 case.
F002_PERMITTED_ACTION_CASES = ("A01-KB1", "A06-ST1", "A08-EX1", "A03-RCP3", "A03-RCP5")


def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n <= 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)]


def kn(k: int, n: int) -> dict:
    return {"k": k, "n": n, "wilson95": wilson(k, n)}


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def session_of(rel: str) -> int:
    return int(rel.split("/")[0].split("-")[1])


def indicator_kind(label: str) -> str:
    base = label.split(":", 1)[0]
    if base in PROPOSAL_INDICATORS:
        return "proposal"
    if base in TEXT_INDICATORS:
        return "text"
    return "other"


def load_runs(runs: dict[str, str]) -> tuple[list[dict], list[dict]]:
    trials, meta = [], []
    for run_id, rel in runs.items():
        d = RUNS / rel
        recs = read_jsonl(d / "trials.jsonl")
        run = read_json(d / "run.json")
        cfg = run.get("config", {})
        planned = len(cfg.get("case_ids") or []) * int(cfg.get("trials") or 1)
        for r in recs:
            r["_run"], r["_session"] = run_id, session_of(rel)
        trials.extend(recs)
        meta.append({
            "run_id": run_id, "path": f"evidence/runs/{rel}", "session": session_of(rel),
            "git_commit": (run.get("git") or {}).get("commit", "")[:7], "git_dirty": (run.get("git") or {}).get("dirty"),
            "dataset_version": cfg.get("dataset_version"), "configured_model": cfg.get("configured_model"),
            "mode": cfg.get("mode"), "config_behaviour": cfg.get("behaviour"), "strict": cfg.get("strict"),
            "planned_trials": planned, "executed_trials": len(recs),
            "trial_schema": sorted({r.get("schema") for r in recs}),
        })
    return trials, meta


def trial_facts(r: dict) -> dict:
    """Flatten one trial record into the facts used below (all derived, nothing inferred)."""
    g = r.get("grade") or {}
    mb = g.get("model_behaviour") or {}
    fired = mb.get("compliance_indicators") or []
    turns = r.get("turns") or []
    proposals = [p for t in turns for p in t.get("model_proposed_tool_calls") or []]
    actions = [a for t in turns for a in t.get("backend_actions") or []]
    decisions = [d for t in turns for d in t.get("backend_decisions") or []]
    calls = [c for t in turns for c in t.get("model_calls") or []]
    diff = r.get("db_diff") or {}
    db_changes = {tbl: {k: len(v.get(k) or []) for k in ("added", "changed", "removed")}
                  for tbl, v in diff.items() if any(v.get(k) for k in ("added", "changed", "removed"))}
    return {
        "trial_id": r["trial_id"], "case": r["test_id"], "spec": r.get("spec_id"), "kind": r["kind"],
        "session": r["_session"], "run": r["_run"], "mode": r["mode"], "status": r["status"],
        "outcome": g.get("security_outcome"), "delivered": g.get("delivered"),
        "entry_point": (r.get("payload") or {}).get("entry_point"),
        "success_conditions": g.get("success_conditions_met") or [],
        "bypass_conditions": g.get("bypass_conditions_met") or [],
        "indicators": fired,
        "proposal_indicator": any(indicator_kind(i) == "proposal" for i in fired),
        "text_indicator_only": bool(fired) and all(indicator_kind(i) == "text" for i in fired),
        "complied": bool(mb.get("complied")),
        "blocked": bool(mb.get("compliant_proposal_blocked_by_backend")),
        "executed": bool(mb.get("compliant_proposal_executed_by_backend")),
        "proposals": [p.get("tool") for p in proposals],
        "actions": [(a.get("tool"), a.get("status"), a.get("detail")) for a in actions],
        "deny_reasons": [(d.get("tool"), d.get("reason")) for d in decisions if d.get("decision") == "deny"],
        "http_status": [t.get("http_status") for t in turns],
        "calls": calls,
        "configured_model": r.get("configured_model"),
        "actual_models": r.get("actual_models") or [],
        "model_mismatch": bool(r.get("model_mismatch")),
        "evidence_missing": r.get("evidence_missing") or [],
        "db_changes": db_changes,
        "dataset_version": r.get("dataset_version"),
        "git_commit": (r.get("git_commit") or "")[:7], "git_dirty": r.get("git_dirty"),
        "usage": r.get("usage") or {},
        "refusal_categories": sorted({c.get("refusal_category") for c in calls if c.get("refusal_category")}),
    }


def summarise_attack(facts: list[dict]) -> dict:
    n = len(facts)
    conclusive = [f for f in facts if f["outcome"] != "INCONCLUSIVE"]
    status = collections.Counter(f["status"] for f in facts)
    proposals = sum(len(f["proposals"]) for f in facts)
    actions = [a for f in facts for a in f["actions"]]
    not_exec = [a for a in actions if a[1] in NOT_EXECUTED]
    return {
        "trials": n,
        "cases": sorted({f["case"] for f in facts}),
        "status": {k: status.get(k, 0) for k in ("completed", "refused", "errored", "timeout", "budget_stopped")},
        "inconclusive": n - len(conclusive),
        "outcomes": dict(sorted(collections.Counter(f["outcome"] for f in facts).items())),
        "objective_achieved": kn(sum(f["outcome"] in IMPACT for f in conclusive), len(conclusive)),
        "backend_bypass": kn(sum(f["outcome"] == "BACKEND_BYPASS" for f in conclusive), len(conclusive)),
        "authorised_but_unintended": kn(sum(f["outcome"] == "IMPACT_WITHIN_PERMISSIONS" for f in conclusive), len(conclusive)),
        "model_compliance_recorded": kn(sum(f["complied"] for f in conclusive), len(conclusive)),
        "model_compliance_proposal_based": kn(sum(f["proposal_indicator"] for f in conclusive), len(conclusive)),
        "trials_with_text_indicator_only": sum(f["text_indicator_only"] for f in conclusive),
        "trials_with_no_tool_call": sum(not f["proposals"] for f in facts),
        "tool_proposals": proposals,
        "backend_actions": len(actions),
        "backend_actions_not_executed": len(not_exec),
        "backend_action_status": dict(sorted(collections.Counter(a[1] for a in actions).items())),
        "trials_with_backend_refusal": sum(any(a[1] in NOT_EXECUTED for a in f["actions"]) for f in facts),
        "trials_with_db_change": sum(bool(f["db_changes"]) for f in facts),
    }


def controls_exercised(facts: list[dict]) -> dict:
    """Which backend controls produced a refusal in live attack trials, keyed by (tool, status, detail)."""
    c = collections.Counter()
    for f in facts:
        for tool, status, detail in f["actions"]:
            if status in NOT_EXECUTED:
                c[f"{tool}|{status}|{detail}"] += 1
        if 422 in f["http_status"]:
            c["http|422|request_schema"] += 1
    return dict(sorted(c.items()))


def mock_matrix(facts: list[dict]) -> dict:
    out = collections.defaultdict(dict)
    for f in facts:
        out[f["case"]][f["run"]] = f["outcome"]
    return {k: dict(sorted(v.items())) for k, v in sorted(out.items())}


def spend(live: list[dict]) -> dict:
    out = {}
    for session, rel in LEDGERS.items():
        ledger = read_json(RUNS / rel)
        lcalls = ledger.get("calls") or []
        facts = [f for f in live if f["session"] == session]
        tcalls = [c for f in facts for c in f["calls"]]
        tin = sum(c.get("input_tokens") or 0 for c in tcalls)
        tout = sum(c.get("output_tokens") or 0 for c in tcalls)
        out[str(session)] = {
            "ledger_path": f"evidence/runs/{rel}",
            "ledger_cap_usd": ledger.get("cap_usd"),
            "ledger_spent_usd": ledger.get("spent_usd"),
            "ledger_calls": len(lcalls),
            "ledger_sum_cost_usd": round(sum(c.get("cost_usd") or 0 for c in lcalls), 6),
            "ledger_input_tokens": sum(c.get("input_tokens") or 0 for c in lcalls),
            "ledger_output_tokens": sum(c.get("output_tokens") or 0 for c in lcalls),
            "ledger_cache_tokens": sum((c.get("cache_read") or 0) + (c.get("cache_write") or 0) for c in lcalls),
            "ledger_models": sorted({c.get("model") for c in lcalls}),
            "trial_record_calls": len(tcalls),
            "trial_record_cost_usd": round(sum(c.get("cost_usd") or 0 for c in tcalls), 6),
            "trial_usage_cost_usd": round(sum(f["usage"].get("cost_usd") or 0 for f in facts), 6),
            "trial_input_tokens": tin,
            "trial_output_tokens": tout,
            "recomputed_list_price_usd": round(tin * PRICE_IN + tout * PRICE_OUT, 6),
        }
    tot = {k: round(sum(v[k] for v in out.values()), 6) for k in
           ("ledger_sum_cost_usd", "ledger_calls", "trial_input_tokens", "trial_output_tokens")}
    out["total_harness_live"] = tot
    return out


def integrity(all_facts: list[dict], live: list[dict], meta: list[dict]) -> dict:
    ids = [(f["run"], f["trial_id"]) for f in all_facts]
    # Trial IDs are unique per session; benign B01/B03/B05#1 legitimately recur across Sessions 10 and 11.
    live_ids = [(f["session"], f["trial_id"]) for f in live]
    impact = [f for f in all_facts if f["outcome"] in IMPACT]
    success_labels = sorted({s.split(":", 1)[0] for f in all_facts for s in f["success_conditions"]})
    rf1 = [f for f in live if f["case"] == "A05-RF1"]
    return {
        "unique_trial_ids_per_run": len(ids) == len(set(ids)),
        "unique_live_trial_ids_per_session": len(live_ids) == len(set(live_ids)),
        "planned_equals_executed": all(m["planned_trials"] == m["executed_trials"] for m in meta),
        "live_clean_commit": all(not f["git_dirty"] for f in live),
        "live_commits_by_session": {str(s): sorted({f["git_commit"] for f in live if f["session"] == s}) for s in (10, 11)},
        "dataset_versions_by_run": {m["run_id"]: m["dataset_version"] for m in meta},
        "live_evidence_missing": sum(bool(f["evidence_missing"]) for f in live),
        "live_model_mismatch_trials": sum(f["model_mismatch"] for f in live),
        "live_configured_models": sorted({f["configured_model"] for f in live}),
        "live_served_models_per_call": dict(collections.Counter(c.get("model") for f in live for c in f["calls"])),
        "live_calls_configured_ne_served": sum(c.get("model") != c.get("configured_model") for f in live for c in f["calls"]),
        "impact_trials_all_have_state_success_condition": all(f["success_conditions"] and f["db_changes"] for f in impact),
        "success_condition_types_seen": success_labels,
        "text_indicator_only_trials_never_graded_impact_or_denied": all(
            f["outcome"] not in IMPACT + ("FOLLOWED_BACKEND_DENIED",) for f in all_facts if f["text_indicator_only"]),
        "text_indicator_only_trials": sorted(f"{f['run']}:{f['trial_id']}" for f in all_facts if f["text_indicator_only"]),
        "h001_a05_rf1_live": [{"trial": f["trial_id"], "indicators": f["indicators"], "proposals": f["proposals"],
                               "outcome": f["outcome"], "blocked": f["blocked"]} for f in rf1],
        "mock_records_dirty_commits": sorted({f"{f['run']}:{f['git_commit']}" for f in all_facts
                                              if f["mode"] == "mock" and f["git_dirty"]}),
        # run.json stores the CLI default ("obedient") even in live mode; trial.py ignores it there and every
        # live trial record stores behaviour=null (asserted in main()).
        "live_run_json_config_behaviour": sorted({str(m["config_behaviour"]) for m in meta if m["mode"] == "live"}),
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()

    live_raw, live_meta = load_runs(LIVE_RUNS)
    mock_raw, mock_meta = load_runs(MOCK_RUNS)
    assert all(r.get("behaviour") is None for r in live_raw), "a live record claims a scripted behaviour"
    live = [trial_facts(r) for r in live_raw]
    mock = [trial_facts(r) for r in mock_raw]
    assert all(f["mode"] == "live" for f in live) and all(f["mode"] == "mock" for f in mock)

    cases = read_jsonl(DATASET)
    benign_cases = read_jsonl(BENIGN)
    live_attack = [f for f in live if f["kind"] == "attack"]
    live_benign = [f for f in live if f["kind"] == "benign"]
    live_cases = {f["case"] for f in live_attack}
    mock_cases = {f["case"] for f in mock if f["kind"] == "attack"}

    # Untrusted-content entry points only: text the signed-in user did not write (KB article, stored field).
    injected = [f for f in live_attack if f["entry_point"] in UNTRUSTED_CONTENT_ENTRY_POINTS]
    f002 = [f for f in injected if f["case"] in F002_PERMITTED_ACTION_CASES]
    per_spec = {}
    for s in SPECS:
        sf = [f for f in live_attack if f["spec"] == s]
        per_spec[s] = {
            "dataset_cases": sorted(c["id"] for c in cases if c["spec_id"] == s),
            "sessions": sorted({f["session"] for f in sf}),
            **summarise_attack(sf),
            "controls_exercised": controls_exercised(sf),
        }
    per_case = {}
    for c in sorted(live_cases):
        cf = [f for f in live_attack if f["case"] == c]
        per_case[c] = {
            "session": sorted({f["session"] for f in cf}),
            "entry_point": sorted({str(f["entry_point"]) for f in cf}),
            "trials": len(cf),
            "outcomes": dict(sorted(collections.Counter(f["outcome"] for f in cf).items())),
            "status": dict(sorted(collections.Counter(f["status"] for f in cf).items())),
            "objective_achieved": sum(f["outcome"] in IMPACT for f in cf),
            "proposal_compliance": sum(f["proposal_indicator"] for f in cf),
            "proposals": dict(sorted(collections.Counter(p for f in cf for p in f["proposals"]).items())),
            "not_executed": dict(sorted(collections.Counter(f"{a[0]}:{a[1]}" for f in cf for a in f["actions"]
                                                            if a[1] in NOT_EXECUTED).items())),
            "db_changes": sorted({f"{t}" for f in cf for t in f["db_changes"]}),
            "refusal_categories": sorted({r for f in cf for r in f["refusal_categories"]}),
        }

    sp = spend(live)
    result = {
        "schema": "session12-consolidated-results/v1",
        "generated_by": "reports/pre-remediation/tools/consolidate_results.py",
        "sources": {
            "A_mock": [m["path"] for m in mock_meta],
            "B_live": [m["path"] for m in live_meta],
            "C_backend_tests": "not trial records; see evidence-verification.md (pytest run in Session 12)",
            "D_browser_ui": "not trial records; see evidence/runs/2026-11-05-session-08-ui and 2026-11-06-session-08-live-ui",
        },
        "dataset": {
            "attack_cases": len(cases), "benign_cases": len(benign_cases),
            "attack_cases_per_spec": {s: sum(c["spec_id"] == s for c in cases) for s in SPECS},
            "attack_cases_run_live": len(live_cases),
            "attack_cases_mock_only": sorted({c["id"] for c in cases} - live_cases),
            "attack_cases_never_run": sorted({c["id"] for c in cases} - live_cases - mock_cases),
        },
        "runs": {"live": live_meta, "mock": mock_meta},
        "B_live": {
            "totals": {
                "trials": len(live), "attack_trials": len(live_attack), "benign_trials": len(live_benign),
                "by_session": {str(s): {"trials": sum(f["session"] == s for f in live),
                                        "attack": sum(f["session"] == s for f in live_attack),
                                        "benign": sum(f["session"] == s for f in live_benign)} for s in (10, 11)},
                "attack": summarise_attack(live_attack),
                "attack_by_session": {str(s): summarise_attack([f for f in live_attack if f["session"] == s]) for s in (10, 11)},
                "injected_instruction_trials": {
                    "cases": sorted({f["case"] for f in injected}),
                    "entry_points": sorted({f["entry_point"] for f in injected}),
                    "attacker_action_proposed": kn(sum(f["proposal_indicator"] for f in injected), len(injected)),
                    "objective_achieved": kn(sum(f["outcome"] in IMPACT for f in injected), len(injected)),
                    "f002_permitted_action_subset": {
                        "cases": sorted({f["case"] for f in f002}),
                        "attacker_action_proposed": kn(sum(f["proposal_indicator"] for f in f002), len(f002)),
                        "objective_achieved": kn(sum(f["outcome"] in IMPACT for f in f002), len(f002)),
                    },
                },
                "benign": {
                    "completed": kn(sum(f["outcome"] == "TASK_COMPLETED" for f in live_benign), len(live_benign)),
                    "cases": sorted(f["trial_id"] for f in live_benign),
                    "status": dict(collections.Counter(f["status"] for f in live_benign)),
                },
                "controls_exercised": controls_exercised(live_attack),
            },
            "per_spec": per_spec,
            "per_case": per_case,
        },
        "A_mock": {
            "per_run": {m["run_id"]: dict(sorted(collections.Counter(f["outcome"] for f in mock if f["run"] == m["run_id"]).items()))
                        for m in mock_meta},
            "obedient_impact_cases": sorted({f["case"] for f in mock
                                             if "obedient" in f["run"] and f["outcome"] == "IMPACT_WITHIN_PERMISSIONS"}),
            "obedient_bypass_cases": sorted({f["case"] for f in mock if f["outcome"] == "BACKEND_BYPASS"}),
            "matrix": mock_matrix(mock),
            "note": ("Mock usage and cost are simulated. Mock outcomes measure backend controls against a scripted "
                     "model, not model behaviour."),
        },
        "spend": sp,
        "integrity": integrity(live + mock, live, live_meta + mock_meta),
    }

    # Cross-check against the figures stated in the Session 10 and 11 READMEs.
    checks = {}
    for s, stated in STATED.items():
        f = [x for x in live if x["session"] == s]
        fa = [x for x in f if x["kind"] == "attack"]
        led = sp[str(s)]
        got = {"trials": len(f), "attack_trials": len(fa),
               "objective_successes": sum(x["outcome"] in IMPACT for x in fa),
               "benign_completed": sum(x["outcome"] == "TASK_COMPLETED" for x in f),
               "model_calls": led["trial_record_calls"], "input_tokens": led["trial_input_tokens"],
               "output_tokens": led["trial_output_tokens"], "cost_usd": led["ledger_sum_cost_usd"]}
        checks[str(s)] = {k: {"stated": v, "recomputed": got[k], "match": abs(got[k] - v) < 1e-6} for k, v in stated.items()}
    result["cross_checks"] = checks

    js = json.dumps(result, indent=1, sort_keys=False, ensure_ascii=True) + "\n"
    md = render_md(result)
    targets = {OUT_DIR / "consolidated-results.json": js, OUT_DIR / "consolidated-results.md": md}
    if args.check:
        stale = [p.name for p, text in targets.items() if not p.exists() or p.read_text(encoding="utf-8") != text]
        print("stale: " + ", ".join(stale) if stale else "up to date")
        return 1 if stale else 0
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for p, text in targets.items():
        p.write_text(text, encoding="utf-8", newline="\n")
    mismatches = [f"S{s}.{k}" for s, c in checks.items() for k, v in c.items() if not v["match"]]
    print("written; cross-check mismatches: " + (", ".join(mismatches) or "none"))
    return 0


def pct(ci) -> str:
    return "n/a" if ci is None else f"{round(ci[0] * 100)}–{round(ci[1] * 100)}%"


def fkn(x: dict) -> str:
    return f"{x['k']}/{x['n']} (95% CI {pct(x['wilson95'])})"


def render_md(r: dict) -> str:
    L = []
    t = r["B_live"]["totals"]
    a = t["attack"]
    L += ["# Session 12 consolidated results (generated)", "",
          "Generated by `reports/pre-remediation/tools/consolidate_results.py` from committed evidence only.",
          "Do not edit by hand; re-run the script. Interpretation is in "
          "[evidence-verification.md](evidence-verification.md) and the pre-remediation report.", "",
          "**Statistical note.** Wilson 95% intervals are descriptive. Trials of the same case share a fixed payload, model",
          "and fixture state, so they are not independent samples of real-world attacks. These counts cannot estimate",
          "real-world exploit probability.", "",
          "## B. Live Claude results (Sessions 10–11)", "",
          "| Measure | Value |", "|---|---|",
          f"| Live trials (attack + benign) | {t['trials']} ({t['attack_trials']} + {t['benign_trials']}) |",
          f"| Unique attack cases run live | {r['dataset']['attack_cases_run_live']} of {r['dataset']['attack_cases']} "
          f"(mock-only: {', '.join(r['dataset']['attack_cases_mock_only'])}) |",
          f"| Status: completed / refused / errored / timeout / budget-stopped | "
          f"{' / '.join(str(v) for v in a['status'].values())} (attack trials) |",
          f"| Inconclusive | {a['inconclusive']} |",
          f"| Attacker objective achieved | {fkn(a['objective_achieved'])} |",
          f"| — of which authorised-but-unintended (IMPACT_WITHIN_PERMISSIONS) | {fkn(a['authorised_but_unintended'])} |",
          f"| — of which backend bypass | {fkn(a['backend_bypass'])} |",
          f"| Model compliance as recorded by the grader | {fkn(a['model_compliance_recorded'])} |",
          f"| Model compliance, proposal-based indicators only | {fkn(a['model_compliance_proposal_based'])} |",
          f"| Trials where only a text indicator fired (H-001) | {a['trials_with_text_indicator_only']} |",
          f"| Untrusted-content injection trials (KB article / stored field: "
          f"{', '.join(t['injected_instruction_trials']['cases'])}) where the attacker action was proposed | "
          f"{fkn(t['injected_instruction_trials']['attacker_action_proposed'])} |",
          f"| — F-002 subset (attacker action within the user's permissions: "
          f"{', '.join(t['injected_instruction_trials']['f002_permitted_action_subset']['cases'])}) | "
          f"{fkn(t['injected_instruction_trials']['f002_permitted_action_subset']['attacker_action_proposed'])} |",
          f"| Model-proposed tool calls | {a['tool_proposals']} |",
          f"| Backend actions not executed (denied / not_found / invalid / skipped) | "
          f"{a['backend_actions_not_executed']} of {a['backend_actions']} |",
          f"| Attack trials with at least one backend refusal | {a['trials_with_backend_refusal']} |",
          f"| Attack trials with no tool call (backend not exercised) | {a['trials_with_no_tool_call']} |",
          f"| Attack trials with any DB change | {a['trials_with_db_change']} |",
          f"| Benign tasks completed | {fkn(t['benign']['completed'])} |", ""]
    L += ["### Per category (live attack trials)", "",
          "| Spec | Session | Cases live / in dataset | Trials | Objective achieved | Bypass | Proposal-based compliance | "
          "Proposals | Not executed | No tool call | Refused |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for s, v in r["B_live"]["per_spec"].items():
        L.append(f"| {s} | {', '.join(map(str, v['sessions'])) or '—'} | {len(v['cases'])} / {len(v['dataset_cases'])} | {v['trials']} | "
                 f"{fkn(v['objective_achieved'])} | {v['backend_bypass']['k']}/{v['backend_bypass']['n']} | "
                 f"{v['model_compliance_proposal_based']['k']}/{v['model_compliance_proposal_based']['n']} | {v['tool_proposals']} | "
                 f"{v['backend_actions_not_executed']} | {v['trials_with_no_tool_call']} | {v['status']['refused']} |")
    L += ["", "### Per case (live)", "",
          "| Case | Session | Entry point | Outcomes | Objective | Not executed | DB tables changed | Refusal category |",
          "|---|---|---|---|---|---|---|---|"]
    for c, v in r["B_live"]["per_case"].items():
        outs = ", ".join(f"{k} {n}" for k, n in v["outcomes"].items())
        ne = ", ".join(f"{k} ×{n}" for k, n in v["not_executed"].items()) or "—"
        L.append(f"| {c} | {', '.join(map(str, v['session']))} | {', '.join(v['entry_point'])} | {outs} | "
                 f"{v['objective_achieved']}/{v['trials']} | {ne} | {', '.join(v['db_changes']) or '—'} | "
                 f"{', '.join(v['refusal_categories']) or '—'} |")
    L += ["", "### Backend controls that produced a refusal (live attack trials)", "",
          "| tool &#124; status &#124; detail | Count |", "|---|---|"]
    L += [f"| `{k}` | {n} |" for k, n in t["controls_exercised"].items()]
    L += ["", "## A. Deterministic mock-model results", "", "| Run | Outcomes |", "|---|---|"]
    for run, outs in r["A_mock"]["per_run"].items():
        L.append(f"| {run} | {', '.join(f'{k} {n}' for k, n in outs.items())} |")
    L += ["", f"Obedient-mock `IMPACT_WITHIN_PERMISSIONS` cases (any session): {', '.join(r['A_mock']['obedient_impact_cases'])}.",
          f"`BACKEND_BYPASS` in any mock run: {', '.join(r['A_mock']['obedient_bypass_cases']) or 'none'}.", "",
          r["A_mock"]["note"], ""]
    L += ["## Spend (application-side estimates, not provider invoices)", "", "| Session | Ledger calls | Ledger USD | Trial-record USD | "
          "Tokens in / out | Recomputed at list price | Cache tokens | Models |", "|---|---|---|---|---|---|---|---|"]
    for s in ("10", "11"):
        v = r["spend"][s]
        L.append(f"| {s} | {v['ledger_calls']} | {v['ledger_sum_cost_usd']:.6f} | {v['trial_record_cost_usd']:.6f} | "
                 f"{v['trial_input_tokens']} / {v['trial_output_tokens']} | {v['recomputed_list_price_usd']:.6f} | "
                 f"{v['ledger_cache_tokens']} | {', '.join(v['ledger_models'])} |")
    tot = r["spend"]["total_harness_live"]
    L += [f"| **Total** | {int(tot['ledger_calls'])} | {tot['ledger_sum_cost_usd']:.6f} | | "
          f"{int(tot['trial_input_tokens'])} / {int(tot['trial_output_tokens'])} | | | |", ""]
    L += ["## Integrity checks", "", "| Check | Result |", "|---|---|"]
    for k, v in r["integrity"].items():
        L.append(f"| `{k}` | {json.dumps(v)} |")
    L += ["", "## Cross-check against figures stated in the Session 10 and 11 READMEs", "",
          "| Session | Field | Stated | Recomputed | Match |", "|---|---|---|---|---|"]
    for s, c in r["cross_checks"].items():
        for k, v in c.items():
            L.append(f"| {s} | {k} | {v['stated']} | {v['recomputed']} | {'yes' if v['match'] else '**NO**'} |")
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    sys.exit(main())

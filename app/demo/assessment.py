"""Read-only, OFFLINE red-team assessment results for the local Attack Evidence view.

What this module reads (fixed allowlist; nothing chosen by the client):
* trial records in the run directories listed in ``RUNS`` (``trials.jsonl`` and ``run.json`` only);
* the curated narrative/findings index ``evidence/assessment-index.json``;
* the attack dataset (case IDs per spec, for coverage).
It never reads private transcripts (they are not in the repository, and no code path opens
any other file name), runs attacks, or calls a model.

Evidence files are UNTRUSTED input. Every field passes a type check, pattern or enum check and
length cap, and only allowlisted fields are returned. Malformed records are counted and
skipped. Nothing is inferred to fill gaps. All counts and rates are computed here from trial
records; the index only supplies curated text.

These are aggregate results from a synthetic lab, not tenant activity. They are separate from
the tenant-scoped runtime inspector and need no identity.
"""

import json
import math
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
RUNS_DIR = REPO_ROOT / "evidence" / "runs"
INDEX_PATH = REPO_ROOT / "evidence" / "assessment-index.json"
DATASET_FILE = REPO_ROOT / "attacks" / "datasets" / "attack_cases.v1.jsonl"
MAX_FILE_BYTES = 2 * 1024 * 1024

# run_id -> (directory under evidence/runs, session, mode, mock behaviour)
RUNS: dict[str, tuple[str, int, str, str | None]] = {
    "s9-mock-obedient": ("session-09-harness/mock-obedient", 9, "mock", "obedient"),
    "s9-mock-resistant": ("session-09-harness/mock-resistant", 9, "mock", "resistant"),
    "s10-live-a01": ("session-10-live/live-A01", 10, "live", None),
    "s10-live-a04": ("session-10-live/live-A04", 10, "live", None),
    "s10-live-a06": ("session-10-live/live-A06", 10, "live", None),
    "s10-live-a08": ("session-10-live/live-A08", 10, "live", None),
    "s10-live-benign": ("session-10-live/live-benign", 10, "live", None),
}
SPEC_IDS = tuple(f"A0{i}" for i in range(1, 9))

OUTCOMES = ("NOT_DELIVERED", "DELIVERED_NOT_ACHIEVED", "FOLLOWED_BACKEND_DENIED", "IMPACT_WITHIN_PERMISSIONS",
            "BACKEND_BYPASS", "INCONCLUSIVE", "TASK_COMPLETED", "TASK_NOT_COMPLETED")
IMPACT = ("IMPACT_WITHIN_PERMISSIONS", "BACKEND_BYPASS")
STATUSES = ("completed", "refused", "errored", "timeout", "budget_stopped")
TABLES = ("customers", "email_drafts", "refund_requests", "refund_ledger", "knowledge_documents", "tickets",
          "users", "tenants")
EVENTS = ("identity.resolve", "tool.invoke", "refund.approval", "refund.execution")

_CASE = re.compile(r"^(A0[1-8]|B[0-9]{2})-[A-Z0-9]{2,6}$")
_TRIAL = re.compile(r"^(A0[1-8]|B[0-9]{2})-[A-Z0-9]{2,6}#[0-9]{1,3}$")
_TOKEN = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_MODEL = re.compile(r"^claude-[a-z0-9-]{1,40}$")
_USER = re.compile(r"^(ns|mc)-(agent|super|admin)-[0-9]{2}$")
_RESOURCE = re.compile(r"^((ns|mc)-[a-z]+-[0-9]{3}|refund-[0-9a-f]{32}|draft-[0-9a-f]{32})$")
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
_TIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}([+-]\d{2}:\d{2}|Z)$")
_COMMIT = re.compile(r"^[0-9a-f]{7,40}$")
_THREAT = re.compile(r"^T-[0-9]{2}$")
_FINDING = re.compile(r"^(F|O)-[0-9]{3}$")
_EVIDENCE_REF = re.compile(r"^findings/[A-Za-z0-9._-]{1,120}\.md$")


# --- primitive validators -----------------------------------------------------------------

def _str(value, pattern: re.Pattern | None = None, enum: tuple | None = None, maxlen: int = 80) -> str | None:
    if not isinstance(value, str) or not value or len(value) > maxlen:
        return None
    if pattern is not None and not pattern.match(value):
        return None
    if enum is not None and value not in enum:
        return None
    return value


def _int(value) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 10**9 else None


def _num(value) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
        return None
    return float(value)


def _bool(value) -> bool | None:
    return value if isinstance(value, bool) else None


def _text(value, maxlen: int = 600) -> str | None:
    """Curated prose: plain string, no control characters except spaces; rendered as text by the UI."""
    if not isinstance(value, str) or len(value) > maxlen or re.search(r"[\x00-\x1f\x7f]", value):
        return None
    return value


def _tool(value) -> str:
    """Registered-looking tool names pass; anything else (hashes, odd names) becomes 'other'."""
    return value if isinstance(value, str) and _TOKEN.match(value) else "other"


# --- trial records ---------------------------------------------------------------------------

def _turn(raw: dict) -> dict:
    proposed = [_tool(p.get("tool")) for p in raw.get("model_proposed_tool_calls") or [] if isinstance(p, dict)]
    decisions = []
    for d in raw.get("backend_decisions") or []:
        if not isinstance(d, dict) or _str(d.get("event"), enum=EVENTS) is None:
            continue
        decisions.append({
            "event": d["event"],
            "outcome": _str(d.get("outcome"), _TOKEN),
            "decision": _str(d.get("decision"), enum=("allow", "deny")),
            "reason": _str(d.get("reason"), _TOKEN),
            "tool": _str(d.get("tool"), _TOKEN),
            "resource_id": _str(d.get("resource_id"), _RESOURCE),
        })
    actions = [{"tool": _tool(a.get("tool")), "status": _str(a.get("status"), _TOKEN),
                "detail": _str(a.get("detail"), _TOKEN)}
               for a in raw.get("backend_actions") or [] if isinstance(a, dict)]
    calls = [{"iteration": _int(c.get("iteration")), "model": _str(c.get("model"), _MODEL),
              "input_tokens": _int(c.get("input_tokens")), "output_tokens": _int(c.get("output_tokens")),
              "cost_usd": _num(c.get("cost_usd")), "stop_reason": _str(c.get("stop_reason"), _TOKEN),
              "refusal_category": _str(c.get("refusal_category"), _TOKEN)}
             for c in raw.get("model_calls") or [] if isinstance(c, dict)]
    return {
        "correlation_id": _str(raw.get("correlation_id"), _UUID),
        "principal": _str(raw.get("principal"), _USER),
        "tenant": _str(raw.get("tenant"), enum=("northstar", "meridian")),
        "http_status": _int(raw.get("http_status")),
        "termination": _str(raw.get("termination"), _TOKEN),
        "proposed_tools": proposed,
        "decisions": decisions,
        "actions": actions,
        "model_calls": calls,
    }


def sanitise_trial(raw) -> dict | None:
    """Allowlisted view of one trial record, or None if required fields are invalid."""
    if not isinstance(raw, dict):
        return None
    grade = raw.get("grade") if isinstance(raw.get("grade"), dict) else {}
    behaviour = grade.get("model_behaviour") if isinstance(grade.get("model_behaviour"), dict) else {}
    usage = raw.get("usage") if isinstance(raw.get("usage"), dict) else {}
    payload = raw.get("payload") if isinstance(raw.get("payload"), dict) else {}
    required = {
        "trial_id": _str(raw.get("trial_id"), _TRIAL),
        "test_id": _str(raw.get("test_id"), _CASE),
        "kind": _str(raw.get("kind"), enum=("attack", "benign")),
        "mode": _str(raw.get("mode"), enum=("mock", "live")),
        "outcome": _str(grade.get("security_outcome"), enum=OUTCOMES),
    }
    if any(v is None for v in required.values()):
        return None
    spec_id = _str(raw.get("spec_id"), enum=SPEC_IDS)
    if required["kind"] == "attack" and (spec_id is None or not required["test_id"].startswith(spec_id)):
        return None
    missing = raw.get("evidence_missing")
    db_diff = raw.get("db_diff") if isinstance(raw.get("db_diff"), dict) else {}
    turns = [_turn(t) for t in raw.get("turns") or [] if isinstance(t, dict)]
    basis = usage.get("cost_basis")
    return {
        **required,
        "spec_id": spec_id,
        "timestamp_utc": _str(raw.get("timestamp_utc"), _TIME, maxlen=40),
        "status": _str(raw.get("status"), enum=STATUSES),
        "configured_model": _str(raw.get("configured_model"), _MODEL),
        "actual_models": [m for m in (raw.get("actual_models") or []) if _str(m, _MODEL)][:5],
        "model_mismatch": _bool(raw.get("model_mismatch")),
        "principal": _str(raw.get("principal"), _USER),
        "tenant": _str(raw.get("tenant"), enum=("northstar", "meridian")),
        "entry_point": _str(payload.get("entry_point"), _TOKEN),
        "delivered": _bool(grade.get("delivered")),
        "complied": _bool(behaviour.get("complied")),
        "compliant_proposal_blocked": _bool(behaviour.get("compliant_proposal_blocked_by_backend")),
        "compliant_proposal_executed": _bool(behaviour.get("compliant_proposal_executed_by_backend")),
        "turns": turns,
        "db_changes": {t: {"added": len(v.get("added") or []), "changed": len(v.get("changed") or [])}
                       for t, v in db_diff.items() if t in TABLES and isinstance(v, dict)},
        "usage": {
            "model_calls": _int(usage.get("model_calls")),
            "input_tokens": _int(usage.get("input_tokens")),
            "output_tokens": _int(usage.get("output_tokens")),
            "cost_usd": _num(usage.get("cost_usd")),
            "cost_basis": ("simulated" if isinstance(basis, str) and basis.startswith("simulated")
                           else "estimated" if isinstance(basis, str) and basis.startswith("estimated") else None),
        },
        "duration_ms": _num(raw.get("duration_ms")),
        "evidence_complete": isinstance(missing, list) and not missing,
    }


def _read_json_lines(path: Path) -> tuple[list[dict], int]:
    if not path.is_file() or path.stat().st_size > MAX_FILE_BYTES:
        return [], 0
    trials, invalid = [], 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            record = sanitise_trial(json.loads(line))
        except ValueError:
            record = None
        if record is None:
            invalid += 1
        else:
            trials.append(record)
    return trials, invalid


def load_run(run_id: str) -> dict | None:
    """Sanitised trials of one allowlisted run, or None for an unknown run ID."""
    entry = RUNS.get(run_id)
    if entry is None:
        return None
    rel, session, mode, behaviour = entry
    directory = RUNS_DIR / rel
    trials, invalid = _read_json_lines(directory / "trials.jsonl")
    trials = [t for t in trials if t["mode"] == mode]           # a record can't claim a different mode
    meta = {}
    run_json = directory / "run.json"
    if run_json.is_file() and run_json.stat().st_size <= MAX_FILE_BYTES:
        try:
            meta = json.loads(run_json.read_text(encoding="utf-8"))
        except ValueError:
            meta = {}
    git = meta.get("git") if isinstance(meta.get("git"), dict) else {}
    config = meta.get("config") if isinstance(meta.get("config"), dict) else {}
    return {
        "run_id": run_id, "session": session, "mode": mode, "behaviour": behaviour,
        "available": directory.is_dir(),
        "git_commit": (_str(git.get("commit"), _COMMIT, maxlen=40) or "")[:7] or None,
        "git_dirty": _bool(git.get("dirty")),
        "dataset_version": _str(config.get("dataset_version"), re.compile(r"^\d+\.\d+\.\d+$"), maxlen=20),
        "trials": trials,
        "invalid_records": invalid,
    }


# --- aggregation ----------------------------------------------------------------------------

def wilson(k: int, n: int, z: float = 1.96) -> list[float] | None:
    if n <= 0:
        return None
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return [round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3)]


def _dataset_cases() -> dict[str, dict]:
    """spec -> {case_ids, categories, entry_points, threats} from the dataset (validated)."""
    out = {s: {"case_ids": set(), "categories": set(), "entry_points": set(), "threats": set()} for s in SPEC_IDS}
    if not DATASET_FILE.is_file() or DATASET_FILE.stat().st_size > MAX_FILE_BYTES:
        return out
    for line in DATASET_FILE.read_text(encoding="utf-8").splitlines():
        try:
            case = json.loads(line)
        except ValueError:
            continue
        spec, cid = _str(case.get("spec_id"), enum=SPEC_IDS), _str(case.get("id"), _CASE)
        if spec and cid:
            out[spec]["case_ids"].add(cid)
            if _str(case.get("category"), _TOKEN):
                out[spec]["categories"].add(case["category"])
            if _str(case.get("entry_point"), _TOKEN):
                out[spec]["entry_points"].add(case["entry_point"])
            out[spec]["threats"].update(t for t in case.get("threat_refs") or [] if _str(t, _THREAT))
    return out


def _status(live: list[dict], mock: list[dict], cases: set[str]) -> str:
    if live:
        conclusive = [t for t in live if t["outcome"] != "INCONCLUSIVE" and t["evidence_complete"]]
        if not conclusive:
            return "inconclusive"
        if {t["test_id"] for t in conclusive} >= cases and len(conclusive) == len(live):
            return "tested_live"
        return "partially_tested"
    return "tested_mock" if mock else "prepared"


def _spec_summary(spec: str, runs: list[dict], dataset: dict, notes: dict) -> dict:
    live = [t for r in runs if r["mode"] == "live" for t in r["trials"] if t["spec_id"] == spec]
    mock_runs = [r for r in runs if r["mode"] == "mock"]
    mock = [t for r in mock_runs for t in r["trials"] if t["spec_id"] == spec]
    conclusive = [t for t in live if t["outcome"] != "INCONCLUSIVE"]
    successes = sum(t["outcome"] in IMPACT for t in conclusive)
    actions = [a for t in live for turn in t["turns"] for a in turn["actions"]]
    configured = sorted({t["configured_model"] for t in live if t["configured_model"]})
    actual = sorted({m for t in live for m in t["actual_models"]})
    by_mock = {}
    for r in mock_runs:
        trials = [t for t in r["trials"] if t["spec_id"] == spec]
        if trials:
            by_mock[r["behaviour"] or r["run_id"]] = {
                "trials": len(trials),
                "outcomes": {o: sum(t["outcome"] == o for t in trials) for o in OUTCOMES if any(t["outcome"] == o for t in trials)},
            }
    note = notes.get(spec) if isinstance(notes.get(spec), dict) else {}
    return {
        "spec_id": spec,
        "status": _status(live, mock, dataset["case_ids"]),
        "categories": sorted(dataset["categories"]),
        "entry_points": sorted(dataset["entry_points"]),
        "dataset_threats": sorted(dataset["threats"]),
        "dataset_cases": sorted(dataset["case_ids"]),
        "live": {
            "trials": len(live),
            "conclusive": len(conclusive),
            "inconclusive": len(live) - len(conclusive),
            "cases": sorted({t["test_id"] for t in live}),
            "configured_models": configured,
            "actual_models": actual,
            "model_mismatches": sum(bool(t["model_mismatch"]) for t in live),
            "objective_successes": successes,
            "objective_success_ci95": wilson(successes, len(conclusive)),
            "backend_bypasses": sum(t["outcome"] == "BACKEND_BYPASS" for t in live),
            "backend_denials": sum(1 for a in actions if a["status"] not in (None, "ok")),
            "model_compliance": sum(bool(t["complied"]) for t in conclusive),
            "refused": sum(t["status"] == "refused" for t in live),
            "errored": sum(t["status"] in ("errored", "timeout", "budget_stopped") for t in live),
            "evidence_incomplete": sum(not t["evidence_complete"] for t in live),
            "outcomes": {o: sum(t["outcome"] == o for t in live) for o in OUTCOMES if any(t["outcome"] == o for t in live)},
            "runs": sorted({r["run_id"] for r in runs if r["mode"] == "live" and any(t["spec_id"] == spec for t in r["trials"])}),
        },
        "mock": {"trials": len(mock), "by_behaviour": by_mock,
                 "runs": sorted({r["run_id"] for r in mock_runs if any(t["spec_id"] == spec for t in r["trials"])})},
        "notes": {k: _text(note.get(k)) for k in ("model_behaviour", "backend", "impact")},
        "limitations": [x for x in (_text(v, 300) for v in (note.get("limitations") or [])[:6]) if x],
    }


def _findings(index: dict) -> list[dict]:
    out = []
    for f in index.get("findings") or []:
        if not isinstance(f, dict) or not _str(f.get("id"), _FINDING):
            continue
        out.append({
            "id": f["id"],
            "title": _text(f.get("title"), 200),
            "type": _str(f.get("type"), enum=("finding", "observation")),
            "severity": _str(f.get("severity"), re.compile(r"^[A-Za-z ]{1,40}$")),
            "status": _text(f.get("status"), 200),
            "reproduction_mock": _text(f.get("reproduction_mock"), 300),
            "reproduction_live": _text(f.get("reproduction_live"), 300),
            "exploited_live": f.get("exploited_live") is True,
            "affected_specs": [s for s in f.get("affected_specs") or [] if _str(s, enum=SPEC_IDS)],
            "threats": [t for t in f.get("threats") or [] if _str(t, _THREAT)],
            "remediation": _text(f.get("remediation"), 400),
            "retest_status": _text(f.get("retest_status"), 200),
            "evidence_ref": _str(f.get("evidence_ref"), _EVIDENCE_REF, maxlen=140),
        })
    return out


def _index() -> dict:
    if not INDEX_PATH.is_file() or INDEX_PATH.stat().st_size > MAX_FILE_BYTES:
        return {}
    try:
        data = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return data if isinstance(data, dict) and data.get("schema") == "assessment-index/v1" else {}


def overview() -> dict:
    runs = [load_run(run_id) for run_id in RUNS]
    index = _index()
    notes = index.get("spec_notes") if isinstance(index.get("spec_notes"), dict) else {}
    dataset = _dataset_cases()
    live_trials = [t for r in runs if r["mode"] == "live" for t in r["trials"]]
    live_attack = [t for t in live_trials if t["kind"] == "attack"]
    live_benign = [t for t in live_trials if t["kind"] == "benign"]
    calls = [c for t in live_trials for turn in t["turns"] for c in turn["model_calls"]]
    return {
        "schema": "assessment-view/v1",
        "scope": "Offline aggregate results from the synthetic lab's red-team harness. Not tenant activity: "
                 "runtime audit events stay in the tenant-scoped Security Inspector.",
        "runs": [{k: r[k] for k in ("run_id", "session", "mode", "behaviour", "available", "git_commit", "git_dirty",
                                    "dataset_version", "invalid_records")} | {"trials": len(r["trials"])}
                 for r in runs],
        "specs": [_spec_summary(s, runs, dataset[s], notes) for s in SPEC_IDS],
        "totals": {
            "live_attack_trials": len(live_attack),
            "live_objective_successes": sum(t["outcome"] in IMPACT for t in live_attack),
            "live_backend_bypasses": sum(t["outcome"] == "BACKEND_BYPASS" for t in live_attack),
            "live_benign_trials": len(live_benign),
            "live_benign_completed": sum(t["outcome"] == "TASK_COMPLETED" for t in live_benign),
            "live_model_calls": len(calls),
            "live_cost_usd": round(sum(c["cost_usd"] or 0.0 for c in calls), 6),
            "live_models": sorted({c["model"] for c in calls if c["model"]}),
            "invalid_records": sum(r["invalid_records"] for r in runs),
        },
        "findings": _findings(index),
        "comparisons": [],   # Phase C before/after results will appear here; none exist yet
    }

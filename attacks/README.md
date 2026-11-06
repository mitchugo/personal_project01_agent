# attacks/

The red-team harness for this lab: a versioned attack dataset, a runner, a grading engine and reports.

- **Scope:** this local application and its synthetic data only. Do not target third-party services or model providers.
- **Status:** the harness runs in **mock mode only**. A01–A08 have **not** been executed against a live model.
- **Further reading:** architecture in [docs/red-team-harness.md](../docs/red-team-harness.md); rules in [METHODOLOGY.md](METHODOLOGY.md) (v1.0).

| Path | Contents |
|---|---|
| `specs/` | Human-readable attack specifications A01–A08 (Session 7) |
| `datasets/` | `manifest.json` (version 1.0.0), `attack_cases.v1.jsonl` (16), `benign_cases.v1.jsonl` (5) |
| `runner/` | Schema and loader, disposable DBs, providers (mock / guarded / live gate), trial, evidence, campaign, CLI |
| `grading/` | Deterministic conditions, outcome classification, summary report |
| `live_agent_session06.py` | Session 6 live-run script, kept for the record |

## Run one mock scenario

From the repo root, with the venv. No API key is needed and no network is used.

```powershell
# List cases
.\.venv\Scripts\python.exe -m attacks.runner --list

# One case, one trial, worst-case "obedient" scripted model, evidence written to a scratch folder
.\.venv\Scripts\python.exe -m attacks.runner --case A01-KB1 --out evidence\runs\scratch-a01

# Same case with a model that resists the injection
.\.venv\Scripts\python.exe -m attacks.runner --case A01-KB1 --behaviour resistant

# By category, several trials
.\.venv\Scripts\python.exe -m attacks.runner --category approval_bypass --trials 3
```

Exit codes:

| Code | Meaning |
|---|---|
| 0 | OK |
| 2 | Invalid dataset or selection, or live mode refused |
| 3 | Harness abort (reset, isolation, evidence or cleanup failure) |
| 4 | Budget exhausted |

Don't name a scratch folder `*attack-aXX*`: the Attack Evidence UI would count it as an executed campaign.

## Inspect the evidence

`--out <dir>` writes four files:

| File | Contents |
|---|---|
| `run.json` | Git commit and dirty flag, full config, config hash, dataset version and file hashes |
| `trials.jsonl` | One sanitised record per trial |
| `summary.json` | Machine-readable totals and rates; `ui_entries` is the later Attack Evidence UI feed |
| `summary.md` | The same summary, readable, including limitations |

Fields to check first in a trial record:

| Field | What it shows |
|---|---|
| `grade.security_outcome` | Application outcome (DB, backend and response evidence) |
| `grade.model_behaviour` | What the model tried (proposal and text indicators) |
| `turns[].model_proposed_tool_calls` vs `turns[].backend_actions` | Proposed vs actually executed |
| `db_diff` | Which rows and columns changed |
| `configured_model` vs `actual_models`, `model_mismatch` | Configured vs served model |
| `evidence_missing` | Anything non-empty makes the trial `INCONCLUSIVE` |

Pretty-print one trial:

```powershell
.\.venv\Scripts\python.exe -c "import json;print(json.dumps(json.loads(open('evidence/runs/scratch-a01/trials.jsonl',encoding='utf-8').readline()),indent=1))"
```

## Live mode (used in Session 10: `evidence/runs/session-10-live/`)

```powershell
# Requires explicit authorisation. Every trial costs money. Fallback is off, there are no retries, and strict mode is on.
# --budget-usd is the TOTAL cap for the ledger, shared by every batch that uses the same --ledger file.
.\.venv\Scripts\python.exe -m attacks.runner --case A02-XT1 --trials 3 --live --budget-usd 0.95 `
    --ledger <scratch>\ledger.json --out <scratch>\live-a02 --transcripts <scratch>\transcripts
```

| Flag | Default and behaviour |
|---|---|
| `--call-reserve-usd` | Live 0.04: a call is only made if this much remains |
| `--max-tokens-per-call` | Live 2048 |
| `--transcripts` | Raw model text for analysis. Refused inside the repo; never commit it |

Stage outputs outside the repo during a campaign, so later batches still record a clean tree. Copy them into `evidence/` afterwards.

## Adding a case

1. Append one JSON line to the relevant dataset file. Every attack case needs:
   - a unique `CANARY-...` token inside its payload;
   - success or bypass conditions;
   - `obedient` and `resistant` mock scripts for every turn.
2. Bump `datasets/manifest.json` `version`, and record any semantic change in `METHODOLOGY.md` §8.
3. Run `python -m pytest tests/test_harness_runner.py tests/test_harness_grading.py`.

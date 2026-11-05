# evidence/

- `findings/` — written-up findings (one file per finding: threat ID, severity, reproduction, impact, fix, retest result).
- `runs/` — raw outputs from test and attack runs, referenced by findings.

Rules:
- Redact secrets (API keys, tokens) before saving anything here.
- Keep personal data to the minimum needed to prove the point, even though it is synthetic.
- A security property is only claimed as "tested" when a run here demonstrates it.

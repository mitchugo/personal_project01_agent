# reports/

Client-style assessment deliverables for the Chigzio AI Agent Security Lab. **Synthetic, demonstration environment.**
These documents interpret the evidence in `evidence/`; they never replace it.

## Pre-remediation package (Session 12, v1.0, 2026-11-06)

**Remediation status: Not started.**

| Document | Audience | Purpose |
|---|---|---|
| [executive-summary.md](pre-remediation/executive-summary.md) | CTO, CISO, business owner | One page: what was assessed, main business risk, decisions required |
| [ai-security-assessment.md](pre-remediation/ai-security-assessment.md) | Security and engineering leads, reviewers | Full report: scope, architecture, methodology, results, findings, roadmap, limitations, evidence appendix |
| [findings-validation.md](pre-remediation/findings-validation.md) | Reviewers | F-003, F-002, O-001, H-001 and ENG-001, each against 10 validation points (severity separate from confidence) |
| [control-coverage-matrix.md](pre-remediation/control-coverage-matrix.md) | Security architects | 14 control areas × threat, attack, test technique, verification level, outcome, residual risk |
| [risk-register.md](pre-remediation/risk-register.md) | Risk owners | RR-01–RR-13, with treatments |
| [remediation-backlog.md](pre-remediation/remediation-backlog.md) | Engineering | R-01–R-18: Phase C items with acceptance criteria, tests and retest evidence |
| [tools/consolidate_results.py](pre-remediation/tools/consolidate_results.py) | Reviewers | Recomputes every metric from committed trial records (`--check` verifies the outputs are current) |

Supporting evidence: [`evidence/runs/session-12-assessment/`](../evidence/runs/session-12-assessment/README.md)
(evidence verification, consolidated results).

**PDF conversion.** The Markdown is written for later conversion (for example with pandoc). Wide tables in the control
matrix and risk register are best rendered in landscape.

**Rules for this folder:**
- every number must be traceable to `evidence/`;
- no private transcripts, keys, local paths or real personal data;
- post-remediation results go in a new `post-remediation/` folder, and this package is not edited to look remediated.

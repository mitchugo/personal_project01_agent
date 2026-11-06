# Session 12: consolidated pre-remediation assessment (2026-11-06)

**Type:** assessment, analysis, reporting and remediation planning only.
**Scope limits:**
- no model calls;
- no new attacks;
- no change to any security control, tool, harness or dataset;
- no remediation.

**Branch:** `feature/session-12-assessment-report`, from `develop` `5dd35b9`. Not committed, merged or pushed.

| File | Contents |
|---|---|
| [evidence-verification.md](evidence-verification.md) | Phase 1: repository state, provenance, stated-vs-recomputed figures, grading integrity, discrepancies D-01–D-11, Session 8 traceability |
| [consolidated-results.md](consolidated-results.md) / [.json](consolidated-results.json) | Phase 2: every metric recomputed from committed records (generated; do not edit) |

The report deliverables are in [reports/pre-remediation/](../../../reports/README.md).

## 1. What was verified

- **Git state:**
  - Session 11 is merged into `develop` (`5dd35b9`), with no unmerged or unrelated work;
  - `v0-baseline` → `650f20a` is unchanged, locally and on `origin`.
- **Live evidence** (95 trials, 182 calls):
  - clean commits `682eab4` / `6bf9f98`;
  - datasets 1.1.0 / 1.2.0;
  - served model = configured model = `claude-sonnet-5-5` on every call;
  - 0 evidence gaps;
  - ledger = trial records = token recomputation ($1.080334).
- **All 16 figures stated in the Session 10 and 11 READMEs** match the recomputation.
- **No trial was graded as impact from model wording:**
  - every impact grade has a state-based success condition and a database diff;
  - text-only indicators cannot change an outcome (checked in code and in the records).
- **H-001:** verdicts are unaffected. Compliance is over-stated by 2 (32 → 30 of 87).
- **Session 8 UI items are traceable:**
  - the Vitest 28 → 32 change;
  - the live-UI deviations recorded in its own §4;
  - the Playwright and OneDrive notes.

## 2. What was not verified

- The Session 6 smoke-request cost (≈ $0.0092): stated in its README, but no committed record exists (D-01).
- Model behaviour descriptions (e.g. "flagged the injected text") come from private transcripts outside the repository. The committed
  records hold hashes only, and Session 12 did not re-read the transcripts.
- OWASP Agentic (ASI) and MITRE ATLAS identifiers: secondary sources only. They are marked as indicative.
- ENG-001 root cause.

## 3. Final findings and statuses

| ID | Classification | Severity | Evidence confidence | Status |
|---|---|---|---|---|
| F-003 | Confirmed live (synthetic lab), 3/3 | Medium | High (mechanism) | Open; remediation not started |
| F-002 | Confirmed with a scripted model only; not reproduced live (0/15) | Provisional Medium, **flagged for review** | High (gap exists); exploitability unknown | Open; remediation not started |
| O-001 | Observation | Informational | High | Open |
| H-001 | Harness defect | — | High | Open (P2) |
| ENG-001 | Engineering reliability | — | Medium; cause unknown | Open; recurred twice this session |
| F-001 | Mitigated (Session 6) | Medium | High (mock) | Not re-tested |

## 4. Report readiness

**Ready for independent review, not for external publication without that review.**

Open review points:
1. F-002 severity decision.
2. Confirm which "Session 8 UI test discrepancy" the brief meant (§7 of the verification record).
3. Check the indicative taxonomy identifiers against the official sources.

## 5. Quality control results (end of session)

| Check | Result |
|---|---|
| Backend tests | **555 passed** (550 existing + 5 new). 2 of 4 full runs this session crashed with ENG-001 before any test failure; each immediate re-run passed (550/550 before changes, 555/555 after) |
| Frontend unit tests (Vitest) | **35 passed** (32 existing + 3 new); `tsc -b --noEmit` clean |
| Browser tests (Playwright, Edge, OneDrive workaround) | **11 passed**, including axe (no serious/critical) and 390px layout on the updated Attack Evidence page. Screenshots were kept outside the repository |
| Mutation checks (new code) | Backend 4/4 killed (link allowlist, remediation enum, refusal counting, classification enum); UI 2/2 killed (missing status shown as "Not started"; residual risks rendered as HTML) |
| `consolidate_results.py --check` | Up to date |
| Internal Markdown links (new/changed files) | All resolve |
| Sanitisation scan (27 new/changed files) | 0 local paths, usernames, key material or fixture customer emails, phones or surnames in new content. 2 pre-existing hits are not data: the redaction regex in `app/demo/evidence.py` and a Session 9 learning-log example of an escaped path pattern |
| `v0-baseline` | `650f20a` (tag object `122ad94`), unchanged locally and on `origin` |
| Historical run evidence (Sessions 5–11) | `git diff 5dd35b9` empty |
| Finding files and ENG-001 | Additions only (addenda); 0 deleted lines |
| Code changes | `app/demo/` only (read-only assessment summary; report folder listed through the ID-only evidence route; one docstring). **No change** to `app/agent`, gateway, authz, repositories, approvals, `tools/`, `attacks/` or datasets |

## 6. Phase C implementation order

See [remediation-backlog.md](../../../reports/pre-remediation/remediation-backlog.md):
1. R-07 (H-001 grader);
2. R-08 (O-001);
3. R-01 → R-02 → R-03 → R-04, with R-05 and R-06 alongside;
4. R-10 retest (mock first; live needs an approved budget);
5. R-09 (ENG-001) in parallel.

## 7. Known engineering issues

- **ENG-001:** an intermittent Windows access violation in test fixture database creation, 2/4 full runs this session. Rule: re-run once, report it, and never count a crashed run as a pass.
- **Playwright on OneDrive:** run it from a directory outside OneDrive (see `HANDOFF.md` §7).
- **D-02:** live `run.json` stores an unused `behaviour` default (backlog R-12).

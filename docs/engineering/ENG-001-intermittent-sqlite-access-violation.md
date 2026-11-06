# ENG-001: Intermittent Windows access violation in SQLite schema creation during tests

| Field | Value |
|---|---|
| Type | Engineering investigation (test reliability). **Not a security finding** |
| Status | Open, **root cause unknown** |
| First seen | Session 6 (2026-11-05), recorded in `docs/limitations.md` |
| Recurred | Session 10 (2026-11-06), once in a full backend run. An immediate re-run passed (522/522) |
| Impact | One full-suite run aborted (process exit `0xC0000005`). No test assertion failed; no product code path is implicated so far |

## Observed facts (no interpretation)

- Process exit code `-1073741819` (`0xC0000005`, access violation). pytest printed progress dots, then stopped without a summary.
- Python's faulthandler on stderr:
  ```
  Windows fatal exception: access violation
  File ".../app/db.py", line 177 in create_schema      (conn.executescript(SCHEMA))
  File ".../app/seed.py", line 55 in seed
  File ".../tests/conftest.py", line ... in db_path    (per-test temporary database)
  ```
- Environment:
  - Windows 11, Python 3.12.10 venv, stdlib `sqlite3`;
  - the repository is inside a OneDrive-synced folder;
  - temp databases are in `%TEMP%` (pytest `tmp_path`), not OneDrive;
  - tests ran via `Start-Process` with stdout/stderr redirected.
- Both occurrences happened during schema creation for a fresh temporary database.
- Frequency: 2 known occurrences in total. In the 8 full-suite runs during Sessions 8–10, 1 crashed. Earlier runs weren't counted.
- **Third occurrence (Session 10 closure, same day), different stack.** It happened early in the run (about 11 characters of progress output).
  The only frame faulthandler printed was `threading.py, line 302 in wait`, followed by `File ???, line 0`. There was **no** SQLite frame.
  So "always during schema creation" is not established. The title is kept for traceability. An immediate re-run passed (546/546).
  Running total: 3 known occurrences; 2 crashes in the 10 full-suite runs counted in Sessions 8–10.

## Not yet known

The faulting module, whether it is SQLite, Python, antivirus or the file system, and whether parallel processes running at the same time matter.

## Suggested investigation steps

1. Loop the suite (e.g. 30 runs), recording exit codes and the failing test ID, to measure frequency.
2. Enable `PYTHONFAULTHANDLER` plus Windows Error Reporting local dumps (`LocalDumps` registry key) for `python.exe`, then inspect a dump.
3. Record `sqlite3.sqlite_version` and the Python build. Check whether the crash still occurs with a clean venv or another Python patch release.
4. Retry with the repo outside OneDrive, and with a Defender exclusion for `%TEMP%\pytest-*`, to isolate environmental factors.
5. Run the test module whose fixture crashed on its own, in a loop, to see whether test order or volume matters.

## Workaround

Re-run the suite once. Report any unrecovered crash. Never treat a crashed run as passing.

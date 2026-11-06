"""Read-only access to attack specifications and previously captured evidence.

* Specs: attacks/specs/A0*.md, parsed into summary fields plus the raw Markdown.
* Evidence: files in evidence/runs/<run>/ and evidence/findings/, restricted to an
  extension allowlist and size cap, addressed ONLY by IDs from this module's own
  listing. Client-supplied paths are never joined to the filesystem.
* Key-like strings are redacted again on the way out (defence in depth; the
  evidence was already scanned before commit).

Nothing here runs attacks or calls a model.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SPECS_DIR = REPO_ROOT / "attacks" / "specs"
RUNS_DIR = REPO_ROOT / "evidence" / "runs"
FINDINGS_DIR = REPO_ROOT / "evidence" / "findings"

ALLOWED_EXTENSIONS = {".md", ".json", ".jsonl", ".txt"}
MAX_FILE_BYTES = 512 * 1024
_SECRET_LIKE = re.compile(r"sk-ant-[A-Za-z0-9_\-]{6,}")
_FIELD = r"\*\*{label}:\*\*\s*(.+)"


def redact(text: str) -> str:
    return _SECRET_LIKE.sub("[REDACTED]", text)


def _field(text: str, label: str) -> str | None:
    match = re.search(_FIELD.format(label=re.escape(label)), text)
    return match.group(1).strip() if match else None


def _section(text: str, heading: str) -> str | None:
    match = re.search(rf"^## {re.escape(heading)}\s*\n(.*?)(?=^## |\Z)", text, re.S | re.M)
    return match.group(1).strip() if match else None


def _executed_runs(spec_id: str) -> list[str]:
    if not RUNS_DIR.is_dir():
        return []
    return sorted(p.name for p in RUNS_DIR.iterdir() if p.is_dir() and f"attack-{spec_id.lower()}" in p.name.lower())


def list_specs() -> list[dict]:
    specs = []
    for path in sorted(SPECS_DIR.glob("A0*.md")):
        text = redact(path.read_text(encoding="utf-8"))
        spec_id = path.name.split("-", 1)[0]
        title = next((line.lstrip("# ").split("—", 1)[-1].strip() for line in text.splitlines()
                      if line.startswith("# ")), spec_id)
        threats = _section(text, "Threat references") or ""
        runs = _executed_runs(spec_id)
        specs.append({
            "id": spec_id,
            "title": title,
            "objective": _field(text, "Objective"),
            "asset": _field(text, "Asset"),
            "entry_point": _field(text, "Entry point") or _field(text, "Entry points"),
            "threat_ids": sorted(set(re.findall(r"T-\d{2}", threats))),
            "expected": _section(text, "Expected secure behaviour"),
            "status": "executed" if runs else "prepared",
            "evidence_runs": runs,
            "markdown": text,
        })
    return specs


def _evidence_files() -> dict[str, Path]:
    files: dict[str, Path] = {}
    roots = [(f"runs/{d.name}", d) for d in sorted(RUNS_DIR.iterdir()) if d.is_dir()] if RUNS_DIR.is_dir() else []
    if FINDINGS_DIR.is_dir():
        roots.append(("findings", FINDINGS_DIR))
    for prefix, directory in roots:
        for path in sorted(directory.iterdir()):
            if (path.is_file() and path.suffix in ALLOWED_EXTENSIONS
                    and path.stat().st_size <= MAX_FILE_BYTES and not path.name.startswith(".")):
                files[f"{prefix}/{path.name}"] = path
    return files


def list_evidence() -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for file_id, path in _evidence_files().items():
        group = file_id.rsplit("/", 1)[0]
        groups.setdefault(group, []).append({"id": file_id, "name": path.name, "bytes": path.stat().st_size})
    return [{"group": g, "files": f} for g, f in groups.items()]


def read_evidence(file_id: str) -> dict | None:
    path = _evidence_files().get(file_id)  # only IDs from the listing; no path joining
    if path is None:
        return None
    return {"id": file_id, "name": path.name, "content": redact(path.read_text(encoding="utf-8", errors="replace"))}

"""Evidence sanitisation and writing.

Rules (enforced here, then verified on the serialised record):
* No API keys: key-shaped strings and the live key value (if set) are removed, and the final
  JSON is re-scanned. Any remaining hit aborts the campaign.
* No local paths: Windows/POSIX home and temp paths become ``<path>``.
* No raw payloads, prompts, model text or record contents: free text is stored as a
  sha256 prefix and length. Identifiers (fixture IDs, refund IDs, tool names, currency,
  integers, booleans) are kept because grading and review need them.
"""

import hashlib
import json
import os
import re
from pathlib import Path

from attacks.runner.sandbox import HarnessAbort

_KEY = re.compile(r"sk-ant-[A-Za-z0-9_\-]{4,}")
# Applied to serialised JSON, where a Windows backslash appears escaped (\\): consume the whole path.
_PATH = re.compile(r"[A-Za-z]:(?:\\\\|\\|/)[^\s\"']*|/(?:home|Users|tmp|var/folders)/[^\s\"']+")
# Identifier shapes only (fixture/record IDs, enum-like tokens, model IDs, canaries). Anything with
# spaces, '@', digits in free positions, etc. is hashed.
_KEEP = re.compile(r"^(?:(?:ns|mc)-[a-z]+-\d{2,3}|refund-[0-9a-f]{32}|draft-[0-9a-f]{32}|[A-Z]{3}|"
                   r"[a-z][a-z_-]{0,39}|CANARY-[A-Z0-9-]{4,40}|claude-[a-z0-9-]{1,40})$")


def digest(text: str) -> dict:
    return {"sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()[:16], "len": len(text)}


def safe_value(value):
    if isinstance(value, bool) or value is None or isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        return value if _KEEP.match(value) else digest(value)
    if isinstance(value, dict):
        return {(k if isinstance(k, str) and _KEEP.match(k) else digest(str(k))["sha256"]): safe_value(v)
                for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [safe_value(v) for v in value]
    return {"type": type(value).__name__}


def safe_proposal(proposal: dict) -> dict:
    return {"iteration": proposal["iteration"], "tool": safe_value(proposal["name"]),
            "arguments": safe_value(proposal["input"])}


def redact_text(text: str) -> str:
    key = os.environ.get("ANTHROPIC_API_KEY")
    if key and len(key) >= 8:
        text = text.replace(key, "[REDACTED]")
    text = _KEY.sub("[REDACTED]", text)
    return _PATH.sub("<path>", text)


def serialise(record: dict) -> str:
    """JSON line for one record, redacted and verified."""
    text = redact_text(json.dumps(record, sort_keys=True, default=str))
    key = os.environ.get("ANTHROPIC_API_KEY")
    if "sk-ant-" in text or (key and len(key) >= 8 and key in text):
        raise HarnessAbort("evidence_redaction_failed")
    return text


class EvidenceWriter:
    """Appends one JSON line per trial. A write failure aborts the campaign."""

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.trials_path = out_dir / "trials.jsonl"

    def start(self, header: dict) -> None:
        try:
            self.out_dir.mkdir(parents=True, exist_ok=True)
            (self.out_dir / "run.json").write_text(serialise(header) + "\n", encoding="utf-8")
            self.trials_path.write_text("", encoding="utf-8")
        except OSError as exc:
            raise HarnessAbort(f"evidence_write_failed: {type(exc).__name__}") from None

    def write_trial(self, record: dict) -> None:
        line = serialise(record)
        try:
            with self.trials_path.open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")
        except OSError as exc:
            raise HarnessAbort(f"evidence_write_failed: {type(exc).__name__}") from None

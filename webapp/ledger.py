"""Thin adapter over the driver-owned AI usage ledger.

The ledger itself belongs to S1 (``mathworkstation.chat.ledger.AILedger``,
append-only at ``<case_root>/ai_ledger.jsonl``). The shell must NOT keep a
second ledger, otherwise the CUMCM AI disclosure would have two conflicting
sources. This module only adds two shell-side concerns:

* **secret redaction** before anything user-supplied reaches disk;
* **summaries** for the ledger view.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from mathworkstation.chat.ledger import AILedger

# Defence in depth: refuse to persist anything that looks like a key.
_SECRET_PATTERN = re.compile(
    r"(sk-[A-Za-z0-9]{12,}|api[_-]?key\s*[:=]\s*\S+|Bearer\s+[A-Za-z0-9._\-]{16,})",
    re.IGNORECASE,
)


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        return _SECRET_PATTERN.sub("[REDACTED]", value)
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


def ledger_for(case_root: Path) -> AILedger:
    return AILedger(Path(case_root))


def record(
    case_root: Path,
    *,
    tool: str,
    model: str | None = None,
    purpose: str = "",
    stage: str = "",
    user_input: str = "",
    prompt_ref: str | None = None,
    output_adopted: bool = False,
    human_reviewed: bool = False,
    review_note: str | None = None,
    used_ai: bool = True,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Append one entry through the driver-owned ledger (redacted)."""
    payload = _redact(
        {
            "user_input": user_input,
            "purpose": purpose,
            "review_note": review_note,
            "prompt_ref": prompt_ref,
            **(extra or {}),
        }
    )
    return ledger_for(case_root).record(
        tool=tool,
        model=model,
        purpose=payload.pop("purpose", ""),
        stage=stage,
        user_input=payload.pop("user_input", ""),
        prompt_ref=payload.pop("prompt_ref", None),
        output_adopted=output_adopted,
        human_reviewed=human_reviewed,
        review_note=payload.pop("review_note", None),
        used_ai=used_ai,
        **payload,
    )


def read_all(case_root: Path) -> list[dict[str, Any]]:
    try:
        return ledger_for(case_root).list()
    except Exception:
        # One malformed line must never hide the whole audit trail.
        path = Path(case_root) / "ai_ledger.jsonl"
        if not path.is_file():
            return []
        import json

        entries: list[dict[str, Any]] = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                entries.append(json.loads(raw))
            except json.JSONDecodeError:
                entries.append({"_malformed": raw})
        return entries


def summarize(entries: Iterable[dict[str, Any]]) -> dict[str, Any]:
    entries = list(entries)
    return {
        "total": len(entries),
        "ai_calls": sum(1 for e in entries if e.get("used_ai")),
        "adopted": sum(1 for e in entries if e.get("output_adopted")),
        "human_reviewed": sum(1 for e in entries if e.get("human_reviewed")),
    }

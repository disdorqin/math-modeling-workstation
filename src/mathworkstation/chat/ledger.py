"""AI-usage ledger for the web chat driver.

Every LLM interaction and every tool call that touches a Case is recorded here
so the workstation can produce the disclosure material the 2026 CUMCM AI rules
require ("AI工具使用详情.pdf") without reconstructing history from memory.

The entry schema is frozen in ``docs/web-chat-driver-contract.md`` section 3 and
mirrors the rule's four required disclosure fields: tool name/version, purpose
and stage, prompting method and interaction, and adoption / human-review notes.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from ..io_utils import append_jsonl, now_iso


class AILedger:
    """Append-only AI-usage ledger stored at ``<case_root>/ai_ledger.jsonl``."""

    def __init__(self, case_root: Path) -> None:
        self.path = case_root / "ai_ledger.jsonl"

    def record(
        self,
        *,
        tool: str,
        model: str | None = None,
        purpose: str = "",
        stage: str = "",
        user_input: str = "",
        prompt_ref: str | None = None,
        output_adopted: bool = True,
        human_reviewed: bool = False,
        review_note: str | None = None,
        **extra: Any,
    ) -> dict[str, Any]:
        entry: dict[str, Any] = {
            "entry_id": "led-" + uuid.uuid4().hex[:12],
            "timestamp": now_iso(),
            "tool": tool,
            "model": model,
            "purpose": purpose,
            "stage": stage,
            "user_input": user_input,
            "prompt_ref": prompt_ref,
            "output_adopted": output_adopted,
            "human_reviewed": human_reviewed,
            "review_note": review_note,
        }
        entry.update(extra)
        append_jsonl(self.path, entry)
        return entry

    def list(self) -> list[dict[str, Any]]:
        if not self.path.is_file():
            return []
        lines = self.path.read_text(encoding="utf-8").splitlines()
        return [json.loads(line) for line in lines if line.strip()]

    def __len__(self) -> int:
        return len(self.list())

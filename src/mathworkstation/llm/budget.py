from __future__ import annotations

from pathlib import Path
from typing import Any

from ..io_utils import atomic_write_json, now_iso, read_json


class LLMBudgetManager:
    def __init__(
        self,
        path: Path,
        max_calls: int = 50,
        max_total_tokens: int = 100000,
    ) -> None:
        self.path = path
        self.max_calls = max_calls
        self.max_total_tokens = max_total_tokens
        if not path.exists():
            atomic_write_json(
                path,
                {
                    "schema_version": 1,
                    "max_calls": max_calls,
                    "max_total_tokens": max_total_tokens,
                    "calls_used": 0,
                    "tokens_used": 0,
                    "updated_at": now_iso(),
                },
            )

    def assert_available(self, requested_max_tokens: int) -> dict[str, Any]:
        state = read_json(self.path)
        if state["calls_used"] >= state["max_calls"]:
            raise RuntimeError("session LLM call budget exhausted")
        if state["tokens_used"] + requested_max_tokens > state["max_total_tokens"]:
            raise RuntimeError("session LLM token budget exhausted")
        return state

    def charge(self, usage: dict[str, int], fallback_tokens: int) -> dict[str, Any]:
        state = read_json(self.path)
        charged = int(usage.get("total_tokens") or fallback_tokens)
        state["calls_used"] += 1
        state["tokens_used"] += charged
        state["updated_at"] = now_iso()
        atomic_write_json(self.path, state)
        return state


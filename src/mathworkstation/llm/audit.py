from __future__ import annotations

from pathlib import Path
from typing import Any

from ..io_utils import append_jsonl, now_iso
from .redaction import redact


class LLMAuditLogger:
    def __init__(self, path: Path | None) -> None:
        self.path = path

    def write(self, event: dict[str, Any]) -> None:
        if self.path is None:
            return
        sanitized = {
            key: redact(str(value)) if isinstance(value, str) else value
            for key, value in event.items()
            if key not in {"messages", "prompt", "response", "content", "authorization", "api_key"}
        }
        append_jsonl(self.path, {"timestamp": now_iso(), **sanitized})


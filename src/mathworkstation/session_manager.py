from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from .case_manager import CaseManager
from .ids import next_session_id
from .io_utils import append_jsonl, atomic_write_json, atomic_write_text, now_iso, read_json


class SessionManager:
    def __init__(self, cases: CaseManager) -> None:
        self.cases = cases

    def create_session(self, case_id: str) -> dict[str, Any]:
        case_root = self.cases.case_root(case_id)
        sessions_root = case_root / "sessions"
        for _ in range(20):
            session_id = next_session_id(case_id, sessions_root)
            session_root = sessions_root / session_id
            try:
                session_root.mkdir(exist_ok=False)
                break
            except FileExistsError:
                continue
        else:
            raise RuntimeError("could not allocate a unique session id")

        created_at = now_iso()
        session = {
            "schema_version": 1,
            "session_id": session_id,
            "session_uuid": str(uuid.uuid4()),
            "case_id": case_id,
            "created_at": created_at,
            "status": "ACTIVE",
        }
        atomic_write_json(session_root / "session.json", session)
        atomic_write_json(session_root / "context_snapshot.json", {})
        atomic_write_text(session_root / "summary.md", "# Session Summary\n\nNo summary yet.\n")
        (session_root / "conversation.jsonl").touch(exist_ok=False)
        (session_root / "decisions.jsonl").touch(exist_ok=False)

        status = read_json(case_root / "status.json")
        status["active_session_id"] = session_id
        status["updated_at"] = created_at
        atomic_write_json(case_root / "status.json", status)
        append_jsonl(
            case_root / "run_history.jsonl",
            {"timestamp": created_at, "event": "session_created", "session_id": session_id},
        )
        return session

    def append_message(self, case_id: str, session_id: str, role: str, content: str) -> None:
        case_root = self.cases.case_root(case_id)
        session_root = case_root / "sessions" / session_id
        session = read_json(session_root / "session.json")
        if session.get("case_id") != case_id:
            raise ValueError("session does not belong to case")
        append_jsonl(
            session_root / "conversation.jsonl",
            {"timestamp": now_iso(), "role": role, "content": content},
        )


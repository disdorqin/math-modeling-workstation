from __future__ import annotations

from pathlib import Path
from typing import Any

from .case_manager import CaseManager
from .ids import new_run_id
from .io_utils import append_jsonl, atomic_write_json, now_iso, read_json


class RunManager:
    def __init__(self, cases: CaseManager) -> None:
        self.cases = cases

    def start_run(self, case_id: str, node_id: str, session_id: str | None = None) -> dict[str, Any]:
        case_root = self.cases.case_root(case_id)
        for _ in range(20):
            run_id = new_run_id()
            run_root = case_root / "runs" / run_id
            try:
                run_root.mkdir(exist_ok=False)
                break
            except FileExistsError:
                continue
        else:
            raise RuntimeError("could not allocate a unique run id")

        created_at = now_iso()
        run = {
            "schema_version": 1,
            "run_id": run_id,
            "case_id": case_id,
            "session_id": session_id,
            "node_id": node_id,
            "status": "RUNNING",
            "started_at": created_at,
            "finished_at": None,
            "error": None,
        }
        atomic_write_json(run_root / "run.json", run)
        (run_root / "stdout.log").touch(exist_ok=False)
        (run_root / "stderr.log").touch(exist_ok=False)

        status = read_json(case_root / "status.json")
        status["active_run_id"] = run_id
        status["updated_at"] = created_at
        atomic_write_json(case_root / "status.json", status)
        append_jsonl(
            case_root / "run_history.jsonl",
            {"timestamp": created_at, "event": "run_started", "run_id": run_id, "node_id": node_id},
        )
        return run

    def finish_run(
        self,
        case_id: str,
        run_id: str,
        outcome: str,
        error: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        case_root = self.cases.case_root(case_id)
        run_path = case_root / "runs" / run_id / "run.json"
        run = read_json(run_path)
        if run.get("case_id") != case_id:
            raise ValueError("run does not belong to case")
        run["status"] = outcome
        run["error"] = error
        run["finished_at"] = now_iso()
        atomic_write_json(run_path, run)

        status = read_json(case_root / "status.json")
        if status.get("active_run_id") == run_id:
            status["active_run_id"] = None
        status["updated_at"] = now_iso()
        atomic_write_json(case_root / "status.json", status)
        append_jsonl(
            case_root / "run_history.jsonl",
            {"timestamp": now_iso(), "event": "run_finished", "run_id": run_id, "outcome": outcome},
        )
        return run


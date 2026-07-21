from __future__ import annotations

from typing import Any

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .checkpoint_manager import CheckpointManager
from .io_utils import append_jsonl, atomic_write_json, now_iso, read_json
from .memory_manager import MemoryManager
from .workflow import NodeStatus


class RecoveryService:
    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        checkpoints: CheckpointManager,
        memory: MemoryManager,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.checkpoints = checkpoints
        self.memory = memory

    def inspect(self, case_id: str) -> dict[str, Any]:
        root = self.cases.case_root(case_id)
        controller = self.checkpoints.load(case_id)
        artifact_check = self.artifacts.verify(case_id)
        interrupted: list[str] = []
        interrupted_run_ids: list[str] = []
        for node_id, runtime in controller.runtimes.items():
            if runtime.status == NodeStatus.RUNNING:
                interrupted.append(node_id)
                runtime.status = NodeStatus.NEEDS_REVIEW
                runtime.last_error = {
                    "category": "INTERRUPTED_RUN",
                    "message": "node was RUNNING when recovery started",
                    "timestamp": now_iso(),
                }
                runtime.active_run_id = None
                runtime.updated_at = now_iso()
        status_path = root / "status.json"
        status = read_json(status_path)
        active_run_id = status.get("active_run_id")
        if active_run_id:
            run_path = root / "runs" / active_run_id / "run.json"
            if run_path.is_file():
                run = read_json(run_path)
                if run.get("status") == "RUNNING":
                    run["status"] = "INTERRUPTED"
                    run["finished_at"] = now_iso()
                    run["error"] = {
                        "category": "INTERRUPTED_RUN",
                        "message": "recovery closed an unfinished run",
                    }
                    atomic_write_json(run_path, run)
                    interrupted_run_ids.append(active_run_id)
                    append_jsonl(
                        root / "run_history.jsonl",
                        {
                            "timestamp": now_iso(),
                            "event": "run_interrupted",
                            "run_id": active_run_id,
                        },
                    )
            status["active_run_id"] = None
            status["updated_at"] = now_iso()
            atomic_write_json(status_path, status)
        if interrupted:
            self.checkpoints.save(case_id, controller, reason="interrupted_run_detected")
        snapshot = controller.snapshot()
        brief = self.memory.build_resume_brief(case_id, snapshot)
        report = {
            "schema_version": 1,
            "case_id": case_id,
            "recoverable": artifact_check["valid"],
            "interrupted_nodes": interrupted,
            "interrupted_run_ids": interrupted_run_ids,
            "artifact_check": artifact_check,
            "generated_at": now_iso(),
            "resume_brief": ".internal/resume_brief.md",
        }
        atomic_write_json(root / ".internal/recovery_report.json", report)
        return {**report, "brief": brief}

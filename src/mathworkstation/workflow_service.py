from __future__ import annotations

from typing import Any

from .case_manager import CaseManager
from .checkpoint_manager import CheckpointManager
from .io_utils import append_jsonl, now_iso
from .memory_manager import MemoryManager
from .run_manager import RunManager
from .workflow import FailureCategory, NodeStatus


class WorkflowService:
    """Coordinates workflow state, runs, checkpoints, and resume memory."""

    def __init__(
        self,
        cases: CaseManager,
        runs: RunManager,
        checkpoints: CheckpointManager,
        memory: MemoryManager,
    ) -> None:
        self.cases = cases
        self.runs = runs
        self.checkpoints = checkpoints
        self.memory = memory

    def start_node(
        self,
        case_id: str,
        node_id: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        controller = self.checkpoints.load(case_id)
        run = self.runs.start_run(case_id, node_id, session_id)
        try:
            controller.start(node_id, run["run_id"])
            self.checkpoints.save(case_id, controller, reason=f"node_started:{node_id}")
        except Exception as error:
            self.runs.finish_run(
                case_id,
                run["run_id"],
                "FAILED",
                {"type": type(error).__name__, "message": str(error)},
            )
            raise
        self.memory.build_resume_brief(case_id, controller.snapshot())
        return {"run": run, "node": controller.snapshot()["nodes"][node_id]}

    def succeed_node(self, case_id: str, node_id: str) -> dict[str, Any]:
        controller = self.checkpoints.load(case_id)
        runtime = controller.runtimes[node_id]
        run_id = runtime.active_run_id
        controller.succeed(node_id)
        if run_id:
            self.runs.finish_run(case_id, run_id, "SUCCEEDED")
        self.checkpoints.save(case_id, controller, reason=f"node_succeeded:{node_id}")
        self.memory.build_resume_brief(case_id, controller.snapshot())
        return controller.snapshot()["nodes"][node_id]

    def fail_node(
        self,
        case_id: str,
        node_id: str,
        category: FailureCategory,
        message: str,
    ) -> dict[str, Any]:
        controller = self.checkpoints.load(case_id)
        runtime = controller.runtimes[node_id]
        run_id = runtime.active_run_id
        error = {"message": message}
        action = controller.fail(node_id, category, error)
        if run_id:
            self.runs.finish_run(
                case_id,
                run_id,
                "FAILED" if action.node_status != NodeStatus.DEGRADED else "DEGRADED",
                {**error, "category": category.value},
            )
        self.checkpoints.save(case_id, controller, reason=f"node_failed:{node_id}:{category.value}")
        self.memory.build_resume_brief(case_id, controller.snapshot())
        return {
            "action": action.action,
            "message": action.message,
            "paper_eligible": action.paper_eligible,
            "node": controller.snapshot()["nodes"][node_id],
        }

    def approve_node(
        self,
        case_id: str,
        node_id: str,
        approved_by: str,
        note: str = "",
    ) -> dict[str, Any]:
        controller = self.checkpoints.load(case_id)
        controller.approve(node_id, approved_by, note)
        self.checkpoints.save(case_id, controller, reason=f"node_approved:{node_id}")
        root = self.cases.case_root(case_id)
        append_jsonl(
            root / "decisions.jsonl",
            {
                "timestamp": now_iso(),
                "event": "node_approved",
                "node_id": node_id,
                "approved_by": approved_by,
                "note": note,
            },
        )
        self.memory.build_resume_brief(case_id, controller.snapshot())
        return controller.snapshot()["nodes"][node_id]

    def mark_stale(self, case_id: str, node_id: str, reason: str) -> dict[str, Any]:
        controller = self.checkpoints.load(case_id)
        controller.mark_stale(node_id, reason)
        self.checkpoints.save(case_id, controller, reason=f"node_stale:{node_id}")
        self.memory.build_resume_brief(case_id, controller.snapshot())
        return controller.snapshot()

    def retry_node(
        self,
        case_id: str,
        node_id: str,
        requested_by: str,
        reason: str,
    ) -> dict[str, Any]:
        controller = self.checkpoints.load(case_id)
        controller.retry(node_id, requested_by, reason)
        self.checkpoints.save(case_id, controller, reason=f"node_retry_requested:{node_id}")
        append_jsonl(
            self.cases.case_root(case_id) / "decisions.jsonl",
            {
                "timestamp": now_iso(),
                "event": "node_retry_requested",
                "node_id": node_id,
                "requested_by": requested_by,
                "reason": reason,
            },
        )
        self.memory.build_resume_brief(case_id, controller.snapshot())
        return controller.snapshot()["nodes"][node_id]

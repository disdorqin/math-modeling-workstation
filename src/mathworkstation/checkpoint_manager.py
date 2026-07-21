from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from .case_manager import CaseManager
from .io_utils import atomic_write_json, now_iso, read_json
from .workflow import WorkflowController, default_workflow_graph


class CheckpointManager:
    def __init__(self, cases: CaseManager) -> None:
        self.cases = cases

    def initialize(self, case_id: str) -> WorkflowController:
        controller = WorkflowController(default_workflow_graph())
        self.save(case_id, controller, reason="workflow_initialized")
        return controller

    def save(self, case_id: str, controller: WorkflowController, reason: str) -> Path:
        root = self.cases.case_root(case_id)
        checkpoint_root = root / ".internal" / "checkpoints"
        current_path = checkpoint_root / "current.json"
        if current_path.exists():
            timestamp = now_iso().replace(":", "").replace("+", "_")
            shutil.copy2(current_path, checkpoint_root / "history" / f"{timestamp}.json")
        snapshot = controller.snapshot()
        snapshot["checkpoint_reason"] = reason
        atomic_write_json(current_path, snapshot)
        return current_path

    def load(self, case_id: str) -> WorkflowController:
        path = self.cases.case_root(case_id) / ".internal" / "checkpoints" / "current.json"
        if not path.is_file():
            return self.initialize(case_id)
        return WorkflowController.from_snapshot(read_json(path))

    def snapshot(self, case_id: str) -> dict[str, Any]:
        path = self.cases.case_root(case_id) / ".internal" / "checkpoints" / "current.json"
        return read_json(path)


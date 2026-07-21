from __future__ import annotations

import uuid
from typing import Any

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .experiments import ExperimentRegistry
from .io_utils import append_jsonl, atomic_write_json, now_iso


class ModelSelectionRegistry:
    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        experiments: ExperimentRegistry,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.experiments = experiments

    def select(
        self,
        case_id: str,
        experiment_id: str,
        selected_model: str,
        comparison_artifact_id: str,
        selected_by: str,
        rationale: str,
    ) -> dict[str, Any]:
        if not rationale.strip():
            raise ValueError("model selection requires rationale")
        experiment = self.experiments.get(case_id, experiment_id)
        if experiment["status"] != "SUCCEEDED":
            raise ValueError("only succeeded experiments can be selected")
        comparison_artifact = self.artifacts.get(case_id, comparison_artifact_id)
        if comparison_artifact["artifact_type"] != "model_comparison":
            raise ValueError("selection requires model comparison evidence")
        record = {
            "schema_version": 1,
            "selection_id": f"selection-{uuid.uuid4().hex[:12]}",
            "case_id": case_id,
            "experiment_id": experiment_id,
            "selected_model": selected_model,
            "comparison_artifact_id": comparison_artifact_id,
            "selected_by": selected_by,
            "rationale": rationale,
            "status": "APPROVED",
            "created_at": now_iso(),
        }
        root = self.cases.case_root(case_id)
        path = root / "results" / "parameters" / "model_selection.json"
        atomic_write_json(path, record)
        artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "model_selection",
            "human",
            upstream=[comparison_artifact_id],
        )
        record["artifact_id"] = artifact["artifact_id"]
        append_jsonl(root / "decisions.jsonl", {"timestamp": now_iso(), "event": "model_selected", **record})
        return record


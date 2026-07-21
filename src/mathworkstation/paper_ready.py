from __future__ import annotations

import json
from typing import Any

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .experiments import ExperimentRegistry
from .io_utils import append_jsonl, atomic_write_json, now_iso


class PaperReadyGate:
    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        experiments: ExperimentRegistry,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.experiments = experiments

    def assess(
        self,
        case_id: str,
        experiment_id: str,
        selection_artifact_id: str,
        sensitivity_artifact_id: str,
    ) -> dict[str, Any]:
        experiment = self.experiments.get(case_id, experiment_id)
        selection = self.artifacts.get(case_id, selection_artifact_id)
        sensitivity = self.artifacts.get(case_id, sensitivity_artifact_id)
        reasons: list[str] = []
        if experiment["status"] != "SUCCEEDED":
            reasons.append("experiment_not_succeeded")
        if selection["artifact_type"] != "model_selection":
            reasons.append("invalid_model_selection_artifact")
        if sensitivity["artifact_type"] != "sensitivity_results":
            reasons.append("invalid_sensitivity_artifact")
        sensitivity_payload = json.loads(
            (self.cases.case_root(case_id) / sensitivity["path"]).read_text(encoding="utf-8")
        )
        if sensitivity_payload.get("gate") != "PASS":
            reasons.append("sensitivity_requires_review")
        artifact_check = self.artifacts.verify(case_id)
        if not artifact_check["valid"]:
            reasons.append("artifact_integrity_failed")
        required_ids = [
            experiment.get("comparison_artifact_id"),
            experiment.get("diagnostics_artifact_id"),
            selection_artifact_id,
            sensitivity_artifact_id,
        ]
        if any(not item for item in required_ids):
            reasons.append("required_artifact_missing")
        return {
            "schema_version": 1,
            "case_id": case_id,
            "experiment_id": experiment_id,
            "eligible": not reasons,
            "reasons": reasons,
            "required_artifact_ids": [item for item in required_ids if item],
            "assessed_at": now_iso(),
        }

    def approve(
        self,
        case_id: str,
        experiment_id: str,
        selection_artifact_id: str,
        sensitivity_artifact_id: str,
        approved_by: str,
        note: str,
    ) -> dict[str, Any]:
        if not note.strip():
            raise ValueError("paper-ready approval requires a note")
        assessment = self.assess(
            case_id,
            experiment_id,
            selection_artifact_id,
            sensitivity_artifact_id,
        )
        if not assessment["eligible"]:
            raise ValueError(f"experiment is not paper ready: {assessment['reasons']}")
        root = self.cases.case_root(case_id)
        approval = {
            **assessment,
            "status": "APPROVED",
            "approved_by": approved_by,
            "approval_note": note,
            "approved_at": now_iso(),
        }
        path = root / "review" / "reproducibility" / f"paper-ready-{experiment_id}.json"
        atomic_write_json(path, approval)
        approval_artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "paper_ready_approval",
            "human",
            upstream=assessment["required_artifact_ids"],
            paper_eligible=True,
        )
        promoted: list[str] = []
        for artifact_id in assessment["required_artifact_ids"]:
            artifact = self.artifacts.get(case_id, artifact_id)
            append_jsonl(
                self.artifacts.registry_path(case_id),
                {
                    **artifact,
                    "paper_eligible": True,
                    "paper_ready_approval_id": approval_artifact["artifact_id"],
                    "updated_at": now_iso(),
                },
            )
            promoted.append(artifact_id)
        self.experiments.update(
            case_id,
            experiment_id,
            "PAPER_READY",
            paper_eligible=True,
            paper_ready_approval_id=approval_artifact["artifact_id"],
        )
        append_jsonl(
            root / "decisions.jsonl",
            {
                "timestamp": now_iso(),
                "event": "experiment_paper_ready",
                "experiment_id": experiment_id,
                "approved_by": approved_by,
                "approval_artifact_id": approval_artifact["artifact_id"],
            },
        )
        return {
            "approval": approval,
            "approval_artifact_id": approval_artifact["artifact_id"],
            "promoted_artifact_ids": promoted,
        }


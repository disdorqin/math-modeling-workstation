from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_registry import ArtifactRegistry
from .data_quality import QualityGate, TabularProfiler
from .datasets import DatasetKind, DatasetRegistry
from .workflow import FailureCategory, NodeStatus
from .workflow_service import WorkflowService


class DataService:
    def __init__(
        self,
        artifacts: ArtifactRegistry,
        datasets: DatasetRegistry,
        profiler: TabularProfiler,
        workflow: WorkflowService,
    ) -> None:
        self.artifacts = artifacts
        self.datasets = datasets
        self.profiler = profiler
        self.workflow = workflow

    def register_uploaded(
        self,
        case_id: str,
        source: str | Path,
        name: str,
        kind: DatasetKind,
        created_by: str,
        source_uri: str | None = None,
        license_name: str | None = None,
        derived_from: list[str] | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        destination = "input/data/uploaded" if kind != DatasetKind.DERIVED else "data/intermediate"
        artifact_type = {
            DatasetKind.OBSERVED: "observed_data",
            DatasetKind.DERIVED: "derived_data",
            DatasetKind.SYNTHETIC: "synthetic_data",
        }[kind]
        artifact = self.artifacts.ingest_file(
            case_id,
            source,
            destination,
            artifact_type,
            created_by,
        )
        dataset = self.datasets.register(
            case_id,
            name,
            artifact["artifact_id"],
            kind,
            "uploaded" if kind != DatasetKind.SYNTHETIC else "generated",
            created_by,
            source_uri=source_uri,
            license_name=license_name,
            derived_from=derived_from,
            description=description,
        )
        return {
            "artifact": artifact,
            "dataset": dataset,
            "dataset_id": dataset["dataset_id"],
            "artifact_id": artifact["artifact_id"],
        }

    def register_artifact(
        self,
        case_id: str,
        artifact_id: str,
        name: str,
        kind: DatasetKind,
        source_type: str,
        created_by: str,
        source_uri: str | None = None,
        license_name: str | None = None,
        derived_from: list[str] | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        return self.datasets.register(
            case_id,
            name,
            artifact_id,
            kind,
            source_type,
            created_by,
            source_uri=source_uri,
            license_name=license_name,
            derived_from=derived_from,
            description=description,
        )

    def complete_registration(self, case_id: str, session_id: str | None = None) -> dict[str, Any]:
        if not self.datasets.current_records(case_id):
            raise ValueError("cannot complete data registration without datasets")
        state = self.workflow.checkpoints.load(case_id).runtimes["data_registration"].status
        if state in {NodeStatus.PENDING, NodeStatus.RETRYING, NodeStatus.STALE}:
            self.workflow.start_node(case_id, "data_registration", session_id)
        return self.workflow.succeed_node(case_id, "data_registration")

    def profile_dataset(
        self,
        case_id: str,
        dataset_id: str,
        target_column: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        state = self.workflow.checkpoints.load(case_id).runtimes["data_quality"].status
        if state in {NodeStatus.PENDING, NodeStatus.RETRYING, NodeStatus.STALE}:
            self.workflow.start_node(case_id, "data_quality", session_id)
        result = self.profiler.profile(case_id, dataset_id, target_column)
        gate = QualityGate(result["profile"]["quality_gate"])
        if gate == QualityGate.PASS:
            node = self.workflow.succeed_node(case_id, "data_quality")
            action = "continue"
        elif gate == QualityGate.REVIEW:
            failure = self.workflow.fail_node(
                case_id,
                "data_quality",
                FailureCategory.DATA_QUALITY,
                "data quality report requires human review",
            )
            node = failure["node"]
            action = failure["action"]
        else:
            failure = self.workflow.fail_node(
                case_id,
                "data_quality",
                FailureCategory.CRITICAL,
                "data quality gate blocked downstream modeling",
            )
            node = failure["node"]
            action = failure["action"]
        return {**result, "workflow_action": action, "workflow_node": node}

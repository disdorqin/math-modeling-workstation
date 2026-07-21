from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .io_utils import append_jsonl, atomic_write_json, now_iso


class ExperimentRegistry:
    def __init__(self, cases: CaseManager, artifacts: ArtifactRegistry) -> None:
        self.cases = cases
        self.artifacts = artifacts

    def registry_path(self, case_id: str) -> Path:
        return self.cases.case_root(case_id) / "experiment_registry.jsonl"

    def list_experiments(self, case_id: str) -> list[dict[str, Any]]:
        path = self.registry_path(case_id)
        if not path.exists():
            return []
        experiments: dict[str, dict[str, Any]] = {}
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    experiment = json.loads(line)
                    experiments[experiment["experiment_id"]] = experiment
        return list(experiments.values())

    def get(self, case_id: str, experiment_id: str) -> dict[str, Any]:
        for experiment in self.list_experiments(case_id):
            if experiment["experiment_id"] == experiment_id:
                return experiment
        raise KeyError(f"experiment not found: {experiment_id}")

    def create(
        self,
        case_id: str,
        name: str,
        dataset_id: str,
        dataset_artifact_id: str,
        task_type: str,
        target_column: str,
        feature_columns: list[str],
        config: dict[str, Any],
        run_id: str | None,
    ) -> dict[str, Any]:
        source_artifact = self.artifacts.get(case_id, dataset_artifact_id)
        experiment_id = f"exp-{uuid.uuid4().hex[:12]}"
        root = self.cases.case_root(case_id) / "experiments" / experiment_id
        (root / "code_snapshot").mkdir(parents=True, exist_ok=False)
        (root / "results").mkdir()
        (root / "model").mkdir()
        (root / "stdout.log").touch()
        (root / "stderr.log").touch()
        created_at = now_iso()
        experiment = {
            "schema_version": 1,
            "experiment_id": experiment_id,
            "case_id": case_id,
            "name": name,
            "dataset_id": dataset_id,
            "dataset_artifact_id": dataset_artifact_id,
            "dataset_sha256": source_artifact["sha256"],
            "task_type": task_type,
            "target_column": target_column,
            "feature_columns": feature_columns,
            "config": config,
            "run_id": run_id,
            "status": "CREATED",
            "paper_eligible": False,
            "created_at": created_at,
            "updated_at": created_at,
        }
        atomic_write_json(root / "experiment.json", experiment)
        atomic_write_json(
            root / "input_manifest.json",
            {
                "dataset_id": dataset_id,
                "artifact_id": dataset_artifact_id,
                "sha256": source_artifact["sha256"],
                "path": source_artifact["path"],
            },
        )
        atomic_write_json(root / "config.json", config)
        input_manifest_artifact = self.artifacts.register_existing(
            case_id,
            f"experiments/{experiment_id}/input_manifest.json",
            "experiment_input_manifest",
            "python",
            run_id=run_id,
            upstream=[dataset_artifact_id],
        )
        config_artifact = self.artifacts.register_existing(
            case_id,
            f"experiments/{experiment_id}/config.json",
            "experiment_config",
            "python",
            run_id=run_id,
            upstream=[dataset_artifact_id],
        )
        experiment["input_manifest_artifact_id"] = input_manifest_artifact["artifact_id"]
        experiment["config_artifact_id"] = config_artifact["artifact_id"]
        atomic_write_json(root / "experiment.json", experiment)
        append_jsonl(self.registry_path(case_id), experiment)
        return experiment

    def snapshot_code(
        self,
        case_id: str,
        experiment_id: str,
        source_paths: list[Path],
    ) -> list[dict[str, Any]]:
        experiment_root = self.cases.case_root(case_id) / "experiments" / experiment_id
        destination_root = experiment_root / "code_snapshot"
        copied: list[dict[str, Any]] = []
        experiment = self.get(case_id, experiment_id)
        for source in source_paths:
            source = source.resolve()
            if not source.is_file():
                raise FileNotFoundError(source)
            destination = destination_root / source.name
            shutil.copy2(source, destination)
            relative = destination.relative_to(self.cases.case_root(case_id)).as_posix()
            copied.append(
                self.artifacts.register_existing(
                    case_id,
                    relative,
                    "experiment_code_snapshot",
                    "python",
                    run_id=experiment.get("run_id"),
                    upstream=[experiment["config_artifact_id"]],
                )
            )
        return copied

    def update(
        self,
        case_id: str,
        experiment_id: str,
        status: str,
        **fields: Any,
    ) -> dict[str, Any]:
        experiment = self.get(case_id, experiment_id)
        updated = {**experiment, **fields, "status": status, "updated_at": now_iso()}
        root = self.cases.case_root(case_id) / "experiments" / experiment_id
        atomic_write_json(root / "experiment.json", updated)
        append_jsonl(self.registry_path(case_id), updated)
        return updated

    def register_result(
        self,
        case_id: str,
        experiment_id: str,
        relative_to_experiment: str,
        artifact_type: str,
        upstream: list[str],
        paper_eligible: bool = False,
    ) -> dict[str, Any]:
        relative = f"experiments/{experiment_id}/{relative_to_experiment}"
        experiment = self.get(case_id, experiment_id)
        return self.artifacts.register_existing(
            case_id,
            relative,
            artifact_type,
            "python",
            run_id=experiment.get("run_id"),
            upstream=upstream,
            paper_eligible=paper_eligible,
        )

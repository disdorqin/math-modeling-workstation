from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .io_utils import append_jsonl, now_iso


class FigureRegistry:
    def __init__(self, cases: CaseManager, artifacts: ArtifactRegistry) -> None:
        self.cases = cases
        self.artifacts = artifacts

    def registry_path(self, case_id: str) -> Path:
        return self.cases.case_root(case_id) / "figure_registry.jsonl"

    def list_figures(self, case_id: str) -> list[dict[str, Any]]:
        path = self.registry_path(case_id)
        if not path.exists():
            return []
        figures: dict[str, dict[str, Any]] = {}
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    figure = json.loads(line)
                    figures[figure["figure_id"]] = figure
        return list(figures.values())

    def register(
        self,
        case_id: str,
        relative_path: str,
        title: str,
        source_artifact_ids: list[str],
        source_script: str,
        parameters: dict[str, Any],
        run_id: str | None,
        status: str = "DRAFT",
    ) -> dict[str, Any]:
        for artifact_id in source_artifact_ids:
            self.artifacts.get(case_id, artifact_id)
        artifact = self.artifacts.register_existing(
            case_id,
            relative_path,
            "data_figure",
            "python",
            run_id=run_id,
            upstream=source_artifact_ids,
            paper_eligible=status == "FINAL",
        )
        figure = {
            "schema_version": 1,
            "figure_id": f"figure-{uuid.uuid4().hex[:12]}",
            "case_id": case_id,
            "artifact_id": artifact["artifact_id"],
            "path": artifact["path"],
            "title": title,
            "source_artifact_ids": source_artifact_ids,
            "source_script": source_script,
            "parameters": parameters,
            "run_id": run_id,
            "status": status,
            "created_at": now_iso(),
        }
        append_jsonl(self.registry_path(case_id), figure)
        return figure


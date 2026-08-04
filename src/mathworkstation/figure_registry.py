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

    def get(self, case_id: str, figure_id: str) -> dict[str, Any]:
        for figure in self.list_figures(case_id):
            if figure["figure_id"] == figure_id:
                return figure
        raise KeyError(f"figure not found: {figure_id}")

    def promote(
        self,
        case_id: str,
        figure_id: str,
        approval_artifact_id: str,
        approved_by: str,
        note: str,
    ) -> dict[str, Any]:
        """Promote a DRAFT figure to FINAL after an explicit human evidence decision.

        Deterministic engines (EDA, baseline, model comparison, sensitivity) always
        register figures as DRAFT so that no plot silently becomes paper evidence.
        A figure only becomes citable in an outline once a human ties it to an
        existing ``paper_ready_approval`` artifact through this method.
        """
        if not note.strip():
            raise ValueError("figure promotion requires a note")
        figure = self.get(case_id, figure_id)
        approval = self.artifacts.get(case_id, approval_artifact_id)
        if approval["artifact_type"] != "paper_ready_approval":
            raise ValueError(
                f"approval artifact is not a paper_ready_approval: {approval_artifact_id}"
            )
        if figure["status"] == "FINAL":
            return figure
        # Idempotent promotion: paper_ready.approve already promotes the
        # figure's artifact (it is part of the evidence chain), so skip the
        # duplicate registry write instead of appending a redundant record.
        artifact = self.artifacts.get(case_id, figure["artifact_id"])
        if not artifact.get("paper_eligible", False):
            self.artifacts.promote_to_paper(case_id, figure["artifact_id"], approval_artifact_id)
        promoted = {
            **figure,
            "status": "FINAL",
            "paper_ready_approval_id": approval_artifact_id,
            "approved_by": approved_by,
            "approval_note": note,
            "updated_at": now_iso(),
        }
        append_jsonl(self.registry_path(case_id), promoted)
        return promoted


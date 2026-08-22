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

    def attach_visual_review(
        self,
        case_id: str,
        figure_id: str,
        review_artifact_id: str,
        *,
        gate: str,
        reviewer: str,
        reviewer_kind: str,
    ) -> dict[str, Any]:
        """Attach a rendered-image review without changing evidence eligibility.

        Visual review is a document-quality concern, not a substitute for the
        paper-ready evidence approval used by :meth:`promote`.  The method only
        annotates the latest figure record so VisualQualityService can distinguish
        an actually inspected diagram from one that merely has clean metadata.
        """

        figure = self.get(case_id, figure_id)
        review = self.artifacts.get(case_id, review_artifact_id)
        if review.get("artifact_type") != "visual_figure_review":
            raise ValueError("visual review artifact must have type visual_figure_review")
        normalized_gate = str(gate or "").upper()
        if normalized_gate not in {"PASS", "REVISE", "REJECT"}:
            raise ValueError("visual review gate must be PASS, REVISE, or REJECT")
        parameters = dict(figure.get("parameters") or {})
        parameters.update(
            {
                "visual_review_status": normalized_gate,
                "visual_review_artifact_id": review_artifact_id,
                "visual_reviewer": reviewer,
                "visual_reviewer_kind": reviewer_kind,
            }
        )
        updated = {
            **figure,
            "parameters": parameters,
            "updated_at": now_iso(),
        }
        append_jsonl(self.registry_path(case_id), updated)
        return updated

    def promote(
        self,
        case_id: str,
        figure_id: str,
        approval_artifact_id: str,
        approved_by: str,
        note: str,
        section_id: str = "",
    ) -> dict[str, Any]:
        """Promote a DRAFT figure to FINAL after an explicit human evidence decision.

        Deterministic engines (EDA, baseline, model comparison, sensitivity) always
        register figures as DRAFT so that no plot silently becomes paper evidence.
        A figure only becomes citable in an outline once a human ties it to an
        existing ``paper_ready_approval`` artifact through this method.

        As a side-effect, every promoted figure has its ``source_artifact_ids``
        recorded as auditable ``sources[]`` entries via ``figure_tracking`` so
        that the provenance chain survives into the paper (task: wire
        figure_tracking into the promotion path).

        Args:
            section_id: optional paper section anchor for the source entries
                (default ``""``).

        Raises:
            ValueError: promotion precondition violated.
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

        # ---- wire figure_tracking: every promoted figure carries a
        # structured sources[] provenance chain. Each source_artifact_id is
        # validated against ArtifactRegistry (same check as
        # figure_tracking.attach_figure_source) and annotated with context +
        # section anchor so that check_figure_tracking sees no REVIEW
        # "FIGURE_WITHOUT_SOURCE" findings for promoted figures. -----------
        existing_sources = figure.get("sources") or []
        existing_ids = {s.get("source_artifact_id") for s in existing_sources}
        new_sources = list(existing_sources)
        source_context = figure.get("source_script", "figure pipeline")
        for source_artifact_id in figure.get("source_artifact_ids", []):
            if source_artifact_id in existing_ids:
                continue
            # validate source artifact exists (mirrors attach_figure_source)
            self.artifacts.get(case_id, source_artifact_id)
            new_sources.append(
                {
                    "source_artifact_id": source_artifact_id,
                    "context": f"provenance via {source_context}",
                    "section_id": section_id,
                    "attached_at": now_iso(),
                }
            )

        promoted = {
            **figure,
            "status": "FINAL",
            "paper_ready_approval_id": approval_artifact_id,
            "approved_by": approved_by,
            "approval_note": note,
            "sources": new_sources,
            "updated_at": now_iso(),
        }
        append_jsonl(self.registry_path(case_id), promoted)
        return promoted


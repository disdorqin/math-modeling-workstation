from __future__ import annotations

import uuid
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .io_utils import atomic_write_json, now_iso


VisualReviewGate = Literal["PASS", "REVISE", "REJECT"]
ReviewerKind = Literal["human", "vision_agent"]


class VisualReviewDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str
    score: float = Field(ge=0.0, le=100.0)
    note: str = ""


class VisualFigureReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str
    figure_id: str
    reviewer_kind: ReviewerKind
    reviewer: str
    gate: VisualReviewGate
    dimensions: list[VisualReviewDimension]
    overall_note: str = ""
    checked_at: str


class FigureVisualReviewService:
    """Persist rendered-image inspection for workflow/mechanism figures.

    A review is intentionally separate from research-evidence approval.  The
    reviewer checks whether the rendered image faithfully communicates already
    accepted semantics, is legible, has a useful hierarchy, and is aesthetically
    suitable for the destination paper.  PASS is attached to FigureRegistry so
    the visual-quality gate can close only after an actual human/vision pass.
    """

    REQUIRED_DIMENSIONS = (
        "semantic_fidelity",
        "legibility",
        "visual_hierarchy",
        "aesthetic_quality",
    )

    def __init__(self, cases: Any, artifacts: Any, figures: Any) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.figures = figures

    def review(
        self,
        case_id: str,
        figure_id: str,
        *,
        reviewer_kind: ReviewerKind,
        reviewer: str,
        scores: dict[str, float],
        notes: dict[str, str] | None = None,
        overall_note: str = "",
        source_artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        figure = self.figures.get(case_id, figure_id)
        if not reviewer.strip():
            raise ValueError("VISUAL_REVIEWER_REQUIRED")
        missing = [name for name in self.REQUIRED_DIMENSIONS if name not in scores]
        if missing:
            raise ValueError("VISUAL_REVIEW_DIMENSIONS_MISSING:" + ",".join(missing))
        dimensions = [
            VisualReviewDimension(
                dimension=name,
                score=float(scores[name]),
                note=str((notes or {}).get(name) or ""),
            )
            for name in self.REQUIRED_DIMENSIONS
        ]
        gate = _review_gate({item.dimension: item.score for item in dimensions})
        review = VisualFigureReview(
            case_id=case_id,
            figure_id=figure_id,
            reviewer_kind=reviewer_kind,
            reviewer=reviewer,
            gate=gate,
            dimensions=dimensions,
            overall_note=overall_note,
            checked_at=now_iso(),
        )
        root = self.cases.case_root(case_id)
        path = root / "review" / "visual_figures" / f"{figure_id}-{uuid.uuid4().hex[:8]}.json"
        atomic_write_json(path, review.model_dump(mode="json"))
        upstream = list(
            dict.fromkeys(
                [
                    str(figure.get("artifact_id") or ""),
                    *(source_artifact_ids or []),
                ]
            )
        )
        upstream = [value for value in upstream if value]
        artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "visual_figure_review",
            reviewer_kind,
            upstream=upstream,
            paper_eligible=False,
        )
        updated_figure = self.figures.attach_visual_review(
            case_id,
            figure_id,
            artifact["artifact_id"],
            gate=gate,
            reviewer=reviewer,
            reviewer_kind=reviewer_kind,
        )
        return {
            "review": review,
            "artifact": artifact,
            "figure": updated_figure,
        }


def _review_gate(scores: dict[str, float]) -> VisualReviewGate:
    semantic = float(scores.get("semantic_fidelity", 0.0))
    minimum = min(scores.values()) if scores else 0.0
    mean = sum(scores.values()) / len(scores) if scores else 0.0
    # Semantic correctness is a hard condition; a gorgeous but incorrect diagram
    # must never be accepted.  Other dimensions can trigger revision without
    # rejecting the underlying research.
    if semantic < 75.0:
        return "REJECT"
    if semantic >= 90.0 and minimum >= 75.0 and mean >= 82.0:
        return "PASS"
    return "REVISE"

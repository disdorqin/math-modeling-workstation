from __future__ import annotations

from pathlib import Path

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.visual_quality import VisualQualityService
from mathworkstation.visual_review import FigureVisualReviewService


def _workflow_figure(cases, artifacts, figures, case_id: str) -> dict:
    root = cases.case_root(case_id)
    path = root / "figures" / "workflow.png"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"fake-png")
    figure = figures.register(
        case_id,
        path.relative_to(root).as_posix(),
        "workflow",
        [],
        "test",
        {
            "semantic_kind": "research_workflow",
            "purpose": "Show the accepted research workflow and dependencies for the competition paper.",
            "visual_review_required": True,
            "vector_source": True,
            "dpi": 600,
            "caption_first": True,
            "editable_sources": {"svg_artifact_id": "svg", "mermaid_artifact_id": "mmd"},
        },
        None,
        status="FINAL",
    )
    return figure


def test_visual_review_pass_is_attached_to_latest_figure_record(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case_id = cases.create_case("CUMCM", "视觉审查")["case_id"]
    artifacts = ArtifactRegistry(cases)
    figures = FigureRegistry(cases, artifacts)
    figure = _workflow_figure(cases, artifacts, figures, case_id)

    result = FigureVisualReviewService(cases, artifacts, figures).review(
        case_id,
        figure["figure_id"],
        reviewer_kind="vision_agent",
        reviewer="vision-reviewer-v1",
        scores={
            "semantic_fidelity": 96,
            "legibility": 90,
            "visual_hierarchy": 88,
            "aesthetic_quality": 86,
        },
        overall_note="Readable and faithful.",
    )

    assert result["review"].gate == "PASS"
    latest = figures.get(case_id, figure["figure_id"])
    assert latest["parameters"]["visual_review_status"] == "PASS"
    assert latest["parameters"]["visual_review_artifact_id"] == result["artifact"]["artifact_id"]
    assert result["artifact"]["artifact_type"] == "visual_figure_review"


def test_semantically_wrong_but_pretty_diagram_is_rejected(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case_id = cases.create_case("CUMCM", "视觉审查")["case_id"]
    artifacts = ArtifactRegistry(cases)
    figures = FigureRegistry(cases, artifacts)
    figure = _workflow_figure(cases, artifacts, figures, case_id)

    result = FigureVisualReviewService(cases, artifacts, figures).review(
        case_id,
        figure["figure_id"],
        reviewer_kind="human",
        reviewer="reviewer",
        scores={
            "semantic_fidelity": 60,
            "legibility": 96,
            "visual_hierarchy": 95,
            "aesthetic_quality": 98,
        },
    )

    assert result["review"].gate == "REJECT"
    assert figures.get(case_id, figure["figure_id"])["parameters"]["visual_review_status"] == "REJECT"

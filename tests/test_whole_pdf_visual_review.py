from __future__ import annotations

from pathlib import Path

import fitz

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.whole_pdf_visual_review import WholePDFVisualReviewer


def _make_pdf(path: Path) -> None:
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 90), "Test paper page with enough prose for structural inspection.", fontsize=12)
    page.insert_text((72, 120), "Evidence remains unchanged; this PDF is only a rendering fixture.", fontsize=12)
    doc.save(path)
    doc.close()


def test_reviewer_renders_pages_and_keeps_vision_pending(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "workspace")
    case_id = cases.create_case("CUMCM", "PDF visual fixture")["case_id"]
    artifacts = ArtifactRegistry(cases)
    pdf_path = tmp_path / "fixture.pdf"
    _make_pdf(pdf_path)

    result = WholePDFVisualReviewer(cases, artifacts).review(case_id, pdf_path, dpi=72)
    assessment = result["assessment"]

    assert assessment.page_count == 1
    assert assessment.vision_gate == "REVIEW_PENDING"
    assert assessment.metrics[0].rendered_path.endswith("page-001.png")
    root = cases.case_root(case_id)
    assert (root / assessment.metrics[0].rendered_path).is_file()
    assert (root / assessment.contact_sheet_path).is_file()
    assert result["manifest_artifact"]["artifact_type"] == "whole_pdf_visual_review"

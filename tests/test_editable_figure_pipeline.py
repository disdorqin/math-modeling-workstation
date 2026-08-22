from __future__ import annotations

import pytest

from mathworkstation.editable_figure_pipeline import EditableFigurePipeline


def test_pipeline_requires_editable_preview_and_review_before_publication() -> None:
    pipeline = EditableFigurePipeline()
    state = pipeline.initial("case:workflow", visual_master_artifact_id="artifact-master")
    assert state.stage == "MASTER_READY"
    assert not state.publication_eligible

    state = pipeline.attach_editable(state, "artifact-pptx")
    assert state.stage == "EDITABLE_REDRAW_READY"
    assert not state.publication_eligible

    state = pipeline.attach_preview(state, "artifact-preview")
    assert state.stage == "RENDERED_PREVIEW_READY"

    state = pipeline.attach_review(state, "artifact-review", gate="PASS")
    assert state.stage == "VISION_REVIEW_PASS"
    assert state.publication_eligible


def test_pipeline_rejects_visual_review_before_rendered_preview() -> None:
    pipeline = EditableFigurePipeline()
    state = pipeline.initial("case:workflow", visual_master_artifact_id="artifact-master")
    with pytest.raises(ValueError, match="VISUAL_REVIEW_NOT_ALLOWED"):
        pipeline.attach_review(state, "artifact-review", gate="PASS")


def test_pipeline_without_master_is_explicitly_waiting() -> None:
    state = EditableFigurePipeline().initial("case:workflow")
    assert state.stage == "WAITING_FOR_VISUAL_MASTER"
    assert not state.publication_eligible

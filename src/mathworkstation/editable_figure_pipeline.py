from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .io_utils import now_iso


EditableFigureStage = Literal[
    "WAITING_FOR_VISUAL_MASTER",
    "MASTER_READY",
    "EDITABLE_REDRAW_READY",
    "RENDERED_PREVIEW_READY",
    "VISION_REVIEW_PASS",
    "VISION_REVIEW_REVISE",
    "VISION_REVIEW_REJECT",
]


class EditableFigurePipelineState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    intent_id: str
    stage: EditableFigureStage
    visual_master_artifact_id: str = ""
    editable_artifact_id: str = ""
    rendered_preview_artifact_id: str = ""
    visual_review_artifact_id: str = ""
    publication_eligible: bool = False
    guardrails: list[str] = Field(default_factory=list)
    updated_at: str


class EditableFigurePipeline:
    """Explicit promotion state machine for generative/editable paper figures."""

    def initial(self, intent_id: str, *, visual_master_artifact_id: str = "") -> EditableFigurePipelineState:
        return EditableFigurePipelineState(
            intent_id=intent_id,
            stage="MASTER_READY" if visual_master_artifact_id else "WAITING_FOR_VISUAL_MASTER",
            visual_master_artifact_id=visual_master_artifact_id,
            publication_eligible=False,
            guardrails=[
                "AI/raster visual masters are never publication-eligible by themselves.",
                "Semantic payload is the source of truth for labels, model names, numbers, and dependency arrows.",
                "Editable output requires a rendered preview before visual review.",
                "Publication requires editable output plus rendered preview plus an explicit PASS visual review.",
            ],
            updated_at=now_iso(),
        )

    def attach_master(self, state: EditableFigurePipelineState, artifact_id: str) -> EditableFigurePipelineState:
        if not artifact_id:
            raise ValueError("VISUAL_MASTER_ARTIFACT_REQUIRED")
        return state.model_copy(
            update={
                "stage": "MASTER_READY",
                "visual_master_artifact_id": artifact_id,
                "publication_eligible": False,
                "updated_at": now_iso(),
            }
        )

    def attach_editable(self, state: EditableFigurePipelineState, artifact_id: str) -> EditableFigurePipelineState:
        if state.stage not in {"MASTER_READY", "EDITABLE_REDRAW_READY", "RENDERED_PREVIEW_READY", "VISION_REVIEW_REVISE"}:
            raise ValueError(f"EDITABLE_REDRAW_NOT_ALLOWED_FROM:{state.stage}")
        if not artifact_id:
            raise ValueError("EDITABLE_ARTIFACT_REQUIRED")
        return state.model_copy(
            update={
                "stage": "EDITABLE_REDRAW_READY",
                "editable_artifact_id": artifact_id,
                "rendered_preview_artifact_id": "",
                "visual_review_artifact_id": "",
                "publication_eligible": False,
                "updated_at": now_iso(),
            }
        )

    def attach_preview(self, state: EditableFigurePipelineState, artifact_id: str) -> EditableFigurePipelineState:
        if state.stage != "EDITABLE_REDRAW_READY":
            raise ValueError(f"RENDERED_PREVIEW_NOT_ALLOWED_FROM:{state.stage}")
        if not artifact_id:
            raise ValueError("RENDERED_PREVIEW_ARTIFACT_REQUIRED")
        return state.model_copy(
            update={
                "stage": "RENDERED_PREVIEW_READY",
                "rendered_preview_artifact_id": artifact_id,
                "publication_eligible": False,
                "updated_at": now_iso(),
            }
        )

    def attach_review(
        self,
        state: EditableFigurePipelineState,
        artifact_id: str,
        *,
        gate: Literal["PASS", "REVISE", "REJECT"],
    ) -> EditableFigurePipelineState:
        if state.stage != "RENDERED_PREVIEW_READY":
            raise ValueError(f"VISUAL_REVIEW_NOT_ALLOWED_FROM:{state.stage}")
        if not artifact_id:
            raise ValueError("VISUAL_REVIEW_ARTIFACT_REQUIRED")
        stage: EditableFigureStage = {
            "PASS": "VISION_REVIEW_PASS",
            "REVISE": "VISION_REVIEW_REVISE",
            "REJECT": "VISION_REVIEW_REJECT",
        }[gate]
        return state.model_copy(
            update={
                "stage": stage,
                "visual_review_artifact_id": artifact_id,
                "publication_eligible": gate == "PASS",
                "updated_at": now_iso(),
            }
        )

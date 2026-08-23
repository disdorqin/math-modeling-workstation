from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .io_utils import now_iso
from .model_story import ModelStoryPlan


CompositionRole = Literal[
    "hero_overview",
    "primary_evidence",
    "comparative_evidence",
    "supporting_evidence",
    "context_reality",
]


class FigureComposition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    figure_id: str
    source_path: str
    semantic_kind: str
    composition_role: CompositionRole
    width_fraction: float = Field(ge=0.45, le=1.0)
    max_height_fraction: float = Field(ge=0.20, le=0.60)
    placement: str = "htbp"
    pairable: bool = False
    preferred_anchor: Literal["overview", "argument", "context"] = "argument"
    rationale: str


class SectionComposition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subproblem_id: str
    role: str
    emphasis: float = Field(ge=0.5, le=1.5)
    keep_validation_adjacent: bool = True
    avoid_page_break_after_heading: bool = True
    allow_dense_table_first: bool = False


class PageCompositionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str
    profile_id: str
    figures: list[FigureComposition]
    sections: list[SectionComposition]
    global_rules: list[str]
    generated_at: str

    def figure_for_path(self, path: str) -> FigureComposition | None:
        target = Path(path.replace("\\", "/")).name.lower()
        for item in self.figures:
            if Path(item.source_path.replace("\\", "/")).name.lower() == target:
                return item
        return None


class PaperArtDirector:
    """Choose page-level visual emphasis without imposing a fixed paper template.

    Inputs are semantic figure metadata and the accepted model story.  The output
    is a soft composition plan consumed by the typesetter.  It changes scale,
    rhythm and placement only; it cannot create figures, evidence, or claims.
    """

    def plan(
        self,
        case_id: str,
        *,
        profile_id: str,
        figures: list[dict[str, Any]],
        story: ModelStoryPlan | None = None,
    ) -> PageCompositionPlan:
        compositions = [self._figure(item) for item in figures if item.get("status") == "FINAL"]
        sections: list[SectionComposition] = []
        if story is not None:
            emphasis_by_role = {
                "FOUNDATION": 0.88,
                "CORE_MODEL": 1.18,
                "EXTENSION": 1.00,
                "INDEPENDENT_MODEL": 1.00,
                "SYNTHESIS": 0.78,
            }
            for section in story.sections:
                sections.append(
                    SectionComposition(
                        subproblem_id=section.subproblem_id,
                        role=section.role,
                        emphasis=emphasis_by_role.get(section.role, 1.0),
                        keep_validation_adjacent=True,
                        avoid_page_break_after_heading=True,
                        allow_dense_table_first=False,
                    )
                )
        return PageCompositionPlan(
            case_id=case_id,
            profile_id=profile_id,
            figures=compositions,
            sections=sections,
            global_rules=[
                "Do not give every figure the same physical footprint.",
                "Give the whole-paper workflow enough space to be read as an overview, but keep it below a full page unless its information density requires more.",
                "Keep the figure that supplies evidence for a claim near the paragraph that interprets it.",
                "Prefer one strong figure plus prose over consecutive decorative figures.",
                "Do not force a dense decision table to begin a modeling subsection; establish the model argument first.",
                "Use whitespace to separate modeling phases; do not compensate for weak hierarchy with extra colors or boxes.",
            ],
            generated_at=now_iso(),
        )

    def _figure(self, figure: dict[str, Any]) -> FigureComposition:
        params = dict(figure.get("parameters") or {})
        semantic = str(params.get("semantic_kind") or "").strip().lower()
        paper_role = str(params.get("paper_role") or "primary").strip().lower()
        path = str(figure.get("path") or "")
        figure_id = str(figure.get("figure_id") or Path(path).stem or "figure")

        if semantic == "research_workflow":
            role: CompositionRole = "hero_overview"
            width, height, anchor, pairable = 0.84, 0.30, "overview", False
            rationale = "Whole-paper roadmap: prominent enough to orient the reader while leaving room for nearby interpretation."
        elif semantic == "model_framework":
            role = "hero_overview"
            width, height, anchor, pairable = 0.88, 0.32, "overview", False
            rationale = "Mathematical architecture should remain readable but must stay attached to the prose that explains how questions inherit the shared structure."
        elif semantic in {
            "correlation_heatmap",
            "matrix_heatmap",
            "confusion_matrix",
            "cluster_map",
        }:
            role = "primary_evidence" if paper_role == "primary" else "supporting_evidence"
            width, height, anchor, pairable = 0.78, 0.40, "argument", True
            rationale = "Matrix evidence is usually readable at a moderate width and can share visual rhythm with adjacent evidence."
        elif semantic in {
            "comparison_evidence",
            "model_comparison",
            "panel_forecast_intervals",
            "retail_price_demand_relationship",
            "parameter_sensitivity_curve",
        } or "comparison" in semantic or "panel" in semantic:
            role = "comparative_evidence"
            width, height, anchor, pairable = 0.96, 0.44, "argument", False
            rationale = "Comparative/panel evidence needs horizontal room for axes, legends, or multiple series."
        elif semantic in {"context_reality", "background_reality", "context_photo"}:
            role = "context_reality"
            width, height, anchor, pairable = 0.62, 0.32, "context", True
            rationale = "Reality/context visuals support orientation and should not dominate mathematical evidence."
        else:
            role = "primary_evidence" if paper_role == "primary" else "supporting_evidence"
            width = 0.86 if role == "primary_evidence" else 0.70
            height = 0.40 if role == "primary_evidence" else 0.33
            anchor = "argument"
            pairable = role == "supporting_evidence"
            rationale = "Default evidence composition uses moderate width; supplementary figures are deliberately quieter."

        return FigureComposition(
            figure_id=figure_id,
            source_path=path,
            semantic_kind=semantic,
            composition_role=role,
            width_fraction=width,
            max_height_fraction=height,
            placement="inline",
            pairable=pairable,
            preferred_anchor=anchor,  # type: ignore[arg-type]
            rationale=rationale,
        )

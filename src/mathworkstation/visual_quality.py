from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .io_utils import atomic_write_json, now_iso


VisualStatus = Literal["PASS", "REVIEW"]


class VisualQualityDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str
    status: VisualStatus
    score: float = Field(ge=0.0, le=100.0)
    evidence: str
    gap: str = ""
    subproblem_ids: list[str] = Field(default_factory=list)


class VisualQualityAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str | None = None
    profile_id: str
    gate: VisualStatus
    score: float = Field(ge=0.0, le=100.0)
    dimensions: list[VisualQualityDimension]
    checked_at: str


_INTERNAL_VISUAL_TERMS = (
    "research state",
    "solverregistry",
    "narrativegraph",
    "evidencegraph",
    "accepted result summary",
    "metric summary fallback",
)

_EXPECTED_FAMILIES = {
    "forecasting": {"forecast_interval", "panel_forecast_intervals", "panel_trend_characterization"},
    "distribution_forecasting": {"distribution_uncertainty"},
    "classification": {"class_probabilities"},
    "explanatory_inference": {"effect_intervals", "activation_rate_comparison"},
    "exploratory_analysis": {
        "association_ranking",
        "panel_profile_heatmap",
        "member_group_profile_heatmap",
        "member_lifecycle_state_shares",
        "market_basket_rule_lift",
    },
    "optimization": {"route_layout_geometry", "optimization_targets", "optimization_solution"},
    "ranking": {"mcdm_ranking", "member_value_top_ranking"},
    "simulation": {"metric_summary_fallback"},
}


class VisualQualityService:
    """Competition-paper visual gate based on semantic evidence, not decoration."""

    def assess(
        self,
        graph: Any,
        figures: list[dict[str, Any]],
        *,
        profile_id: str,
        case_id: str | None = None,
        paper_text: str | None = None,
    ) -> VisualQualityAssessment:
        finals = [item for item in figures if item.get("status") == "FINAL"]
        dimensions = [
            self._workflow(graph, finals),
            self._question_coverage(graph, finals),
            self._semantic_diversity(graph, finals),
            self._palette_diversity(finals),
            self._argumentative_metadata(finals),
            self._caption_hygiene(finals),
            self._editable_vector_source(finals),
            self._visual_review_completion(finals),
        ]
        if paper_text is None:
            weights = {
                "global_workflow": 0.20,
                "question_figure_coverage": 0.22,
                "semantic_diversity": 0.13,
                "palette_diversity": 0.08,
                "argumentative_metadata": 0.12,
                "caption_hygiene": 0.09,
                "editable_vector_source": 0.10,
                "visual_review_completion": 0.06,
            }
        else:
            dimensions.append(self._argument_flow(paper_text, finals))
            dimensions.append(self._publication_output_quality(finals))
            weights = {
                "global_workflow": 0.13,
                "question_figure_coverage": 0.15,
                "semantic_diversity": 0.10,
                "palette_diversity": 0.08,
                "argumentative_metadata": 0.09,
                "caption_hygiene": 0.07,
                "editable_vector_source": 0.07,
                "visual_review_completion": 0.09,
                "figure_argument_flow": 0.11,
                "publication_output_quality": 0.11,
            }
        score = sum(item.score * weights[item.dimension] for item in dimensions)
        by_dimension = {item.dimension: item for item in dimensions}
        critical = [
            by_dimension["global_workflow"].status,
            by_dimension["question_figure_coverage"].status,
            by_dimension["visual_review_completion"].status,
        ]
        if paper_text is not None:
            critical.extend([dimensions[-2].status, dimensions[-1].status])
        gate: VisualStatus = "PASS" if score >= 80 and all(value == "PASS" for value in critical) else "REVIEW"
        return VisualQualityAssessment(
            case_id=case_id,
            profile_id=profile_id,
            gate=gate,
            score=round(float(score), 2),
            dimensions=dimensions,
            checked_at=now_iso(),
        )

    def persist(
        self,
        cases: Any,
        artifacts: Any,
        case_id: str,
        assessment: VisualQualityAssessment,
        *,
        source_artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        root = cases.case_root(case_id)
        path = root / "review" / "visual_quality" / "assessment.json"
        atomic_write_json(path, assessment.model_dump(mode="json"))
        artifact = artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "visual_quality_assessment",
            "visual_quality",
            upstream=list(source_artifact_ids or []),
            paper_eligible=False,
        )
        return {"assessment": assessment, "artifact": artifact}

    def _workflow(self, graph: Any, figures: list[dict[str, Any]]) -> VisualQualityDimension:
        research_count = sum(getattr(node, "role", "") == "RESEARCH" for node in graph.nodes)
        workflows = [item for item in figures if _kind(item) == "research_workflow"]
        required = research_count >= 2
        pass_gate = bool(workflows) or not required
        evidence = "not required for a single research node" if not required else f"research workflow figures = {len(workflows)}"
        return VisualQualityDimension(
            dimension="global_workflow",
            status="PASS" if pass_gate else "REVIEW",
            score=100.0 if pass_gate else 20.0,
            evidence=evidence,
            gap="" if pass_gate else "Multi-question competition papers need one actual problem-derived research/process flowchart.",
        )

    def _question_coverage(self, graph: Any, figures: list[dict[str, Any]]) -> VisualQualityDimension:
        research_nodes = [node for node in graph.nodes if getattr(node, "role", "") == "RESEARCH"]
        required = [node for node in research_nodes if getattr(node, "key_results", [])]
        owners = {
            str((item.get("parameters") or {}).get("subproblem_id"))
            for item in figures
            if (item.get("parameters") or {}).get("subproblem_id")
        }
        missing = [node.subproblem_id for node in required if node.subproblem_id not in owners]
        ratio = 1.0 if not required else (len(required) - len(missing)) / len(required)
        return VisualQualityDimension(
            dimension="question_figure_coverage",
            status="PASS" if ratio >= 0.9 else "REVIEW",
            score=100.0 * ratio,
            evidence=f"research questions with numeric evidence and a semantic figure = {len(required) - len(missing)}/{len(required)}",
            gap="" if ratio >= 0.9 else "Some evidence-bearing questions have no argumentative figure; add one only where the result semantics justify it.",
            subproblem_ids=missing,
        )

    def _semantic_diversity(self, graph: Any, figures: list[dict[str, Any]]) -> VisualQualityDimension:
        semantic = {
            _kind(item)
            for item in figures
            if _kind(item) and _kind(item) not in {"research_workflow", "context_reality"}
        }
        research_count = sum(getattr(node, "role", "") == "RESEARCH" for node in graph.nodes)
        target = min(3, max(1, research_count))
        ratio = min(1.0, len(semantic) / target)
        return VisualQualityDimension(
            dimension="semantic_diversity",
            status="PASS" if ratio >= 1.0 else "REVIEW",
            score=100.0 * ratio,
            evidence=f"distinct argumentative semantic figure kinds = {len(semantic)}; target for this paper = {target}; kinds={sorted(semantic)}",
            gap="" if ratio >= 1.0 else "The paper is visually repetitive. Prefer different evidence-matched chart families rather than adding decorative duplicates.",
        )

    def _palette_diversity(self, figures: list[dict[str, Any]]) -> VisualQualityDimension:
        data_figures = [
            item
            for item in figures
            if _kind(item) and _kind(item) not in {"research_workflow", "context_reality"}
        ]
        routed = [
            item
            for item in data_figures
            if str((item.get("parameters") or {}).get("palette_family") or "").strip()
        ]
        # Legacy/imported figures may not have gone through FigureColorDirector.
        # Do not retroactively penalize them; once a paper has enough routed figures,
        # palette repetition becomes an explicit quality signal.
        if len(routed) < 3:
            return VisualQualityDimension(
                dimension="palette_diversity",
                status="PASS",
                score=100.0,
                evidence=f"palette-routed figures = {len(routed)}; diversity gate activates at 3",
                gap="",
            )
        families = [str((item.get("parameters") or {}).get("palette_family") or "") for item in routed]
        counts = {family: families.count(family) for family in sorted(set(families))}
        distinct = len(counts)
        dominant_share = max(counts.values()) / len(families)
        pass_gate = distinct >= 2 and dominant_share <= 0.75
        score = min(100.0, 55.0 + 15.0 * distinct + max(0.0, 30.0 * (1.0 - dominant_share)))
        return VisualQualityDimension(
            dimension="palette_diversity",
            status="PASS" if pass_gate else "REVIEW",
            score=score if pass_gate else min(score, 65.0),
            evidence=f"palette families={counts}; dominant share={dominant_share:.0%}",
            gap="" if pass_gate else "Data figures are visually monochromatic across the paper; vary publication-safe palette families by figure intent rather than defaulting to one research-blue scheme.",
        )

    def _argumentative_metadata(self, figures: list[dict[str, Any]]) -> VisualQualityDimension:
        argumentative = [item for item in figures if _kind(item)]
        weak = []
        for item in argumentative:
            params = item.get("parameters") or {}
            purpose = str(params.get("purpose") or "").strip()
            if len(purpose) < 20:
                weak.append(str(item.get("figure_id") or item.get("title") or "figure"))
        ratio = 1.0 if not argumentative else (len(argumentative) - len(weak)) / len(argumentative)
        return VisualQualityDimension(
            dimension="argumentative_metadata",
            status="PASS" if ratio >= 0.9 else "REVIEW",
            score=100.0 * ratio,
            evidence=f"figures with semantic_kind + substantive purpose = {len(argumentative) - len(weak)}/{len(argumentative)}",
            gap="" if ratio >= 0.9 else "Every paper figure needs a clear argumentative purpose, not merely a plotting function.",
        )

    def _caption_hygiene(self, figures: list[dict[str, Any]]) -> VisualQualityDimension:
        contaminated = []
        for item in figures:
            text = (str(item.get("title") or "") + " " + str((item.get("parameters") or {}).get("purpose") or "")).lower()
            if any(term in text for term in _INTERNAL_VISUAL_TERMS):
                contaminated.append(str(item.get("figure_id") or item.get("title") or "figure"))
        score = max(0.0, 100.0 - 35.0 * len(contaminated))
        return VisualQualityDimension(
            dimension="caption_hygiene",
            status="PASS" if not contaminated else "REVIEW",
            score=score,
            evidence=f"internal/engineering vocabulary contaminated figures = {contaminated or 'none'}",
            gap="" if not contaminated else "Rewrite captions/purposes into competition-paper language without changing evidence.",
        )

    def _argument_flow(self, paper_text: str, figures: list[dict[str, Any]]) -> VisualQualityDimension:
        """Check that figures are introduced and interpreted in the final prose.

        This is intentionally structural rather than semantic NLP: it prevents the
        most visible layout defect—an image dropped between headings/tables/images
        with no prose bridge—without inventing any interpretation of the evidence.
        """

        lines = paper_text.splitlines()
        image_lines = [index for index, line in enumerate(lines) if line.lstrip().startswith("![")]
        weak: list[int] = []
        for index in image_lines:
            before = _nearest_content_line(lines, index, step=-1)
            after = _nearest_content_line(lines, index, step=1)
            if not _is_prose_bridge(before) or not _is_prose_bridge(after):
                weak.append(index + 1)
        ratio = 1.0 if not image_lines else (len(image_lines) - len(weak)) / len(image_lines)
        return VisualQualityDimension(
            dimension="figure_argument_flow",
            status="PASS" if ratio >= 0.9 else "REVIEW",
            score=100.0 * ratio,
            evidence=f"figures with prose lead-in and prose interpretation/transition = {len(image_lines) - len(weak)}/{len(image_lines)}; weak markdown lines={weak or 'none'}",
            gap="" if ratio >= 0.9 else "Some figures are dropped next to headings/tables/other figures without a prose lead-in and follow-up interpretation.",
        )

    def _publication_output_quality(self, figures: list[dict[str, Any]]) -> VisualQualityDimension:
        # Real-world context photos are provenance-checked raster material, not
        # deterministic scientific plots.  Requiring vector source / 600 dpi for
        # them would reward tracing a photograph instead of preserving provenance.
        evaluable = [item for item in figures if _kind(item) and _kind(item) != "context_reality"]
        weak: list[str] = []
        for item in evaluable:
            params = item.get("parameters") or {}
            dpi = int(params.get("dpi") or 0)
            vector = bool(params.get("vector_source"))
            caption_first = bool(params.get("caption_first"))
            if dpi < 600 or not vector or not caption_first:
                weak.append(str(item.get("figure_id") or item.get("title") or "figure"))
        ratio = 1.0 if not evaluable else (len(evaluable) - len(weak)) / len(evaluable)
        return VisualQualityDimension(
            dimension="publication_output_quality",
            status="PASS" if ratio >= 0.9 else "REVIEW",
            score=100.0 * ratio,
            evidence=f"600dpi + vector + caption-first figures = {len(evaluable) - len(weak)}/{len(evaluable)}; weak={weak or 'none'}",
            gap="" if ratio >= 0.9 else "Paper figures should be 600dpi, retain a vector source, and avoid duplicating the paper caption as an in-plot title.",
        )

    def _visual_review_completion(self, figures: list[dict[str, Any]]) -> VisualQualityDimension:
        """Do not confuse metadata cleanliness with actual visual inspection.

        Diagram-generation research systems render and inspect the produced image
        before accepting it.  Any figure that declares ``visual_review_required``
        therefore remains REVIEW until an external vision agent or human records a
        PASS in figure metadata. Deterministic numeric plots do not need this extra
        gate unless they explicitly opt in.
        """

        required = [
            item
            for item in figures
            if bool((item.get("parameters") or {}).get("visual_review_required"))
        ]
        pending = []
        for item in required:
            params = item.get("parameters") or {}
            status = str(params.get("visual_review_status") or "").upper()
            artifact_id = str(params.get("visual_review_artifact_id") or "").strip()
            if status != "PASS" or not artifact_id:
                pending.append(str(item.get("figure_id") or item.get("title") or "figure"))
        ratio = 1.0 if not required else (len(required) - len(pending)) / len(required)
        return VisualQualityDimension(
            dimension="visual_review_completion",
            status="PASS" if not pending else "REVIEW",
            score=100.0 * ratio,
            evidence=f"figures requiring rendered-image review passed = {len(required) - len(pending)}/{len(required)}; pending={pending or 'none'}",
            gap="" if not pending else "At least one explanatory diagram still needs rendered-image inspection (vision agent or human) before aesthetic quality can be claimed PASS.",
        )

    def _editable_vector_source(self, figures: list[dict[str, Any]]) -> VisualQualityDimension:
        workflow = next((item for item in figures if _kind(item) == "research_workflow"), None)
        if workflow is None:
            return VisualQualityDimension(
                dimension="editable_vector_source",
                status="REVIEW",
                score=20.0,
                evidence="no research workflow figure",
                gap="Flowchart should have an editable/vector source (SVG plus Mermaid/DOT) before final layout work.",
            )
        params = workflow.get("parameters") or {}
        editable = params.get("editable_sources") or {}
        vector = bool(params.get("vector_source")) and bool(editable.get("svg_artifact_id")) and bool(editable.get("mermaid_artifact_id"))
        return VisualQualityDimension(
            dimension="editable_vector_source",
            status="PASS" if vector else "REVIEW",
            score=100.0 if vector else 45.0,
            evidence=f"workflow vector/editable source complete = {vector}",
            gap="" if vector else "Keep SVG and an editable diagram source so flowchart styling can be refined without raster tracing.",
        )


def _nearest_content_line(lines: list[str], index: int, *, step: int) -> str:
    cursor = index + step
    while 0 <= cursor < len(lines):
        value = lines[cursor].strip()
        if value:
            return value
        cursor += step
    return ""


def _is_prose_bridge(value: str) -> bool:
    if not value:
        return False
    stripped = value.lstrip()
    if stripped.startswith(("#", "|", "![", "```", "$$", "- **")):
        return False
    return len(stripped) >= 12


def _kind(figure: dict[str, Any]) -> str:
    return str((figure.get("parameters") or {}).get("semantic_kind") or "")

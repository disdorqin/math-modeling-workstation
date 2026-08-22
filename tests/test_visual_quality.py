from __future__ import annotations

from mathworkstation.io_utils import now_iso
from mathworkstation.narrative_graph import NarrativeGraph, NarrativeNode, NarrativeResult
from mathworkstation.visual_quality import VisualQualityService


def _graph() -> NarrativeGraph:
    result = NarrativeResult(metric="objective_value", value=12.3, direction="DESCRIPTIVE")
    return NarrativeGraph(
        case_id="fixture",
        gate="PASS",
        research_gate="PASS",
        model_graph_gate="PASS",
        evidence_graph_gate="PASS",
        storyline=["Q1 -> Q2"],
        nodes=[
            NarrativeNode(
                subproblem_id="SP1", title="数据画像", role="RESEARCH", task_family="exploratory_analysis",
                objective="分析特征", method="member group profile", answer="得到画像", limitation="观察期内",
                key_results=[result], gate="PASS",
            ),
            NarrativeNode(
                subproblem_id="SP2", title="优化决策", role="RESEARCH", task_family="optimization",
                objective="求最优方案", dependencies=["SP1"], method="linear programming", answer="得到方案", limitation="约束内",
                key_results=[result], gate="PASS",
            ),
        ],
        generated_at=now_iso(),
    )


def _figure(kind: str, *, owner: str | None = None, vector: bool = False) -> dict:
    parameters = {
        "semantic_kind": kind,
        "purpose": "This figure directly visualizes evidence used to support the corresponding question conclusion.",
        "dpi": 600,
        "vector_source": True,
        "caption_first": True,
    }
    if owner:
        parameters["subproblem_id"] = owner
    if vector:
        parameters["vector_source"] = True
        parameters["editable_sources"] = {
            "svg_artifact_id": "a-svg",
            "mermaid_artifact_id": "a-mmd",
            "dot_artifact_id": "a-dot",
        }
    return {"figure_id": f"fig-{kind}-{owner or 'global'}", "status": "FINAL", "title": kind.replace("_", " "), "parameters": parameters}


def test_visual_quality_passes_problem_derived_workflow_and_question_figures() -> None:
    figures = [
        _figure("research_workflow", vector=True),
        _figure("member_group_profile_heatmap", owner="SP1"),
        _figure("optimization_solution", owner="SP2"),
    ]
    assessment = VisualQualityService().assess(_graph(), figures, profile_id="CUMCM_C")

    assert assessment.gate == "PASS"
    assert assessment.score >= 80
    dims = {item.dimension: item for item in assessment.dimensions}
    assert dims["global_workflow"].status == "PASS"
    assert dims["question_figure_coverage"].status == "PASS"
    assert dims["editable_vector_source"].status == "PASS"


def test_visual_quality_checks_final_figure_argument_flow_when_paper_text_is_available() -> None:
    figures = [
        _figure("research_workflow", vector=True),
        _figure("member_group_profile_heatmap", owner="SP1"),
        _figure("optimization_solution", owner="SP2"),
    ]
    good = """引导研究路线如下，并据此安排后续各问。\n\n![图1](workflow.png)\n\n该路线决定各问的依赖与展开顺序。\n\n先观察消费画像的整体结构。\n\n![图2](profile.png)\n\n图中结构为后续评价模型提供数据依据。\n\n再展示最终决策的整体差异。\n\n![图3](decision.png)\n\n该图与下方精确方案共同支撑最终结论。"""
    assessment = VisualQualityService().assess(_graph(), figures, profile_id="CUMCM_C", paper_text=good)
    dims = {item.dimension: item for item in assessment.dimensions}
    assert dims["figure_argument_flow"].status == "PASS"

    bad = """# 结果\n\n![图1](workflow.png)\n\n![图2](profile.png)\n\n# 下一节\n\n![图3](decision.png)"""
    assessment = VisualQualityService().assess(_graph(), figures, profile_id="CUMCM_C", paper_text=bad)
    dims = {item.dimension: item for item in assessment.dimensions}
    assert dims["figure_argument_flow"].status == "REVIEW"
    assert assessment.gate == "REVIEW"


def test_visual_quality_keeps_explanatory_diagram_pending_until_rendered_image_review() -> None:
    figures = [
        _figure("research_workflow", vector=True),
        _figure("member_group_profile_heatmap", owner="SP1"),
        _figure("optimization_solution", owner="SP2"),
    ]
    figures[0]["parameters"]["visual_review_required"] = True
    pending = VisualQualityService().assess(_graph(), figures, profile_id="CUMCM_C")
    dims = {item.dimension: item for item in pending.dimensions}
    assert dims["visual_review_completion"].status == "REVIEW"
    assert pending.gate == "REVIEW"

    figures[0]["parameters"]["visual_review_status"] = "PASS"
    figures[0]["parameters"]["visual_review_artifact_id"] = "artifact-vision-review"
    reviewed = VisualQualityService().assess(_graph(), figures, profile_id="CUMCM_C")
    dims = {item.dimension: item for item in reviewed.dimensions}
    assert dims["visual_review_completion"].status == "PASS"
    assert reviewed.gate == "PASS"


def test_visual_quality_detects_monochromatic_routed_data_figures() -> None:
    figures = [
        _figure("research_workflow", vector=True),
        _figure("member_group_profile_heatmap", owner="SP1"),
        _figure("optimization_solution", owner="SP2"),
        _figure("parameter_sensitivity_curve", owner="SP2"),
    ]
    for item in figures[1:]:
        item["parameters"]["palette_family"] = "research_blue"
    assessment = VisualQualityService().assess(_graph(), figures, profile_id="CUMCM_C")
    dims = {item.dimension: item for item in assessment.dimensions}

    assert dims["palette_diversity"].status == "REVIEW"
    assert "research_blue" in dims["palette_diversity"].evidence


def test_visual_quality_reviews_fixed_or_missing_visual_evidence() -> None:
    figures = [
        {
            "figure_id": "bad",
            "status": "FINAL",
            "title": "accepted Research State metric summary fallback",
            "parameters": {"semantic_kind": "metric_summary_fallback", "purpose": "short"},
        }
    ]
    assessment = VisualQualityService().assess(_graph(), figures, profile_id="CUMCM_C")

    assert assessment.gate == "REVIEW"
    dims = {item.dimension: item for item in assessment.dimensions}
    assert dims["global_workflow"].status == "REVIEW"
    assert dims["question_figure_coverage"].subproblem_ids == ["SP1", "SP2"]
    assert dims["caption_hygiene"].status == "REVIEW"

from __future__ import annotations

from pathlib import Path

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.io_utils import atomic_write_json, now_iso
from mathworkstation.model_spine import ModelSpinePlanner
from mathworkstation.narrative_graph import NarrativeGraph, NarrativeNode
from mathworkstation.research_flowchart import ResearchFlowchartRenderer


def _graph() -> NarrativeGraph:
    return NarrativeGraph(
        case_id="fixture",
        gate="PASS",
        research_gate="PASS",
        model_graph_gate="PASS",
        evidence_graph_gate="PASS",
        storyline=["profile -> optimization -> strategy"],
        nodes=[
            NarrativeNode(
                subproblem_id="SP1",
                title="刻画会员消费特征",
                role="RESEARCH",
                task_family="exploratory_analysis",
                objective="比较会员与非会员群体的消费差异",
                method="member group profile",
                answer="会员消费画像已形成。",
                limitation="仅适用于登记观察期。",
                gate="PASS",
            ),
            NarrativeNode(
                subproblem_id="SP2",
                title="识别会员价值",
                role="RESEARCH",
                task_family="ranking",
                objective="构建每位会员的价值评分",
                dependencies=["SP1"],
                method="RFM member value",
                answer="得到会员价值排序。",
                limitation="权重解释受观察窗口影响。",
                validation_protocol_id="ranking.leave-one-dimension-out.v1",
                validation_gate="PASS",
                gate="PASS",
            ),
            NarrativeNode(
                subproblem_id="SP3",
                title="形成营销策略",
                role="SYNTHESIS",
                task_family="synthesis",
                objective="综合前序结果形成可执行策略",
                dependencies=["SP1", "SP2"],
                method="evidence synthesis",
                answer="形成差异化营销策略。",
                limitation="策略仅综合已登记证据。",
                gate="PASS",
            ),
        ],
        generated_at=now_iso(),
    )


def test_research_flowchart_uses_actual_graph_and_emits_editable_sources(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    manifest = cases.create_case("CUMCM", "会员画像", "zh")
    case_id = manifest["case_id"]
    artifacts = ArtifactRegistry(cases)
    figures = FigureRegistry(cases, artifacts)
    root = cases.case_root(case_id)
    source = root / "analysis" / "narrative-fixture.json"
    atomic_write_json(source, {"fixture": True})
    source_artifact = artifacts.register_existing(
        case_id,
        source.relative_to(root).as_posix(),
        "narrative_graph",
        "test",
    )

    graph = _graph()
    rendered = ResearchFlowchartRenderer(cases, artifacts, figures).render(
        case_id,
        graph,
        profile_id="CUMCM_C",
        upstream_artifact_ids=[source_artifact["artifact_id"]],
        model_spine=ModelSpinePlanner().plan(graph),
    )

    figure = rendered["figure"]
    assert figure["status"] == "FINAL"
    assert figure["parameters"]["semantic_kind"] == "research_workflow"
    assert figure["parameters"]["vector_source"] is True
    assert rendered["backend"] == "matplotlib_model_spine_v1"
    assert rendered["visual_plan"].primary_backend == "deterministic_vector"
    assert rendered["visual_plan"].visual_review_required is True
    assert rendered["visual_brief_artifact"]["artifact_type"] == "visual_design_brief"
    assert rendered["ppt_mcp_handoff_artifact"]["artifact_type"] == "ppt_mcp_figure_handoff"

    visual_brief = (root / rendered["visual_brief_artifact"]["path"]).read_text(encoding="utf-8")
    ppt_handoff = (root / rendered["ppt_mcp_handoff_artifact"]["path"]).read_text(encoding="utf-8")
    assert '"research_questions"' in visual_brief
    assert '"nodes"' not in visual_brief
    assert "识别会员价值" in visual_brief
    assert "Infer layout" in ppt_handoff

    mermaid = (root / rendered["mermaid_artifact"]["path"]).read_text(encoding="utf-8")
    dot = (root / rendered["dot_artifact"]["path"]).read_text(encoding="utf-8")
    assert "刻画会员消费特征" in mermaid
    assert "识别会员价值" in mermaid
    assert "decision_SP1 -.->|承接上问| analysis_SP2" in mermaid
    assert "赛题数据与业务约束" in mermaid
    assert "检验：" in mermaid
    assert "数据—分析—模型—验证—决策" not in mermaid  # title belongs to the caption, not a decorative node
    assert '"decision_SP1" -> "analysis_SP2" [style=dashed' in dot
    assert "rank=same" in dot
    assert (root / rendered["svg_artifact"]["path"]).stat().st_size > 200
    assert (root / figure["path"]).stat().st_size > 200
    handoff = (root / rendered["ppt_mcp_handoff_artifact"]["path"]).read_text(encoding="utf-8")
    assert '"modeling_role"' in handoff
    assert '"paper_emphasis"' in handoff
    assert "CORE_MODEL" in handoff or "FOUNDATION" in handoff


def test_flowchart_spec_changes_with_problem_structure(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    artifacts = ArtifactRegistry(cases)
    figures = FigureRegistry(cases, artifacts)
    renderer = ResearchFlowchartRenderer(cases, artifacts, figures)
    spec = renderer.build_spec(_graph(), profile_id="MCM_C")

    assert spec.profile_id == "MCM_C"
    assert spec.direction == "TB"
    assert {node.stage for node in spec.nodes} == {"DATA", "ANALYSIS", "MODEL", "VALIDATION", "DECISION"}
    assert {edge.source + ">" + edge.target for edge in spec.edges} >= {
        "data>analysis_SP1",
        "analysis_SP2>model_SP2",
        "model_SP2>validation_SP2",
        "validation_SP2>decision_SP2",
        "decision_SP1>analysis_SP2",
        "decision_SP1>synthesis_SP3",
        "decision_SP2>synthesis_SP3",
    }
    sp2_model = next(node for node in spec.nodes if node.node_id == "model_SP2")
    sp2_validation = next(node for node in spec.nodes if node.node_id == "validation_SP2")
    assert "RFM" in sp2_model.label
    assert "Validation:" in sp2_validation.label
    dependency = next(edge for edge in spec.edges if edge.source == "decision_SP1" and edge.target == "analysis_SP2")
    assert dependency.kind == "DEPENDENCY"

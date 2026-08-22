from __future__ import annotations

from mathworkstation.io_utils import now_iso
from mathworkstation.model_spine import ModelSpinePlanner
from mathworkstation.model_story import ModelStoryPlanner, extract_solver_story_evidence
from mathworkstation.narrative_graph import NarrativeGraph, NarrativeNode


def _graph() -> NarrativeGraph:
    return NarrativeGraph(
        case_id="story-fixture",
        gate="PASS",
        research_gate="PASS",
        model_graph_gate="PASS",
        evidence_graph_gate="PASS",
        storyline=["SP1", "SP2", "SP3", "SP4"],
        nodes=[
            NarrativeNode(
                subproblem_id="SP1",
                title="结构探索",
                role="RESEARCH",
                task_family="exploratory_analysis",
                objective="识别数据结构与关联规律，为后续模型提供依据",
                method="spearman_iqr_mean_shift_scan",
                answer="得到结构证据",
                limitation="描述性证据",
                validation_gate="PASS",
                validation_protocol_id="exploration.v1",
                source_artifact_ids=["a1"],
                gate="PASS",
            ),
            NarrativeNode(
                subproblem_id="SP2",
                title="需求响应与联合优化",
                role="RESEARCH",
                task_family="optimization",
                objective="建立可验证的需求关系并联合优化决策",
                dependencies=["SP1"],
                method="pricing_replenishment",
                answer="得到核心策略",
                limitation="支持域内有效",
                validation_gate="PASS",
                validation_protocol_id="optimization.v1",
                source_artifact_ids=["solver-sp2"],
                gate="PASS",
            ),
            NarrativeNode(
                subproblem_id="SP3",
                title="约束下的单体决策",
                role="RESEARCH",
                task_family="optimization",
                objective="在前问模型基础上加入数量约束形成单体决策",
                dependencies=["SP2"],
                method="item_pricing_replenishment",
                answer="得到约束方案",
                limitation="受可售集合约束",
                validation_gate="PASS",
                validation_protocol_id="optimization.v1",
                source_artifact_ids=["solver-sp3"],
                gate="PASS",
            ),
            NarrativeNode(
                subproblem_id="SP4",
                title="综合建议",
                role="SYNTHESIS",
                task_family="synthesis",
                objective="综合前序结果形成建议",
                dependencies=["SP1", "SP2", "SP3"],
                method="evidence synthesis",
                answer="形成建议",
                limitation="不新增数值",
                source_artifact_ids=["syn"],
                gate="PASS",
            ),
        ],
        generated_at=now_iso(),
    )


def test_story_extracts_simple_to_richer_solver_trace_without_inventing_results() -> None:
    payload = {
        "result": {
            "protocol": {
                "method": "chronological_simple_to_richer",
                "candidate_feature_order": ["simple", "linear", "quadratic"],
                "complexity_upgrade_min_relative_improvement": 0.01,
                "feature_variants_selected": {
                    "A": "simple",
                    "B": "linear",
                    "C": "simple",
                },
            }
        }
    }
    evidence = extract_solver_story_evidence(payload, artifact_id="solver-sp2")

    assert evidence is not None
    assert evidence.simple_candidate == "simple"
    assert evidence.richer_candidates == ["linear", "quadratic"]
    assert evidence.richer_selected is True
    assert evidence.upgrade_threshold == 0.01
    assert evidence.source_artifact_ids == ["solver-sp2"]


def test_story_plan_uses_burden_of_proof_before_complexity_upgrade() -> None:
    graph = _graph()
    spine = ModelSpinePlanner().plan(graph)
    evidence = extract_solver_story_evidence(
        {
            "result": {
                "protocol": {
                    "candidate_feature_order": ["simple", "linear", "quadratic"],
                    "complexity_upgrade_min_relative_improvement": 0.01,
                    "feature_variants_selected": {
                        "A": "simple",
                        "B": "linear",
                        "C": "simple",
                    },
                }
            }
        },
        artifact_id="solver-sp2",
    )
    assert evidence is not None

    plan = ModelStoryPlanner().plan(graph, spine, solver_evidence={"SP2": evidence})
    kinds = [move.kind for move in plan.section("SP2").moves]

    assert kinds.index("SIMPLE_RELATION") < kinds.index("INSUFFICIENCY_EVIDENCE")
    assert kinds.index("INSUFFICIENCY_EVIDENCE") < kinds.index("NECESSARY_CORRECTION")
    assert kinds.index("NECESSARY_CORRECTION") < kinds.index("CORE_MODEL")
    gap = next(move for move in plan.section("SP2").moves if move.kind == "INSUFFICIENCY_EVIDENCE")
    assert gap.burden_of_proof_required is True
    assert gap.burden_of_proof_satisfied is True
    assert "1.0%" in gap.directive_zh


def test_story_plan_does_not_fabricate_gap_or_correction_without_solver_evidence() -> None:
    graph = _graph()
    spine = ModelSpinePlanner().plan(graph)

    plan = ModelStoryPlanner().plan(graph, spine)
    kinds = [move.kind for move in plan.section("SP2").moves]

    assert "INSUFFICIENCY_EVIDENCE" not in kinds
    assert "NECESSARY_CORRECTION" not in kinds
    assert "CORE_MODEL" in kinds


def test_extension_inherits_before_new_layer_and_does_not_repeat_full_derivation() -> None:
    graph = _graph()
    spine = ModelSpinePlanner().plan(graph)
    plan = ModelStoryPlanner().plan(graph, spine)

    section = plan.section("SP3")
    kinds = [move.kind for move in section.moves]

    assert section.repeat_full_derivation is False
    assert section.inherits_from == ["SP2"]
    assert kinds.index("INHERITED_RESULT") < kinds.index("EXTENSION")
    assert kinds.index("EXTENSION") < kinds.index("VALIDATION")
    assert spine.node("SP3").role == "EXTENSION"


def test_synthesis_has_no_model_building_move() -> None:
    graph = _graph()
    spine = ModelSpinePlanner().plan(graph)
    plan = ModelStoryPlanner().plan(graph, spine)
    kinds = [move.kind for move in plan.section("SP4").moves]

    assert "CORE_MODEL" not in kinds
    assert "EXTENSION" not in kinds
    assert kinds[-1] == "DECISION"

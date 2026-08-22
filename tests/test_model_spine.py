from __future__ import annotations

from mathworkstation.io_utils import now_iso
from mathworkstation.model_spine import ModelSpinePlanner
from mathworkstation.narrative_graph import NarrativeGraph, NarrativeNode
from mathworkstation.paper_model_equations import select_equations_for_paper


def _retail_graph() -> NarrativeGraph:
    return NarrativeGraph(
        case_id="fixture",
        gate="PASS",
        research_gate="PASS",
        model_graph_gate="PASS",
        evidence_graph_gate="PASS",
        storyline=["SP1", "SP2", "SP3", "SP4"],
        nodes=[
            NarrativeNode(
                subproblem_id="SP1",
                title="销售分布与关联规律探索",
                role="RESEARCH",
                task_family="exploratory_analysis",
                objective="识别分布、异常和关联规律，为后续定价模型提供依据",
                method="spearman_iqr_mean_shift_scan",
                answer="得到结构证据",
                limitation="描述性证据",
                gate="PASS",
            ),
            NarrativeNode(
                subproblem_id="SP2",
                title="品类级需求响应与定价补货",
                role="RESEARCH",
                task_family="optimization",
                objective="建立价格需求关系并联合优化定价与补货",
                dependencies=["SP1"],
                method="retail_category_pricing_replenishment",
                answer="得到品类方案",
                limitation="历史支持域内",
                gate="PASS",
            ),
            NarrativeNode(
                subproblem_id="SP3",
                title="单品级可售组合与约束优化",
                role="RESEARCH",
                task_family="optimization",
                objective="继承品类需求与价格，在单品数量和最小陈列量约束下形成方案",
                dependencies=["SP2"],
                method="retail_item_pricing_replenishment",
                answer="得到单品方案",
                limitation="受约束经营基线",
                gate="PASS",
            ),
            NarrativeNode(
                subproblem_id="SP4",
                title="经营建议",
                role="SYNTHESIS",
                task_family="synthesis",
                objective="综合前三问",
                dependencies=["SP1", "SP2", "SP3"],
                method="evidence synthesis",
                answer="形成建议",
                limitation="不新增数值",
                gate="PASS",
            ),
        ],
        generated_at=now_iso(),
    )


def test_model_spine_infers_foundation_core_extension_without_question_index_rules() -> None:
    spine = ModelSpinePlanner().plan(_retail_graph())

    assert spine.core_subproblem_ids == ["SP2"]
    assert spine.node("SP1").role == "FOUNDATION"
    assert spine.node("SP2").role == "CORE_MODEL"
    assert spine.node("SP3").role == "EXTENSION"
    assert spine.node("SP3").inherits_from == ["SP2"]
    assert spine.node("SP3").inheritance_kind in {"MODEL", "CONSTRAINT"}
    assert spine.node("SP4").role == "SYNTHESIS"
    assert spine.node("SP2").equation_budget > spine.node("SP1").equation_budget


def test_model_spine_selects_core_from_structure_not_fixed_sp2() -> None:
    graph = _retail_graph()
    # Move the substantive core model to SP1 and make SP2 an exploratory child.
    core = graph.nodes[0]
    core.task_family = "optimization"
    core.title = "联合优化核心模型"
    core.objective = "建立核心优化模型并向后续问题提供决策变量"
    core.method = "linear_programming"
    graph.nodes[1].task_family = "exploratory_analysis"
    graph.nodes[1].method = "spearman_iqr_mean_shift_scan"
    graph.nodes[1].dependencies = ["SP1"]
    graph.nodes[2].dependencies = ["SP1"]

    spine = ModelSpinePlanner().plan(graph)

    assert "SP1" in spine.core_subproblem_ids
    assert spine.node("SP1").role == "CORE_MODEL"
    assert spine.node("SP3").role == "EXTENSION"


def test_formula_budget_hides_routine_estimator_equations_but_keeps_model_core() -> None:
    equations = select_equations_for_paper("retail_category_pricing_replenishment", budget=3)
    labels = {item.label for item in equations}

    assert len(equations) == 3
    assert "Category demand-response candidates" in labels
    assert "Expected profit under markup decision" in labels
    assert "Ridge estimation and candidate selection" not in labels

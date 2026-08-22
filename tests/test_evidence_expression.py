from mathworkstation.cumcm_2023_gate import cumcm_2023_c_contracts, link_cumcm_2023_c_dependencies
from mathworkstation.evidence_expression import EvidenceExpressionPlanner
from mathworkstation.mcm2024_gate import mcm2024_c_contracts, link_mcm2024_c_dependencies
from mathworkstation.model_structure import ModelStructurePlanner
from mathworkstation.problem_graph import ProblemGraphBuilder
from mathworkstation.research_preferences import ResearchPreferenceProfile


def _award_preferences():
    return ResearchPreferenceProfile(
        preferred_modeling_styles=["probabilistic_graphical", "hybrid"],
        priorities=["mathematical_structure", "logical_rigor", "mechanism_depth", "robustness", "visual_storytelling"],
        paper_style="balanced",
        visual_density="adaptive",
        unified_framework_preferred=True,
        predictive_accuracy_is_primary=False,
        human_loop_mode="OFF",
    )


def test_mcm_expression_plan_requires_workflow_framework_equations_and_structural_visuals_without_count_quota():
    graph = link_mcm2024_c_dependencies(ProblemGraphBuilder().build(mcm2024_c_contracts()))
    preferences = _award_preferences()
    structures = {node.subproblem_id: ModelStructurePlanner().plan_node(node, graph, preferences) for node in graph.nodes}
    framework = ModelStructurePlanner().plan_graph(graph, preferences)
    plan = EvidenceExpressionPlanner().plan_paper(structures, framework, preferences)

    global_kinds = {need.semantic_kind for need in plan.global_needs}
    assert "research_workflow" in global_kinds
    assert "model_framework" in global_kinds
    sp2 = plan.subproblem_plans["SP2"]
    media = {need.medium for need in sp2.needs}
    kinds = {need.semantic_kind for need in sp2.needs}
    assert "EQUATION" in media
    assert "FIGURE" in media
    assert "state_structure" in kinds
    assert any("no target number" in rule.lower() for rule in sp2.anti_quota_rules)
    assert any("naked scalars" in rule.lower() for rule in sp2.selection_rules)


def test_optimization_expression_plan_prefers_exact_decision_table_and_robustness_figure():
    graph = link_cumcm_2023_c_dependencies(ProblemGraphBuilder().build(cumcm_2023_c_contracts()))
    structure = ModelStructurePlanner().plan_node(graph.node("SP2"), graph)
    plan = EvidenceExpressionPlanner().plan_node(structure)

    assert any(need.medium == "TABLE" and need.semantic_kind == "decision_table" for need in plan.needs)
    assert any(need.medium == "FIGURE" and need.semantic_kind == "sensitivity" for need in plan.needs)
    assert any(need.medium == "EQUATION" and need.semantic_kind == "objective_function" for need in plan.needs)
    assert any(need.medium == "EQUATION" and need.semantic_kind == "constraint_system" for need in plan.needs)

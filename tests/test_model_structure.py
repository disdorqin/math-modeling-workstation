from mathworkstation.cumcm_2023_gate import cumcm_2023_c_contracts, link_cumcm_2023_c_dependencies
from mathworkstation.mcm2024_gate import mcm2024_c_contracts, link_mcm2024_c_dependencies
from mathworkstation.model_structure import ModelStructurePlanner
from mathworkstation.problem_graph import ProblemGraphBuilder
from mathworkstation.research_preferences import ResearchPreferenceProfile


def test_2024_mcm_builds_unified_dynamic_probabilistic_structure_without_algorithm_quota():
    graph = link_mcm2024_c_dependencies(ProblemGraphBuilder().build(mcm2024_c_contracts()))
    planner = ModelStructurePlanner()
    preferences = ResearchPreferenceProfile(
        preferred_modeling_styles=["probabilistic_graphical", "hybrid"],
        priorities=["mathematical_structure", "logical_rigor", "mechanism_depth", "robustness"],
        paper_style="balanced",
        unified_framework_preferred=True,
        predictive_accuracy_is_primary=False,
        human_loop_mode="OFF",
    )
    framework = planner.plan_graph(graph, preferences)
    sp2 = planner.plan_node(graph.node("SP2"), graph, preferences)

    assert framework.node_roles["SP1"] == "FOUNDATION"
    assert framework.node_roles["SP2"] == "CORE_MODEL"
    assert framework.node_roles["SP3"] == "EXTENSION"
    assert "dynamic_state" in sp2.archetypes
    assert "probabilistic_state" in sp2.archetypes
    assert any("P(y_t" in relation for relation in sp2.core_relations)
    assert any("state transition" in role for role in sp2.equation_roles)
    assert any("graphical model" in role for role in sp2.visual_roles)
    assert "Random Forest" not in " ".join(sp2.core_relations + sp2.equation_roles + sp2.visual_roles)


def test_cumcm_optimization_structure_requires_decisions_constraints_and_robustness():
    graph = link_cumcm_2023_c_dependencies(ProblemGraphBuilder().build(cumcm_2023_c_contracts()))
    planner = ModelStructurePlanner()
    framework = planner.plan_graph(graph)
    sp1 = planner.plan_node(graph.node("SP1"), graph)
    sp2 = planner.plan_node(graph.node("SP2"), graph)
    sp3 = planner.plan_node(graph.node("SP3"), graph)

    assert "optimization" not in sp1.archetypes
    assert not sp1.decision_variables
    assert "optimization" in sp2.archetypes
    assert framework.node_roles["SP2"] == "CORE_MODEL"
    assert framework.node_roles["SP3"] == "EXTENSION"
    assert "optimization" in sp2.archetypes
    assert sp2.decision_variables
    assert any("feasibility" in item.lower() for item in sp2.constraints)
    assert any("sensitivity" in item.lower() or "robust" in item.lower() for item in sp2.validation_requirements)
    assert sp3.inherited_structure
    assert any("extend" in item.lower() for item in sp3.new_structure)


def test_deliverable_does_not_invent_new_model():
    graph = link_cumcm_2023_c_dependencies(ProblemGraphBuilder().build(cumcm_2023_c_contracts()))
    plan = ModelStructurePlanner().plan_node(graph.node("SP4"), graph)

    assert plan.framework_role == "SYNTHESIS"
    assert any("no new model" in item.lower() for item in plan.new_structure)

from types import SimpleNamespace

from mathworkstation.cumcm_2010_gate import cumcm_2010_c_contracts, link_cumcm_2010_c_dependencies
from mathworkstation.problem_graph import ProblemGraphBuilder
from mathworkstation.semantic_alternative_compatibility import SemanticAlternativeCompatibility


def test_continuous_geometry_does_not_treat_generic_lp_as_like_for_like_alternative() -> None:
    graph = link_cumcm_2010_c_dependencies(ProblemGraphBuilder().build(cumcm_2010_c_contracts()))
    node = graph.node("SP2")
    gate = SemanticAlternativeCompatibility()

    generic_lp = gate.assess(
        node,
        "linear programming",
        accepted_method="pipeline layout continuous optimization",
    )
    geometric = gate.assess(
        node,
        "pipeline geometry optimization",
        accepted_method="pipeline layout continuous optimization",
    )

    assert generic_lp.comparable is False
    assert generic_lp.representation_compatible is False
    assert generic_lp.constraint_compatible is False
    assert geometric.comparable is True


def test_same_family_time_series_methods_are_protocol_comparable() -> None:
    node = SimpleNamespace(
        task_family="forecasting",
        title="Future demand forecast",
        objective="forecast next-period demand from chronological observations",
        inputs=["date", "historical demand"],
        outputs=["future demand"],
        constraints=["preserve temporal order"],
        plan=SimpleNamespace(selected_method="holt exponential smoothing"),
    )
    gate = SemanticAlternativeCompatibility()

    ridge = gate.assess(node, "ridge time trend", accepted_method="holt exponential smoothing")
    classifier = gate.assess(node, "logistic regression", accepted_method="holt exponential smoothing")

    assert ridge.comparable is True
    assert ridge.input_compatible is True
    assert ridge.protocol_comparable is True
    assert classifier.comparable is False
    assert classifier.input_compatible is False
    assert classifier.protocol_comparable is False

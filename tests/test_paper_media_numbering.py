from types import SimpleNamespace

from mathworkstation.io_utils import now_iso
from mathworkstation.narrative_graph import NarrativeGraph, NarrativeNode
from mathworkstation.research_state_paper import _question_media_numbers


def test_media_numbering_follows_argument_order_not_registry_order() -> None:
    node = NarrativeNode(
        subproblem_id="SP1",
        title="Core model",
        role="RESEARCH",
        task_family="optimization",
        objective="Build and validate a decision model",
        method="fixture",
        answer="done",
        limitation="fixture",
        gate="PASS",
    )
    graph = NarrativeGraph(
        case_id="fixture",
        gate="PASS",
        research_gate="PASS",
        model_graph_gate="PASS",
        evidence_graph_gate="PASS",
        nodes=[node],
        storyline=["SP1"],
        generated_at=now_iso(),
    )
    # Registry order deliberately puts the decision figure before the mechanism
    # figure.  The argument planner must render the mechanism first.
    decision = {
        "figure_id": "decision",
        "status": "FINAL",
        "parameters": {"semantic_kind": "retail_category_replenishment_plan", "paper_role": "primary"},
    }
    mechanism = {
        "figure_id": "mechanism",
        "status": "FINAL",
        "parameters": {"semantic_kind": "retail_price_demand_relationship", "paper_role": "primary"},
    }
    decision_table = SimpleNamespace(
        table_id="decision-table",
        metadata={"table_role": "decision_schedule"},
    )
    relationship_table = SimpleNamespace(
        table_id="relationship-table",
        metadata={"table_role": "relationship_validation"},
    )

    figure_numbers, table_numbers = _question_media_numbers(
        graph,
        {"SP1": [decision, mechanism]},
        {"SP1": [decision_table, relationship_table]},
        figure_start=3,
    )

    assert figure_numbers == {"mechanism": 3, "decision": 4}
    assert table_numbers == {"relationship-table": 1, "decision-table": 2}

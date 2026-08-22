from __future__ import annotations

from types import SimpleNamespace

from mathworkstation.argument_layout import group_question_tables, plan_argument_blocks


def _table(table_id: str, role: str):
    return SimpleNamespace(
        table_id=table_id,
        title=table_id,
        metadata={"subproblem_id": "SP2", "table_role": role},
    )


def _figure(figure_id: str, semantic_kind: str, paper_role: str = "primary") -> dict:
    return {
        "figure_id": figure_id,
        "title": figure_id,
        "parameters": {
            "subproblem_id": "SP2",
            "semantic_kind": semantic_kind,
            "paper_role": paper_role,
        },
    }


def test_argument_layout_orders_evidence_as_a_reasoning_chain() -> None:
    figures = [
        _figure("fig-decision", "retail_category_replenishment_plan"),
        _figure("fig-robust", "parameter_sensitivity_curve", "supplementary_evidence"),
        _figure("fig-relation", "retail_price_demand_relationship"),
    ]
    tables = [
        _table("table-summary", "summary_metrics"),
        _table("table-decision", "decision_schedule"),
        _table("table-relation", "relationship_validation"),
    ]

    blocks = plan_argument_blocks(SimpleNamespace(subproblem_id="SP2"), figures, tables)
    signatures = [
        (block.phase, block.kind, getattr(block.item, "table_id", block.item.get("figure_id") if isinstance(block.item, dict) else ""))
        for block in blocks
    ]

    assert signatures == [
        ("model_evidence", "figure", "fig-relation"),
        ("model_evidence", "table", "table-relation"),
        ("decision", "figure", "fig-decision"),
        ("decision", "table", "table-decision"),
        ("robustness", "figure", "fig-robust"),
    ]
    assert all(block.lead_zh and block.tail_zh for block in blocks)
    assert all(block.lead_en and block.tail_en for block in blocks)


def test_group_question_tables_uses_registered_subproblem_metadata() -> None:
    sp2 = _table("table-sp2", "decision_schedule")
    sp3 = SimpleNamespace(
        table_id="table-sp3",
        title="table-sp3",
        metadata={"subproblem_id": "SP3", "table_role": "decision_schedule"},
    )
    grouped = group_question_tables([sp3, sp2])
    assert [item.table_id for item in grouped["SP2"]] == ["table-sp2"]
    assert [item.table_id for item in grouped["SP3"]] == ["table-sp3"]

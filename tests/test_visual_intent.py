from __future__ import annotations

from mathworkstation.visual_intent import FigureIntent, VisualIntentRouter, build_ppt_mcp_handoff, build_visual_brief


def _workflow_intent() -> FigureIntent:
    return FigureIntent(
        intent_id="case:workflow",
        kind="workflow_diagram",
        profile_id="CUMCM_C",
        purpose="Explain the accepted modeling route.",
        source_summary="NarrativeGraph",
        evidence_refs=["artifact-1"],
        required_content=["Preserve dependency direction"],
        forbidden_content=["Do not invent numbers"],
        editable_preferred=True,
    )


def test_workflow_routes_to_ai_candidate_but_keeps_safe_publication_fallback() -> None:
    plan = VisualIntentRouter().route(
        _workflow_intent(),
        capabilities={"ai_image": True, "ppt_mcp": False, "deterministic_vector": True},
    )

    assert plan.primary_backend == "ai_image"
    assert plan.publication_backend == "deterministic_vector"
    assert plan.visual_review_required is True
    assert plan.numeric_fidelity_required is False


def test_numeric_evidence_never_prefers_generative_backend() -> None:
    intent = FigureIntent(
        intent_id="case:fit",
        kind="numeric_evidence",
        profile_id="MCM_C",
        purpose="Show observed and fitted values.",
        source_summary="executed model",
    )
    plan = VisualIntentRouter().route(
        intent,
        capabilities={"ai_image": True, "deterministic_plot": True, "editable_vector": True},
    )

    assert plan.primary_backend == "deterministic_plot"
    assert plan.publication_backend == "deterministic_plot"
    assert plan.numeric_fidelity_required is True


def test_visual_brief_and_ppt_handoff_preserve_semantics_without_fixed_layout() -> None:
    intent = _workflow_intent()
    payload = {"nodes": [{"id": "SP1", "label": "问题1"}], "edges": []}
    brief = build_visual_brief(intent, semantic_payload=payload)
    handoff = build_ppt_mcp_handoff(intent, semantic_payload=payload)

    assert "Choose the composition" in brief
    assert "Do not invent numbers" in brief
    assert '"SP1"' in brief
    assert handoff["kind"] == "editable_powerpoint_figure_handoff"
    assert handoff["semantic_payload"] == payload
    assert any("Infer layout" in item for item in handoff["instructions"])

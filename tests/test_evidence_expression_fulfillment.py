from types import SimpleNamespace

from mathworkstation.evidence_expression import EvidenceExpressionNeed, EvidenceExpressionPlan
from mathworkstation.evidence_expression_fulfillment import EvidenceExpressionFulfillmentService
from mathworkstation.model_structure import ModelStructurePlan


class _Preferences:
    unified_framework_preferred = True


class _PreferenceService:
    def load(self, case_id):
        return _Preferences()


def _structure() -> ModelStructurePlan:
    return ModelStructurePlan(
        subproblem_id="SP1",
        framework_role="CORE_MODEL",
        archetypes=["optimization"],
        mathematical_objects=["decisions"],
        observed_variables=["cost"],
        decision_variables=["u"],
        parameters=["theta"],
        core_relations=["profit relation"],
        constraints=["feasibility"],
        objective_or_estimand="maximize profit",
        validation_requirements=["sensitivity analysis"],
        equation_roles=["objective equation"],
        visual_roles=["sensitivity response"],
        solver_role="solve declared structure",
    )


def _service():
    service = object.__new__(EvidenceExpressionFulfillmentService)
    service.preferences = _PreferenceService()
    return service


def test_fulfillment_distinguishes_missing_validation_figure_from_quota_gap():
    plan = EvidenceExpressionPlan(
        subproblem_id="SP1",
        selection_rules=[],
        anti_quota_rules=[],
        needs=[
            EvidenceExpressionNeed(
                need_id="SP1:sensitivity",
                medium="FIGURE",
                priority="RECOMMENDED",
                purpose="robustness",
                semantic_kind="sensitivity",
                evidence_requirement="validated perturbations",
                rationale="show stability",
            )
        ],
    )
    node = SimpleNamespace(
        role="RESEARCH",
        subproblem_id="SP1",
        expression_plan=plan,
        model_structure=_structure(),
        method="unknown_unexecuted_method",
        key_results=[SimpleNamespace(value=1.0)],
    )
    graph = SimpleNamespace(nodes=[node])
    assessment = _service().assess("case", graph, figures=[], tables=[])

    item = next(item for item in assessment.items if item.need_id == "SP1:sensitivity")
    assert item.status == "MISSING_PRESENTATION"
    assert item.repair_phase == "paper_visual"
    assert assessment.gate == "PASS"  # recommended gaps are advisory, not a hidden quota


def test_fulfillment_accepts_structural_figures_and_does_not_require_count_quota():
    plan = EvidenceExpressionPlan(subproblem_id="SP1", needs=[], selection_rules=[], anti_quota_rules=[])
    node1 = SimpleNamespace(
        role="RESEARCH",
        subproblem_id="SP1",
        expression_plan=plan,
        model_structure=_structure(),
        method="unknown",
        key_results=[],
    )
    node2 = SimpleNamespace(
        role="RESEARCH",
        subproblem_id="SP2",
        expression_plan=EvidenceExpressionPlan(subproblem_id="SP2", needs=[], selection_rules=[], anti_quota_rules=[]),
        model_structure=_structure().model_copy(update={"subproblem_id": "SP2"}),
        method="unknown",
        key_results=[],
    )
    graph = SimpleNamespace(nodes=[node1, node2])
    figures = [
        {"status": "FINAL", "figure_id": "workflow", "parameters": {"semantic_kind": "research_workflow"}},
        {"status": "FINAL", "figure_id": "framework", "parameters": {"semantic_kind": "model_framework"}},
    ]
    assessment = _service().assess("case", graph, figures=figures, tables=[])

    assert assessment.gate == "PASS"
    assert assessment.required_missing_count == 0
    assert {item.need_id for item in assessment.items} == {
        "paper:research-workflow",
        "paper:unified-model-framework",
    }

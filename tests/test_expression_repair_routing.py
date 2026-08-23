from pathlib import Path

from mathworkstation.case_manager import CaseManager
from mathworkstation.io_utils import atomic_write_json
from mathworkstation.recurrent_workstation import WorkstationGlobalAuditor, WorkstationRepairRouter


def test_expression_fulfillment_routes_evidence_gap_upstream_and_visual_gap_to_presentation(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "expression routing fixture", problem_type="C")
    case_id = case["case_id"]
    root = cases.case_root(case_id)
    path = root / "review" / "expression_fulfillment" / "assessment.json"
    atomic_write_json(
        path,
        {
            "schema_version": 1,
            "case_id": case_id,
            "gate": "REVIEW",
            "required_missing_count": 1,
            "recommended_missing_count": 1,
            "checked_at": "2026-08-22T00:00:00+00:00",
            "items": [
                {
                    "need_id": "SP2:robustness-evidence",
                    "subproblem_id": "SP2",
                    "medium": "FIGURE",
                    "semantic_kind": "sensitivity",
                    "priority": "REQUIRED",
                    "status": "MISSING_EVIDENCE",
                    "matched_ids": [],
                    "repair_phase": "validation",
                    "detail": "Sensitivity evidence has not been computed.",
                },
                {
                    "need_id": "paper:unified-model-framework",
                    "subproblem_id": None,
                    "medium": "FIGURE",
                    "semantic_kind": "model_framework",
                    "priority": "RECOMMENDED",
                    "status": "MISSING_PRESENTATION",
                    "matched_ids": [],
                    "repair_phase": "paper_visual",
                    "detail": "Model structure exists but the explanatory figure is absent.",
                },
            ],
        },
    )

    auditor = WorkstationGlobalAuditor(cases)
    findings = auditor._expression_fulfillment_findings(root)
    by_code = {item.code: item for item in findings}

    sensitivity = by_code["EXPRESSION_SENSITIVITY"]
    assert sensitivity.severity == "P1"
    assert sensitivity.domain == "experiment"
    assert sensitivity.repair_node == "experiments"
    assert sensitivity.subproblem_id == "SP2"
    assert sensitivity.repair_phase == "validation"

    framework = by_code["EXPRESSION_MODEL_FRAMEWORK"]
    assert framework.severity == "P2"
    assert framework.domain == "presentation"
    assert framework.repair_node == "supplementary_figure"

    # The recurrent router must restart from the earliest upstream defect and
    # preserve the subproblem/phase target instead of treating both as cosmetic.
    audit = auditor.audit(case_id)
    plan = WorkstationRepairRouter().plan(audit, round_number=3)
    assert plan.pivot in {"experiments", "input_validation", "problem_analysis"}
    assert any(target.subproblem_id == "SP2" and target.phase == "validation" for target in plan.repair_targets)

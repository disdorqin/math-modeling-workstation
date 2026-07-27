from pathlib import Path

import pytest

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.control_plane import BudgetPolicy, ControlPlane
from mathworkstation.paper_contracts import PaperContractService
from mathworkstation.review_engine import ReviewEngine
from mathworkstation.task_plugins import validate_task_protocol


def _case(tmp_path: Path):
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "four-phase")
    artifacts = ArtifactRegistry(cases)
    return cases, case["case_id"], artifacts


def test_task_plugins_accept_golden_and_reject_invalid_protocol() -> None:
    assert validate_task_protocol("forecasting", {"time_column": "date", "horizon": 3, "split_strategy": "temporal"})["valid"]
    invalid = validate_task_protocol("optimization", {"objective": "cost"})
    assert not invalid["valid"]
    assert "DECISION_VARIABLES_REQUIRED" in invalid["errors"]


def test_control_plane_requires_human_and_persists_budget_stop(tmp_path: Path) -> None:
    cases, case_id, _ = _case(tmp_path)
    control = ControlPlane(cases)
    with pytest.raises(ValueError, match="human actor"):
        control.approve(case_id, "final_review", "model", "auto", "digest", "SYSTEM")
    assert control.approve(case_id, "final_review", "human-1", "checked", "digest").actor_type == "HUMAN"
    control.initialize_budget(case_id, BudgetPolicy(max_experiments=1))
    with pytest.raises(RuntimeError, match="CONTROL_BUDGET_EXHAUSTED"):
        control.consume(case_id, experiments=2)


def test_review_engine_blocks_missing_diagnostics_and_answers(tmp_path: Path) -> None:
    cases, case_id, artifacts = _case(tmp_path)
    contract = PaperContractService(cases, artifacts)
    review = ReviewEngine(cases, artifacts).review(case_id, "摘要 结果 结论", contract)
    codes = {item["code"] for item in review["report"]["issues"]}
    assert review["report"]["gate"] == "BLOCK"
    assert {"SUBPROBLEM_CONTRACT_MISSING", "DIAGNOSTIC_RECORD_MISSING", "SUBPROBLEM_ANSWER_MISSING"} <= codes

from pathlib import Path

import pandas as pd

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.problem_graph import ProblemGraphBuilder
from mathworkstation.paper_contracts import SubproblemContract
from mathworkstation.solver_engine import SolverEngineService
from mathworkstation.validation_protocol import ValidationProtocolRegistry, ValidationRunner
from mathworkstation.wordle_2023_gate import prepare_wordle_2023_research


CASE_ROOT = Path("output/mcm-c-2023/v3/20260805-MCM-0001-EUP7")


def _contracts() -> list[SubproblemContract]:
    return [
        SubproblemContract.model_validate_json(line)
        for line in (CASE_ROOT / "results/contracts/subproblems.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_registry_assigns_distinct_protocols_to_wordle_research_families() -> None:
    graph = ProblemGraphBuilder().build(_contracts())
    registry = ValidationProtocolRegistry()
    protocols = {
        node.subproblem_id: registry.resolve(node.task_family, {})
        for node in graph.nodes
        if node.subproblem_id != "SP6"
    }
    assert len({item.protocol_id for item in protocols.values()}) == 5
    assert protocols["SP1"].protocol_id.startswith("forecasting.")
    assert protocols["SP2"].protocol_id.startswith("inference.")
    assert protocols["SP3"].protocol_id.startswith("distribution.")
    assert protocols["SP4"].protocol_id.startswith("classification.")
    assert protocols["SP5"].protocol_id.startswith("exploration.")


def test_validation_runner_blocks_forecasting_with_random_split() -> None:
    assessment = ValidationRunner().assess(
        "forecasting",
        {"time_column": "Date", "target_column": "y"},
        {
            "protocol": {"split": "random"},
            "metrics": {"rmse": 1.0, "mae": 0.8},
            "leakage_check": "PASS",
        },
        {"status": "PASS"},
    )
    assert assessment.gate == "FAIL"
    assert "FORECAST_SPLIT_NOT_TEMPORAL" in {item.code for item in assessment.findings}


def test_real_wordle_sp1_to_sp5_run_under_family_specific_validation(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "Wordle Validation Gate")
    artifacts = ArtifactRegistry(cases)
    engine = SolverEngineService(cases, artifacts)
    frame, plans = prepare_wordle_2023_research(
        pd.read_csv(CASE_ROOT / "input/data/uploaded/_wordle_data_clean.csv")
    )
    families = {
        "SP1": "forecasting",
        "SP2": "explanatory_inference",
        "SP3": "distribution_forecasting",
        "SP4": "classification",
        "SP5": "exploratory_analysis",
    }
    assessments = {}
    for subproblem_id, family in families.items():
        executed = engine.execute(
            case["case_id"],
            subproblem_id,
            family,
            plans[subproblem_id],
            frame=frame,
        )
        assessment = executed["validation"]["assessment"]
        assessments[subproblem_id] = assessment
        assert assessment.gate != "FAIL"
        assert executed["build"]["validation_protocol_id"] == assessment.protocol_id
        assert executed["artifact"]["artifact_type"] == "solver_execution_result"
        validation_artifact = executed["validation"]["artifact"]
        assert validation_artifact["artifact_type"] == "validation_assessment"
        assert validation_artifact["artifact_id"] in executed["artifact"]["upstream"]

    assert len({assessment.protocol_id for assessment in assessments.values()}) == 5
    assert assessments["SP1"].gate == "PASS"
    assert assessments["SP2"].metrics["bootstrap_runs"] >= 100
    assert assessments["SP3"].metrics["projected_simplex_error"] <= 1e-8
    assert "calibration_ece" in assessments["SP4"].metrics
    assert "leading_association_sign_stability" in assessments["SP5"].metrics
    assert artifacts.verify(case["case_id"])["valid"]


def test_lp_validation_surfaces_sensitivity_as_review_not_fake_pass(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "LP validation")
    artifacts = ArtifactRegistry(cases)
    engine = SolverEngineService(cases, artifacts)
    result = engine.execute(
        case["case_id"],
        "SP1",
        "optimization",
        {
            "solver_method": "linear_programming",
            "variables": [
                {"name": "x", "lower": 0, "upper": 10, "type": "continuous"},
                {"name": "y", "lower": 0, "upper": 10, "type": "continuous"},
            ],
            "objective": {"sense": "max", "coefficients": {"x": 3, "y": 2}},
            "constraints": [
                {"coefficients": {"x": 1, "y": 1}, "operator": "<=", "rhs": 4}
            ],
        },
    )
    assessment = result["validation"]["assessment"]
    assert assessment.gate == "REVIEW"
    assert "OPTIMIZATION_SENSITIVITY_PENDING" in {item.code for item in assessment.findings}

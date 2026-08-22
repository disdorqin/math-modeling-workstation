from pathlib import Path

import pandas as pd

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.modeling_brain import CandidateStrategy, ModelingBrainDecision
from mathworkstation.solver_engine import SolverEngineService, SolverRegistry
from mathworkstation.wordle_2023_gate import prepare_wordle_2023_research


def test_gold_solver_registry_exposes_current_capabilities() -> None:
    registry = SolverRegistry()
    capabilities = {family for item in registry.capabilities() for family in item["families"]}
    assert capabilities >= {
        "forecasting",
        "classification",
        "explanatory_inference",
        "distribution_forecasting",
        "exploratory_analysis",
        "optimization",
        "simulation",
        "ranking",
    }
    assert registry.resolve("forecasting", {}).name == "gold.forecasting"


def test_linear_programming_and_milp_plugins_solve_exact_small_models(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "Optimization solvers")
    artifacts = ArtifactRegistry(cases)
    engine = SolverEngineService(cases, artifacts)

    lp = engine.execute(
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
                {"coefficients": {"x": 1, "y": 1}, "operator": "<=", "rhs": 4},
                {"coefficients": {"x": 1}, "operator": "<=", "rhs": 2},
                {"coefficients": {"y": 1}, "operator": "<=", "rhs": 3},
            ],
        },
    )
    assert lp["solver"] == "gold.linear_programming"
    assert abs(lp["result"]["objective_value"] - 10.0) < 1e-8
    assert lp["result"]["constraint_status"] == "PASS"

    milp = engine.execute(
        case["case_id"],
        "SP2",
        "optimization",
        {
            "solver_method": "milp",
            "variables": [
                {"name": "x", "lower": 0, "upper": 2, "type": "integer"},
                {"name": "y", "lower": 0, "upper": 4, "type": "integer"},
            ],
            "objective": {"sense": "max", "coefficients": {"x": 3, "y": 2}},
            "constraints": [
                {"coefficients": {"x": 2, "y": 1}, "operator": "<=", "rhs": 4}
            ],
        },
    )
    assert milp["solver"] == "gold.milp"
    assert milp["result"]["constraint_status"] == "PASS"
    assert all(abs(value - round(value)) < 1e-8 for value in milp["result"]["solution"].values())
    assert artifacts.verify(case["case_id"])["valid"]


def test_clustering_plugin_runs_when_modeling_brain_requests_kmeans(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "Clustering solver")
    artifacts = ArtifactRegistry(cases)
    engine = SolverEngineService(cases, artifacts)
    frame = pd.DataFrame(
        {
            "x": [0, 0.1, -0.1, 5, 5.1, 4.9],
            "y": [0, -0.1, 0.1, 5, 4.9, 5.1],
        }
    )
    result = engine.execute(
        case["case_id"],
        "SP5",
        "exploratory_analysis",
        {
            "solver_method": "kmeans",
            "feature_columns": ["x", "y"],
            "n_clusters": 2,
            "random_seed": 42,
        },
        frame=frame,
    )
    assert result["solver"] == "gold.clustering"
    assert result["result"]["cluster_count"] == 2
    assert result["result"]["silhouette"] is not None


def test_real_wordle_holt_and_random_forest_alternatives_use_same_family_validation(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "Wordle alternative solver Gate")
    artifacts = ArtifactRegistry(cases)
    engine = SolverEngineService(cases, artifacts)
    source = Path("output/mcm-c-2023/v3/20260805-MCM-0001-EUP7/input/data/uploaded/_wordle_data_clean.csv")
    frame, plans = prepare_wordle_2023_research(pd.read_csv(source))

    holt_plan = {**plans["SP1"], "solver_method": "holt_exponential_smoothing"}
    holt = engine.execute(case["case_id"], "SP1-alt", "forecasting", holt_plan, frame=frame)
    assert holt["solver"] == "gold.holt_exponential_smoothing"
    assert holt["validation"]["assessment"].gate in {"PASS", "REVIEW"}
    assert holt["result"]["forecast"]["interval"]
    assert holt["result"]["leakage_check"] == "PASS"

    lifecycle_plan = {**plans["SP1"], "solver_method": "popularity_lifecycle"}
    lifecycle = engine.execute(case["case_id"], "SP1-lifecycle-alt", "forecasting", lifecycle_plan, frame=frame)
    assert lifecycle["solver"] == "gold.popularity_lifecycle"
    assert lifecycle["validation"]["assessment"].gate in {"PASS", "REVIEW"}
    assert lifecycle["result"]["forecast"]["interval"]
    assert lifecycle["result"]["leakage_check"] == "PASS"
    assert lifecycle["result"]["mechanism"]["kind"] == "two_phase_popularity_lifecycle"
    assert lifecycle["result"]["protocol"]["change_point_selected_on_training_only"] is True

    rf_plan = {**plans["SP4"], "solver_method": "random_forest_classifier"}
    forest = engine.execute(case["case_id"], "SP4-alt", "classification", rf_plan, frame=frame)
    assert forest["solver"] == "gold.random_forest_classification"
    assert forest["validation"]["assessment"].gate in {"PASS", "REVIEW"}
    assert forest["validation"]["assessment"].metrics["probability_source"] == "executed_solver_holdout"
    assert forest["result"]["future_prediction"] in {"easy", "medium", "hard"}
    assert forest["result"]["future_probabilities"]
    assert artifacts.verify(case["case_id"])["valid"]


def test_entropy_topsis_solver_is_mcdm_not_ir_ranking(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "entropy topsis")
    artifacts = ArtifactRegistry(cases)
    engine = SolverEngineService(cases, artifacts)
    frame = pd.DataFrame(
        {
            "state": ["AZ", "CA", "NM", "TX"],
            "renew_cons_share": [0.0712, 0.0890, 0.0532, 0.0316],
            "renew_prod_share": [0.1551, 0.2438, 0.0140, 0.0255],
            "renew_per_capita": [15.7, 19.3, 17.7, 14.7],
            "energy_per_capita": [220.8, 217.0, 333.8, 456.1],
        }
    )
    plan = {
        "solver_method": "entropy_topsis",
        "entity_column": "state",
        "criteria": [
            {"column": "renew_cons_share", "direction": "benefit"},
            {"column": "renew_prod_share", "direction": "benefit"},
            {"column": "renew_per_capita", "direction": "benefit"},
            {"column": "energy_per_capita", "direction": "cost"},
        ],
    }

    result = engine.execute(case["case_id"], "I-C", "ranking", plan, frame=frame)

    assert result["solver"] == "gold.entropy_topsis"
    assert result["result"]["protocol"]["method"] == "entropy_topsis"
    assert result["result"]["winner"] == "CA"
    assert abs(sum(result["result"]["weights"].values()) - 1.0) < 1e-9
    assert result["validation"]["assessment"].protocol_id == "ranking.entropy-topsis-stability.v1"
    assert result["validation"]["assessment"].gate in {"PASS", "REVIEW"}
    assert len(result["result"]["sensitivity"]["leave_one_criterion_out"]) == 4
    assert artifacts.verify(case["case_id"])["valid"]


def test_solver_engine_executes_and_exports_traceable_evidence(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "Solver Engine")
    artifacts = ArtifactRegistry(cases)
    engine = SolverEngineService(cases, artifacts)
    dates = pd.date_range("2025-01-01", periods=80, freq="D")
    frame = pd.DataFrame({"Date": dates, "x": range(80), "y": [100 + value * 2 for value in range(80)]})

    executed = engine.execute(
        case["case_id"],
        "SP1",
        "forecasting",
        {
            "time_column": "Date",
            "target_column": "y",
            "feature_columns": ["x"],
            "future_time": "2025-04-01",
            "future_features": {"x": 90},
            "bootstrap_runs": 50,
        },
        frame=frame,
    )
    assert executed["solver"] == "gold.forecasting"
    assert executed["diagnostics"]["status"] == "PASS"
    assert executed["result"]["forecast"]["interval"]
    artifact = executed["artifact"]
    assert artifact["artifact_type"] == "solver_execution_result"
    input_frame = executed["input_frame_artifact"]
    assert input_frame is not None
    assert input_frame["artifact_type"] == "solver_input_frame"
    assert executed["build"]["input_frame_artifact_id"] == input_frame["artifact_id"]
    assert input_frame["artifact_id"] in executed["validation"]["artifact"]["upstream"]
    assert input_frame["artifact_id"] in artifact["upstream"]
    assert artifacts.verify(case["case_id"])["valid"]


def test_solver_engine_persists_capability_gap_as_traceable_artifact(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "Solver capability gap")
    artifacts = ArtifactRegistry(cases)
    engine = SolverEngineService(cases, artifacts)
    decision = ModelingBrainDecision(
        case_id=case["case_id"],
        subproblem_id="SP1",
        task_family="forecasting",
        gate="PASS",
        query="forecast future series",
        candidates=[
            CandidateStrategy(
                candidate_id="card:arima",
                method="ARIMA",
                source="knowledge_card",
                retrieval_score=0.9,
                feasibility="NEEDS_SOLVER",
                rationale="relevant but not executable",
            )
        ],
        selected_candidate_ids=["card:arima"],
        selected_methods=["ARIMA"],
        generated_at="2026-08-19T00:00:00+08:00",
    )
    report = engine.persist_gap_report(case["case_id"], "SP1", decision)
    assert report["missing_count"] == 1
    artifact = artifacts.get(case["case_id"], report["artifact_id"])
    assert artifact["artifact_type"] == "solver_capability_gap"
    assert artifacts.verify(case["case_id"])["valid"]


def test_solver_registry_turns_modeling_brain_needs_solver_into_explicit_gap() -> None:
    decision = ModelingBrainDecision(
        case_id="case-x",
        subproblem_id="SP1",
        task_family="forecasting",
        gate="PASS",
        query="forecast future series",
        candidates=[
            CandidateStrategy(
                candidate_id="card:arima",
                method="ARIMA",
                source="knowledge_card",
                retrieval_score=0.9,
                feasibility="NEEDS_SOLVER",
                rationale="relevant but not executable",
            ),
            CandidateStrategy(
                candidate_id="native:ridge",
                method="ridge time trend",
                source="native",
                retrieval_score=1.0,
                feasibility="PASS",
                rationale="registered",
            ),
        ],
        selected_candidate_ids=["native:ridge", "card:arima"],
        selected_methods=["ridge time trend", "ARIMA"],
        generated_at="2026-08-19T00:00:00+08:00",
    )
    report = SolverRegistry().gap_report(decision)
    assert report["missing_count"] == 1
    assert report["missing_solver_methods"] == [{"method": "ARIMA", "source": "knowledge_card"}]

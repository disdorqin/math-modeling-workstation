from __future__ import annotations

import numpy as np
import pandas as pd

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.subproblem_executors import (
    SubproblemExecutionService,
    execute_classification_with_future,
    execute_distribution_forecasting,
    execute_scalar_forecast_interval,
    execute_explanatory_inference,
    execute_exploratory_analysis,
)


def test_scalar_forecast_interval_returns_future_point_and_temporal_residual_interval() -> None:
    rows = 80
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=rows, freq="D"),
            "target": np.exp(8.0 - np.arange(rows) * 0.01),
        }
    )

    result = execute_scalar_forecast_interval(
        frame,
        {
            "time_column": "date",
            "target_column": "target",
            "future_time": "2024-04-15",
            "test_size": 0.2,
            "bootstrap_runs": 40,
            "random_seed": 3,
        },
    )

    assert result["family"] == "forecasting"
    assert result["protocol"]["split"] == "temporal_holdout"
    assert result["leakage_check"] == "PASS"
    assert result["forecast"]["point"] > 0
    assert result["forecast"]["interval"][0] <= result["forecast"]["point"] <= result["forecast"]["interval"][1]


def test_classification_with_future_reuses_validation_schema_for_future_item() -> None:
    rng = np.random.default_rng(5)
    x1 = rng.normal(size=120)
    x2 = rng.normal(size=120)
    labels = np.where(x1 + x2 > 0.7, "hard", np.where(x1 + x2 < -0.7, "easy", "medium"))
    frame = pd.DataFrame({"x1": x1, "x2": x2, "difficulty": labels})

    result = execute_classification_with_future(
        frame,
        {
            "target_column": "difficulty",
            "feature_columns": ["x1", "x2"],
            "class_balance": "observed",
            "test_size": 0.2,
            "random_seed": 8,
            "future_features": {"x1": 1.5, "x2": 1.2},
        },
    )

    assert result["family"] == "classification"
    assert result["future_prediction"] in {"easy", "medium", "hard"}
    assert abs(sum(result["future_probabilities"].values()) - 1.0) < 1e-9


def test_explanatory_inference_reports_directional_effects_with_bootstrap_intervals() -> None:
    rng = np.random.default_rng(7)
    rows = 120
    x1 = rng.normal(size=rows)
    x2 = rng.normal(size=rows)
    target = 3.0 * x1 - 1.5 * x2 + rng.normal(scale=0.25, size=rows)
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=rows, freq="D"),
            "x1": x1,
            "x2": x2,
            "target": target,
        }
    )

    result = execute_explanatory_inference(
        frame,
        {
            "target_column": "target",
            "feature_columns": ["x1", "x2"],
            "split_strategy": "temporal",
            "time_column": "date",
            "test_size": 0.2,
            "bootstrap_runs": 30,
            "random_seed": 11,
        },
    )

    assert result["family"] == "explanatory_inference"
    assert result["protocol"]["split"] == "temporal_holdout"
    assert result["interpretation_guard"] == "associational_not_causal"
    effects = {item["feature"]: item for item in result["effects"]}
    assert effects["x1"]["direction"] == "positive"
    assert effects["x2"]["direction"] == "negative"
    assert result["metrics"]["r2"] > 0.8


def test_distribution_forecasting_enforces_simplex_and_temporal_holdout() -> None:
    rows = 90
    t = np.arange(rows, dtype=float)
    p1 = 20 + 0.08 * t
    p2 = 50 - 0.04 * t
    p3 = 100 - p1 - p2
    frame = pd.DataFrame(
        {
            "date": pd.date_range("2024-01-01", periods=rows, freq="D"),
            "feature": np.sin(t / 8),
            "p1": p1,
            "p2": p2,
            "p3": p3,
        }
    )

    result = execute_distribution_forecasting(
        frame,
        {
            "time_column": "date",
            "feature_columns": ["feature"],
            "output_columns": ["p1", "p2", "p3"],
            "test_size": 0.2,
            "distribution_total": 100,
            "future_features": {"feature": 0.25},
        },
    )

    predicted = np.asarray(result["predictions"], dtype=float)
    assert result["family"] == "distribution_forecasting"
    assert result["protocol"]["split"] == "temporal_holdout"
    assert np.all(predicted >= 0)
    assert np.allclose(predicted.sum(axis=1), 100.0)
    assert result["metrics"]["projected_simplex_error"] < 1e-9
    assert result["future_distribution"] is not None
    assert abs(sum(result["future_distribution"].values()) - 100.0) < 1e-9
    assert result["future_uncertainty_95"] is not None
    assert set(result["future_uncertainty_95"]) == {"p1", "p2", "p3"}


def test_exploratory_analysis_surfaces_association_outlier_and_change_point_candidates() -> None:
    x = np.arange(80, dtype=float)
    frame = pd.DataFrame(
        {
            "x": x,
            "strong": x * 2 + 1,
            "shifted": np.r_[np.zeros(40), np.ones(40) * 12],
            "outlier": np.r_[np.ones(79), 100.0],
        }
    )

    result = execute_exploratory_analysis(frame, {"numeric_columns": list(frame.columns)})

    assert result["family"] == "exploratory_analysis"
    assert result["discoveries"]["strongest_associations"]
    assert result["discoveries"]["highest_outlier_rates"][0]["iqr_outlier_rate"] > 0
    assert result["discoveries"]["largest_mean_shift_candidates"][0]["standardized_mean_shift"] > 0


def test_subproblem_execution_service_registers_immutable_subproblem_evidence(tmp_path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "Subproblem executor")
    artifacts = ArtifactRegistry(cases)
    source = tmp_path / "source.csv"
    frame = pd.DataFrame({"a": np.arange(30), "b": np.arange(30) * 2})
    frame.to_csv(source, index=False)
    source_artifact = artifacts.ingest_file(
        case["case_id"], source, "input/data/uploaded/source.csv", "observed_data"
    )

    execution = SubproblemExecutionService(cases, artifacts).execute(
        case["case_id"],
        "exploratory_analysis",
        {"numeric_columns": ["a", "b"]},
        frame,
        [source_artifact["artifact_id"]],
        subproblem_id="SP5",
    )

    assert execution["artifact"]["artifact_type"] == "subproblem_execution_result"
    assert execution["artifact"]["upstream"] == [source_artifact["artifact_id"]]
    assert "results/subproblems/SP5/" in execution["artifact"]["path"]
    assert artifacts.verify(case["case_id"])["valid"] is True

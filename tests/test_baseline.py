from pathlib import Path

import pandas as pd

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.baseline import BaselineEngine, _resolve_task, _stratify_target
from mathworkstation.case_manager import CaseManager
from mathworkstation.data_quality import TabularProfiler
from mathworkstation.datasets import DatasetKind, DatasetRegistry
from mathworkstation.experiments import ExperimentRegistry
from mathworkstation.figure_registry import FigureRegistry


def test_regression_baseline_writes_reproducible_artifacts(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Baseline")
    source = tmp_path / "data.csv"
    frame = pd.DataFrame(
        {
            "x1": list(range(80)),
            "x2": [value % 7 for value in range(80)],
            "group": ["A", "B"] * 40,
            "target": [3 * value + (value % 7) for value in range(80)],
        }
    )
    frame.to_csv(source, index=False)
    artifacts = ArtifactRegistry(cases)
    source_artifact = artifacts.ingest_file(case["case_id"], source, "input/data/uploaded", "observed_data")
    datasets = DatasetRegistry(cases, artifacts)
    dataset = datasets.register(
        case["case_id"], "Baseline", source_artifact["artifact_id"], DatasetKind.OBSERVED, "uploaded", "human"
    )
    TabularProfiler(cases, artifacts, datasets).profile(case["case_id"], dataset["dataset_id"], "target")
    experiments = ExperimentRegistry(cases, artifacts)
    result = BaselineEngine(
        cases,
        artifacts,
        datasets,
        experiments,
        FigureRegistry(cases, artifacts),
    ).run(case["case_id"], dataset["dataset_id"], "target", task_type="regression", run_id="run-baseline")
    assert result["best_model"] in {"linear", "ridge", "random_forest", "dummy_mean"}
    assert result["metrics"]["test_rows"] == 20
    assert experiments.get(case["case_id"], result["experiment_id"])["status"] == "SUCCEEDED"
    assert artifacts.verify(case["case_id"])["valid"]
    for artifact_id in (
        result["metrics_artifact_id"],
        result["predictions_artifact_id"],
        result["model_artifact_id"],
    ):
        assert artifacts.get(case["case_id"], artifact_id)["paper_eligible"] is False
    metric_artifact = artifacts.get(case["case_id"], result["metrics_artifact_id"])
    upstream_types = {artifacts.get(case["case_id"], item)["artifact_type"] for item in metric_artifact["upstream"]}
    assert {"observed_data", "experiment_config", "experiment_code_snapshot"} <= upstream_types


def test_classification_baseline_reports_accuracy_and_f1(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Classification")
    source = tmp_path / "classes.csv"
    frame = pd.DataFrame(
        {
            "x": list(range(90)),
            "group": ["A", "B", "C"] * 30,
            "target": ["low" if value < 30 else "mid" if value < 60 else "high" for value in range(90)],
        }
    )
    frame.to_csv(source, index=False)
    artifacts = ArtifactRegistry(cases)
    source_artifact = artifacts.ingest_file(case["case_id"], source, "input/data/uploaded", "observed_data")
    datasets = DatasetRegistry(cases, artifacts)
    dataset = datasets.register(
        case["case_id"], "Classes", source_artifact["artifact_id"], DatasetKind.OBSERVED, "uploaded", "human"
    )
    TabularProfiler(cases, artifacts, datasets).profile(case["case_id"], dataset["dataset_id"], "target")
    result = BaselineEngine(
        cases,
        artifacts,
        datasets,
        ExperimentRegistry(cases, artifacts),
        FigureRegistry(cases, artifacts),
    ).run(case["case_id"], dataset["dataset_id"], "target", task_type="classification")
    assert result["metrics"]["task_type"] == "classification"
    assert "accuracy" in result["metrics"]["metrics"][result["best_model"]]
    assert "macro_f1" in result["metrics"]["metrics"][result["best_model"]]


def test_auto_task_detection_distinguishes_continuous_numeric_target() -> None:
    assert _resolve_task(pd.Series([1.1, 1.8, 2.7, 3.6, 4.4, 5.9, 6.3, 7.8]), "auto") == "regression"
    assert _resolve_task(pd.Series([0, 1, 0, 1, 0, 1, 0, 1]), "auto") == "classification"


def test_small_classification_split_disables_unsafe_stratification() -> None:
    target = pd.Series(["A", "A", "B", "B", "C", "C", "D", "D"])
    assert _stratify_target(target, "classification", 0.25) is None

from pathlib import Path

import pandas as pd

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.data_quality import TabularProfiler
from mathworkstation.datasets import DatasetKind, DatasetRegistry
from mathworkstation.experiments import ExperimentRegistry
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.model_evaluation import ModelEvaluationEngine
from mathworkstation.model_plan import ModelPlan


def test_cross_validation_comparison_registers_diagnostics(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "CV")
    source = tmp_path / "data.csv"
    pd.DataFrame(
        {
            "x1": list(range(60)),
            "x2": [value % 5 for value in range(60)],
            "target": [2.5 * value + (value % 5) for value in range(60)],
        }
    ).to_csv(source, index=False)
    artifacts = ArtifactRegistry(cases)
    source_artifact = artifacts.ingest_file(case["case_id"], source, "input/data/uploaded", "observed_data")
    datasets = DatasetRegistry(cases, artifacts)
    dataset = datasets.register(
        case["case_id"], "CV", source_artifact["artifact_id"], DatasetKind.OBSERVED, "uploaded", "human"
    )
    TabularProfiler(cases, artifacts, datasets).profile(case["case_id"], dataset["dataset_id"], "target")
    plan = ModelPlan.model_validate(
        {
            "purpose": "compare candidates",
            "dataset_id": dataset["dataset_id"],
            "task_type": "regression",
            "target_column": "target",
            "feature_columns": ["x1", "x2"],
            "candidate_models": [
                {"name": "linear", "parameters": {}, "rationale": "interpretable"},
                {"name": "ridge", "parameters": {"alpha": 1.0}, "rationale": "regularized"},
                {"name": "random_forest", "parameters": {"n_estimators": 50}, "rationale": "nonlinear"},
            ],
            "primary_metric": "rmse",
            "cv_folds": 3,
            "paper_eligible": False,
        }
    )
    plan_file = cases.case_root(case["case_id"]) / ".internal" / "test-plan.json"
    plan_file.write_text(plan.model_dump_json(), encoding="utf-8")
    plan_artifact = artifacts.register_existing(
        case["case_id"], ".internal/test-plan.json", "model_plan_validated", "python"
    )
    result = ModelEvaluationEngine(
        cases,
        artifacts,
        datasets,
        ExperimentRegistry(cases, artifacts),
        FigureRegistry(cases, artifacts),
    ).run(case["case_id"], plan, plan_artifact["artifact_id"], "run-cv")
    assert result["best_model"] in {"linear", "ridge", "random_forest"}
    assert len(result["comparison"]["ranking"]) == 3
    assert "residual_shapiro_pvalue" in result["diagnostics"]
    comparison = artifacts.get(case["case_id"], result["comparison_artifact_id"])
    assert plan_artifact["artifact_id"] in comparison["upstream"]


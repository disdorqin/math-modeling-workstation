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
from mathworkstation.selection import ModelSelectionRegistry
from mathworkstation.sensitivity import SensitivityEngine


def test_sensitivity_and_model_selection_are_evidence_backed(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Sensitivity")
    source = tmp_path / "data.csv"
    pd.DataFrame(
        {
            "x": list(range(80)),
            "target": [2.2 * value + (value % 3) for value in range(80)],
        }
    ).to_csv(source, index=False)
    artifacts = ArtifactRegistry(cases)
    source_artifact = artifacts.ingest_file(case["case_id"], source, "input/data/uploaded", "observed_data")
    datasets = DatasetRegistry(cases, artifacts)
    dataset = datasets.register(
        case["case_id"], "Sensitivity", source_artifact["artifact_id"], DatasetKind.OBSERVED, "uploaded", "human"
    )
    TabularProfiler(cases, artifacts, datasets).profile(case["case_id"], dataset["dataset_id"], "target")
    plan = ModelPlan.model_validate(
        {
            "purpose": "sensitivity test",
            "dataset_id": dataset["dataset_id"],
            "task_type": "regression",
            "target_column": "target",
            "feature_columns": ["x"],
            "candidate_models": [
                {"name": "linear", "parameters": {}, "rationale": "interpretable"},
                {"name": "ridge", "parameters": {"alpha": 1.0}, "rationale": "regularized"},
            ],
            "primary_metric": "rmse",
            "cv_folds": 3,
            "sensitivity_fractions": [0.7, 1.0],
            "paper_eligible": False,
        }
    )
    plan_path = cases.case_root(case["case_id"]) / ".internal" / "plan.json"
    plan_path.write_text(plan.model_dump_json(), encoding="utf-8")
    plan_artifact = artifacts.register_existing(
        case["case_id"], ".internal/plan.json", "model_plan_validated", "python"
    )
    experiments = ExperimentRegistry(cases, artifacts)
    figures = FigureRegistry(cases, artifacts)
    comparison = ModelEvaluationEngine(cases, artifacts, datasets, experiments, figures).run(
        case["case_id"], plan, plan_artifact["artifact_id"]
    )
    sensitivity = SensitivityEngine(cases, artifacts, datasets, experiments, figures).run(
        case["case_id"], comparison["experiment_id"], plan, plan_artifact["artifact_id"], seeds=[1, 2]
    )
    assert sensitivity["summary"]["gate"] in {"PASS", "REVIEW"}
    selection = ModelSelectionRegistry(cases, artifacts, experiments).select(
        case["case_id"],
        comparison["experiment_id"],
        comparison["best_model"],
        comparison["comparison_artifact_id"],
        "human",
        "best cross-validation score with acceptable stability",
    )
    assert artifacts.get(case["case_id"], selection["artifact_id"])["artifact_type"] == "model_selection"


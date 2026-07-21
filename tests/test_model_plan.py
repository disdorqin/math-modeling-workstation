import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.model_plan import ModelPlan, ModelPlanService


def valid_plan() -> dict:
    return {
        "schema_version": 1,
        "purpose": "compare regression candidates",
        "dataset_id": "dataset-test",
        "task_type": "regression",
        "target_column": "target",
        "feature_columns": ["x1", "x2"],
        "candidate_models": [
            {"name": "linear", "parameters": {}, "rationale": "interpretable baseline"},
            {"name": "ridge", "parameters": {"alpha": 1.0}, "rationale": "regularized baseline"},
        ],
        "primary_metric": "rmse",
        "cv_folds": 5,
        "test_size": 0.2,
        "random_seed": 42,
        "sensitivity_fractions": [0.7, 0.85, 1.0],
        "paper_eligible": False,
    }


def test_model_plan_rejects_target_leakage_and_unknown_model() -> None:
    leaked = valid_plan()
    leaked["feature_columns"].append("target")
    with pytest.raises(ValidationError):
        ModelPlan.model_validate(leaked)
    unknown = valid_plan()
    unknown["candidate_models"][1]["name"] = "magic_model"
    with pytest.raises(ValidationError):
        ModelPlan.model_validate(unknown)


def test_model_plan_service_registers_validated_artifact(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Plan")
    source = tmp_path / "plan.json"
    source.write_text(json.dumps(valid_plan()), encoding="utf-8")
    artifacts = ArtifactRegistry(cases)
    result = ModelPlanService(cases, artifacts).validate_file(case["case_id"], source)
    assert artifacts.get(case["case_id"], result["plan_artifact_id"])["artifact_type"] == "model_plan_validated"
    loaded = ModelPlanService(cases, artifacts).load(case["case_id"], result["plan_artifact_id"])
    assert loaded.primary_metric == "rmse"
    assert result["plan"]["validation"]["validated_at"]


def test_model_plan_dataset_can_be_safely_bound_at_validation(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Bound Plan")
    source = tmp_path / "plan.json"
    source.write_text(json.dumps(valid_plan()), encoding="utf-8")
    result = ModelPlanService(cases, ArtifactRegistry(cases)).validate_file(
        case["case_id"], source, "dataset-runtime"
    )
    assert result["plan"]["plan"]["dataset_id"] == "dataset-runtime"

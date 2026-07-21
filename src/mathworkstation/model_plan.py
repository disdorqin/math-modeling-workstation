from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .io_utils import atomic_write_json, atomic_write_text, now_iso


REGRESSION_MODELS = {
    "linear",
    "ridge",
    "lasso",
    "elastic_net",
    "random_forest",
    "gradient_boosting",
}
CLASSIFICATION_MODELS = {
    "logistic",
    "random_forest",
    "gradient_boosting",
}


class CandidateModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    rationale: str = Field(min_length=3)


class ModelPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1] = 1
    purpose: str = Field(min_length=3)
    dataset_id: str = Field(min_length=3)
    task_type: Literal["regression", "classification"]
    target_column: str = Field(min_length=1)
    feature_columns: list[str] = Field(min_length=1)
    candidate_models: list[CandidateModel] = Field(min_length=2)
    primary_metric: str
    cv_folds: int = Field(default=5, ge=2, le=10)
    test_size: float = Field(default=0.2, gt=0.05, lt=0.5)
    random_seed: int = Field(default=42, ge=0)
    sensitivity_fractions: list[float] = Field(default_factory=lambda: [0.7, 0.85, 1.0])
    paper_eligible: Literal[False] = False

    @model_validator(mode="after")
    def validate_semantics(self) -> "ModelPlan":
        if len(self.feature_columns) != len(set(self.feature_columns)):
            raise ValueError("feature_columns contains duplicates")
        if self.target_column in self.feature_columns:
            raise ValueError("target_column cannot be a feature")
        names = [candidate.name for candidate in self.candidate_models]
        if len(names) != len(set(names)):
            raise ValueError("candidate model names must be unique")
        allowed = REGRESSION_MODELS if self.task_type == "regression" else CLASSIFICATION_MODELS
        unknown = sorted(set(names) - allowed)
        if unknown:
            raise ValueError(f"unsupported candidate models: {unknown}")
        allowed_metrics = {"rmse", "mae", "r2"} if self.task_type == "regression" else {"macro_f1", "accuracy"}
        if self.primary_metric not in allowed_metrics:
            raise ValueError(f"invalid primary_metric for {self.task_type}: {self.primary_metric}")
        if sorted(set(self.sensitivity_fractions)) != sorted(self.sensitivity_fractions):
            raise ValueError("sensitivity_fractions must be unique")
        if any(value <= 0.2 or value > 1.0 for value in self.sensitivity_fractions):
            raise ValueError("sensitivity fractions must be in (0.2, 1.0]")
        return self


class ModelPlanService:
    def __init__(self, cases: CaseManager, artifacts: ArtifactRegistry) -> None:
        self.cases = cases
        self.artifacts = artifacts

    def validate_file(
        self,
        case_id: str,
        source_path: str | Path,
        dataset_id: str | None = None,
    ) -> dict[str, Any]:
        source = Path(source_path).resolve()
        payload = json.loads(source.read_text(encoding="utf-8"))
        if dataset_id:
            payload["dataset_id"] = dataset_id
        plan = ModelPlan.model_validate(payload)
        case_root = self.cases.case_root(case_id)
        output_path = case_root / ".internal" / "model_plan.json"
        validated = {
            "schema_version": 1,
            "plan": plan.model_dump(mode="json"),
            "validation": {
                "validated_at": now_iso(),
                "validation_source": str(source),
            },
        }
        atomic_write_json(output_path, validated)
        artifact = self.artifacts.register_existing(
            case_id,
            output_path.relative_to(case_root).as_posix(),
            "model_plan_validated",
            "python",
            paper_eligible=False,
        )
        report_path = case_root / "analysis" / "模型方案.md"
        atomic_write_text(report_path, _render_plan(plan, artifact["artifact_id"]))
        report_artifact = self.artifacts.register_existing(
            case_id,
            report_path.relative_to(case_root).as_posix(),
            "model_plan_report",
            "python",
            upstream=[artifact["artifact_id"]],
        )
        return {
            "plan": validated,
            "plan_artifact_id": artifact["artifact_id"],
            "report_artifact_id": report_artifact["artifact_id"],
        }

    def load(self, case_id: str, artifact_id: str) -> ModelPlan:
        artifact = self.artifacts.get(case_id, artifact_id)
        if artifact["artifact_type"] != "model_plan_validated":
            raise ValueError("artifact is not a validated model plan")
        path = self.cases.case_root(case_id) / artifact["path"]
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ModelPlan.model_validate(payload["plan"])


def _render_plan(plan: ModelPlan, artifact_id: str) -> str:
    candidates = "\n".join(
        f"- `{candidate.name}`：{candidate.rationale}；参数 `{json.dumps(candidate.parameters, ensure_ascii=False)}`"
        for candidate in plan.candidate_models
    )
    return (
        "# 模型方案\n\n"
        f"- Plan Artifact：`{artifact_id}`\n"
        f"- Dataset：`{plan.dataset_id}`\n"
        f"- 任务：`{plan.task_type}`\n"
        f"- 目标变量：`{plan.target_column}`\n"
        f"- 特征：`{', '.join(plan.feature_columns)}`\n"
        f"- 主指标：`{plan.primary_metric}`\n"
        f"- 交叉验证：`{plan.cv_folds}` 折\n\n"
        "## 候选模型\n\n"
        f"{candidates}\n\n"
        "该方案通过结构验证，但仍需人工审批后才能运行正式实验。\n"
    )

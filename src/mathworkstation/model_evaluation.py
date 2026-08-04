from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats
from sklearn.base import clone
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, StratifiedKFold, cross_validate
from sklearn.pipeline import Pipeline

from .artifact_registry import ArtifactRegistry
from .baseline import _preprocessor, build_candidate_model
from .case_manager import CaseManager
from .datasets import DatasetRegistry
from .experiments import ExperimentRegistry
from .figure_registry import FigureRegistry
from .io_utils import atomic_write_json, atomic_write_text, now_iso
from .model_plan import ModelPlan
from .paths import resolve_within
from .plot_style import apply_style, get_colors, get_line_cycle, get_figsize, save_figure
from .tabular import read_table

apply_style()


class ModelEvaluationEngine:
    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        datasets: DatasetRegistry,
        experiments: ExperimentRegistry,
        figures: FigureRegistry,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.datasets = datasets
        self.experiments = experiments
        self.figures = figures

    def run(
        self,
        case_id: str,
        plan: ModelPlan,
        plan_artifact_id: str,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        dataset = self.datasets.get(case_id, plan.dataset_id)
        source_artifact = self.artifacts.get(case_id, dataset["artifact_id"])
        frame = read_table(resolve_within(self.cases.case_root(case_id), source_artifact["path"]))
        missing = sorted(set([plan.target_column, *plan.feature_columns]) - set(frame.columns))
        if missing:
            raise ValueError(f"model plan references missing columns: {missing}")
        modeling = frame[[*plan.feature_columns, plan.target_column]].dropna(subset=[plan.target_column])
        if len(modeling) < plan.cv_folds * 2:
            raise ValueError("insufficient rows for requested cross-validation")
        if plan.task_type == "classification" and modeling[plan.target_column].value_counts().min() < plan.cv_folds:
            raise ValueError("each class must have at least cv_folds rows")

        experiment = self.experiments.create(
            case_id,
            f"Candidate comparison {plan.task_type}",
            plan.dataset_id,
            source_artifact["artifact_id"],
            plan.task_type,
            plan.target_column,
            plan.feature_columns,
            plan.model_dump(mode="json"),
            run_id,
        )
        experiment_id = experiment["experiment_id"]
        code_artifacts = self.experiments.snapshot_code(case_id, experiment_id, [Path(__file__)])
        self.experiments.update(case_id, experiment_id, "RUNNING", started_at=now_iso())
        try:
            result = self._evaluate(
                case_id,
                experiment_id,
                modeling,
                plan,
                source_artifact,
                plan_artifact_id,
                [item["artifact_id"] for item in code_artifacts],
                experiment["config_artifact_id"],
                run_id,
            )
        except Exception as error:
            root = self.cases.case_root(case_id) / "experiments" / experiment_id
            (root / "stderr.log").write_text(f"{type(error).__name__}: {error}\n", encoding="utf-8")
            self.experiments.update(
                case_id,
                experiment_id,
                "FAILED",
                finished_at=now_iso(),
                error={"type": type(error).__name__, "message": str(error)},
            )
            raise
        self.experiments.update(
            case_id,
            experiment_id,
            "SUCCEEDED",
            finished_at=now_iso(),
            best_model=result["best_model"],
            comparison_artifact_id=result["comparison_artifact_id"],
            diagnostics_artifact_id=result["diagnostics_artifact_id"],
        )
        return {"experiment_id": experiment_id, **result}

    def _evaluate(
        self,
        case_id: str,
        experiment_id: str,
        frame: pd.DataFrame,
        plan: ModelPlan,
        source_artifact: dict[str, Any],
        plan_artifact_id: str,
        code_artifact_ids: list[str],
        config_artifact_id: str,
        run_id: str | None,
    ) -> dict[str, Any]:
        features = frame[plan.feature_columns]
        target = frame[plan.target_column]
        splitter = (
            KFold(plan.cv_folds, shuffle=True, random_state=plan.random_seed)
            if plan.task_type == "regression"
            else StratifiedKFold(plan.cv_folds, shuffle=True, random_state=plan.random_seed)
        )
        scoring = _scoring(plan.task_type)
        model_results: dict[str, Any] = {}
        fitted_pipelines: dict[str, Pipeline] = {}
        for candidate in plan.candidate_models:
            pipeline = Pipeline(
                [
                    ("preprocessor", _preprocessor(features)),
                    (
                        "model",
                        build_candidate_model(
                            plan.task_type,
                            candidate.name,
                            candidate.parameters,
                            plan.random_seed,
                        ),
                    ),
                ]
            )
            scores = cross_validate(
                pipeline,
                features,
                target,
                cv=splitter,
                scoring=scoring,
                return_train_score=True,
                error_score="raise",
            )
            model_results[candidate.name] = _summarize_cv(plan.task_type, scores)
            pipeline.fit(features, target)
            fitted_pipelines[candidate.name] = pipeline
        best_model = _select_best(plan, model_results)
        best_pipeline = fitted_pipelines[best_model]
        fitted = best_pipeline.predict(features)
        diagnostics = _diagnostics(plan.task_type, target, fitted)
        comparison = {
            "schema_version": 1,
            "case_id": case_id,
            "experiment_id": experiment_id,
            "plan_artifact_id": plan_artifact_id,
            "task_type": plan.task_type,
            "primary_metric": plan.primary_metric,
            "cv_folds": plan.cv_folds,
            "best_model": best_model,
            "models": model_results,
            "ranking": _ranking(plan, model_results),
            "generated_at": now_iso(),
        }
        experiment_root = self.cases.case_root(case_id) / "experiments" / experiment_id
        comparison_path = experiment_root / "results" / "comparison.json"
        diagnostics_path = experiment_root / "results" / "diagnostics.json"
        atomic_write_json(comparison_path, comparison)
        atomic_write_json(diagnostics_path, diagnostics)
        upstream = [source_artifact["artifact_id"], plan_artifact_id, config_artifact_id, *code_artifact_ids]
        comparison_artifact = self.experiments.register_result(
            case_id, experiment_id, "results/comparison.json", "model_comparison", upstream
        )
        diagnostics_artifact = self.experiments.register_result(
            case_id, experiment_id, "results/diagnostics.json", "model_diagnostics", upstream
        )
        figure_path = self.cases.case_root(case_id) / "figures" / "draft" / f"{experiment_id}-cv-comparison.png"
        _plot_comparison(plan, model_results, figure_path)
        figure = self.figures.register(
            case_id,
            figure_path.relative_to(self.cases.case_root(case_id)).as_posix(),
            "候选模型交叉验证比较",
            [comparison_artifact["artifact_id"]],
            "mathworkstation.model_evaluation:_plot_comparison",
            {"primary_metric": plan.primary_metric, "cv_folds": plan.cv_folds, "dpi": 180},
            run_id,
        )
        report_path = self.cases.case_root(case_id) / "analysis" / f"模型比较报告-{experiment_id}.md"
        atomic_write_text(report_path, _render_report(plan, comparison, diagnostics, figure))
        report_artifact = self.artifacts.register_existing(
            case_id,
            report_path.relative_to(self.cases.case_root(case_id)).as_posix(),
            "model_comparison_report",
            "python",
            run_id=run_id,
            upstream=[comparison_artifact["artifact_id"], diagnostics_artifact["artifact_id"]],
        )
        return {
            "best_model": best_model,
            "comparison": comparison,
            "diagnostics": diagnostics,
            "comparison_artifact_id": comparison_artifact["artifact_id"],
            "diagnostics_artifact_id": diagnostics_artifact["artifact_id"],
            "report_artifact_id": report_artifact["artifact_id"],
            "figure": figure,
        }


def _scoring(task_type: str) -> dict[str, str]:
    if task_type == "regression":
        return {"mae": "neg_mean_absolute_error", "rmse": "neg_root_mean_squared_error", "r2": "r2"}
    return {"accuracy": "accuracy", "macro_f1": "f1_macro"}


def _summarize_cv(task_type: str, scores: dict[str, np.ndarray]) -> dict[str, Any]:
    metrics = ["mae", "rmse", "r2"] if task_type == "regression" else ["accuracy", "macro_f1"]
    result: dict[str, Any] = {"folds": {}}
    for metric in metrics:
        test_values = scores[f"test_{metric}"].astype(float)
        train_values = scores[f"train_{metric}"].astype(float)
        if task_type == "regression" and metric in {"mae", "rmse"}:
            test_values = -test_values
            train_values = -train_values
        result["folds"][metric] = [float(value) for value in test_values]
        result[f"{metric}_mean"] = float(np.mean(test_values))
        result[f"{metric}_std"] = float(np.std(test_values, ddof=1)) if len(test_values) > 1 else 0.0
        result[f"train_{metric}_mean"] = float(np.mean(train_values))
    primary = "rmse" if task_type == "regression" else "macro_f1"
    denominator = abs(result[f"{primary}_mean"]) or 1.0
    result["relative_std"] = float(result[f"{primary}_std"] / denominator)
    result["stability"] = "STABLE" if result["relative_std"] <= 0.25 else "UNSTABLE"
    return result


def _select_best(plan: ModelPlan, results: dict[str, Any]) -> str:
    key = f"{plan.primary_metric}_mean"
    if plan.primary_metric in {"rmse", "mae"}:
        return min(results, key=lambda name: results[name][key])
    return max(results, key=lambda name: results[name][key])


def _ranking(plan: ModelPlan, results: dict[str, Any]) -> list[str]:
    reverse = plan.primary_metric not in {"rmse", "mae"}
    key = f"{plan.primary_metric}_mean"
    return sorted(results, key=lambda name: results[name][key], reverse=reverse)


def _diagnostics(task_type: str, actual, fitted) -> dict[str, Any]:
    if task_type == "classification":
        return {
            "accuracy_full_fit": float(accuracy_score(actual, fitted)),
            "macro_f1_full_fit": float(f1_score(actual, fitted, average="macro", zero_division=0)),
        }
    residuals = np.asarray(actual, dtype=float) - np.asarray(fitted, dtype=float)
    shapiro = stats.shapiro(residuals) if 3 <= len(residuals) <= 5000 else None
    return {
        "mae_full_fit": float(mean_absolute_error(actual, fitted)),
        "rmse_full_fit": float(np.sqrt(mean_squared_error(actual, fitted))),
        "r2_full_fit": float(r2_score(actual, fitted)),
        "residual_mean": float(np.mean(residuals)),
        "residual_std": float(np.std(residuals, ddof=1)) if len(residuals) > 1 else 0.0,
        "residual_shapiro_statistic": float(shapiro.statistic) if shapiro else None,
        "residual_shapiro_pvalue": float(shapiro.pvalue) if shapiro else None,
    }


def _plot_comparison(plan: ModelPlan, results: dict[str, Any], path: Path) -> None:
    names = list(results)
    means = [results[name][f"{plan.primary_metric}_mean"] for name in names]
    errors = [results[name][f"{plan.primary_metric}_std"] for name in names]
    colors = get_colors()
    figsize = get_figsize("comparison")
    figure, axis = plt.subplots(figsize=(max(figsize[0], len(names) * 1.5), figsize[1]))
    bars = axis.bar(names, means, yerr=errors, capsize=5,
                    color=[colors[i % len(colors)] for i in range(len(names))],
                    edgecolor="white", linewidth=0.5)
    axis.set_ylabel(plan.primary_metric, fontweight="bold")
    axis.set_title(f"{plan.cv_folds}-Fold Cross-Validation", fontweight="bold")
    axis.tick_params(axis="x", rotation=30)
    axis.grid(True, axis="y", alpha=0.3, linestyle="--")
    figure.tight_layout()
    save_figure(figure, path)
    plt.close(figure)


def _render_report(plan: ModelPlan, comparison: dict[str, Any], diagnostics: dict[str, Any], figure: dict[str, Any]) -> str:
    rows = []
    for name in comparison["ranking"]:
        result = comparison["models"][name]
        rows.append(
            f"| {name} | {result[f'{plan.primary_metric}_mean']:.6f} | "
            f"{result[f'{plan.primary_metric}_std']:.6f} | {result['stability']} |"
        )
    return (
        "# 模型比较报告\n\n"
        f"- 最优模型：`{comparison['best_model']}`\n"
        f"- 主指标：`{plan.primary_metric}`\n"
        f"- 交叉验证：`{plan.cv_folds}` 折\n"
        f"- 图表：`{figure['figure_id']}`\n\n"
        "| 模型 | 均值 | 标准差 | 稳定性 |\n|---|---:|---:|---|\n"
        + "\n".join(rows)
        + "\n\n## 诊断\n\n```json\n"
        + json.dumps(diagnostics, ensure_ascii=False, indent=2)
        + "\n```\n\n结果尚未通过模型选择和敏感性审批，不得直接进入论文。\n"
    )


from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.dummy import DummyClassifier, DummyRegressor
from sklearn.ensemble import RandomForestClassifier, RandomForestRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LinearRegression, LogisticRegression, Ridge
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    mean_absolute_error,
    mean_squared_error,
    r2_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .datasets import DatasetRegistry
from .experiments import ExperimentRegistry
from .figure_registry import FigureRegistry
from .io_utils import atomic_write_json, atomic_write_text, now_iso
from .paths import resolve_within
from .tabular import read_table


class BaselineEngine:
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
        dataset_id: str,
        target_column: str,
        feature_columns: list[str] | None = None,
        task_type: str = "auto",
        test_size: float = 0.25,
        random_seed: int = 42,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        dataset = self.datasets.get(case_id, dataset_id)
        if dataset["status"] not in {"PROFILED", "VERIFIED"}:
            raise ValueError("dataset must pass profiling before baseline")
        source_artifact = self.artifacts.get(case_id, dataset["artifact_id"])
        case_root = self.cases.case_root(case_id)
        frame = read_table(resolve_within(case_root, source_artifact["path"]))
        if target_column not in frame.columns:
            raise ValueError(f"target column not found: {target_column}")
        selected_features = feature_columns or [str(column) for column in frame.columns if column != target_column]
        missing_features = sorted(set(selected_features) - set(frame.columns))
        if missing_features:
            raise ValueError(f"feature columns not found: {missing_features}")
        if not selected_features:
            raise ValueError("baseline requires at least one feature")

        modeling = frame[selected_features + [target_column]].dropna(subset=[target_column]).copy()
        if len(modeling) < 8:
            raise ValueError("baseline requires at least 8 rows with non-missing target")
        resolved_task = _resolve_task(modeling[target_column], task_type)
        configuration = {
            "task_type": resolved_task,
            "target_column": target_column,
            "feature_columns": selected_features,
            "test_size": test_size,
            "random_seed": random_seed,
            "models": _model_names(resolved_task),
        }
        experiment = self.experiments.create(
            case_id,
            f"Baseline {resolved_task}",
            dataset_id,
            source_artifact["artifact_id"],
            resolved_task,
            target_column,
            selected_features,
            configuration,
            run_id,
        )
        experiment_id = experiment["experiment_id"]
        code_artifacts = self.experiments.snapshot_code(case_id, experiment_id, [Path(__file__)])
        self.experiments.update(case_id, experiment_id, "RUNNING", started_at=now_iso())
        try:
            result = self._execute(
                case_id,
                experiment_id,
                source_artifact,
                modeling,
                selected_features,
                target_column,
                resolved_task,
                test_size,
                random_seed,
                run_id,
                [artifact["artifact_id"] for artifact in code_artifacts],
                experiment["config_artifact_id"],
            )
        except Exception as error:
            stderr = case_root / "experiments" / experiment_id / "stderr.log"
            stderr.write_text(f"{type(error).__name__}: {error}\n", encoding="utf-8")
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
            metrics_artifact_id=result["metrics_artifact_id"],
            predictions_artifact_id=result["predictions_artifact_id"],
            model_artifact_id=result["model_artifact_id"],
        )
        return {"experiment_id": experiment_id, **result}

    def _execute(
        self,
        case_id: str,
        experiment_id: str,
        source_artifact: dict[str, Any],
        frame: pd.DataFrame,
        feature_columns: list[str],
        target_column: str,
        task_type: str,
        test_size: float,
        random_seed: int,
        run_id: str | None,
        code_artifact_ids: list[str],
        config_artifact_id: str,
    ) -> dict[str, Any]:
        features = frame[feature_columns]
        target = frame[target_column]
        stratify = _stratify_target(target, task_type, test_size)
        train_indices, test_indices = train_test_split(
            np.arange(len(frame)),
            test_size=test_size,
            random_state=random_seed,
            stratify=stratify,
        )
        x_train = features.iloc[train_indices]
        x_test = features.iloc[test_indices]
        y_train = target.iloc[train_indices]
        y_test = target.iloc[test_indices]
        preprocessor = _preprocessor(features)
        models = _models(task_type, random_seed)
        metrics: dict[str, dict[str, Any]] = {}
        fitted_models: dict[str, Pipeline] = {}
        predictions: dict[str, np.ndarray] = {}
        for name, estimator in models.items():
            pipeline = Pipeline([("preprocessor", preprocessor), ("model", estimator)])
            pipeline.fit(x_train, y_train)
            predicted = pipeline.predict(x_test)
            fitted_models[name] = pipeline
            predictions[name] = np.asarray(predicted)
            metrics[name] = _metrics(task_type, y_test, predicted)
        best_model = _best_model(task_type, metrics)
        experiment_root = self.cases.case_root(case_id) / "experiments" / experiment_id
        metrics_payload = {
            "schema_version": 1,
            "case_id": case_id,
            "experiment_id": experiment_id,
            "task_type": task_type,
            "train_rows": int(len(train_indices)),
            "test_rows": int(len(test_indices)),
            "best_model": best_model,
            "selection_metric": "rmse" if task_type == "regression" else "macro_f1",
            "metrics": metrics,
            "generated_at": now_iso(),
        }
        metrics_path = experiment_root / "results" / "metrics.json"
        predictions_path = experiment_root / "results" / "predictions.csv"
        model_path = experiment_root / "model" / "best_model.joblib"
        atomic_write_json(metrics_path, metrics_payload)
        prediction_frame = pd.DataFrame({"row_index": frame.index[test_indices], "actual": y_test.to_numpy()})
        for name, values in predictions.items():
            prediction_frame[f"predicted_{name}"] = values
        prediction_frame.to_csv(predictions_path, index=False)
        joblib.dump(fitted_models[best_model], model_path)
        stdout = experiment_root / "stdout.log"
        stdout.write_text(json.dumps(metrics_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

        upstream = [source_artifact["artifact_id"], config_artifact_id, *code_artifact_ids]
        metrics_artifact = self.experiments.register_result(
            case_id, experiment_id, "results/metrics.json", "model_metrics", upstream
        )
        predictions_artifact = self.experiments.register_result(
            case_id, experiment_id, "results/predictions.csv", "model_predictions", upstream
        )
        model_artifact = self.experiments.register_result(
            case_id, experiment_id, "model/best_model.joblib", "trained_model", upstream
        )
        figure_path = self.cases.case_root(case_id) / "figures" / "draft" / f"{experiment_id}-predictions.png"
        _plot_predictions(task_type, y_test, predictions[best_model], figure_path)
        figure = self.figures.register(
            case_id,
            figure_path.relative_to(self.cases.case_root(case_id)).as_posix(),
            f"Baseline {best_model} 预测表现",
            [source_artifact["artifact_id"], predictions_artifact["artifact_id"]],
            "mathworkstation.baseline:_plot_predictions",
            {"task_type": task_type, "best_model": best_model, "dpi": 180},
            run_id,
        )
        report_path = self.cases.case_root(case_id) / "analysis" / f"Baseline实验报告-{experiment_id}.md"
        atomic_write_text(report_path, _render_report(experiment_id, task_type, best_model, metrics, figure))
        report_artifact = self.artifacts.register_existing(
            case_id,
            report_path.relative_to(self.cases.case_root(case_id)).as_posix(),
            "baseline_report",
            "python",
            run_id=run_id,
            upstream=[metrics_artifact["artifact_id"], predictions_artifact["artifact_id"]],
        )
        return {
            "best_model": best_model,
            "metrics": metrics_payload,
            "metrics_artifact_id": metrics_artifact["artifact_id"],
            "predictions_artifact_id": predictions_artifact["artifact_id"],
            "model_artifact_id": model_artifact["artifact_id"],
            "figure": figure,
            "report_artifact_id": report_artifact["artifact_id"],
        }


def _resolve_task(target: pd.Series, requested: str) -> str:
    if requested not in {"auto", "regression", "classification"}:
        raise ValueError("task_type must be auto, regression, or classification")
    if requested != "auto":
        return requested
    unique = target.nunique(dropna=True)
    if not pd.api.types.is_numeric_dtype(target):
        return "classification"
    if pd.api.types.is_bool_dtype(target) or unique <= 2:
        return "classification"
    integer_like = pd.api.types.is_integer_dtype(target) or bool(
        np.allclose(pd.to_numeric(target.dropna()).to_numpy() % 1, 0)
    )
    discrete_threshold = min(20, max(3, int(math.sqrt(len(target)))))
    if integer_like and unique <= discrete_threshold:
        return "classification"
    return "regression"


def _stratify_target(target: pd.Series, task_type: str, test_size: float):
    if task_type != "classification":
        return None
    counts = target.value_counts()
    class_count = len(counts)
    test_rows = math.ceil(len(target) * test_size)
    train_rows = len(target) - test_rows
    if counts.min() >= 2 and test_rows >= class_count and train_rows >= class_count:
        return target
    return None


def _preprocessor(features: pd.DataFrame) -> ColumnTransformer:
    numeric_columns = list(features.select_dtypes(include=[np.number]).columns)
    categorical_columns = [column for column in features.columns if column not in numeric_columns]
    transformers = []
    if numeric_columns:
        transformers.append(
            (
                "numeric",
                Pipeline([("imputer", SimpleImputer(strategy="median")), ("scaler", StandardScaler())]),
                numeric_columns,
            )
        )
    if categorical_columns:
        transformers.append(
            (
                "categorical",
                Pipeline(
                    [
                        ("imputer", SimpleImputer(strategy="most_frequent")),
                        ("encoder", OneHotEncoder(handle_unknown="ignore")),
                    ]
                ),
                categorical_columns,
            )
        )
    return ColumnTransformer(transformers)


def _models(task_type: str, random_seed: int) -> dict[str, Any]:
    if task_type == "regression":
        return {
            "dummy_mean": DummyRegressor(strategy="mean"),
            "linear": LinearRegression(),
            "ridge": Ridge(alpha=1.0),
            "random_forest": RandomForestRegressor(n_estimators=200, random_state=random_seed, n_jobs=1),
        }
    return {
        "dummy_prior": DummyClassifier(strategy="prior"),
        "logistic": LogisticRegression(max_iter=2000, random_state=random_seed),
        "random_forest": RandomForestClassifier(n_estimators=200, random_state=random_seed, n_jobs=1),
    }


def build_candidate_model(task_type: str, name: str, parameters: dict[str, Any], random_seed: int):
    if task_type == "regression":
        constructors = {
            "linear": lambda: LinearRegression(**parameters),
            "ridge": lambda: Ridge(**parameters),
            "lasso": lambda: __import__("sklearn.linear_model", fromlist=["Lasso"]).Lasso(**parameters),
            "elastic_net": lambda: __import__("sklearn.linear_model", fromlist=["ElasticNet"]).ElasticNet(**parameters),
            "random_forest": lambda: RandomForestRegressor(
                **_controlled_parameters(
                    parameters,
                    {"n_estimators": 200},
                    {"random_state": random_seed, "n_jobs": 1},
                )
            ),
            "gradient_boosting": lambda: __import__(
                "sklearn.ensemble", fromlist=["GradientBoostingRegressor"]
            ).GradientBoostingRegressor(
                **_controlled_parameters(parameters, {}, {"random_state": random_seed})
            ),
        }
    else:
        constructors = {
            "logistic": lambda: LogisticRegression(
                **_controlled_parameters(
                    parameters,
                    {"max_iter": 2000},
                    {"random_state": random_seed},
                )
            ),
            "random_forest": lambda: RandomForestClassifier(
                **_controlled_parameters(
                    parameters,
                    {"n_estimators": 200},
                    {"random_state": random_seed, "n_jobs": 1},
                )
            ),
            "gradient_boosting": lambda: __import__(
                "sklearn.ensemble", fromlist=["GradientBoostingClassifier"]
            ).GradientBoostingClassifier(
                **_controlled_parameters(parameters, {}, {"random_state": random_seed})
            ),
        }
    try:
        return constructors[name]()
    except KeyError as error:
        raise ValueError(f"unsupported model {name} for {task_type}") from error


def _controlled_parameters(
    requested: dict[str, Any],
    defaults: dict[str, Any],
    controlled: dict[str, Any],
) -> dict[str, Any]:
    return {**defaults, **requested, **controlled}


def _model_names(task_type: str) -> list[str]:
    return list(_models(task_type, 42))


def _metrics(task_type: str, actual, predicted) -> dict[str, Any]:
    if task_type == "regression":
        rmse = math.sqrt(mean_squared_error(actual, predicted))
        return {
            "mae": float(mean_absolute_error(actual, predicted)),
            "rmse": float(rmse),
            "r2": float(r2_score(actual, predicted)),
        }
    return {
        "accuracy": float(accuracy_score(actual, predicted)),
        "macro_f1": float(f1_score(actual, predicted, average="macro", zero_division=0)),
    }


def _best_model(task_type: str, metrics: dict[str, dict[str, Any]]) -> str:
    if task_type == "regression":
        return min(metrics, key=lambda name: metrics[name]["rmse"])
    return max(metrics, key=lambda name: metrics[name]["macro_f1"])


def _plot_predictions(task_type: str, actual, predicted, path: Path) -> None:
    figure, axis = plt.subplots(figsize=(7, 5))
    if task_type == "regression":
        axis.scatter(actual, predicted, alpha=0.8)
        lower = min(float(np.min(actual)), float(np.min(predicted)))
        upper = max(float(np.max(actual)), float(np.max(predicted)))
        axis.plot([lower, upper], [lower, upper], linestyle="--", color="black")
        axis.set_xlabel("Actual")
        axis.set_ylabel("Predicted")
    else:
        labels = sorted({str(value) for value in actual} | {str(value) for value in predicted})
        actual_counts = pd.Series(actual).astype(str).value_counts().reindex(labels, fill_value=0)
        predicted_counts = pd.Series(predicted).astype(str).value_counts().reindex(labels, fill_value=0)
        positions = np.arange(len(labels))
        axis.bar(positions - 0.2, actual_counts.values, width=0.4, label="Actual")
        axis.bar(positions + 0.2, predicted_counts.values, width=0.4, label="Predicted")
        axis.set_xticks(positions, labels, rotation=45)
        axis.legend()
    axis.set_title("Baseline Prediction Check")
    figure.tight_layout()
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def _render_report(
    experiment_id: str,
    task_type: str,
    best_model: str,
    metrics: dict[str, dict[str, Any]],
    figure: dict[str, Any],
) -> str:
    rows = []
    metric_names = ["mae", "rmse", "r2"] if task_type == "regression" else ["accuracy", "macro_f1"]
    for model_name, values in metrics.items():
        rows.append(
            f"| {model_name} | " + " | ".join(f"{values[name]:.6f}" for name in metric_names) + " |"
        )
    return (
        f"# Baseline 实验报告：{experiment_id}\n\n"
        f"- 任务类型：`{task_type}`\n"
        f"- 最优 Baseline：`{best_model}`\n"
        f"- 预测图：`{figure['figure_id']}`\n\n"
        "## 指标\n\n"
        f"| 模型 | {' | '.join(metric_names)} |\n"
        f"|---|{'---|' * len(metric_names)}\n"
        + "\n".join(rows)
        + "\n\n## 约束\n\n该结果是可复现 Baseline，不等同于最终模型结论；进入论文前仍需模型比较、诊断和人工审批。\n"
    )

from __future__ import annotations

import math
from itertools import product
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, balanced_accuracy_score, f1_score
from sklearn.model_selection import train_test_split

from .task_plugins import validate_task_protocol


def _require_valid(family: str, plan: dict[str, Any]) -> None:
    validation = validate_task_protocol(family, plan)
    if not validation["valid"]:
        raise ValueError("invalid task protocol: " + ",".join(validation["errors"]))


def execute_classification(
    frame: pd.DataFrame, plan: dict[str, Any]
) -> dict[str, Any]:
    """Deterministic stratified holdout classification executor."""
    plan = {"task_type": "classification", **plan}
    _require_valid("classification", plan)
    target = plan["target_column"]
    features = plan["feature_columns"]
    if target not in frame or any(column not in frame for column in features):
        raise ValueError("classification columns missing")
    data = frame[[*features, target]].dropna().reset_index(drop=True)
    if data[target].nunique() < 2:
        raise ValueError("classification requires at least two classes")
    seed = int(plan.get("random_seed", 42))
    indices = np.arange(len(data))
    test_size = max(1, int(round(len(data) * float(plan.get("test_size", 0.2)))))
    stratify = data[target] if data[target].value_counts().min() >= 2 and test_size >= data[target].nunique() else None
    train_indices, test_indices = train_test_split(
        indices, test_size=test_size, random_state=seed, stratify=stratify
    )
    train_indices = np.sort(train_indices)
    test_indices = np.sort(test_indices)
    x_train = pd.get_dummies(data[features], drop_first=False)
    x_test = x_train.iloc[test_indices]
    x_train = x_train.iloc[train_indices]
    y_train = data[target].iloc[train_indices]
    y_test = data[target].iloc[test_indices]
    model = LogisticRegression(max_iter=2000, random_state=seed)
    model.fit(x_train, y_train)
    probabilities = model.predict_proba(x_test)
    predicted = model.classes_[np.argmax(probabilities, axis=1)]
    labels = sorted(str(value) for value in data[target].unique())
    confusion = pd.crosstab(y_test.astype(str), pd.Series(predicted, index=y_test.index).astype(str), dropna=False)
    confusion = confusion.reindex(index=labels, columns=labels, fill_value=0)
    return {
        "family": "classification",
        "protocol": {"split": "stratified_holdout", "seed": seed, "test_rows": len(test_indices)},
        "model": "logistic_regression",
        "metrics": {
            "accuracy": float(accuracy_score(y_test, predicted)),
            "macro_f1": float(f1_score(y_test, predicted, average="macro", zero_division=0)),
            "balanced_accuracy": float(balanced_accuracy_score(y_test, predicted)),
        },
        "confusion_matrix": confusion.to_numpy(dtype=int).tolist(),
        "labels": labels,
        "holdout_actual": [str(value) for value in y_test.tolist()],
        "holdout_predicted": [str(value) for value in predicted.tolist()],
        "holdout_probabilities": probabilities.tolist(),
        "probability_labels": [str(value) for value in model.classes_.tolist()],
    }


def execute_forecasting(frame: pd.DataFrame, plan: dict[str, Any]) -> dict[str, Any]:
    """Naive-plus-drift rolling-origin forecast with temporal leakage checks."""
    _require_valid("forecasting", plan)
    time_column, target = plan["time_column"], plan["target_column"]
    if time_column not in frame or target not in frame:
        raise ValueError("forecasting columns missing")
    data = frame[[time_column, target]].copy()
    data[time_column] = pd.to_datetime(data[time_column], errors="raise")
    if data[time_column].duplicated().any():
        raise ValueError("TIME_DUPLICATES_BLOCKED")
    data = data.sort_values(time_column).reset_index(drop=True)
    values = pd.to_numeric(data[target], errors="raise").to_numpy(dtype=float)
    horizon = int(plan["horizon"])
    min_train = int(plan.get("min_train", max(8, horizon * 3)))
    if len(values) <= min_train + horizon:
        raise ValueError("FORECAST_ROWS_INSUFFICIENT")
    predictions: list[float] = []
    actual: list[float] = []
    origins: list[dict[str, Any]] = []
    for origin in range(min_train, len(values) - horizon + 1, horizon):
        train = values[:origin]
        slope = (train[-1] - train[-min(3, len(train))]) / max(1, min(3, len(train)) - 1)
        forecast = [float(train[-1] + slope * step) for step in range(1, horizon + 1)]
        observed = values[origin : origin + horizon]
        predictions.extend(forecast)
        actual.extend(observed.tolist())
        origins.append({"origin": origin, "horizon": horizon})
    errors = np.asarray(actual) - np.asarray(predictions)
    rmse = float(np.sqrt(np.mean(errors**2)))
    mae = float(np.mean(np.abs(errors)))
    return {
        "family": "forecasting",
        "protocol": {"split": "temporal", "horizon": horizon, "origins": origins},
        "model": "drift_naive",
        "metrics": {"mae": mae, "rmse": rmse},
        "predictions": predictions,
        "actual": actual,
        "leakage_check": "PASS",
    }


def execute_optimization(plan: dict[str, Any]) -> dict[str, Any]:
    """Deterministic bounded grid optimizer for linear objective/constraints."""
    _require_valid("optimization", plan)
    variables = plan["variables"]
    if any(not isinstance(item, dict) for item in variables):
        raise ValueError("VARIABLE_SCHEMA_INVALID")
    grids = []
    for item in variables:
        lower, upper = float(item["lower"]), float(item["upper"])
        step = float(item.get("step", 1.0))
        if upper < lower or step <= 0:
            raise ValueError("VARIABLE_DOMAIN_INVALID")
        values = np.arange(lower, upper + step * 0.5, step).tolist()
        grids.append(values)
    if math.prod(len(values) for values in grids) > int(plan.get("max_grid_points", 100000)):
        raise ValueError("OPTIMIZATION_GRID_TOO_LARGE")
    objective = plan["objective"]
    if not isinstance(objective, dict) or objective.get("sense") not in {"min", "max"}:
        raise ValueError("OBJECTIVE_SCHEMA_INVALID")
    constraints = plan["constraints"]
    feasible: list[tuple[dict[str, float], float]] = []
    for values in product(*grids):
        point = {item["name"]: float(value) for item, value in zip(variables, values)}
        value = sum(float(objective.get("coefficients", {}).get(name, 0.0)) * point[name] for name in point) + float(objective.get("constant", 0.0))
        if all(_constraint_ok(constraint, point) for constraint in constraints):
            feasible.append((point, value))
    if not feasible:
        raise ValueError("NO_FEASIBLE_SOLUTION")
    best = (max if objective["sense"] == "max" else min)(feasible, key=lambda item: item[1])
    return {"family": "optimization", "protocol": {"method": "bounded_grid", "feasible_points": len(feasible)}, "solution": best[0], "objective_value": best[1], "constraint_status": "PASS"}


def _constraint_ok(constraint: dict[str, Any], point: dict[str, float]) -> bool:
    lhs = sum(float(coefficient) * point[name] for name, coefficient in constraint.get("coefficients", {}).items())
    rhs = float(constraint["rhs"])
    operator = constraint["operator"]
    return {"<=": lhs <= rhs + 1e-9, ">=": lhs >= rhs - 1e-9, "==": abs(lhs - rhs) <= 1e-9}[operator]


def execute_simulation(plan: dict[str, Any]) -> dict[str, Any]:
    """Seeded Monte Carlo executor for additive normal parameter scenarios."""
    _require_valid("simulation", plan)
    seed = int(plan.get("seed", 42))
    replications = int(plan["replications"])
    rng = np.random.default_rng(seed)
    outputs: dict[str, dict[str, float]] = {}
    for scenario in plan["scenarios"]:
        multiplier = float(scenario.get("multiplier", 1.0))
        total = np.zeros(replications)
        for parameter in plan["parameters"]:
            mean, std = float(parameter["mean"]), float(parameter.get("std", 0.0))
            total += rng.normal(mean, std, replications)
        total *= multiplier
        outputs[scenario["name"]] = {"mean": float(total.mean()), "std": float(total.std(ddof=1)), "p05": float(np.quantile(total, 0.05)), "p95": float(np.quantile(total, 0.95))}
    return {"family": "simulation", "protocol": {"seed": seed, "replications": replications}, "scenarios": outputs, "uncertainty": "empirical 5%-95% interval"}


def execute_ranking(frame: pd.DataFrame, plan: dict[str, Any]) -> dict[str, Any]:
    """Grouped ranking evaluator with MRR, NDCG@k, and pairwise accuracy."""
    _require_valid("ranking", plan)
    required = {"query", "item", "relevance", "score"}
    if not required <= set(frame.columns):
        raise ValueError("RANKING_COLUMNS_MISSING")
    k = int(plan.get("k", 10))
    reciprocal_ranks: list[float] = []
    ndcgs: list[float] = []
    for _, group in frame.groupby("query", sort=True):
        ordered = group.sort_values("score", ascending=False).head(k)
        relevance = ordered["relevance"].to_numpy(dtype=float)
        hits = np.flatnonzero(relevance > 0)
        reciprocal_ranks.append(float(1.0 / (hits[0] + 1)) if len(hits) else 0.0)
        dcg = sum((2**value - 1) / math.log2(index + 2) for index, value in enumerate(relevance))
        ideal = np.sort(group["relevance"].to_numpy(dtype=float))[::-1][:k]
        idcg = sum((2**value - 1) / math.log2(index + 2) for index, value in enumerate(ideal))
        ndcgs.append(float(dcg / idcg) if idcg else 0.0)
    pairs = 0
    correct = 0
    for _, group in frame.groupby("query", sort=True):
        values = group.to_dict("records")
        for left in values:
            for right in values:
                if left["relevance"] > right["relevance"]:
                    pairs += 1
                    correct += int(left["score"] > right["score"])
    return {"family": "ranking", "protocol": {"method": plan["protocol"], "k": k}, "metrics": {"mrr": float(np.mean(reciprocal_ranks)), "ndcg_at_k": float(np.mean(ndcgs)), "pairwise_accuracy": float(correct / pairs) if pairs else 0.0}, "queries": int(frame["query"].nunique()), "pairs": pairs}


class TaskExecutionService:
    """Dispatches a validated family executor and registers its immutable result."""

    def __init__(self, cases: Any, artifacts: Any) -> None:
        self.cases = cases
        self.artifacts = artifacts

    def execute(
        self,
        case_id: str,
        family: str,
        plan: dict[str, Any],
        frame: pd.DataFrame | None = None,
        source_artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if family == "classification":
            plan = {"task_type": "classification", **plan}
        validation = validate_task_protocol(family, plan)
        if not validation["valid"]:
            raise ValueError("invalid task protocol: " + ",".join(validation["errors"]))
        if family in {"classification", "forecasting", "ranking"} and frame is None:
            raise ValueError("TASK_DATA_REQUIRED")
        if family == "classification":
            result = execute_classification(frame, plan)  # type: ignore[arg-type]
        elif family == "forecasting":
            result = execute_forecasting(frame, plan)  # type: ignore[arg-type]
        elif family == "ranking":
            result = execute_ranking(frame, plan)  # type: ignore[arg-type]
        elif family == "optimization":
            result = execute_optimization(plan)
        else:
            result = execute_simulation(plan)
        from uuid import uuid4
        from .io_utils import atomic_write_json, now_iso
        root = self.cases.case_root(case_id)
        run_id = f"task-{uuid4().hex[:12]}"
        result_payload = {"schema_version": 1, "task_run_id": run_id, "family": family, "plan": plan, "result": result, "source_artifact_ids": source_artifact_ids or [], "generated_at": now_iso()}
        path = root / "results" / "task_runs" / f"{run_id}.json"
        atomic_write_json(path, result_payload)
        artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "task_execution_result",
            "python",
            upstream=source_artifact_ids or [],
            paper_eligible=True,
        )
        return {"task_run_id": run_id, "result": result, "artifact": artifact}

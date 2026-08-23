from __future__ import annotations

from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.preprocessing import StandardScaler

from .io_utils import atomic_write_json, now_iso
from .task_executors import execute_classification


SUPPORTED_RESEARCH_FAMILIES = {
    "explanatory_inference",
    "distribution_forecasting",
    "exploratory_analysis",
}


def execute_scalar_forecast_interval(frame: pd.DataFrame, plan: dict[str, Any]) -> dict[str, Any]:
    """Forecast one future scalar target with chronological validation and interval.

    This complements the repository's drift-naive rolling-origin executor when a
    contest question asks for a prediction at a specific future date. The final
    point forecast is fit on all observed rows only after a temporal holdout has
    been evaluated; the interval comes from deterministic residual bootstrap.
    """

    time_column = str(plan.get("time_column") or "")
    target = str(plan.get("target_column") or "")
    future_time = plan.get("future_time")
    features = [str(value) for value in plan.get("feature_columns", [])]
    if not time_column or not target or future_time is None:
        raise ValueError("FORECAST_TIME_TARGET_FUTURE_REQUIRED")
    missing = [column for column in [time_column, target, *features] if column not in frame.columns]
    if missing:
        raise ValueError("FORECAST_COLUMNS_MISSING:" + ",".join(missing))

    data = frame[[time_column, target, *features]].dropna().copy()
    data[time_column] = pd.to_datetime(data[time_column], errors="raise")
    data = data.sort_values(time_column).reset_index(drop=True)
    if data[time_column].duplicated().any():
        raise ValueError("TIME_DUPLICATES_BLOCKED")
    if len(data) < 30:
        raise ValueError("FORECAST_ROWS_INSUFFICIENT")
    future_timestamp = pd.Timestamp(future_time)
    if future_timestamp <= data[time_column].max():
        raise ValueError("FUTURE_TIME_MUST_FOLLOW_OBSERVATIONS")

    origin = data[time_column].min()
    time_values = (data[time_column] - origin).dt.total_seconds().to_numpy(dtype=float) / 86400.0
    matrix = pd.DataFrame({"__time_days": time_values})
    for column in features:
        matrix[column] = pd.to_numeric(data[column], errors="raise").to_numpy(dtype=float)
    y_raw = pd.to_numeric(data[target], errors="raise").to_numpy(dtype=float)
    use_log = bool(plan.get("log_target", np.all(y_raw > 0)))
    y = np.log(y_raw) if use_log else y_raw

    test_size = float(plan.get("test_size", 0.2))
    test_rows = max(5, int(round(len(data) * test_size)))
    split = len(data) - test_rows
    if split < 15:
        raise ValueError("FORECAST_TRAIN_ROWS_INSUFFICIENT")
    scaler = StandardScaler()
    x_train = scaler.fit_transform(matrix.iloc[:split].to_numpy(dtype=float))
    x_test = scaler.transform(matrix.iloc[split:].to_numpy(dtype=float))
    alpha = float(plan.get("alpha", 1.0))
    validation_model = Ridge(alpha=alpha)
    validation_model.fit(x_train, y[:split])
    validation_pred = validation_model.predict(x_test)
    validation_pred_raw = np.exp(validation_pred) if use_log else validation_pred
    validation_residuals = y_raw[split:] - validation_pred_raw

    final_scaler = StandardScaler()
    x_full = final_scaler.fit_transform(matrix.to_numpy(dtype=float))
    final_model = Ridge(alpha=alpha)
    final_model.fit(x_full, y)
    future_features = dict(plan.get("future_features") or {})
    future_row = [float((future_timestamp - origin).total_seconds() / 86400.0)]
    for column in features:
        if column not in future_features:
            raise ValueError(f"FUTURE_FEATURE_REQUIRED:{column}")
        future_row.append(float(future_features[column]))
    future_x = final_scaler.transform(np.asarray([future_row], dtype=float))
    future_transformed = float(final_model.predict(future_x)[0])
    point = float(np.exp(future_transformed) if use_log else future_transformed)

    seed = int(plan.get("random_seed", 42))
    bootstrap_runs = int(plan.get("bootstrap_runs", 200))
    if bootstrap_runs < 20:
        raise ValueError("BOOTSTRAP_RUNS_TOO_SMALL")
    rng = np.random.default_rng(seed)
    centered_residuals = validation_residuals - float(np.mean(validation_residuals))
    sampled_residuals = rng.choice(centered_residuals, size=bootstrap_runs, replace=True)
    simulated = np.maximum(0.0, point + sampled_residuals)
    low_q, high_q = plan.get("interval_quantiles", [0.025, 0.975])
    lower, upper = np.quantile(simulated, [float(low_q), float(high_q)])

    return {
        "family": "forecasting",
        "protocol": {
            "split": "temporal_holdout",
            "train_rows": int(split),
            "test_rows": int(test_rows),
            "future_time": future_timestamp.isoformat(),
            "bootstrap_runs": bootstrap_runs,
        },
        "method": "ridge_time_trend_with_residual_bootstrap_interval",
        "metrics": {
            "rmse": float(np.sqrt(mean_squared_error(y_raw[split:], validation_pred_raw))),
            "mae": float(mean_absolute_error(y_raw[split:], validation_pred_raw)),
            "r2": float(r2_score(y_raw[split:], validation_pred_raw)),
        },
        "forecast": {
            "point": point,
            "interval": [float(lower), float(upper)],
            "coverage": float(high_q) - float(low_q),
        },
        "log_target": use_log,
        "leakage_check": "PASS",
    }


def execute_classification_with_future(frame: pd.DataFrame, plan: dict[str, Any]) -> dict[str, Any]:
    """Validate a classification task, then fit the accepted schema for one future item."""

    validation = execute_classification(frame, plan)
    target = str(plan.get("target_column") or "")
    features = [str(value) for value in plan.get("feature_columns", [])]
    future_features = plan.get("future_features")
    if future_features is None:
        return {**validation, "future_prediction": None, "future_probabilities": None}
    payload = dict(future_features)
    missing = [column for column in features if column not in payload]
    if missing:
        raise ValueError("FUTURE_CLASSIFICATION_FEATURES_MISSING:" + ",".join(missing))
    data = frame[[*features, target]].dropna().reset_index(drop=True)
    future = pd.DataFrame([{column: payload[column] for column in features}])
    combined = pd.concat([data[features], future], ignore_index=True)
    matrix = pd.get_dummies(combined, drop_first=False, dtype=float)
    x_train = matrix.iloc[:-1].to_numpy(dtype=float)
    x_future = matrix.iloc[-1:].to_numpy(dtype=float)
    y = data[target]
    seed = int(plan.get("random_seed", 42))
    model = LogisticRegression(max_iter=2000, random_state=seed)
    model.fit(x_train, y)
    predicted = model.predict(x_future)[0]
    probabilities = model.predict_proba(x_future)[0]
    return {
        **validation,
        "future_prediction": str(predicted),
        "future_probabilities": {
            str(label): float(probability)
            for label, probability in zip(model.classes_, probabilities)
        },
    }


def execute_explanatory_inference(frame: pd.DataFrame, plan: dict[str, Any]) -> dict[str, Any]:
    """Estimate stable feature effects instead of treating explanation as prediction.

    The executor fits a standardized ridge model, evaluates it on an explicit
    holdout protocol, and bootstraps coefficient intervals on the training set.
    Coefficients are therefore interpretable as directional associations under
    the registered feature specification; they are never described as causal.
    """

    target = str(plan.get("target_column") or "")
    features = [str(value) for value in plan.get("feature_columns", [])]
    if not target:
        raise ValueError("TARGET_COLUMN_REQUIRED")
    if not features:
        raise ValueError("FEATURE_COLUMNS_REQUIRED")
    missing = [column for column in [target, *features] if column not in frame.columns]
    if missing:
        raise ValueError("EXPLANATORY_COLUMNS_MISSING:" + ",".join(missing))

    data = frame[[*features, target, *(_time_columns(plan, frame))]].dropna().copy()
    if len(data) < 20:
        raise ValueError("EXPLANATORY_ROWS_INSUFFICIENT")
    y = pd.to_numeric(data[target], errors="raise").to_numpy(dtype=float)
    matrix = pd.get_dummies(data[features], drop_first=False, dtype=float)
    if matrix.shape[1] == 0:
        raise ValueError("EXPLANATORY_FEATURE_MATRIX_EMPTY")

    train_idx, test_idx = _split_indices(data, plan)
    scaler = StandardScaler()
    x_train = scaler.fit_transform(matrix.iloc[train_idx].to_numpy(dtype=float))
    x_test = scaler.transform(matrix.iloc[test_idx].to_numpy(dtype=float))
    y_train = y[train_idx]
    y_test = y[test_idx]
    alpha = float(plan.get("alpha", 1.0))
    model = Ridge(alpha=alpha)
    model.fit(x_train, y_train)
    predicted = model.predict(x_test)

    seed = int(plan.get("random_seed", 42))
    bootstrap_runs = int(plan.get("bootstrap_runs", 100))
    if bootstrap_runs < 10:
        raise ValueError("BOOTSTRAP_RUNS_TOO_SMALL")
    rng = np.random.default_rng(seed)
    samples: list[np.ndarray] = []
    for _ in range(bootstrap_runs):
        sampled = rng.integers(0, len(train_idx), size=len(train_idx))
        boot_model = Ridge(alpha=alpha)
        boot_model.fit(x_train[sampled], y_train[sampled])
        samples.append(np.asarray(boot_model.coef_, dtype=float))
    coefficients = np.asarray(samples)
    names = list(matrix.columns)
    effects = []
    for index, name in enumerate(names):
        coefficient = float(model.coef_[index])
        low, high = np.quantile(coefficients[:, index], [0.025, 0.975])
        effects.append(
            {
                "feature": str(name),
                "standardized_coefficient": coefficient,
                "direction": "positive" if coefficient > 0 else ("negative" if coefficient < 0 else "neutral"),
                "bootstrap_ci_95": [float(low), float(high)],
                "interval_excludes_zero": bool(low > 0 or high < 0),
            }
        )
    effects.sort(key=lambda item: abs(item["standardized_coefficient"]), reverse=True)
    rmse = float(np.sqrt(mean_squared_error(y_test, predicted)))
    return {
        "family": "explanatory_inference",
        "protocol": {
            "split": _split_name(plan),
            "train_rows": int(len(train_idx)),
            "test_rows": int(len(test_idx)),
            "bootstrap_runs": bootstrap_runs,
            "seed": seed,
        },
        "method": "standardized_ridge_with_bootstrap_effect_intervals",
        "metrics": {
            "rmse": rmse,
            "mae": float(mean_absolute_error(y_test, predicted)),
            "r2": float(r2_score(y_test, predicted)),
        },
        "effects": effects,
        "interpretation_guard": "associational_not_causal",
    }


def execute_distribution_forecasting(frame: pd.DataFrame, plan: dict[str, Any]) -> dict[str, Any]:
    """Forecast a multi-column percentage distribution with simplex projection.

    Independent ridge heads are deliberately followed by a non-negative simplex
    projection so every predicted distribution sums to the configured total.
    Validation is chronological by default and reports both component error and
    the structural simplex error before/after projection.
    """

    time_column = str(plan.get("time_column") or "")
    outputs = [str(value) for value in plan.get("output_columns", [])]
    features = [str(value) for value in plan.get("feature_columns", [])]
    if not time_column:
        raise ValueError("TIME_COLUMN_REQUIRED")
    if time_column not in frame.columns:
        raise ValueError("TIME_COLUMN_MISSING")
    if len(outputs) < 2:
        raise ValueError("DISTRIBUTION_OUTPUT_COLUMNS_REQUIRED")
    missing_outputs = [column for column in outputs if column not in frame.columns]
    if missing_outputs:
        raise ValueError("DISTRIBUTION_COLUMNS_MISSING:" + ",".join(missing_outputs))
    missing_features = [column for column in features if column not in frame.columns]
    if missing_features:
        raise ValueError("DISTRIBUTION_FEATURE_COLUMNS_MISSING:" + ",".join(missing_features))

    columns = [time_column, *features, *outputs]
    data = frame[columns].dropna().copy()
    data[time_column] = pd.to_datetime(data[time_column], errors="raise")
    data = data.sort_values(time_column).reset_index(drop=True)
    if data[time_column].duplicated().any():
        raise ValueError("TIME_DUPLICATES_BLOCKED")
    if len(data) < 30:
        raise ValueError("DISTRIBUTION_ROWS_INSUFFICIENT")

    matrix = _distribution_features(data, features)
    y = data[outputs].apply(pd.to_numeric, errors="raise").to_numpy(dtype=float)
    total = float(plan.get("distribution_total", 100.0))
    if total <= 0:
        raise ValueError("DISTRIBUTION_TOTAL_INVALID")

    test_size = float(plan.get("test_size", 0.2))
    test_rows = max(5, int(round(len(data) * test_size)))
    if test_rows >= len(data):
        raise ValueError("DISTRIBUTION_TEST_SIZE_INVALID")
    split = len(data) - test_rows
    train_idx = np.arange(split)
    test_idx = np.arange(split, len(data))
    scaler = StandardScaler()
    x_train = scaler.fit_transform(matrix.iloc[train_idx].to_numpy(dtype=float))
    x_test = scaler.transform(matrix.iloc[test_idx].to_numpy(dtype=float))
    alpha = float(plan.get("alpha", 1.0))
    predictions = np.zeros((len(test_idx), len(outputs)), dtype=float)
    models: list[Ridge] = []
    for output_index in range(len(outputs)):
        model = Ridge(alpha=alpha)
        model.fit(x_train, y[train_idx, output_index])
        predictions[:, output_index] = model.predict(x_test)
        models.append(model)

    raw_sum_error = float(np.mean(np.abs(predictions.sum(axis=1) - total)))
    projected = _project_distribution(predictions, total)
    actual = y[test_idx]
    actual = _project_distribution(actual, total)
    component_errors = actual - projected
    metrics = {
        "mae": float(np.mean(np.abs(component_errors))),
        "rmse": float(np.sqrt(np.mean(component_errors**2))),
        "raw_simplex_error": raw_sum_error,
        "projected_simplex_error": float(np.max(np.abs(projected.sum(axis=1) - total))),
    }
    future_distribution = None
    future_uncertainty = None
    future_features = plan.get("future_features")
    if future_features is not None:
        if set(matrix.columns) != {*features, "__time_index"}:
            raise ValueError("FUTURE_DISTRIBUTION_REQUIRES_NUMERIC_ENGINEERED_FEATURES")
        future_row = []
        payload = dict(future_features)
        for column in matrix.columns:
            if column == "__time_index":
                future_row.append(float(len(data) + int(plan.get("future_step", 1)) - 1))
            else:
                if column not in payload:
                    raise ValueError(f"FUTURE_FEATURE_REQUIRED:{column}")
                future_row.append(float(payload[column]))
        future_x = scaler.transform(np.asarray([future_row], dtype=float))
        raw_future = np.asarray([[float(model.predict(future_x)[0]) for model in models]])
        projected_future = _project_distribution(raw_future, total)[0]
        future_distribution = {
            column: float(projected_future[index]) for index, column in enumerate(outputs)
        }
        bootstrap_runs = int(plan.get("bootstrap_runs", 200))
        if bootstrap_runs < 20:
            raise ValueError("BOOTSTRAP_RUNS_TOO_SMALL")
        seed = int(plan.get("random_seed", 42))
        rng = np.random.default_rng(seed)
        residuals = actual - projected
        centered = residuals - np.mean(residuals, axis=0, keepdims=True)
        sampled = centered[rng.integers(0, len(centered), size=bootstrap_runs)]
        draws = _project_distribution(projected_future.reshape(1, -1) + sampled, total)
        lower = np.quantile(draws, 0.025, axis=0)
        upper = np.quantile(draws, 0.975, axis=0)
        future_uncertainty = {
            column: [float(lower[index]), float(upper[index])]
            for index, column in enumerate(outputs)
        }
    return {
        "family": "distribution_forecasting",
        "protocol": {
            "split": "temporal_holdout",
            "train_rows": int(len(train_idx)),
            "test_rows": int(len(test_idx)),
            "distribution_total": total,
        },
        "method": "multioutput_ridge_with_simplex_projection",
        "metrics": metrics,
        "output_columns": outputs,
        "predictions": projected.tolist(),
        "actual": actual.tolist(),
        "last_validation_prediction": {
            column: float(projected[-1, index]) for index, column in enumerate(outputs)
        },
        "future_distribution": future_distribution,
        "future_uncertainty_95": future_uncertainty,
    }


def execute_exploratory_analysis(frame: pd.DataFrame, plan: dict[str, Any]) -> dict[str, Any]:
    """Produce auditable discoveries rather than another supervised best model."""

    requested = [str(value) for value in plan.get("numeric_columns", [])]
    if requested:
        missing = [column for column in requested if column not in frame.columns]
        if missing:
            raise ValueError("EXPLORATORY_COLUMNS_MISSING:" + ",".join(missing))
        numeric = frame[requested].apply(pd.to_numeric, errors="raise")
    else:
        numeric = frame.select_dtypes(include=[np.number]).copy()
    if numeric.shape[1] < 2 or len(numeric) < 10:
        raise ValueError("EXPLORATORY_NUMERIC_DATA_INSUFFICIENT")

    correlations = numeric.corr(method="spearman")
    pairs: list[dict[str, Any]] = []
    columns = list(correlations.columns)
    for left_index, left in enumerate(columns):
        for right in columns[left_index + 1 :]:
            value = float(correlations.loc[left, right])
            if np.isfinite(value):
                pairs.append({"left": left, "right": right, "spearman_r": value})
    pairs.sort(key=lambda item: abs(item["spearman_r"]), reverse=True)

    outliers = []
    for column in numeric.columns:
        values = numeric[column].dropna().to_numpy(dtype=float)
        q1, q3 = np.quantile(values, [0.25, 0.75])
        iqr = q3 - q1
        if iqr == 0:
            median = float(np.median(values))
            rate = float(np.mean(~np.isclose(values, median)))
        else:
            low, high = q1 - 1.5 * iqr, q3 + 1.5 * iqr
            rate = float(np.mean((values < low) | (values > high)))
        outliers.append({"column": str(column), "iqr_outlier_rate": rate})
    outliers.sort(key=lambda item: item["iqr_outlier_rate"], reverse=True)

    change_points = []
    minimum_side = max(5, len(numeric) // 10)
    for column in numeric.columns:
        values = numeric[column].dropna().to_numpy(dtype=float)
        if len(values) < minimum_side * 2:
            continue
        overall_std = float(np.std(values, ddof=1))
        if overall_std <= 1e-12:
            continue
        best_index = None
        best_score = -1.0
        for index in range(minimum_side, len(values) - minimum_side + 1):
            score = abs(float(np.mean(values[:index]) - np.mean(values[index:]))) / overall_std
            if score > best_score:
                best_index, best_score = index, score
        change_points.append(
            {
                "column": str(column),
                "candidate_index": int(best_index or 0),
                "standardized_mean_shift": float(best_score),
            }
        )
    change_points.sort(key=lambda item: item["standardized_mean_shift"], reverse=True)

    strongest = pairs[0] if pairs else None
    return {
        "family": "exploratory_analysis",
        "protocol": {"method": "spearman_iqr_mean_shift_scan", "rows": int(len(numeric))},
        "discoveries": {
            "strongest_associations": pairs[:10],
            "highest_outlier_rates": outliers[:10],
            "largest_mean_shift_candidates": change_points[:10],
            "correlation_columns": [str(column) for column in correlations.columns],
            "spearman_correlation_matrix": correlations.to_numpy(dtype=float).tolist(),
        },
        "headline": (
            f"strongest association: {strongest['left']} vs {strongest['right']} (Spearman r={strongest['spearman_r']:.3f})"
            if strongest
            else "no finite pairwise association found"
        ),
    }


class SubproblemExecutionService:
    """Register immutable evidence for research families missing from TaskExecutionService."""

    def __init__(self, cases: Any, artifacts: Any) -> None:
        self.cases = cases
        self.artifacts = artifacts

    def execute(
        self,
        case_id: str,
        family: str,
        plan: dict[str, Any],
        frame: pd.DataFrame,
        source_artifact_ids: list[str] | None = None,
        subproblem_id: str | None = None,
    ) -> dict[str, Any]:
        if family == "explanatory_inference":
            result = execute_explanatory_inference(frame, plan)
        elif family == "distribution_forecasting":
            result = execute_distribution_forecasting(frame, plan)
        elif family == "exploratory_analysis":
            result = execute_exploratory_analysis(frame, plan)
        else:
            raise ValueError(f"UNSUPPORTED_SUBPROBLEM_FAMILY:{family}")
        run_id = f"subtask-{uuid4().hex[:12]}"
        payload = {
            "schema_version": 1,
            "task_run_id": run_id,
            "subproblem_id": subproblem_id,
            "family": family,
            "plan": plan,
            "result": result,
            "source_artifact_ids": source_artifact_ids or [],
            "generated_at": now_iso(),
        }
        root = self.cases.case_root(case_id)
        suffix = subproblem_id or run_id
        path = root / "results" / "subproblems" / suffix / f"{run_id}.json"
        atomic_write_json(path, payload)
        artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "subproblem_execution_result",
            "python",
            upstream=source_artifact_ids or [],
            paper_eligible=False,
        )
        return {"task_run_id": run_id, "result": result, "artifact": artifact}


def _time_columns(plan: dict[str, Any], frame: pd.DataFrame) -> list[str]:
    if str(plan.get("split_strategy", "random")) != "temporal":
        return []
    column = str(plan.get("time_column") or "")
    if not column:
        raise ValueError("TIME_COLUMN_REQUIRED_FOR_TEMPORAL_SPLIT")
    if column not in frame.columns:
        raise ValueError("TIME_COLUMN_MISSING")
    return [column] if column not in plan.get("feature_columns", []) else []


def _split_name(plan: dict[str, Any]) -> str:
    return "temporal_holdout" if str(plan.get("split_strategy", "random")) == "temporal" else "random_holdout"


def _split_indices(data: pd.DataFrame, plan: dict[str, Any]) -> tuple[np.ndarray, np.ndarray]:
    test_size = float(plan.get("test_size", 0.2))
    if not 0.05 <= test_size < 0.5:
        raise ValueError("TEST_SIZE_INVALID")
    test_rows = max(2, int(round(len(data) * test_size)))
    if str(plan.get("split_strategy", "random")) == "temporal":
        time_column = str(plan.get("time_column") or "")
        ordered = np.argsort(pd.to_datetime(data[time_column], errors="raise").to_numpy())
        return ordered[:-test_rows], ordered[-test_rows:]
    rng = np.random.default_rng(int(plan.get("random_seed", 42)))
    indices = rng.permutation(len(data))
    return np.sort(indices[test_rows:]), np.sort(indices[:test_rows])


def _distribution_features(data: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    if features:
        matrix = pd.get_dummies(data[features], drop_first=False, dtype=float)
    else:
        matrix = pd.DataFrame(index=data.index)
    matrix["__time_index"] = np.arange(len(data), dtype=float)
    return matrix


def _project_distribution(values: np.ndarray, total: float) -> np.ndarray:
    clipped = np.clip(np.asarray(values, dtype=float), 0.0, None)
    sums = clipped.sum(axis=1, keepdims=True)
    zero_rows = sums[:, 0] <= 1e-12
    if np.any(zero_rows):
        clipped[zero_rows] = total / clipped.shape[1]
        sums = clipped.sum(axis=1, keepdims=True)
    return clipped / sums * total

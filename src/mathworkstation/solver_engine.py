from __future__ import annotations

from abc import ABC, abstractmethod
from itertools import combinations
from typing import Any
from uuid import uuid4

import numpy as np
import pandas as pd
from scipy import optimize
from sklearn.cluster import DBSCAN, KMeans
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, adjusted_rand_score, balanced_accuracy_score, f1_score, silhouette_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from .io_utils import atomic_write_json, now_iso
from .retail_pricing import solve_retail_pricing_replenishment, validate_retail_plan
from .subproblem_executors import (
    execute_classification_with_future,
    execute_distribution_forecasting,
    execute_explanatory_inference,
    execute_exploratory_analysis,
    execute_scalar_forecast_interval,
)
from .task_executors import (
    execute_classification,
    execute_forecasting,
    execute_optimization,
    execute_ranking,
    execute_simulation,
)
from .validation_protocol import ValidationRunner


class SolverPlugin(ABC):
    """Unified executable solver contract for one research task family."""

    name: str = "solver.unknown"
    families: tuple[str, ...] = ()
    method_aliases: tuple[str, ...] = ()

    def supports(self, family: str, plan: dict[str, Any]) -> bool:
        return family in self.families

    @abstractmethod
    def validate_inputs(
        self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None
    ) -> list[str]:
        """Return validation error codes; empty means executable."""

    def build(self, family: str, plan: dict[str, Any]) -> dict[str, Any]:
        return {
            "solver": self.name,
            "family": family,
            "method_aliases": list(self.method_aliases),
            "plan": dict(plan),
        }

    @abstractmethod
    def solve(
        self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None
    ) -> dict[str, Any]:
        """Execute deterministic numerical/statistical work."""

    def diagnose(
        self,
        family: str,
        plan: dict[str, Any],
        result: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "status": "PASS",
            "solver": self.name,
            "family": family,
            "metrics": result.get("metrics", {}),
        }

    def sensitivity(
        self,
        family: str,
        plan: dict[str, Any],
        frame: pd.DataFrame | None,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "status": "NOT_REQUESTED",
            "solver": self.name,
            "family": family,
            "reason": "Section 3 registers the solver contract; family-specific validation protocols are expanded in Section 4.",
        }

    def export_evidence(
        self,
        cases: Any,
        artifacts: Any,
        case_id: str,
        subproblem_id: str,
        family: str,
        plan: dict[str, Any],
        build: dict[str, Any],
        result: dict[str, Any],
        diagnostics: dict[str, Any],
        sensitivity: dict[str, Any],
        source_artifact_ids: list[str] | None,
    ) -> dict[str, Any]:
        run_id = f"solver-{uuid4().hex[:12]}"
        root = cases.case_root(case_id)
        path = root / "results" / "solvers" / subproblem_id / f"{run_id}.json"
        payload = {
            "schema_version": 1,
            "solver_run_id": run_id,
            "subproblem_id": subproblem_id,
            "solver": self.name,
            "family": family,
            "plan": plan,
            "build": build,
            "result": result,
            "diagnostics": diagnostics,
            "sensitivity": sensitivity,
            "source_artifact_ids": list(source_artifact_ids or []),
            "generated_at": now_iso(),
        }
        atomic_write_json(path, payload)
        artifact = artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "solver_execution_result",
            self.name,
            upstream=list(source_artifact_ids or []),
            paper_eligible=False,
        )
        return {"solver_run_id": run_id, "artifact": artifact, "payload": payload}


class ForecastingSolverPlugin(SolverPlugin):
    name = "gold.forecasting"
    families = ("forecasting",)
    method_aliases = ("time-series baseline", "drift naive", "ridge time trend", "residual bootstrap interval")

    def supports(self, family: str, plan: dict[str, Any]) -> bool:
        method = str(plan.get("solver_method") or "").lower()
        return family == "forecasting" and method in {"", "ridge_time_trend", "ridge", "default"}

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        errors: list[str] = []
        if frame is None:
            errors.append("TASK_DATA_REQUIRED")
            return errors
        for field in ("time_column", "target_column"):
            if not plan.get(field):
                errors.append(f"{field.upper()}_REQUIRED")
            elif str(plan[field]) not in frame.columns:
                errors.append(f"{field.upper()}_MISSING")
        if plan.get("future_time") is None and plan.get("split_strategy") != "temporal":
            errors.append("TEMPORAL_SPLIT_REQUIRED")
        return errors

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        assert frame is not None
        if plan.get("future_time") is not None:
            return execute_scalar_forecast_interval(frame, plan)
        return execute_forecasting(frame, plan)

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        payload = super().diagnose(family, plan, result)
        payload.update(
            {
                "leakage_check": result.get("leakage_check"),
                "future_interval_present": bool(result.get("forecast", {}).get("interval")),
            }
        )
        if result.get("leakage_check") not in {None, "PASS"}:
            payload["status"] = "FAIL"
        return payload


class HoltForecastSolverPlugin(SolverPlugin):
    """Pure time-series alternative to the feature-aware Ridge forecast."""

    name = "gold.holt_exponential_smoothing"
    families = ("forecasting",)
    method_aliases = ("Holt", "Holt trend", "exponential smoothing", "double exponential smoothing")

    def supports(self, family: str, plan: dict[str, Any]) -> bool:
        return family == "forecasting" and str(plan.get("solver_method") or "").lower() in {
            "holt",
            "holt_trend",
            "holt_exponential_smoothing",
            "exponential_smoothing",
        }

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        if frame is None:
            return ["TASK_DATA_REQUIRED"]
        errors: list[str] = []
        time_column = str(plan.get("time_column") or "")
        target = str(plan.get("target_column") or "")
        if not time_column:
            errors.append("TIME_COLUMN_REQUIRED")
        elif time_column not in frame.columns:
            errors.append("TIME_COLUMN_MISSING")
        if not target:
            errors.append("TARGET_COLUMN_REQUIRED")
        elif target not in frame.columns:
            errors.append("TARGET_COLUMN_MISSING")
        if plan.get("future_time") is None:
            errors.append("FUTURE_TIME_REQUIRED")
        return errors

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        assert frame is not None
        time_column = str(plan["time_column"])
        target = str(plan["target_column"])
        data = frame[[time_column, target]].dropna().copy()
        data[time_column] = pd.to_datetime(data[time_column], errors="raise")
        data = data.sort_values(time_column).reset_index(drop=True)
        if data[time_column].duplicated().any():
            raise ValueError("TIME_DUPLICATES_BLOCKED")
        if len(data) < 30:
            raise ValueError("FORECAST_ROWS_INSUFFICIENT")
        values_raw = pd.to_numeric(data[target], errors="raise").to_numpy(dtype=float)
        use_log = bool(plan.get("log_target", np.all(values_raw > 0)))
        values = np.log(values_raw) if use_log else values_raw
        test_rows = max(5, int(round(len(data) * float(plan.get("test_size", 0.2)))))
        split = len(data) - test_rows
        if split < 15:
            raise ValueError("FORECAST_TRAIN_ROWS_INSUFFICIENT")

        validation_model = ExponentialSmoothing(
            values[:split],
            trend="add",
            damped_trend=True,
            seasonal=None,
            initialization_method="estimated",
        ).fit(optimized=True, use_brute=False)
        validation_transformed = np.asarray(validation_model.forecast(test_rows), dtype=float)
        validation_pred = np.exp(validation_transformed) if use_log else validation_transformed
        actual = values_raw[split:]
        residuals = actual - validation_pred
        rmse = float(np.sqrt(np.mean(residuals**2)))
        mae = float(np.mean(np.abs(residuals)))
        ss_total = float(np.sum((actual - float(np.mean(actual))) ** 2))
        r2 = float(1.0 - np.sum(residuals**2) / ss_total) if ss_total > 1e-12 else 0.0

        final_model = ExponentialSmoothing(
            values,
            trend="add",
            damped_trend=True,
            seasonal=None,
            initialization_method="estimated",
        ).fit(optimized=True, use_brute=False)
        future_timestamp = pd.Timestamp(plan["future_time"])
        last_timestamp = data[time_column].iloc[-1]
        if future_timestamp <= last_timestamp:
            raise ValueError("FUTURE_TIME_MUST_FOLLOW_OBSERVATIONS")
        deltas = data[time_column].diff().dropna().dt.total_seconds().to_numpy(dtype=float) / 86400.0
        step_days = float(np.median(deltas)) if len(deltas) else 1.0
        if step_days <= 0:
            raise ValueError("FORECAST_TIME_STEP_INVALID")
        future_steps = max(1, int(round((future_timestamp - last_timestamp).total_seconds() / 86400.0 / step_days)))
        future_transformed = float(np.asarray(final_model.forecast(future_steps), dtype=float)[-1])
        point = float(np.exp(future_transformed) if use_log else future_transformed)

        bootstrap_runs = int(plan.get("bootstrap_runs", 200))
        if bootstrap_runs < 20:
            raise ValueError("BOOTSTRAP_RUNS_TOO_SMALL")
        seed = int(plan.get("random_seed", 42))
        rng = np.random.default_rng(seed)
        centered = residuals - float(np.mean(residuals))
        draws = np.maximum(0.0, point + rng.choice(centered, size=bootstrap_runs, replace=True))
        lower, upper = np.quantile(draws, [0.025, 0.975])
        return {
            "family": "forecasting",
            "protocol": {
                "split": "temporal_holdout",
                "train_rows": int(split),
                "test_rows": int(test_rows),
                "future_time": future_timestamp.isoformat(),
                "future_steps": int(future_steps),
                "bootstrap_runs": bootstrap_runs,
            },
            "method": "holt_exponential_smoothing_with_residual_bootstrap_interval",
            "metrics": {"rmse": rmse, "mae": mae, "r2": r2},
            "forecast": {
                "point": point,
                "interval": [float(lower), float(upper)],
                "coverage": 0.95,
            },
            "log_target": use_log,
            "leakage_check": "PASS",
        }

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        payload = super().diagnose(family, plan, result)
        payload.update(
            {
                "leakage_check": result.get("leakage_check"),
                "future_interval_present": bool(result.get("forecast", {}).get("interval")),
                "alternative_model": True,
            }
        )
        return payload


class PopularityLifecycleForecastSolverPlugin(SolverPlugin):
    """Two-phase exponential popularity lifecycle for event-attention decay.

    The model deliberately avoids pretending that latent player compartments are
    observed. Instead it represents a weaker, identifiable mechanism supported
    by the available aggregate report-count series: the log popularity level has
    one decay/growth rate before a training-selected change point and another
    afterwards. The change point is selected on the training portion only during
    validation, preventing look-ahead leakage.
    """

    name = "gold.popularity_lifecycle"
    families = ("forecasting",)
    method_aliases = (
        "popularity lifecycle",
        "popularity relaxation",
        "piecewise exponential decay",
        "change point exponential",
        "two phase popularity decay",
    )

    def supports(self, family: str, plan: dict[str, Any]) -> bool:
        return family == "forecasting" and str(plan.get("solver_method") or "").lower() in {
            "popularity_lifecycle",
            "popularity_relaxation",
            "piecewise_exponential_decay",
            "change_point_exponential",
            "two_phase_popularity_decay",
        }

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        if frame is None:
            return ["TASK_DATA_REQUIRED"]
        errors: list[str] = []
        time_column = str(plan.get("time_column") or "")
        target = str(plan.get("target_column") or "")
        if not time_column:
            errors.append("TIME_COLUMN_REQUIRED")
        elif time_column not in frame.columns:
            errors.append("TIME_COLUMN_MISSING")
        if not target:
            errors.append("TARGET_COLUMN_REQUIRED")
        elif target not in frame.columns:
            errors.append("TARGET_COLUMN_MISSING")
        if plan.get("future_time") is None:
            errors.append("FUTURE_TIME_REQUIRED")
        return errors

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        assert frame is not None
        time_column = str(plan["time_column"])
        target = str(plan["target_column"])
        data = frame[[time_column, target]].dropna().copy()
        data[time_column] = pd.to_datetime(data[time_column], errors="raise")
        data = data.sort_values(time_column).reset_index(drop=True)
        if data[time_column].duplicated().any():
            raise ValueError("TIME_DUPLICATES_BLOCKED")
        if len(data) < 40:
            raise ValueError("POPULARITY_LIFECYCLE_ROWS_INSUFFICIENT")
        values_raw = pd.to_numeric(data[target], errors="raise").to_numpy(dtype=float)
        if np.any(values_raw <= 0):
            raise ValueError("POPULARITY_LIFECYCLE_REQUIRES_POSITIVE_TARGET")
        origin = data[time_column].iloc[0]
        times = (
            (data[time_column] - origin).dt.total_seconds().to_numpy(dtype=float) / 86400.0
        )
        transformed = np.log(values_raw)
        test_rows = max(5, int(round(len(data) * float(plan.get("test_size", 0.2)))))
        split = len(data) - test_rows
        if split < 30:
            raise ValueError("POPULARITY_LIFECYCLE_TRAIN_ROWS_INSUFFICIENT")

        train_fit = _fit_popularity_lifecycle(times[:split], transformed[:split])
        validation_transformed = _predict_popularity_lifecycle(times[split:], train_fit)
        validation_pred = np.exp(validation_transformed)
        actual = values_raw[split:]
        residuals = actual - validation_pred
        rmse = float(np.sqrt(np.mean(residuals**2)))
        mae = float(np.mean(np.abs(residuals)))
        ss_total = float(np.sum((actual - float(np.mean(actual))) ** 2))
        r2 = float(1.0 - np.sum(residuals**2) / ss_total) if ss_total > 1e-12 else 0.0

        final_fit = _fit_popularity_lifecycle(times, transformed)
        future_timestamp = pd.Timestamp(plan["future_time"])
        if future_timestamp <= data[time_column].iloc[-1]:
            raise ValueError("FUTURE_TIME_MUST_FOLLOW_OBSERVATIONS")
        future_days = float((future_timestamp - origin).total_seconds() / 86400.0)
        point = float(np.exp(_predict_popularity_lifecycle(np.asarray([future_days]), final_fit)[0]))

        bootstrap_runs = int(plan.get("bootstrap_runs", 200))
        if bootstrap_runs < 20:
            raise ValueError("BOOTSTRAP_RUNS_TOO_SMALL")
        seed = int(plan.get("random_seed", 42))
        rng = np.random.default_rng(seed)
        centered = residuals - float(np.mean(residuals))
        draws = np.maximum(0.0, point + rng.choice(centered, size=bootstrap_runs, replace=True))
        lower, upper = np.quantile(draws, [0.025, 0.975])
        change_timestamp = origin + pd.to_timedelta(float(final_fit["tau"]), unit="D")
        pre_slope = float(final_fit["beta"][1])
        post_slope = float(final_fit["beta"][1] + final_fit["beta"][2])
        return {
            "family": "forecasting",
            "protocol": {
                "split": "temporal_holdout",
                "train_rows": int(split),
                "test_rows": int(test_rows),
                "future_time": future_timestamp.isoformat(),
                "bootstrap_runs": bootstrap_runs,
                "change_point_selected_on_training_only": True,
            },
            "method": "piecewise_exponential_popularity_lifecycle_with_residual_bootstrap_interval",
            "metrics": {"rmse": rmse, "mae": mae, "r2": r2},
            "forecast": {
                "point": point,
                "interval": [float(lower), float(upper)],
                "coverage": 0.95,
            },
            "mechanism": {
                "kind": "two_phase_popularity_lifecycle",
                "change_point": change_timestamp.isoformat(),
                "pre_change_daily_log_slope": pre_slope,
                "post_change_daily_log_slope": post_slope,
                "interpretation_guard": "aggregate popularity lifecycle; no latent player compartments are claimed",
            },
            "log_target": True,
            "leakage_check": "PASS",
        }

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        payload = super().diagnose(family, plan, result)
        payload.update(
            {
                "leakage_check": result.get("leakage_check"),
                "future_interval_present": bool(result.get("forecast", {}).get("interval")),
                "change_point_present": bool(result.get("mechanism", {}).get("change_point")),
                "mechanism_guard": result.get("mechanism", {}).get("interpretation_guard"),
                "alternative_model": True,
            }
        )
        if result.get("leakage_check") != "PASS":
            payload["status"] = "FAIL"
        return payload


def _fit_popularity_lifecycle(times: np.ndarray, transformed: np.ndarray) -> dict[str, Any]:
    if len(times) != len(transformed) or len(times) < 20:
        raise ValueError("POPULARITY_LIFECYCLE_FIT_ROWS_INSUFFICIENT")
    lower = max(5, int(round(len(times) * 0.15)))
    upper = min(len(times) - 5, int(round(len(times) * 0.85)))
    if upper <= lower:
        raise ValueError("POPULARITY_LIFECYCLE_CHANGEPOINT_RANGE_INVALID")
    best: dict[str, Any] | None = None
    for index in range(lower, upper + 1):
        tau = float(times[index])
        design = np.column_stack(
            [
                np.ones(len(times), dtype=float),
                times,
                np.maximum(0.0, times - tau),
            ]
        )
        beta, *_ = np.linalg.lstsq(design, transformed, rcond=None)
        residuals = transformed - design @ beta
        mse = float(np.mean(residuals**2))
        candidate = {"tau": tau, "beta": beta, "training_mse": mse, "change_index": index}
        if best is None or mse < float(best["training_mse"]):
            best = candidate
    assert best is not None
    return best


def _predict_popularity_lifecycle(times: np.ndarray, fit: dict[str, Any]) -> np.ndarray:
    tau = float(fit["tau"])
    beta = np.asarray(fit["beta"], dtype=float)
    design = np.column_stack(
        [
            np.ones(len(times), dtype=float),
            times,
            np.maximum(0.0, times - tau),
        ]
    )
    return design @ beta


class PanelProfileSummarySolverPlugin(SolverPlugin):
    """Comparable multi-entity profile snapshot over a shared panel schema."""

    name = "gold.panel_profile_summary"
    families = ("exploratory_analysis",)
    method_aliases = ("panel profile summary", "group profile summary", "multi-entity profile")

    def supports(self, family: str, plan: dict[str, Any]) -> bool:
        return family == "exploratory_analysis" and str(plan.get("solver_method") or "").lower() in {
            "panel_profile",
            "panel_profile_summary",
            "group_profile_summary",
        }

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        if frame is None:
            return ["TASK_DATA_REQUIRED"]
        group_column = str(plan.get("group_column") or "")
        time_column = str(plan.get("time_column") or "")
        columns = [str(value) for value in plan.get("profile_columns", [])]
        errors: list[str] = []
        if not group_column:
            errors.append("GROUP_COLUMN_REQUIRED")
        elif group_column not in frame.columns:
            errors.append("GROUP_COLUMN_MISSING")
        if not time_column:
            errors.append("TIME_COLUMN_REQUIRED")
        elif time_column not in frame.columns:
            errors.append("TIME_COLUMN_MISSING")
        if len(columns) < 2:
            errors.append("PROFILE_COLUMNS_INSUFFICIENT")
        missing = [column for column in columns if column not in frame.columns]
        if missing:
            errors.append("PROFILE_COLUMNS_MISSING:" + ",".join(missing))
        return errors

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        assert frame is not None
        group_column = str(plan["group_column"])
        time_column = str(plan["time_column"])
        columns = [str(value) for value in plan["profile_columns"]]
        data = frame[[group_column, time_column, *columns]].dropna().copy()
        data[time_column] = pd.to_datetime(data[time_column], errors="raise")
        data = data.sort_values([group_column, time_column]).reset_index(drop=True)
        if data[[group_column, time_column]].duplicated().any():
            raise ValueError("PANEL_PROFILE_TIME_DUPLICATED")
        requested_reference = plan.get("reference_time")
        reference_time = pd.Timestamp(requested_reference) if requested_reference is not None else data[time_column].max()
        reference = data[data[time_column] == reference_time].copy()
        entities = sorted(str(value) for value in data[group_column].dropna().unique())
        if len(reference) != len(entities):
            raise ValueError("PANEL_PROFILE_REFERENCE_COVERAGE_INCOMPLETE")
        profiles: list[dict[str, Any]] = []
        for entity in entities:
            row = reference[reference[group_column].astype(str) == entity]
            if len(row) != 1:
                raise ValueError(f"PANEL_PROFILE_REFERENCE_ENTITY_INVALID:{entity}")
            values = {column: float(pd.to_numeric(row.iloc[0][column], errors="raise")) for column in columns}
            history = data[data[group_column].astype(str) == entity]
            first = history.iloc[0]
            change = {
                column: float(pd.to_numeric(row.iloc[0][column], errors="raise") - pd.to_numeric(first[column], errors="raise"))
                for column in columns
            }
            profiles.append({"entity": entity, "values": values, "change_from_first": change})
        return {
            "family": "exploratory_analysis",
            "solver_method": "panel_profile_summary",
            "protocol": {
                "reference_time": reference_time.isoformat(),
                "group_column": group_column,
                "time_column": time_column,
                "history_start": data[time_column].min().isoformat(),
                "history_end": data[time_column].max().isoformat(),
            },
            "profiles": profiles,
            "profile_columns": columns,
            "metrics": {
                "entity_count": float(len(entities)),
                "profile_dimension_count": float(len(columns)),
            },
            "headline": f"Comparable {len(columns)}-dimension profiles registered for {len(entities)} entities at {reference_time.date()}.",
        }

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        profiles = result.get("profiles") or []
        return {
            "status": "PASS" if len(profiles) >= 2 else "FAIL",
            "solver": self.name,
            "family": family,
            "entity_count": len(profiles),
            "profile_dimension_count": len(result.get("profile_columns") or []),
        }


class PanelTrendCharacterizationSolverPlugin(SolverPlugin):
    """Historical panel trend characterization with entity-wise temporal holdout."""

    name = "gold.panel_trend_characterization"
    families = ("forecasting",)
    method_aliases = ("panel trend characterization", "panel linear trend", "multi-entity historical trend")

    def supports(self, family: str, plan: dict[str, Any]) -> bool:
        return family == "forecasting" and str(plan.get("solver_method") or "").lower() in {
            "panel_trend",
            "panel_trend_characterization",
            "panel_linear_trend",
        }

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        if frame is None:
            return ["TASK_DATA_REQUIRED"]
        group_column = str(plan.get("group_column") or "")
        time_column = str(plan.get("time_column") or "")
        targets = [str(value) for value in plan.get("target_columns", [])]
        errors: list[str] = []
        if not group_column:
            errors.append("GROUP_COLUMN_REQUIRED")
        elif group_column not in frame.columns:
            errors.append("GROUP_COLUMN_MISSING")
        if not time_column:
            errors.append("TIME_COLUMN_REQUIRED")
        elif time_column not in frame.columns:
            errors.append("TIME_COLUMN_MISSING")
        if not targets:
            errors.append("TARGET_COLUMNS_REQUIRED")
        missing = [column for column in targets if column not in frame.columns]
        if missing:
            errors.append("TARGET_COLUMNS_MISSING:" + ",".join(missing))
        return errors

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        assert frame is not None
        group_column = str(plan["group_column"])
        time_column = str(plan["time_column"])
        targets = [str(value) for value in plan["target_columns"]]
        test_size = float(plan.get("test_size", 0.2))
        data = frame[[group_column, time_column, *targets]].dropna().copy()
        data[time_column] = pd.to_datetime(data[time_column], errors="raise")
        data = data.sort_values([group_column, time_column]).reset_index(drop=True)
        if data[[group_column, time_column]].duplicated().any():
            raise ValueError("PANEL_TIME_DUPLICATES_BLOCKED")
        squared: list[float] = []
        absolute: list[float] = []
        trends: list[dict[str, Any]] = []
        for entity, group in data.groupby(group_column, sort=True):
            group = group.sort_values(time_column).reset_index(drop=True)
            if len(group) < 20:
                raise ValueError(f"PANEL_TREND_ROWS_INSUFFICIENT:{entity}")
            origin = group[time_column].iloc[0]
            years = (group[time_column] - origin).dt.total_seconds().to_numpy(dtype=float) / (365.25 * 86400.0)
            test_rows = max(4, int(round(len(group) * test_size)))
            split = len(group) - test_rows
            if split < 14:
                raise ValueError(f"PANEL_TREND_TRAIN_ROWS_INSUFFICIENT:{entity}")
            for target in targets:
                values = pd.to_numeric(group[target], errors="raise").to_numpy(dtype=float)
                train_design = np.column_stack([np.ones(split), years[:split]])
                beta, *_ = np.linalg.lstsq(train_design, values[:split], rcond=None)
                validation_design = np.column_stack([np.ones(test_rows), years[split:]])
                predicted = validation_design @ beta
                residuals = values[split:] - predicted
                squared.extend((residuals**2).tolist())
                absolute.extend(np.abs(residuals).tolist())
                full_design = np.column_stack([np.ones(len(group)), years])
                full_beta, *_ = np.linalg.lstsq(full_design, values, rcond=None)
                slope = float(full_beta[1])
                total_change = float(values[-1] - values[0])
                trends.append(
                    {
                        "entity": str(entity),
                        "target": target,
                        "annual_slope": slope,
                        "observed_change": total_change,
                        "direction": "increase" if slope > 0 else "decrease" if slope < 0 else "flat",
                        "start_value": float(values[0]),
                        "end_value": float(values[-1]),
                    }
                )
        return {
            "family": "forecasting",
            "protocol": {
                "split": "panel_temporal_holdout",
                "group_column": group_column,
                "time_column": time_column,
                "test_size": test_size,
                "history_start": data[time_column].min().isoformat(),
                "history_end": data[time_column].max().isoformat(),
            },
            "method": "panel_linear_trend_characterization_with_temporal_holdout",
            "metrics": {
                "rmse": float(np.sqrt(np.mean(squared))),
                "mae": float(np.mean(absolute)),
                "trend_count": float(len(trends)),
            },
            "trend_grid": trends,
            "leakage_check": "PASS",
        }

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        trends = result.get("trend_grid") or []
        return {
            "status": "PASS" if trends and result.get("leakage_check") == "PASS" else "FAIL",
            "solver": self.name,
            "family": family,
            "trend_count": len(trends),
            "leakage_check": result.get("leakage_check"),
        }


class PanelHoltForecastSolverPlugin(SolverPlugin):
    """Entity-wise Holt forecasting for panel data with shared schema.

    Each entity is fit independently under the same temporal holdout rule. The
    result keeps every entity/target/horizon forecast explicit instead of
    collapsing a multi-region problem into one synthetic scalar series.
    """

    name = "gold.panel_holt"
    families = ("forecasting",)
    method_aliases = (
        "panel Holt",
        "panel exponential smoothing",
        "multi-entity temporal forecast",
        "panel forecast",
    )

    def supports(self, family: str, plan: dict[str, Any]) -> bool:
        return family == "forecasting" and str(plan.get("solver_method") or "").lower() in {
            "panel_holt",
            "panel_holt_exponential_smoothing",
            "panel_forecast",
        }

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        if frame is None:
            return ["TASK_DATA_REQUIRED"]
        errors: list[str] = []
        group_column = str(plan.get("group_column") or "")
        time_column = str(plan.get("time_column") or "")
        targets = [str(value) for value in plan.get("target_columns", [])]
        future_times = list(plan.get("future_times") or [])
        if not group_column:
            errors.append("GROUP_COLUMN_REQUIRED")
        elif group_column not in frame.columns:
            errors.append("GROUP_COLUMN_MISSING")
        if not time_column:
            errors.append("TIME_COLUMN_REQUIRED")
        elif time_column not in frame.columns:
            errors.append("TIME_COLUMN_MISSING")
        if not targets:
            errors.append("TARGET_COLUMNS_REQUIRED")
        else:
            missing = [column for column in targets if column not in frame.columns]
            if missing:
                errors.append("TARGET_COLUMNS_MISSING:" + ",".join(missing))
        if not future_times:
            errors.append("FUTURE_TIMES_REQUIRED")
        if group_column in frame.columns and frame[group_column].nunique(dropna=True) < 2:
            errors.append("PANEL_GROUPS_INSUFFICIENT")
        return errors

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        assert frame is not None
        group_column = str(plan["group_column"])
        time_column = str(plan["time_column"])
        targets = [str(value) for value in plan["target_columns"]]
        future_times = sorted(pd.Timestamp(value) for value in plan["future_times"])
        test_size = float(plan.get("test_size", 0.2))
        bootstrap_runs = int(plan.get("bootstrap_runs", 300))
        seed = int(plan.get("random_seed", 42))
        if bootstrap_runs < 20:
            raise ValueError("BOOTSTRAP_RUNS_TOO_SMALL")
        if not 0.05 < test_size < 0.5:
            raise ValueError("TEST_SIZE_INVALID")

        data = frame[[group_column, time_column, *targets]].dropna().copy()
        data[time_column] = pd.to_datetime(data[time_column], errors="raise")
        if data[[group_column, time_column]].duplicated().any():
            raise ValueError("PANEL_TIME_DUPLICATES_BLOCKED")
        data = data.sort_values([group_column, time_column]).reset_index(drop=True)
        transforms = {str(key): str(value) for key, value in (plan.get("target_transforms") or {}).items()}
        forecasts: list[dict[str, Any]] = []
        validation_errors: list[float] = []
        validation_absolute: list[float] = []
        by_series: list[dict[str, Any]] = []

        for entity, group in data.groupby(group_column, sort=True):
            group = group.sort_values(time_column).reset_index(drop=True)
            if len(group) < 24:
                raise ValueError(f"PANEL_SERIES_ROWS_INSUFFICIENT:{entity}")
            last_time = group[time_column].iloc[-1]
            if any(value <= last_time for value in future_times):
                raise ValueError(f"FUTURE_TIME_MUST_FOLLOW_OBSERVATIONS:{entity}")
            deltas = group[time_column].diff().dropna().dt.total_seconds().to_numpy(dtype=float) / 86400.0
            step_days = float(np.median(deltas)) if len(deltas) else 365.25
            if step_days <= 0:
                raise ValueError(f"FORECAST_TIME_STEP_INVALID:{entity}")

            for target_index, target in enumerate(targets):
                raw = pd.to_numeric(group[target], errors="raise").to_numpy(dtype=float)
                transform = transforms.get(target, "identity")
                transformed = _panel_transform(raw, transform)
                test_rows = max(4, int(round(len(group) * test_size)))
                split = len(group) - test_rows
                if split < 16:
                    raise ValueError(f"PANEL_TRAIN_ROWS_INSUFFICIENT:{entity}:{target}")
                validation_model = ExponentialSmoothing(
                    transformed[:split],
                    trend="add",
                    damped_trend=True,
                    seasonal=None,
                    initialization_method="estimated",
                ).fit(optimized=True, use_brute=False)
                validation_t = np.asarray(validation_model.forecast(test_rows), dtype=float)
                validation_pred = _panel_inverse_transform(validation_t, transform)
                actual = raw[split:]
                residuals = actual - validation_pred
                validation_errors.extend((residuals**2).tolist())
                validation_absolute.extend(np.abs(residuals).tolist())
                series_rmse = float(np.sqrt(np.mean(residuals**2)))
                series_mae = float(np.mean(np.abs(residuals)))

                final_model = ExponentialSmoothing(
                    transformed,
                    trend="add",
                    damped_trend=True,
                    seasonal=None,
                    initialization_method="estimated",
                ).fit(optimized=True, use_brute=False)
                rng = np.random.default_rng(seed + target_index + len(by_series) * 1009)
                centered = residuals - float(np.mean(residuals))
                for future_time in future_times:
                    horizon_days = float((future_time - last_time).total_seconds() / 86400.0)
                    steps = max(1, int(round(horizon_days / step_days)))
                    point_t = float(np.asarray(final_model.forecast(steps), dtype=float)[-1])
                    point = float(_panel_inverse_transform(np.asarray([point_t]), transform)[0])
                    draws = point + rng.choice(centered, size=bootstrap_runs, replace=True)
                    if transform == "logit_01":
                        draws = np.clip(draws, 0.0, 1.0)
                    elif transform == "log_positive":
                        draws = np.maximum(draws, 0.0)
                    lower, upper = np.quantile(draws, [0.025, 0.975])
                    point = float(np.clip(point, 0.0, 1.0)) if transform == "logit_01" else point
                    forecasts.append(
                        {
                            "entity": str(entity),
                            "target": target,
                            "future_time": future_time.isoformat(),
                            "point": point,
                            "interval": [float(min(lower, point)), float(max(upper, point))],
                            "coverage": 0.95,
                        }
                    )
                by_series.append(
                    {
                        "entity": str(entity),
                        "target": target,
                        "validation_rmse": series_rmse,
                        "validation_mae": series_mae,
                        "train_rows": int(split),
                        "test_rows": int(test_rows),
                        "transform": transform,
                    }
                )

        return {
            "family": "forecasting",
            "protocol": {
                "split": "panel_temporal_holdout",
                "group_column": group_column,
                "time_column": time_column,
                "test_size": test_size,
                "bootstrap_runs": bootstrap_runs,
                "future_times": [value.isoformat() for value in future_times],
            },
            "method": "panel_holt_exponential_smoothing_with_residual_bootstrap_intervals",
            "metrics": {
                "rmse": float(np.sqrt(np.mean(validation_errors))),
                "mae": float(np.mean(validation_absolute)),
                "series_count": float(len(by_series)),
            },
            "forecast_grid": forecasts,
            "series_validation": by_series,
            "leakage_check": "PASS",
        }

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        payload = super().diagnose(family, plan, result)
        grid = result.get("forecast_grid") or []
        payload.update(
            {
                "leakage_check": result.get("leakage_check"),
                "forecast_count": len(grid),
                "entity_count": len({item.get("entity") for item in grid}),
                "target_count": len({item.get("target") for item in grid}),
            }
        )
        if result.get("leakage_check") != "PASS" or not grid:
            payload["status"] = "FAIL"
        return payload


def _panel_transform(values: np.ndarray, transform: str) -> np.ndarray:
    data = np.asarray(values, dtype=float)
    if transform == "identity":
        return data
    if transform == "log_positive":
        if np.any(data <= 0):
            raise ValueError("PANEL_LOG_TARGET_REQUIRES_POSITIVE_VALUES")
        return np.log(data)
    if transform == "logit_01":
        if np.any((data < 0) | (data > 1)):
            raise ValueError("PANEL_LOGIT_TARGET_OUTSIDE_UNIT_INTERVAL")
        clipped = np.clip(data, 1e-5, 1.0 - 1e-5)
        return np.log(clipped / (1.0 - clipped))
    raise ValueError(f"PANEL_TARGET_TRANSFORM_UNSUPPORTED:{transform}")


def _panel_inverse_transform(values: np.ndarray, transform: str) -> np.ndarray:
    data = np.asarray(values, dtype=float)
    if transform == "identity":
        return data
    if transform == "log_positive":
        return np.exp(data)
    if transform == "logit_01":
        return 1.0 / (1.0 + np.exp(-data))
    raise ValueError(f"PANEL_TARGET_TRANSFORM_UNSUPPORTED:{transform}")


class ClassificationSolverPlugin(SolverPlugin):
    name = "gold.classification"
    families = ("classification",)
    method_aliases = ("logistic regression", "classification baseline", "future prediction")

    def supports(self, family: str, plan: dict[str, Any]) -> bool:
        method = str(plan.get("solver_method") or "").lower()
        return family == "classification" and method in {"", "logistic", "logistic_regression", "default"}

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        if frame is None:
            return ["TASK_DATA_REQUIRED"]
        target = str(plan.get("target_column") or "")
        features = [str(value) for value in plan.get("feature_columns", [])]
        errors = []
        if not target:
            errors.append("TARGET_COLUMN_REQUIRED")
        if not features:
            errors.append("FEATURE_COLUMNS_REQUIRED")
        missing = [column for column in [target, *features] if column and column not in frame.columns]
        if missing:
            errors.append("CLASSIFICATION_COLUMNS_MISSING:" + ",".join(missing))
        return errors

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        assert frame is not None
        if plan.get("future_features") is not None:
            return execute_classification_with_future(frame, plan)
        return execute_classification(frame, plan)

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        payload = super().diagnose(family, plan, result)
        payload.update(
            {
                "confusion_matrix_present": bool(result.get("confusion_matrix")),
                "future_probability_present": bool(result.get("future_probabilities")),
            }
        )
        return payload


class RandomForestClassificationSolverPlugin(SolverPlugin):
    """Nonlinear tree-ensemble alternative to the logistic classification baseline."""

    name = "gold.random_forest_classification"
    families = ("classification",)
    method_aliases = ("random forest classifier", "random forest", "tree ensemble classifier")

    def supports(self, family: str, plan: dict[str, Any]) -> bool:
        return family == "classification" and str(plan.get("solver_method") or "").lower() in {
            "random_forest",
            "random_forest_classifier",
            "rf",
        }

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        if frame is None:
            return ["TASK_DATA_REQUIRED"]
        target = str(plan.get("target_column") or "")
        features = [str(value) for value in plan.get("feature_columns", [])]
        errors: list[str] = []
        if not target:
            errors.append("TARGET_COLUMN_REQUIRED")
        if not features:
            errors.append("FEATURE_COLUMNS_REQUIRED")
        missing = [column for column in [target, *features] if column and column not in frame.columns]
        if missing:
            errors.append("CLASSIFICATION_COLUMNS_MISSING:" + ",".join(missing))
        return errors

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        assert frame is not None
        target = str(plan["target_column"])
        features = [str(value) for value in plan["feature_columns"]]
        data = frame[[*features, target]].dropna().reset_index(drop=True)
        if data[target].nunique() < 2:
            raise ValueError("classification requires at least two classes")
        seed = int(plan.get("random_seed", 42))
        indices = np.arange(len(data))
        test_size = max(1, int(round(len(data) * float(plan.get("test_size", 0.2)))))
        stratify = data[target] if data[target].value_counts().min() >= 2 and test_size >= data[target].nunique() else None
        train_idx, test_idx = train_test_split(
            indices,
            test_size=test_size,
            random_state=seed,
            stratify=stratify,
        )
        train_idx = np.sort(train_idx)
        test_idx = np.sort(test_idx)
        encoded = pd.get_dummies(data[features], drop_first=False, dtype=float)
        y_train = data[target].iloc[train_idx]
        y_test = data[target].iloc[test_idx]
        model = RandomForestClassifier(
            n_estimators=int(plan.get("rf_estimators", 300)),
            max_depth=int(plan.get("rf_max_depth", 6)),
            min_samples_leaf=int(plan.get("rf_min_samples_leaf", 3)),
            random_state=seed,
            class_weight="balanced",
            n_jobs=1,
        )
        model.fit(encoded.iloc[train_idx], y_train)
        probabilities = model.predict_proba(encoded.iloc[test_idx])
        predicted = model.classes_[np.argmax(probabilities, axis=1)]
        labels = sorted(str(value) for value in data[target].unique())
        confusion = pd.crosstab(
            y_test.astype(str),
            pd.Series(predicted, index=y_test.index).astype(str),
            dropna=False,
        ).reindex(index=labels, columns=labels, fill_value=0)
        result: dict[str, Any] = {
            "family": "classification",
            "protocol": {"split": "stratified_holdout", "seed": seed, "test_rows": len(test_idx)},
            "model": "random_forest_classifier",
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
            "future_prediction": None,
            "future_probabilities": None,
        }
        future_features = plan.get("future_features")
        if future_features is not None:
            future_payload = dict(future_features)
            missing_future = [column for column in features if column not in future_payload]
            if missing_future:
                raise ValueError("FUTURE_CLASSIFICATION_FEATURES_MISSING:" + ",".join(missing_future))
            future = pd.DataFrame([{column: future_payload[column] for column in features}])
            combined = pd.concat([data[features], future], ignore_index=True)
            final_encoded = pd.get_dummies(combined, drop_first=False, dtype=float)
            final_model = RandomForestClassifier(
                n_estimators=int(plan.get("rf_estimators", 300)),
                max_depth=int(plan.get("rf_max_depth", 6)),
                min_samples_leaf=int(plan.get("rf_min_samples_leaf", 3)),
                random_state=seed,
                class_weight="balanced",
                n_jobs=1,
            )
            final_model.fit(final_encoded.iloc[:-1], data[target])
            future_probability = final_model.predict_proba(final_encoded.iloc[-1:])[0]
            result["future_prediction"] = str(final_model.classes_[int(np.argmax(future_probability))])
            result["future_probabilities"] = {
                str(label): float(value)
                for label, value in zip(final_model.classes_, future_probability, strict=True)
            }
        return result

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        payload = super().diagnose(family, plan, result)
        payload.update(
            {
                "confusion_matrix_present": bool(result.get("confusion_matrix")),
                "future_probability_present": bool(result.get("future_probabilities")),
                "alternative_model": True,
            }
        )
        return payload


class ExplanatoryInferenceSolverPlugin(SolverPlugin):
    name = "gold.explanatory_inference"
    families = ("explanatory_inference",)
    method_aliases = ("standardized ridge", "ridge", "linear regression", "regression baseline", "bootstrap intervals")

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        if frame is None:
            return ["TASK_DATA_REQUIRED"]
        target = str(plan.get("target_column") or "")
        features = [str(value) for value in plan.get("feature_columns", [])]
        errors = []
        if not target:
            errors.append("TARGET_COLUMN_REQUIRED")
        if not features:
            errors.append("FEATURE_COLUMNS_REQUIRED")
        missing = [column for column in [target, *features] if column and column not in frame.columns]
        if missing:
            errors.append("EXPLANATORY_COLUMNS_MISSING:" + ",".join(missing))
        return errors

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        assert frame is not None
        return execute_explanatory_inference(frame, plan)

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        stable = [item for item in result.get("effects", []) if item.get("interval_excludes_zero")]
        payload = super().diagnose(family, plan, result)
        payload.update(
            {
                "interpretation_guard": result.get("interpretation_guard"),
                "stable_effect_count": len(stable),
            }
        )
        return payload


class DistributionForecastSolverPlugin(SolverPlugin):
    name = "gold.distribution_forecasting"
    families = ("distribution_forecasting",)
    method_aliases = ("multi-output ridge", "simplex projection", "distribution forecast")

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        if frame is None:
            return ["TASK_DATA_REQUIRED"]
        errors = []
        time_column = str(plan.get("time_column") or "")
        outputs = [str(value) for value in plan.get("output_columns", [])]
        if not time_column:
            errors.append("TIME_COLUMN_REQUIRED")
        elif time_column not in frame.columns:
            errors.append("TIME_COLUMN_MISSING")
        if len(outputs) < 2:
            errors.append("DISTRIBUTION_OUTPUT_COLUMNS_REQUIRED")
        missing = [column for column in outputs if column not in frame.columns]
        if missing:
            errors.append("DISTRIBUTION_COLUMNS_MISSING:" + ",".join(missing))
        return errors

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        assert frame is not None
        return execute_distribution_forecasting(frame, plan)

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        metrics = result.get("metrics", {})
        simplex_error = float(metrics.get("projected_simplex_error", 0.0))
        payload = super().diagnose(family, plan, result)
        payload.update(
            {
                "projected_simplex_error": simplex_error,
                "future_distribution_present": bool(result.get("future_distribution")),
                "future_uncertainty_present": bool(result.get("future_uncertainty_95")),
            }
        )
        if simplex_error > 1e-8:
            payload["status"] = "FAIL"
        return payload


class ExploratoryAnalysisSolverPlugin(SolverPlugin):
    name = "gold.exploratory_analysis"
    families = ("exploratory_analysis",)
    method_aliases = ("EDA", "Spearman association", "IQR outlier", "mean-shift scan", "outlier scan", "change scan")

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        if frame is None:
            return ["TASK_DATA_REQUIRED"]
        requested = [str(value) for value in plan.get("numeric_columns", [])]
        missing = [column for column in requested if column not in frame.columns]
        return ["EXPLORATORY_COLUMNS_MISSING:" + ",".join(missing)] if missing else []

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        assert frame is not None
        return execute_exploratory_analysis(frame, plan)

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        discoveries = result.get("discoveries", {})
        return {
            "status": "PASS",
            "solver": self.name,
            "family": family,
            "association_count": len(discoveries.get("strongest_associations", [])),
            "outlier_scan_count": len(discoveries.get("highest_outlier_rates", [])),
            "change_scan_count": len(discoveries.get("largest_mean_shift_candidates", [])),
        }


class LinearProgrammingSolverPlugin(SolverPlugin):
    name = "gold.linear_programming"
    families = ("optimization",)
    method_aliases = ("linear programming", "LP")

    def supports(self, family: str, plan: dict[str, Any]) -> bool:
        return family == "optimization" and str(plan.get("solver_method", "")).lower() in {
            "linear_programming",
            "lp",
        }

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        errors = _validate_linear_optimization_plan(plan)
        if any(str(item.get("type", "continuous")).lower() not in {"continuous", "real"} for item in plan.get("variables", [])):
            errors.append("LP_REQUIRES_CONTINUOUS_VARIABLES")
        return errors

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        names, c, bounds, a_ub, b_ub, a_eq, b_eq, sense, constant = _linear_problem_arrays(plan)
        signed_c = c if sense == "min" else -c
        result = optimize.linprog(
            signed_c,
            A_ub=a_ub if len(a_ub) else None,
            b_ub=b_ub if len(b_ub) else None,
            A_eq=a_eq if len(a_eq) else None,
            b_eq=b_eq if len(b_eq) else None,
            bounds=bounds,
            method="highs",
        )
        if not result.success:
            raise ValueError(f"LP_SOLVE_FAILED:{result.message}")
        solution = {name: float(value) for name, value in zip(names, result.x, strict=True)}
        objective_value = float(np.dot(c, result.x) + constant)
        return {
            "family": "optimization",
            "solver_method": "linear_programming",
            "solution": solution,
            "objective_value": objective_value,
            "constraint_status": "PASS" if _constraints_satisfied(plan, solution) else "FAIL",
            "solver_status": int(result.status),
            "solver_message": str(result.message),
        }

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "PASS" if result.get("constraint_status") == "PASS" else "FAIL",
            "solver": self.name,
            "family": family,
            "constraint_status": result.get("constraint_status"),
            "solver_status": result.get("solver_status"),
        }


class MilpSolverPlugin(SolverPlugin):
    name = "gold.milp"
    families = ("optimization",)
    method_aliases = ("integer programming", "mixed integer programming", "MILP", "0-1 programming")

    def supports(self, family: str, plan: dict[str, Any]) -> bool:
        requested = str(plan.get("solver_method", "")).lower()
        has_integer = any(
            str(item.get("type", "continuous")).lower() in {"integer", "binary"}
            for item in plan.get("variables", [])
        )
        return family == "optimization" and (requested in {"milp", "integer_programming", "mixed_integer_programming"} or has_integer)

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        errors = _validate_linear_optimization_plan(plan)
        if not any(
            str(item.get("type", "continuous")).lower() in {"integer", "binary"}
            for item in plan.get("variables", [])
        ):
            errors.append("MILP_INTEGER_VARIABLE_REQUIRED")
        return errors

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        names, c, bounds, _a_ub, _b_ub, _a_eq, _b_eq, sense, constant = _linear_problem_arrays(plan)
        variables = plan["variables"]
        lower = []
        upper = []
        integrality = []
        for item, (low, high) in zip(variables, bounds, strict=True):
            variable_type = str(item.get("type", "continuous")).lower()
            if variable_type == "binary":
                low, high = max(0.0, float(low)), min(1.0, float(high))
                integrality.append(1)
            elif variable_type == "integer":
                integrality.append(1)
            else:
                integrality.append(0)
            lower.append(float(low))
            upper.append(float(high))

        constraints = []
        for item in plan.get("constraints", []):
            row = np.asarray(
                [float(item.get("coefficients", {}).get(name, 0.0)) for name in names],
                dtype=float,
            )
            rhs = float(item["rhs"])
            operator = item["operator"]
            if operator == "<=":
                constraints.append(optimize.LinearConstraint(row, -np.inf, rhs))
            elif operator == ">=":
                constraints.append(optimize.LinearConstraint(row, rhs, np.inf))
            else:
                constraints.append(optimize.LinearConstraint(row, rhs, rhs))
        signed_c = c if sense == "min" else -c
        result = optimize.milp(
            c=signed_c,
            integrality=np.asarray(integrality, dtype=int),
            bounds=optimize.Bounds(np.asarray(lower), np.asarray(upper)),
            constraints=constraints or None,
        )
        if not result.success or result.x is None:
            raise ValueError(f"MILP_SOLVE_FAILED:{result.message}")
        solution = {name: float(value) for name, value in zip(names, result.x, strict=True)}
        objective_value = float(np.dot(c, result.x) + constant)
        return {
            "family": "optimization",
            "solver_method": "milp",
            "solution": solution,
            "objective_value": objective_value,
            "constraint_status": "PASS" if _constraints_satisfied(plan, solution) else "FAIL",
            "solver_status": int(result.status),
            "solver_message": str(result.message),
        }

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "PASS" if result.get("constraint_status") == "PASS" else "FAIL",
            "solver": self.name,
            "family": family,
            "constraint_status": result.get("constraint_status"),
            "solver_status": result.get("solver_status"),
        }


def _retail_member_features(frame: pd.DataFrame, plan: dict[str, Any]) -> pd.DataFrame:
    """Aggregate a transaction-level retail table into reusable member features.

    Column names are always supplied by the plan.  This keeps the solver useful
    beyond CUMCM 2018 C and prevents competition-specific aliases from becoming
    hidden global assumptions.
    """

    member = str(plan.get("member_column") or "")
    time = str(plan.get("time_column") or "")
    transaction = str(plan.get("transaction_column") or "")
    amount = str(plan.get("amount_column") or "")
    data = frame[[member, time, transaction, amount]].copy()
    data[time] = pd.to_datetime(data[time], errors="coerce")
    data[amount] = pd.to_numeric(data[amount], errors="coerce")
    data = data.dropna(subset=[member, time, transaction, amount])
    if bool(plan.get("drop_negative_amounts", True)):
        data = data[data[amount] >= 0].copy()
    if data.empty:
        raise ValueError("RETAIL_MEMBER_TRANSACTIONS_EMPTY")
    reference = pd.Timestamp(plan.get("reference_time")) if plan.get("reference_time") else data[time].max()
    basket = (
        data.groupby([member, transaction], as_index=False)
        .agg(basket_amount=(amount, "sum"), basket_time=(time, "max"))
    )
    grouped = basket.groupby(member)
    features = grouped.agg(
        last_purchase=("basket_time", "max"),
        first_purchase=("basket_time", "min"),
        frequency=(transaction, "nunique"),
        monetary=("basket_amount", "sum"),
        max_basket=("basket_amount", "max"),
        mean_basket=("basket_amount", "mean"),
    ).reset_index()
    features["recency_days"] = (reference - features["last_purchase"]).dt.days.astype(float)
    features["observed_span_days"] = (
        features["last_purchase"] - features["first_purchase"]
    ).dt.days.astype(float)
    return features


class MemberGroupProfileSolverPlugin(SolverPlugin):
    """Compare member and non-member consumption on one explicit schema."""

    name = "gold.member_group_profile"
    families = ("exploratory_analysis",)
    method_aliases = (
        "member group profile",
        "member consumption profile",
        "member nonmember consumption comparison",
    )

    def supports(self, family: str, plan: dict[str, Any]) -> bool:
        return family == "exploratory_analysis" and _normalize_method_text(plan.get("solver_method", "")) in {
            "member group profile",
            "member consumption profile",
            "member nonmember consumption comparison",
        }

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        if frame is None:
            return ["TASK_DATA_REQUIRED"]
        required = [
            str(plan.get("member_flag_column") or ""),
            str(plan.get("transaction_column") or ""),
            str(plan.get("amount_column") or ""),
        ]
        if any(not value for value in required):
            return ["MEMBER_PROFILE_SCHEMA_REQUIRED"]
        missing = [column for column in required if column not in frame.columns]
        if missing:
            return ["MEMBER_PROFILE_COLUMNS_MISSING:" + ",".join(missing)]
        if frame[required[0]].nunique(dropna=True) < 2:
            return ["MEMBER_PROFILE_GROUPS_INSUFFICIENT"]
        return []

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        assert frame is not None
        flag = str(plan["member_flag_column"])
        transaction = str(plan["transaction_column"])
        amount = str(plan["amount_column"])
        quantity = str(plan.get("quantity_column") or "")
        columns = [flag, transaction, amount, *([quantity] if quantity and quantity in frame.columns else [])]
        data = frame[columns].copy()
        data[amount] = pd.to_numeric(data[amount], errors="coerce")
        if quantity and quantity in data.columns:
            data[quantity] = pd.to_numeric(data[quantity], errors="coerce")
        data = data.dropna(subset=[flag, transaction, amount])
        if bool(plan.get("drop_negative_amounts", True)):
            data = data[data[amount] >= 0].copy()
        member_value = plan.get("member_value", True)
        data["_group"] = np.where(data[flag] == member_value, "member", "non_member")
        baskets = data.groupby(["_group", transaction], as_index=False)[amount].sum()
        profiles: list[dict[str, Any]] = []
        total_sales = float(data[amount].sum())
        for group_name, group in data.groupby("_group"):
            group_baskets = baskets[baskets["_group"] == group_name]
            values = {
                "total_sales": float(group[amount].sum()),
                "transaction_count": float(group_baskets[transaction].nunique()),
                "mean_basket_amount": float(group_baskets[amount].mean()) if len(group_baskets) else 0.0,
                "sales_share": float(group[amount].sum() / total_sales) if total_sales > 0 else 0.0,
            }
            if quantity and quantity in group.columns:
                values["quantity_total"] = float(group[quantity].sum())
            profiles.append({"entity": str(group_name), "values": values})
        dimensions = len(profiles[0]["values"]) if profiles else 0
        return {
            "family": family,
            "solver_method": "member_group_profile",
            "profiles": profiles,
            "metrics": {
                "entity_count": len(profiles),
                "profile_dimension_count": dimensions,
                "row_count": int(len(data)),
            },
        }

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        profiles = list(result.get("profiles") or [])
        return {
            "status": "PASS" if len(profiles) == 2 else "FAIL",
            "solver": self.name,
            "family": family,
            "groups": [item.get("entity") for item in profiles],
        }


class RFMMemberValueSolverPlugin(SolverPlugin):
    """Evidence-grounded RFM/RFMT-style member value scoring.

    The model deliberately exposes the representation and weights.  It does not
    assume one published paper's AHP weights are universally correct.
    """

    name = "gold.rfm_member_value"
    families = ("ranking",)
    method_aliases = ("RFM member value", "RFMT member value", "RFMS member value", "member value scoring")

    def supports(self, family: str, plan: dict[str, Any]) -> bool:
        return family == "ranking" and _normalize_method_text(plan.get("solver_method", "")) in {
            "rfm member value",
            "rfmt member value",
            "rfms member value",
            "member value scoring",
        }

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        if frame is None:
            return ["TASK_DATA_REQUIRED"]
        required = [
            str(plan.get("member_column") or ""),
            str(plan.get("time_column") or ""),
            str(plan.get("transaction_column") or ""),
            str(plan.get("amount_column") or ""),
        ]
        if any(not value for value in required):
            return ["RFM_SCHEMA_REQUIRED"]
        missing = [column for column in required if column not in frame.columns]
        if missing:
            return ["RFM_COLUMNS_MISSING:" + ",".join(missing)]
        if frame[required[0]].nunique(dropna=True) < 10:
            return ["RFM_MEMBERS_INSUFFICIENT"]
        return []

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        assert frame is not None
        member = str(plan["member_column"])
        features = _retail_member_features(frame, plan)
        dimensions = list(plan.get("score_dimensions") or ["recency_days", "frequency", "monetary", "max_basket"])
        directions = {"recency_days": "cost", "frequency": "benefit", "monetary": "benefit", "max_basket": "benefit", "mean_basket": "benefit", "observed_span_days": "benefit"}
        invalid = [value for value in dimensions if value not in features.columns or value not in directions]
        if invalid:
            raise ValueError("RFM_SCORE_DIMENSIONS_INVALID:" + ",".join(invalid))
        raw_weights = {str(key): float(value) for key, value in (plan.get("weights") or {}).items() if str(key) in dimensions}
        if not raw_weights:
            raw_weights = {value: 1.0 for value in dimensions}
        total = sum(max(0.0, value) for value in raw_weights.values())
        if total <= 0:
            raise ValueError("RFM_WEIGHTS_NONPOSITIVE")
        weights = {value: max(0.0, raw_weights.get(value, 0.0)) / total for value in dimensions}
        normalized = pd.DataFrame(index=features.index)
        for value in dimensions:
            pct = features[value].rank(method="average", pct=True)
            normalized[value] = 1.0 - pct if directions[value] == "cost" else pct
        score = sum(weights[value] * normalized[value] for value in dimensions) * 100.0
        features["member_value_score"] = score
        order = features.sort_values("member_value_score", ascending=False).reset_index(drop=True)
        ranking = [
            {
                "entity": str(row[member]),
                "rank": index + 1,
                "score": float(row["member_value_score"]),
                "recency_days": float(row["recency_days"]),
                "frequency": float(row["frequency"]),
                "monetary": float(row["monetary"]),
                "max_basket": float(row["max_basket"]),
            }
            for index, (_, row) in enumerate(order.iterrows())
        ]
        top_n = max(1, int(np.ceil(len(order) * 0.10)))
        top_full = set(order.head(top_n)[member].astype(str))
        retentions: list[float] = []
        for omitted in dimensions:
            keep = [value for value in dimensions if value != omitted]
            if not keep:
                continue
            denom = sum(weights[value] for value in keep)
            alt_score = sum((weights[value] / denom) * normalized[value] for value in keep)
            alt_top = set(features.assign(_score=alt_score).nlargest(top_n, "_score")[member].astype(str))
            retentions.append(len(top_full & alt_top) / top_n)
        top_decile_stability = float(np.mean(retentions)) if retentions else 1.0
        threshold = float(order.iloc[top_n - 1]["member_value_score"])
        return {
            "family": family,
            "solver_method": "rfm_member_value",
            "protocol": {"method": "rfm_member_value", "representation": dimensions},
            "weights": weights,
            "ranking": ranking,
            "metrics": {
                "member_count": int(len(order)),
                "score_dimension_count": len(dimensions),
                "top_decile_stability": top_decile_stability,
                "median_score": float(order["member_value_score"].median()),
                "top_decile_threshold": threshold,
            },
        }

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        metrics = result.get("metrics", {})
        return {
            "status": "PASS" if int(metrics.get("member_count", 0)) >= 10 else "FAIL",
            "solver": self.name,
            "family": family,
            "member_count": metrics.get("member_count"),
            "top_decile_stability": metrics.get("top_decile_stability"),
        }


class MemberLifecycleStateSolverPlugin(SolverPlugin):
    """Unsupervised lifecycle-state segmentation from member behavior."""

    name = "gold.member_lifecycle_states"
    families = ("exploratory_analysis",)
    method_aliases = ("member lifecycle states", "lifecycle state segmentation", "RFM lifecycle clustering")

    def supports(self, family: str, plan: dict[str, Any]) -> bool:
        return family == "exploratory_analysis" and _normalize_method_text(plan.get("solver_method", "")) in {
            "member lifecycle states",
            "lifecycle state segmentation",
            "rfm lifecycle clustering",
        }

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        if frame is None:
            return ["TASK_DATA_REQUIRED"]
        required = [
            str(plan.get("member_column") or ""),
            str(plan.get("time_column") or ""),
            str(plan.get("transaction_column") or ""),
            str(plan.get("amount_column") or ""),
        ]
        if any(not value for value in required):
            return ["LIFECYCLE_SCHEMA_REQUIRED"]
        missing = [column for column in required if column not in frame.columns]
        if missing:
            return ["LIFECYCLE_COLUMNS_MISSING:" + ",".join(missing)]
        if frame[required[0]].nunique(dropna=True) < max(12, int(plan.get("n_states", 3)) * 4):
            return ["LIFECYCLE_MEMBERS_INSUFFICIENT"]
        return []

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        assert frame is not None
        member = str(plan["member_column"])
        features = _retail_member_features(frame, plan)
        feature_columns = list(plan.get("state_features") or ["recency_days", "frequency", "monetary"])
        matrix = StandardScaler().fit_transform(features[feature_columns].to_numpy(dtype=float))
        n_states = int(plan.get("n_states", 3))
        seed = int(plan.get("random_seed", 42))
        model = KMeans(n_clusters=n_states, random_state=seed, n_init=20)
        labels = model.fit_predict(matrix)
        alt = KMeans(n_clusters=n_states, random_state=seed + 1, n_init=20).fit_predict(matrix)
        ari = float(adjusted_rand_score(labels, alt))
        silhouette = float(silhouette_score(matrix, labels)) if n_states >= 2 and len(features) > n_states else 0.0
        features["_cluster"] = labels
        recency_order = (
            features.groupby("_cluster")["recency_days"].mean().sort_values().index.tolist()
        )
        if n_states == 3:
            state_by_cluster = {
                int(recency_order[0]): "active",
                int(recency_order[1]): "dormant",
                int(recency_order[2]): "lost",
            }
        else:
            state_by_cluster = {int(cluster): f"state_{rank + 1}" for rank, cluster in enumerate(recency_order)}
        features["state"] = features["_cluster"].map(state_by_cluster)
        profiles = []
        for state, group in features.groupby("state"):
            profiles.append(
                {
                    "state": str(state),
                    "count": int(len(group)),
                    "share": float(len(group) / len(features)),
                    "mean_recency_days": float(group["recency_days"].mean()),
                    "mean_frequency": float(group["frequency"].mean()),
                    "mean_monetary": float(group["monetary"].mean()),
                }
            )
        member_states = [
            {"member": str(row[member]), "state": str(row["state"])}
            for _, row in features[[member, "state"]].iterrows()
        ]
        return {
            "family": family,
            "solver_method": "member_lifecycle_states",
            "state_profiles": profiles,
            "member_states": member_states,
            "metrics": {
                "member_count": int(len(features)),
                "state_count": len(profiles),
                "silhouette": silhouette,
                "seed_adjusted_rand": ari,
            },
        }

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        metrics = result.get("metrics", {})
        return {
            "status": "PASS" if int(metrics.get("state_count", 0)) >= 2 else "FAIL",
            "solver": self.name,
            "family": family,
            "state_count": metrics.get("state_count"),
            "seed_adjusted_rand": metrics.get("seed_adjusted_rand"),
        }


class ActivationPromotionAssociationSolverPlugin(SolverPlugin):
    """Estimate non-active -> active transition rates versus promotion exposure."""

    name = "gold.activation_promotion_association"
    families = ("explanatory_inference",)
    method_aliases = ("activation promotion association", "member activation rate", "promotion activation bootstrap")

    def supports(self, family: str, plan: dict[str, Any]) -> bool:
        return family == "explanatory_inference" and _normalize_method_text(plan.get("solver_method", "")) in {
            "activation promotion association",
            "member activation rate",
            "promotion activation bootstrap",
        }

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        if frame is None:
            return ["TASK_DATA_REQUIRED"]
        required = [
            str(plan.get("member_column") or ""),
            str(plan.get("time_column") or ""),
            str(plan.get("transaction_column") or ""),
            str(plan.get("promotion_column") or ""),
        ]
        if any(not value for value in required):
            return ["ACTIVATION_SCHEMA_REQUIRED"]
        missing = [column for column in required if column not in frame.columns]
        if missing:
            return ["ACTIVATION_COLUMNS_MISSING:" + ",".join(missing)]
        if frame[required[0]].nunique(dropna=True) < 10:
            return ["ACTIVATION_MEMBERS_INSUFFICIENT"]
        return []

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        assert frame is not None
        member = str(plan["member_column"])
        time = str(plan["time_column"])
        transaction = str(plan["transaction_column"])
        promotion = str(plan["promotion_column"])
        window_days = max(7, int(plan.get("window_days", 30)))
        inactive_max = max(0, int(plan.get("inactive_max_transactions", 1)))
        active_min = max(inactive_max + 1, int(plan.get("active_min_transactions", 2)))
        data = frame[[member, time, transaction, promotion]].copy()
        data[time] = pd.to_datetime(data[time], errors="coerce")
        data[promotion] = pd.to_numeric(data[promotion], errors="coerce").fillna(0.0)
        data = data.dropna(subset=[member, time, transaction])
        origin = data[time].min().normalize()
        data["_window"] = ((data[time] - origin).dt.days // window_days).astype(int)
        grouped = data.groupby([member, "_window"]).agg(
            transactions=(transaction, "nunique"),
            promotion_exposure=(promotion, lambda value: float(np.mean(np.asarray(value, dtype=float) > 0))),
        )
        members = sorted(data[member].astype(str).unique())
        max_window = int(data["_window"].max())
        first_windows = data.groupby(member)["_window"].min().to_dict()
        rows: list[dict[str, Any]] = []
        for member_value in members:
            first = int(first_windows.get(member_value, 0))
            for current in range(first, max_window):
                prev = grouped.loc[(member_value, current)] if (member_value, current) in grouped.index else None
                nxt = grouped.loc[(member_value, current + 1)] if (member_value, current + 1) in grouped.index else None
                prev_count = int(prev["transactions"]) if prev is not None else 0
                if prev_count > inactive_max:
                    continue
                next_count = int(nxt["transactions"]) if nxt is not None else 0
                promo_exposure = float(prev["promotion_exposure"]) if prev is not None else 0.0
                rows.append(
                    {
                        "member": member_value,
                        "window": current,
                        "promotion_exposed": promo_exposure > 0,
                        "activated": next_count >= active_min,
                    }
                )
        transitions = pd.DataFrame(rows)
        if len(transitions) < 20:
            raise ValueError("ACTIVATION_TRANSITIONS_INSUFFICIENT")
        promo_mask = transitions["promotion_exposed"]
        if promo_mask.sum() < 2 or (~promo_mask).sum() < 2:
            raise ValueError("ACTIVATION_PROMOTION_GROUPS_INSUFFICIENT")
        overall = float(transitions["activated"].mean())
        promo_rate = float(transitions.loc[promo_mask, "activated"].mean())
        nonpromo_rate = float(transitions.loc[~promo_mask, "activated"].mean())
        effect = promo_rate - nonpromo_rate
        runs = max(100, int(plan.get("bootstrap_runs", 400)))
        seed = int(plan.get("random_seed", 42))
        rng = np.random.default_rng(seed)
        boot: list[float] = []
        for _ in range(runs):
            sample = transitions.iloc[rng.integers(0, len(transitions), size=len(transitions))]
            mask = sample["promotion_exposed"]
            if mask.sum() == 0 or (~mask).sum() == 0:
                continue
            boot.append(float(sample.loc[mask, "activated"].mean() - sample.loc[~mask, "activated"].mean()))
        if len(boot) < max(50, runs // 2):
            raise ValueError("ACTIVATION_BOOTSTRAP_UNSTABLE")
        lower, upper = (float(value) for value in np.quantile(boot, [0.025, 0.975]))
        return {
            "family": family,
            "solver_method": "activation_promotion_association",
            "protocol": {"split": "temporal_state_transitions", "bootstrap_runs": runs, "window_days": window_days},
            "interpretation_guard": "associational_not_causal",
            "effects": [
                {
                    "feature": "promotion_exposure",
                    "standardized_coefficient": effect,
                    "bootstrap_ci_95": [lower, upper],
                    "interval_excludes_zero": bool(lower > 0 or upper < 0),
                }
            ],
            "metrics": {
                "transition_count": int(len(transitions)),
                "activation_rate": overall,
                "promotion_activation_rate": promo_rate,
                "nonpromotion_activation_rate": nonpromo_rate,
                "promotion_rate_difference": effect,
            },
        }

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        metrics = result.get("metrics", {})
        return {
            "status": "PASS" if int(metrics.get("transition_count", 0)) >= 20 else "FAIL",
            "solver": self.name,
            "family": family,
            "transition_count": metrics.get("transition_count"),
            "promotion_rate_difference": metrics.get("promotion_rate_difference"),
        }


class MarketBasketAssociationSolverPlugin(SolverPlugin):
    """Pairwise market-basket association rules with support/confidence/lift."""

    name = "gold.market_basket_association"
    families = ("exploratory_analysis",)
    method_aliases = ("market basket association", "association rules", "pairwise basket lift")

    def supports(self, family: str, plan: dict[str, Any]) -> bool:
        return family == "exploratory_analysis" and _normalize_method_text(plan.get("solver_method", "")) in {
            "market basket association",
            "association rules",
            "pairwise basket lift",
        }

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        if frame is None:
            return ["TASK_DATA_REQUIRED"]
        transaction = str(plan.get("transaction_column") or "")
        item = str(plan.get("item_column") or "")
        if not transaction or not item:
            return ["MARKET_BASKET_SCHEMA_REQUIRED"]
        missing = [column for column in (transaction, item) if column not in frame.columns]
        if missing:
            return ["MARKET_BASKET_COLUMNS_MISSING:" + ",".join(missing)]
        if frame[transaction].nunique(dropna=True) < 10:
            return ["MARKET_BASKET_TRANSACTIONS_INSUFFICIENT"]
        return []

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        assert frame is not None
        transaction = str(plan["transaction_column"])
        item = str(plan["item_column"])
        data = frame[[transaction, item]].dropna().copy()
        baskets = data.groupby(transaction)[item].agg(lambda values: sorted(set(str(value) for value in values)))
        max_items = max(2, int(plan.get("max_items_per_basket", 50)))
        usable = [values for values in baskets if 1 <= len(values) <= max_items]
        transaction_count = len(usable)
        if transaction_count < 10:
            raise ValueError("MARKET_BASKET_USABLE_TRANSACTIONS_INSUFFICIENT")
        item_counts: dict[str, int] = {}
        pair_counts: dict[tuple[str, str], int] = {}
        for values in usable:
            for value in values:
                item_counts[value] = item_counts.get(value, 0) + 1
            for left, right in combinations(values, 2):
                pair_counts[(left, right)] = pair_counts.get((left, right), 0) + 1
        min_support_fraction = float(plan.get("min_support", 0.01))
        min_support_count = int(plan.get("min_support_count", 0))
        required_count = max(min_support_count, int(np.ceil(min_support_fraction * transaction_count)), 1)
        min_confidence = float(plan.get("min_confidence", 0.2))
        rules: list[dict[str, Any]] = []
        for (left, right), pair_count in pair_counts.items():
            if pair_count < required_count:
                continue
            support = pair_count / transaction_count
            for antecedent, consequent in ((left, right), (right, left)):
                confidence = pair_count / item_counts[antecedent]
                consequent_support = item_counts[consequent] / transaction_count
                lift = confidence / consequent_support if consequent_support > 0 else 0.0
                if confidence >= min_confidence:
                    rules.append(
                        {
                            "antecedent": antecedent,
                            "consequent": consequent,
                            "support": float(support),
                            "confidence": float(confidence),
                            "lift": float(lift),
                            "support_count": int(pair_count),
                        }
                    )
        rules.sort(key=lambda value: (value["lift"], value["confidence"], value["support"]), reverse=True)
        top_k = max(1, int(plan.get("top_k", 20)))
        top_rules = rules[:top_k]
        max_lift = float(top_rules[0]["lift"]) if top_rules else 0.0
        return {
            "family": family,
            "solver_method": "market_basket_association",
            "top_rules": top_rules,
            "metrics": {
                "transaction_count": int(transaction_count),
                "unique_item_count": len(item_counts),
                "rule_count": len(rules),
                "max_lift": max_lift,
                "skipped_large_baskets": int(len(baskets) - len(usable)),
            },
            "protocol": {
                "min_support_count": required_count,
                "min_confidence": min_confidence,
                "rule_semantics": "pairwise_directional_support_confidence_lift",
            },
        }

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        metrics = result.get("metrics", {})
        return {
            "status": "PASS" if int(metrics.get("rule_count", 0)) > 0 else "FAIL",
            "solver": self.name,
            "family": family,
            "rule_count": metrics.get("rule_count"),
            "max_lift": metrics.get("max_lift"),
        }


class ClusteringSolverPlugin(SolverPlugin):
    name = "gold.clustering"
    families = ("exploratory_analysis",)
    method_aliases = ("K-Means", "DBSCAN", "clustering")

    def supports(self, family: str, plan: dict[str, Any]) -> bool:
        return family == "exploratory_analysis" and str(plan.get("solver_method", "")).lower() in {
            "kmeans",
            "k-means",
            "dbscan",
        }

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        if frame is None:
            return ["TASK_DATA_REQUIRED"]
        features = [str(value) for value in plan.get("feature_columns", [])]
        if not features:
            return ["CLUSTER_FEATURE_COLUMNS_REQUIRED"]
        missing = [column for column in features if column not in frame.columns]
        if missing:
            return ["CLUSTER_COLUMNS_MISSING:" + ",".join(missing)]
        if len(frame[features].dropna()) < 5:
            return ["CLUSTER_ROWS_INSUFFICIENT"]
        method = str(plan.get("solver_method", "")).lower()
        if method in {"kmeans", "k-means"} and int(plan.get("n_clusters", 0)) < 2:
            return ["KMEANS_CLUSTER_COUNT_REQUIRED"]
        return []

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        assert frame is not None
        features = [str(value) for value in plan["feature_columns"]]
        data = frame[features].dropna().reset_index(drop=True)
        matrix = StandardScaler().fit_transform(data.to_numpy(dtype=float))
        method = str(plan.get("solver_method", "")).lower()
        seed = int(plan.get("random_seed", 42))
        if method in {"kmeans", "k-means"}:
            model = KMeans(n_clusters=int(plan["n_clusters"]), random_state=seed, n_init=10)
            labels = model.fit_predict(matrix)
            inertia = float(model.inertia_)
        else:
            model = DBSCAN(eps=float(plan.get("eps", 0.5)), min_samples=int(plan.get("min_samples", 5)))
            labels = model.fit_predict(matrix)
            inertia = None
        unique = sorted(set(int(value) for value in labels))
        non_noise = [value for value in unique if value != -1]
        score = None
        if len(non_noise) >= 2:
            mask = labels != -1
            if int(mask.sum()) > len(non_noise):
                score = float(silhouette_score(matrix[mask], labels[mask]))
        counts = {str(label): int(np.sum(labels == label)) for label in unique}
        return {
            "family": "exploratory_analysis",
            "solver_method": "kmeans" if method in {"kmeans", "k-means"} else "dbscan",
            "cluster_count": len(non_noise),
            "noise_count": int(np.sum(labels == -1)),
            "cluster_counts": counts,
            "silhouette": score,
            "inertia": inertia,
            "rows": int(len(data)),
        }

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        status = "PASS" if int(result.get("cluster_count", 0)) >= 1 else "FAIL"
        return {
            "status": status,
            "solver": self.name,
            "family": family,
            "cluster_count": result.get("cluster_count"),
            "noise_count": result.get("noise_count"),
            "silhouette": result.get("silhouette"),
        }


class PipelineLayoutOptimizationSolverPlugin(SolverPlugin):
    """Continuous geometry optimizer for C-problem pipeline/route layout.

    The plan describes two facilities on one side of a straight transport line,
    one urban boundary, a shared junction E, a boundary crossing F and a station
    G on the transport line.  Nothing in this solver is hard-coded to the 2010
    published optimum; the historical values are used only in regression tests.
    """

    name = "gold.pipeline_layout_continuous"
    families = ("optimization",)
    method_aliases = (
        "pipeline layout continuous optimization",
        "pipeline geometry optimization",
        "geometric pipeline layout",
        "continuous route layout optimization",
    )

    def supports(self, family: str, plan: dict[str, Any]) -> bool:
        method = _normalize_method_text(str(plan.get("solver_method") or ""))
        return family == "optimization" and method in {
            "pipeline layout continuous",
            "pipeline layout continuous optimization",
            "pipeline geometry optimization",
            "geometric pipeline layout",
        }

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        errors: list[str] = []
        required = (
            "factory_a_height",
            "factory_b_height",
            "factory_b_x",
            "urban_boundary_x",
            "a_nonshared_cost",
            "b_nonshared_cost",
            "shared_cost",
            "urban_surcharge",
        )
        for field in required:
            if plan.get(field) is None:
                errors.append(f"{field.upper()}_REQUIRED")
        if errors:
            return errors
        a = float(plan["factory_a_height"])
        b = float(plan["factory_b_height"])
        d = float(plan["factory_b_x"])
        c = float(plan["urban_boundary_x"])
        if min(a, b, d, c) < 0 or c > d:
            errors.append("PIPELINE_GEOMETRY_INVALID")
        if min(float(plan[name]) for name in ("a_nonshared_cost", "b_nonshared_cost", "shared_cost", "urban_surcharge")) < 0:
            errors.append("PIPELINE_COST_INVALID")
        return errors

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        result = self._solve_core(plan)
        surcharge = float(plan["urban_surcharge"])
        stress_runs: list[dict[str, Any]] = []
        for factor in (0.9, 1.1):
            stressed = dict(plan)
            stressed["urban_surcharge"] = surcharge * factor
            solved = self._solve_core(stressed, include_sensitivity=False)
            stress_runs.append(
                {
                    "urban_surcharge_factor": factor,
                    "objective_value": solved["objective_value"],
                    "station_x": solved["solution"]["station_x"],
                    "shared_length": solved["route_lengths"]["shared_EG"],
                }
            )
        baseline = float(result["objective_value"])
        result["sensitivity_runs"] = stress_runs
        result["metrics"] = {
            "objective_value": baseline,
            "surcharge_sensitivity_max_relative_change": max(
                abs(float(item["objective_value"]) - baseline) / max(abs(baseline), 1e-12)
                for item in stress_runs
            ),
        }
        if bool(plan.get("compare_no_shared", False)) and not bool(plan.get("force_zero_shared", False)):
            alternative_plan = dict(plan)
            alternative_plan["force_zero_shared"] = True
            alternative_plan["compare_no_shared"] = False
            alternative = self._solve_core(alternative_plan, include_sensitivity=False)
            result["no_shared_comparison"] = {
                "objective_value": float(alternative["objective_value"]),
                "solution": dict(alternative["solution"]),
                "route_lengths": dict(alternative["route_lengths"]),
                "cost_difference_vs_shared": float(alternative["objective_value"] - baseline),
            }
            result["metrics"]["no_shared_objective_value"] = float(alternative["objective_value"])
            result["metrics"]["shared_cost_advantage"] = float(alternative["objective_value"] - baseline)
        return result

    def _solve_core(self, plan: dict[str, Any], *, include_sensitivity: bool = True) -> dict[str, Any]:
        a = float(plan["factory_a_height"])
        b = float(plan["factory_b_height"])
        d = float(plan["factory_b_x"])
        c = float(plan["urban_boundary_x"])
        ca = float(plan["a_nonshared_cost"])
        cb = float(plan["b_nonshared_cost"])
        cs = float(plan["shared_cost"])
        urban = float(plan["urban_surcharge"])
        force_zero_shared = bool(plan.get("force_zero_shared", False))

        def components(values: np.ndarray) -> tuple[float, float, float, float]:
            x, y, z = (float(values[0]), float(values[1]), float(values[2]))
            s1 = float(np.hypot(x, y - a))
            s2 = float(np.hypot(c - x, z - y))
            s3 = float(y)
            s4 = float(np.hypot(d - c, b - z))
            return s1, s2, s3, s4

        def objective(values: np.ndarray) -> float:
            s1, s2, s3, s4 = components(values)
            return ca * s1 + cb * s2 + cs * s3 + (cb + urban) * s4

        y_bounds = (0.0, 0.0) if force_zero_shared else (0.0, a)
        bounds = [(0.0, c), y_bounds, (0.0, b)]
        starts = [
            np.asarray([c / 3.0, 0.0 if force_zero_shared else a / 3.0, max(0.0, b - 1.0)]),
            np.asarray([c / 2.0, 0.0 if force_zero_shared else a / 2.0, b]),
            np.asarray([2.0 * c / 3.0, 0.0 if force_zero_shared else 0.1 * a, 0.8 * b]),
        ]
        candidates = [optimize.minimize(objective, start, method="L-BFGS-B", bounds=bounds) for start in starts]
        best = min(candidates, key=lambda item: float(item.fun))
        if not bool(best.success):
            raise ValueError("PIPELINE_OPTIMIZATION_FAILED:" + str(best.message))
        x, y, z = (float(best.x[0]), float(best.x[1]), float(best.x[2]))
        s1, s2, s3, s4 = components(best.x)
        return {
            "family": "optimization",
            "solver_method": "pipeline_layout_continuous",
            "protocol": {"method": "multi_start_lbfgsb", "starts": len(starts)},
            "solver_status": 0,
            "constraint_status": "PASS",
            "solution": {
                "station_x": x,
                "shared_junction_y": y,
                "urban_boundary_crossing_y": z,
            },
            "route_lengths": {
                "a_nonshared_AE": s1,
                "b_suburban_EF": s2,
                "shared_EG": s3,
                "b_urban_BF": s4,
            },
            "objective_value": float(best.fun),
            "force_zero_shared": force_zero_shared,
        }

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        solution = result.get("solution") or {}
        valid = (
            result.get("constraint_status") == "PASS"
            and int(result.get("solver_status", -1)) == 0
            and all(np.isfinite(float(value)) for value in solution.values())
        )
        return {
            "status": "PASS" if valid else "FAIL",
            "solver": self.name,
            "family": family,
            "objective_value": result.get("objective_value"),
            "route_lengths": result.get("route_lengths", {}),
        }

    def sensitivity(
        self,
        family: str,
        plan: dict[str, Any],
        frame: pd.DataFrame | None,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "status": "PASS",
            "solver": self.name,
            "family": family,
            "parameter": "urban_surcharge",
            "runs": list(result.get("sensitivity_runs", [])),
        }


class RetailPricingReplenishmentSolverPlugin(SolverPlugin):
    """Demand-aware pricing and replenishment baseline for perishable retail.

    The plugin is intentionally generic: competition-specific data preparation is
    kept outside the solver.  It accepts a daily entity panel, uses chronological
    demand validation, searches only the historically observed markup range, and
    carries loss/replenishment constraints explicitly.
    """

    name = "gold.retail_pricing_replenishment"
    families = ("optimization",)
    method_aliases = (
        "retail category pricing replenishment",
        "retail item pricing replenishment",
        "demand aware pricing replenishment",
        "perishable retail pricing optimization",
    )

    def supports(self, family: str, plan: dict[str, Any]) -> bool:
        method = str(plan.get("solver_method") or "").lower()
        return family == "optimization" and method in {
            "retail_category_pricing_replenishment",
            "retail_item_pricing_replenishment",
            "demand_aware_pricing_replenishment",
        }

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        return validate_retail_plan(frame, plan)

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        assert frame is not None
        return solve_retail_pricing_replenishment(frame, plan)

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        status = "PASS" if result.get("constraint_status") == "PASS" and int(result.get("solver_status", -1)) == 0 else "FAIL"
        return {
            "status": status,
            "solver": self.name,
            "family": family,
            "mode": plan.get("mode"),
            "objective_value": result.get("objective_value"),
            "selected_item_count": result.get("selected_item_count"),
            "constraint_status": result.get("constraint_status"),
        }

    def sensitivity(
        self,
        family: str,
        plan: dict[str, Any],
        frame: pd.DataFrame | None,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        runs = list(result.get("sensitivity_runs") or [])
        return {
            "status": "PASS" if len(runs) >= 2 else "NOT_AVAILABLE",
            "solver": self.name,
            "family": family,
            "parameter": "wholesale_cost_factor" if runs else None,
            "runs": runs,
        }


class OptimizationSolverPlugin(SolverPlugin):
    name = "gold.optimization_grid"
    families = ("optimization",)
    method_aliases = ("bounded-grid optimization", "bounded grid", "constrained grid search")

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        errors = []
        for field in ("variables", "constraints", "objective"):
            if not plan.get(field):
                errors.append(f"{field.upper()}_REQUIRED")
        return errors

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        return execute_optimization(plan)

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "PASS" if result.get("constraint_status") == "PASS" else "FAIL",
            "solver": self.name,
            "family": family,
            "constraint_status": result.get("constraint_status"),
            "feasible_points": result.get("protocol", {}).get("feasible_points"),
        }


class SimulationSolverPlugin(SolverPlugin):
    name = "gold.monte_carlo"
    families = ("simulation",)
    method_aliases = ("Monte Carlo additive-normal", "Monte Carlo", "scenario simulation")

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        errors = []
        if not plan.get("parameters"):
            errors.append("PARAMETERS_REQUIRED")
        if int(plan.get("replications", 0)) < 2:
            errors.append("REPLICATIONS_REQUIRED")
        if not plan.get("scenarios"):
            errors.append("SCENARIOS_REQUIRED")
        return errors

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        return execute_simulation(plan)

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        return {
            "status": "PASS",
            "solver": self.name,
            "family": family,
            "scenario_count": len(result.get("scenarios", {})),
            "uncertainty": result.get("uncertainty"),
        }


class EntropyTopsisRankingSolverPlugin(SolverPlugin):
    """Multi-criteria decision-making with entropy weights and TOPSIS.

    This plugin exists because contest-style evaluation/ranking is not the same
    task as information-retrieval ranking. Criterion directions are explicit,
    entropy weights are learned from the registered decision matrix, and the
    final ordering is stress-tested by leaving one criterion out at a time.
    """

    name = "gold.entropy_topsis"
    families = ("ranking",)
    method_aliases = ("entropy TOPSIS", "entropy-topsis", "TOPSIS", "multi-criteria evaluation", "MCDM")

    def supports(self, family: str, plan: dict[str, Any]) -> bool:
        return family == "ranking" and str(plan.get("solver_method") or "").lower() in {
            "entropy_topsis",
            "entropy-topsis",
            "topsis",
            "mcdm",
        }

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        if frame is None:
            return ["TASK_DATA_REQUIRED"]
        errors: list[str] = []
        entity_column = str(plan.get("entity_column") or "")
        criteria = plan.get("criteria") or []
        if not entity_column:
            errors.append("ENTITY_COLUMN_REQUIRED")
        elif entity_column not in frame.columns:
            errors.append("ENTITY_COLUMN_MISSING")
        if len(criteria) < 2:
            errors.append("MCDM_CRITERIA_INSUFFICIENT")
        for item in criteria:
            if not isinstance(item, dict):
                errors.append("MCDM_CRITERION_SCHEMA_INVALID")
                continue
            column = str(item.get("column") or "")
            direction = str(item.get("direction") or "")
            if column not in frame.columns:
                errors.append(f"MCDM_CRITERION_MISSING:{column}")
            if direction not in {"benefit", "cost"}:
                errors.append(f"MCDM_DIRECTION_INVALID:{column}")
        if entity_column in frame.columns and frame[entity_column].nunique(dropna=True) < 2:
            errors.append("MCDM_ENTITIES_INSUFFICIENT")
        return list(dict.fromkeys(errors))

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        assert frame is not None
        entity_column = str(plan["entity_column"])
        criteria = [dict(item) for item in plan["criteria"]]
        columns = [str(item["column"]) for item in criteria]
        data = frame[[entity_column, *columns]].dropna().copy()
        if data[entity_column].duplicated().any():
            raise ValueError("MCDM_ENTITY_DUPLICATED")
        matrix = data[columns].apply(pd.to_numeric, errors="raise").to_numpy(dtype=float)
        directions = [str(item["direction"]) for item in criteria]
        scores, weights, normalized = _entropy_topsis_scores(matrix, directions)
        order = np.argsort(-scores)
        ranking = [
            {
                "entity": str(data.iloc[index][entity_column]),
                "rank": rank,
                "score": float(scores[index]),
            }
            for rank, index in enumerate(order, start=1)
        ]
        full_rank = {
            item["entity"]: int(item["rank"])
            for item in ranking
        }
        winner = ranking[0]["entity"]
        leave_one_out: list[dict[str, Any]] = []
        correlations: list[float] = []
        retained = 0
        if len(criteria) >= 3:
            for omit_index, criterion in enumerate(criteria):
                keep = [index for index in range(len(criteria)) if index != omit_index]
                subset_scores, _subset_weights, _subset_norm = _entropy_topsis_scores(
                    matrix[:, keep],
                    [directions[index] for index in keep],
                )
                subset_order = np.argsort(-subset_scores)
                subset_ranking = [str(data.iloc[index][entity_column]) for index in subset_order]
                subset_winner = subset_ranking[0]
                if subset_winner == winner:
                    retained += 1
                subset_rank = {entity: rank for rank, entity in enumerate(subset_ranking, start=1)}
                left = np.asarray([full_rank[entity] for entity in sorted(full_rank)], dtype=float)
                right = np.asarray([subset_rank[entity] for entity in sorted(full_rank)], dtype=float)
                correlation = float(pd.Series(left).corr(pd.Series(right), method="spearman"))
                if np.isfinite(correlation):
                    correlations.append(correlation)
                leave_one_out.append(
                    {
                        "omitted_criterion": str(criterion["column"]),
                        "winner": subset_winner,
                        "spearman_rank_correlation": correlation,
                    }
                )
        winner_retention = retained / len(criteria) if len(criteria) >= 3 else 1.0
        mean_spearman = float(np.mean(correlations)) if correlations else 1.0
        top_margin = float(ranking[0]["score"] - ranking[1]["score"]) if len(ranking) > 1 else 1.0
        return {
            "family": "ranking",
            "protocol": {"method": "entropy_topsis", "entity_column": entity_column},
            "criteria": criteria,
            "weights": {columns[index]: float(weights[index]) for index in range(len(columns))},
            "normalized_matrix": normalized.tolist(),
            "ranking": ranking,
            "winner": winner,
            "metrics": {
                "winner_retention_rate": float(winner_retention),
                "mean_spearman": mean_spearman,
                "top_score_margin": top_margin,
            },
            "sensitivity": {"leave_one_criterion_out": leave_one_out},
        }

    def diagnose(self, family: str, plan: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        weights = result.get("weights", {})
        scores = [float(item.get("score", np.nan)) for item in result.get("ranking", [])]
        status = "PASS"
        if not weights or abs(sum(float(value) for value in weights.values()) - 1.0) > 1e-6:
            status = "FAIL"
        if not scores or not all(np.isfinite(scores)):
            status = "FAIL"
        return {
            "status": status,
            "solver": self.name,
            "family": family,
            "weights_sum": float(sum(float(value) for value in weights.values())) if weights else 0.0,
            "winner": result.get("winner"),
            "winner_retention_rate": result.get("metrics", {}).get("winner_retention_rate"),
            "mean_spearman": result.get("metrics", {}).get("mean_spearman"),
        }


def _entropy_topsis_scores(matrix: np.ndarray, directions: list[str]) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    values = np.asarray(matrix, dtype=float)
    if values.ndim != 2 or values.shape[0] < 2 or values.shape[1] < 2:
        raise ValueError("MCDM_MATRIX_INVALID")
    if len(directions) != values.shape[1]:
        raise ValueError("MCDM_DIRECTION_COUNT_MISMATCH")
    normalized = np.zeros_like(values, dtype=float)
    for index, direction in enumerate(directions):
        column = values[:, index]
        low = float(np.min(column))
        high = float(np.max(column))
        if abs(high - low) <= 1e-12:
            normalized[:, index] = 0.5
        elif direction == "benefit":
            normalized[:, index] = (column - low) / (high - low)
        elif direction == "cost":
            normalized[:, index] = (high - column) / (high - low)
        else:
            raise ValueError(f"MCDM_DIRECTION_INVALID:{direction}")

    shifted = normalized + 1e-12
    proportions = shifted / shifted.sum(axis=0, keepdims=True)
    k = 1.0 / np.log(values.shape[0])
    entropy = -k * np.sum(proportions * np.log(proportions), axis=0)
    divergence = np.maximum(0.0, 1.0 - entropy)
    weights = (
        divergence / divergence.sum()
        if float(divergence.sum()) > 1e-12
        else np.full(values.shape[1], 1.0 / values.shape[1])
    )
    weighted = normalized * weights
    ideal = np.max(weighted, axis=0)
    anti = np.min(weighted, axis=0)
    distance_ideal = np.linalg.norm(weighted - ideal, axis=1)
    distance_anti = np.linalg.norm(weighted - anti, axis=1)
    denominator = distance_ideal + distance_anti
    scores = np.divide(
        distance_anti,
        denominator,
        out=np.full_like(distance_anti, 0.5),
        where=denominator > 1e-12,
    )
    return scores, weights, normalized


class RankingSolverPlugin(SolverPlugin):
    name = "gold.ranking"
    families = ("ranking",)
    method_aliases = ("pairwise/listwise ranking evaluation", "pairwise ranking", "listwise ranking", "evaluation ranking")

    def validate_inputs(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> list[str]:
        if frame is None:
            return ["TASK_DATA_REQUIRED"]
        required = {"query", "item", "relevance", "score"}
        missing = sorted(required - set(frame.columns))
        if missing:
            return ["RANKING_COLUMNS_MISSING:" + ",".join(missing)]
        if plan.get("protocol") not in {"pairwise", "listwise"}:
            return ["RANKING_PROTOCOL_REQUIRED"]
        return []

    def solve(self, family: str, plan: dict[str, Any], frame: pd.DataFrame | None) -> dict[str, Any]:
        assert frame is not None
        return execute_ranking(frame, plan)


def _validate_linear_optimization_plan(plan: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    variables = plan.get("variables", [])
    objective = plan.get("objective")
    if not variables:
        errors.append("DECISION_VARIABLES_REQUIRED")
        return errors
    names = [str(item.get("name") or "") for item in variables if isinstance(item, dict)]
    if len(names) != len(variables) or any(not name for name in names):
        errors.append("VARIABLE_SCHEMA_INVALID")
    if len(set(names)) != len(names):
        errors.append("VARIABLE_NAMES_DUPLICATED")
    for item in variables:
        if not isinstance(item, dict):
            continue
        lower = float(item.get("lower", 0.0))
        upper = float(item.get("upper", np.inf))
        if upper < lower:
            errors.append(f"VARIABLE_DOMAIN_INVALID:{item.get('name', '')}")
    if not isinstance(objective, dict) or objective.get("sense") not in {"min", "max"}:
        errors.append("OBJECTIVE_SCHEMA_INVALID")
    for constraint in plan.get("constraints", []):
        if not isinstance(constraint, dict) or constraint.get("operator") not in {"<=", ">=", "=="}:
            errors.append("CONSTRAINT_SCHEMA_INVALID")
            break
        unknown = sorted(set(constraint.get("coefficients", {})) - set(names))
        if unknown:
            errors.append("CONSTRAINT_UNKNOWN_VARIABLE:" + ",".join(unknown))
    return list(dict.fromkeys(errors))


def _linear_problem_arrays(
    plan: dict[str, Any],
) -> tuple[
    list[str],
    np.ndarray,
    list[tuple[float, float]],
    list[list[float]],
    list[float],
    list[list[float]],
    list[float],
    str,
    float,
]:
    variables = plan["variables"]
    names = [str(item["name"]) for item in variables]
    objective = plan["objective"]
    coefficients = objective.get("coefficients", {})
    c = np.asarray([float(coefficients.get(name, 0.0)) for name in names], dtype=float)
    bounds = [
        (float(item.get("lower", 0.0)), float(item.get("upper", np.inf)))
        for item in variables
    ]
    a_ub: list[list[float]] = []
    b_ub: list[float] = []
    a_eq: list[list[float]] = []
    b_eq: list[float] = []
    for constraint in plan.get("constraints", []):
        row = [float(constraint.get("coefficients", {}).get(name, 0.0)) for name in names]
        rhs = float(constraint["rhs"])
        operator = constraint["operator"]
        if operator == "<=":
            a_ub.append(row)
            b_ub.append(rhs)
        elif operator == ">=":
            a_ub.append([-value for value in row])
            b_ub.append(-rhs)
        else:
            a_eq.append(row)
            b_eq.append(rhs)
    return (
        names,
        c,
        bounds,
        a_ub,
        b_ub,
        a_eq,
        b_eq,
        str(objective["sense"]),
        float(objective.get("constant", 0.0)),
    )


def _constraints_satisfied(plan: dict[str, Any], solution: dict[str, float]) -> bool:
    tolerance = 1e-7
    for constraint in plan.get("constraints", []):
        lhs = sum(
            float(coefficient) * float(solution[name])
            for name, coefficient in constraint.get("coefficients", {}).items()
        )
        rhs = float(constraint["rhs"])
        operator = constraint["operator"]
        if operator == "<=" and lhs > rhs + tolerance:
            return False
        if operator == ">=" and lhs < rhs - tolerance:
            return False
        if operator == "==" and abs(lhs - rhs) > tolerance:
            return False
    return True


def _normalize_method_text(value: str) -> str:
    return " ".join(str(value).lower().replace("_", " ").replace("-", " ").split())


DEFAULT_GOLD_SOLVERS = (
    ForecastingSolverPlugin,
    HoltForecastSolverPlugin,
    PopularityLifecycleForecastSolverPlugin,
    PanelTrendCharacterizationSolverPlugin,
    PanelHoltForecastSolverPlugin,
    ClassificationSolverPlugin,
    RandomForestClassificationSolverPlugin,
    ActivationPromotionAssociationSolverPlugin,
    ExplanatoryInferenceSolverPlugin,
    DistributionForecastSolverPlugin,
    LinearProgrammingSolverPlugin,
    MilpSolverPlugin,
    MemberGroupProfileSolverPlugin,
    RFMMemberValueSolverPlugin,
    MemberLifecycleStateSolverPlugin,
    MarketBasketAssociationSolverPlugin,
    ClusteringSolverPlugin,
    PanelProfileSummarySolverPlugin,
    ExploratoryAnalysisSolverPlugin,
    PipelineLayoutOptimizationSolverPlugin,
    RetailPricingReplenishmentSolverPlugin,
    OptimizationSolverPlugin,
    SimulationSolverPlugin,
    EntropyTopsisRankingSolverPlugin,
    RankingSolverPlugin,
)


class SolverRegistry:
    def __init__(self, plugins: list[SolverPlugin] | None = None) -> None:
        self.plugins = plugins or [plugin() for plugin in DEFAULT_GOLD_SOLVERS]

    def resolve(self, family: str, plan: dict[str, Any]) -> SolverPlugin:
        matches = [plugin for plugin in self.plugins if plugin.supports(family, plan)]
        if not matches:
            raise ValueError(f"SOLVER_PLUGIN_UNAVAILABLE:{family}")
        return matches[0]

    def supports_method(self, method: str, family: str | None = None) -> bool:
        lowered = _normalize_method_text(method)
        return any(
            (family is None or family in plugin.families)
            and any(
                _normalize_method_text(alias) in lowered
                or lowered in _normalize_method_text(alias)
                for alias in plugin.method_aliases
            )
            for plugin in self.plugins
        )

    def capabilities(self) -> list[dict[str, Any]]:
        return [
            {
                "name": plugin.name,
                "families": list(plugin.families),
                "method_aliases": list(plugin.method_aliases),
            }
            for plugin in self.plugins
        ]

    def gap_report(self, modeling_decision: Any) -> dict[str, Any]:
        candidates = (
            modeling_decision.candidates
            if hasattr(modeling_decision, "candidates")
            else modeling_decision.get("candidates", [])
        )
        task_family = (
            str(modeling_decision.task_family)
            if hasattr(modeling_decision, "task_family")
            else str(modeling_decision.get("task_family", ""))
        )
        gaps = []
        for item in candidates:
            if hasattr(item, "feasibility"):
                feasibility = item.feasibility
                method = str(item.method)
                source = str(item.source)
            else:
                feasibility = item.get("feasibility")
                method = str(item.get("method", ""))
                source = str(item.get("source", ""))
            if feasibility == "NEEDS_SOLVER" and not self.supports_method(method, task_family or None):
                gaps.append({"method": method, "source": source})
        return {
            "missing_solver_methods": gaps,
            "missing_count": len(gaps),
            "registered_solver_count": len(self.plugins),
        }


class SolverEngineService:
    def __init__(
        self,
        cases: Any,
        artifacts: Any,
        registry: SolverRegistry | None = None,
        validation: ValidationRunner | None = None,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.registry = registry or SolverRegistry()
        self.validation = validation or ValidationRunner()

    def persist_gap_report(
        self,
        case_id: str,
        subproblem_id: str,
        modeling_decision: Any,
        source_artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        report = self.registry.gap_report(modeling_decision)
        root = self.cases.case_root(case_id)
        path = root / "analysis" / "solver_gaps" / f"{subproblem_id}.json"
        decision_gate = (
            str(modeling_decision.gate)
            if hasattr(modeling_decision, "gate")
            else str(modeling_decision.get("gate", ""))
        )
        payload = {
            "schema_version": 1,
            "case_id": case_id,
            "subproblem_id": subproblem_id,
            **report,
            "modeling_gate": decision_gate,
            "blocking": bool(report["missing_count"] and decision_gate == "BLOCKED"),
            "registered_capabilities": self.registry.capabilities(),
            "generated_at": now_iso(),
        }
        atomic_write_json(path, payload)
        artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "solver_capability_gap",
            "solver_engine",
            upstream=list(source_artifact_ids or []),
            paper_eligible=False,
        )
        return {**payload, "artifact_id": artifact["artifact_id"]}

    def execute(
        self,
        case_id: str,
        subproblem_id: str,
        family: str,
        plan: dict[str, Any],
        *,
        frame: pd.DataFrame | None = None,
        source_artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        solver = self.registry.resolve(family, plan)
        input_frame_artifact = self._persist_input_frame(
            case_id,
            subproblem_id,
            frame,
            source_artifact_ids,
        )
        execution_sources = list(
            dict.fromkeys(
                [
                    *(source_artifact_ids or []),
                    *(
                        [input_frame_artifact["artifact_id"]]
                        if input_frame_artifact is not None
                        else []
                    ),
                ]
            )
        )
        errors = solver.validate_inputs(family, plan, frame)
        if errors:
            raise ValueError("SOLVER_INPUT_INVALID:" + ";".join(errors))
        build = solver.build(family, plan)
        if input_frame_artifact is not None:
            build["input_frame_artifact_id"] = input_frame_artifact["artifact_id"]
        result = solver.solve(family, plan, frame)
        diagnostics = solver.diagnose(family, plan, result)
        if diagnostics.get("status") == "FAIL":
            raise ValueError(f"SOLVER_DIAGNOSTICS_FAILED:{solver.name}")
        assessment = self.validation.assess(
            family,
            plan,
            result,
            diagnostics,
            frame,
            case_id=case_id,
            subproblem_id=subproblem_id,
        )
        validation = self.validation.persist(
            self.cases,
            self.artifacts,
            case_id,
            subproblem_id,
            assessment,
            execution_sources,
        )
        if assessment.gate == "FAIL":
            raise ValueError(
                "VALIDATION_PROTOCOL_FAILED:"
                + ",".join(item.code for item in assessment.findings if item.severity == "BLOCK")
            )
        build["validation_protocol_id"] = assessment.protocol_id
        build["validation_gate"] = assessment.gate
        sensitivity = solver.sensitivity(family, plan, frame, result)
        evidence_sources = list(
            dict.fromkeys([*execution_sources, validation["artifact"]["artifact_id"]])
        )
        evidence = solver.export_evidence(
            self.cases,
            self.artifacts,
            case_id,
            subproblem_id,
            family,
            plan,
            build,
            result,
            diagnostics,
            sensitivity,
            evidence_sources,
        )
        return {
            "task_run_id": evidence["solver_run_id"],
            "solver": solver.name,
            "build": build,
            "result": result,
            "diagnostics": diagnostics,
            "sensitivity": sensitivity,
            "validation": validation,
            "input_frame_artifact": input_frame_artifact,
            "artifact": evidence["artifact"],
        }

    def _persist_input_frame(
        self,
        case_id: str,
        subproblem_id: str,
        frame: pd.DataFrame | None,
        source_artifact_ids: list[str] | None,
    ) -> dict[str, Any] | None:
        if frame is None:
            return None
        root = self.cases.case_root(case_id)
        snapshot_id = uuid4().hex[:12]
        path = root / "results" / "solvers" / subproblem_id / "inputs" / f"input-{snapshot_id}.csv"
        path.parent.mkdir(parents=True, exist_ok=True)
        frame.to_csv(path, index=False)
        return self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "solver_input_frame",
            "solver_engine",
            upstream=list(source_artifact_ids or []),
            paper_eligible=False,
        )

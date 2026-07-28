from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class TaskFamilyPlugin:
    family: str
    required_plan_fields: tuple[str, ...]
    required_result_types: tuple[str, ...]
    validate_protocol: Callable[[dict[str, Any]], list[str]]


def _tabular(plan: dict[str, Any]) -> list[str]:
    errors = []
    if plan.get("task_type") not in {"regression", "classification"}:
        errors.append("TABULAR_TASK_TYPE_INVALID")
    if not plan.get("feature_columns"):
        errors.append("FEATURE_COLUMNS_MISSING")
    return errors


def _forecasting(plan: dict[str, Any]) -> list[str]:
    errors = []
    if not plan.get("time_column"):
        errors.append("TIME_COLUMN_REQUIRED")
    if plan.get("split_strategy") != "temporal":
        errors.append("TEMPORAL_SPLIT_REQUIRED")
    return errors


def _optimization(plan: dict[str, Any]) -> list[str]:
    errors = []
    if not plan.get("variables"):
        errors.append("DECISION_VARIABLES_REQUIRED")
    if not plan.get("constraints"):
        errors.append("CONSTRAINTS_REQUIRED")
    return errors


def _simulation(plan: dict[str, Any]) -> list[str]:
    errors = []
    if not plan.get("parameters"):
        errors.append("PARAMETERS_REQUIRED")
    if int(plan.get("replications", 0)) < 2:
        errors.append("REPLICATIONS_REQUIRED")
    return errors


def _ranking(plan: dict[str, Any]) -> list[str]:
    if plan.get("protocol") not in {"pairwise", "listwise"}:
        return ["RANKING_PROTOCOL_REQUIRED"]
    return []


PLUGINS = {
    "tabular": TaskFamilyPlugin("tabular", ("target_column", "feature_columns", "primary_metric"), ("MODEL_COMPARISON",), _tabular),
    "classification": TaskFamilyPlugin("classification", ("target_column", "feature_columns", "class_balance"), ("MODEL_COMPARISON",), _tabular),
    "forecasting": TaskFamilyPlugin("forecasting", ("time_column", "horizon", "split_strategy"), ("FORECAST",), _forecasting),
    "optimization": TaskFamilyPlugin("optimization", ("variables", "constraints", "objective"), ("OPTIMUM",), _optimization),
    "simulation": TaskFamilyPlugin("simulation", ("parameters", "replications", "scenarios"), ("SIMULATION",), _simulation),
    "ranking": TaskFamilyPlugin("ranking", ("protocol", "items", "metrics"), ("RANKING",), _ranking),
}


def validate_task_protocol(family: str, plan: dict[str, Any]) -> dict[str, Any]:
    if family not in PLUGINS:
        return {"valid": False, "errors": ["TASK_FAMILY_UNSUPPORTED"]}
    plugin = PLUGINS[family]
    missing = [field for field in plugin.required_plan_fields if not plan.get(field)]
    errors = list(dict.fromkeys([*missing, *plugin.validate_protocol(plan)]))
    return {"valid": not errors, "family": family, "required_result_types": list(plugin.required_result_types), "errors": errors}

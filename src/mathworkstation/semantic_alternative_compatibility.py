from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, ConfigDict


class AlternativeCompatibilityAssessment(BaseModel):
    """Whether a candidate is a meaningful like-for-like empirical alternative."""

    model_config = ConfigDict(extra="forbid")

    input_compatible: bool
    representation_compatible: bool
    constraint_compatible: bool
    protocol_comparable: bool
    comparable: bool
    rationale: str


_GEOMETRY_TOKENS = (
    "geometry",
    "geometric",
    "coordinate",
    "route layout",
    "pipeline",
    "distance",
    "straight line",
    "坐标",
    "几何",
    "管线",
    "直线段",
    "距离",
    "交接点",
    "边界",
)
_CONTINUOUS_TOKENS = ("continuous", "连续", "坐标", "位置", "distance", "距离")
_DISCRETE_TOKENS = ("integer", "binary", "discrete", "整数", "0-1", "二元", "离散")
_LINEAR_PROGRAMMING_TOKENS = ("linear programming", "lp", "线性规划")
_INTEGER_PROGRAMMING_TOKENS = ("integer programming", "milp", "mixed integer", "整数规划")
_NONLINEAR_GEOMETRY_METHOD_TOKENS = (
    "geometry",
    "geometric",
    "pipeline layout",
    "route layout",
    "nonlinear",
    "continuous optimization",
)
_TIME_SERIES_TOKENS = (
    "time series",
    "temporal",
    "forecast",
    "trend",
    "日期",
    "时间",
    "预测",
    "趋势",
)
_FORECAST_METHOD_TOKENS = (
    "forecast",
    "holt",
    "arima",
    "time trend",
    "ridge",
    "lifecycle",
    "exponential smoothing",
)
_CLASSIFICATION_METHOD_TOKENS = ("classification", "logistic", "svm", "random forest", "xgboost")
_RANKING_METHOD_TOKENS = ("topsis", "ranking", "ahp", "entropy weight", "综合评价")


class SemanticAlternativeCompatibility:
    """Conservative semantic gate for empirical alternative comparisons.

    Solver availability answers "can this plugin run?". This service answers a
    narrower question: "would running it constitute a fair comparison for this
    subproblem?" Unknown/mismatched representations do not create an empirical
    comparison obligation. The gate never selects a model or certifies quality.
    """

    def assess(self, node: Any, candidate_method: str, *, accepted_method: str = "") -> AlternativeCompatibilityAssessment:
        task_family = str(getattr(node, "task_family", "") or "")
        node_text = _normalize(
            " ".join(
                [
                    str(getattr(node, "title", "") or ""),
                    str(getattr(node, "objective", "") or ""),
                    *[str(value) for value in getattr(node, "inputs", [])],
                    *[str(value) for value in getattr(node, "outputs", [])],
                    *[str(value) for value in getattr(node, "constraints", [])],
                ]
            )
        )
        candidate = _normalize(candidate_method)
        accepted = _normalize(accepted_method or str(getattr(getattr(node, "plan", None), "selected_method", "") or ""))

        input_compatible = self._input_compatible(task_family, node_text, candidate)
        representation_compatible = self._representation_compatible(node_text, candidate, accepted)
        constraint_compatible = self._constraint_compatible(node_text, candidate)
        protocol_comparable = self._protocol_comparable(task_family, candidate)
        comparable = all(
            (input_compatible, representation_compatible, constraint_compatible, protocol_comparable)
        )
        failed = [
            label
            for label, ok in (
                ("input", input_compatible),
                ("representation", representation_compatible),
                ("constraint", constraint_compatible),
                ("protocol", protocol_comparable),
            )
            if not ok
        ]
        rationale = (
            "Candidate is semantically compatible with the current subproblem and can form a like-for-like empirical comparison."
            if comparable
            else "Not a like-for-like empirical alternative because " + ", ".join(failed) + " compatibility is not established."
        )
        return AlternativeCompatibilityAssessment(
            input_compatible=input_compatible,
            representation_compatible=representation_compatible,
            constraint_compatible=constraint_compatible,
            protocol_comparable=protocol_comparable,
            comparable=comparable,
            rationale=rationale,
        )

    @staticmethod
    def _input_compatible(task_family: str, node_text: str, candidate: str) -> bool:
        if task_family == "forecasting" and _contains(node_text, _TIME_SERIES_TOKENS):
            return _contains(candidate, _FORECAST_METHOD_TOKENS)
        if task_family == "classification":
            return _contains(candidate, _CLASSIFICATION_METHOD_TOKENS)
        if task_family == "ranking":
            return _contains(candidate, _RANKING_METHOD_TOKENS)
        # For optimization and exploratory families, input shape alone is rarely
        # enough to reject a candidate; representation/constraint checks below
        # carry the stronger semantics.
        return True

    @staticmethod
    def _representation_compatible(node_text: str, candidate: str, accepted: str) -> bool:
        geometry_problem = _contains(node_text, _GEOMETRY_TOKENS)
        continuous_problem = _contains(node_text, _CONTINUOUS_TOKENS)
        if geometry_problem and continuous_problem:
            return _contains(candidate, _NONLINEAR_GEOMETRY_METHOD_TOKENS)
        if _contains(node_text, _DISCRETE_TOKENS):
            return _contains(candidate, _INTEGER_PROGRAMMING_TOKENS + _DISCRETE_TOKENS)

        # When the accepted method and candidate clearly belong to the same
        # familiar family, representation comparability is established.
        for tokens in (_FORECAST_METHOD_TOKENS, _CLASSIFICATION_METHOD_TOKENS, _RANKING_METHOD_TOKENS):
            if _contains(accepted, tokens) and _contains(candidate, tokens):
                return True
        return True

    @staticmethod
    def _constraint_compatible(node_text: str, candidate: str) -> bool:
        geometry_problem = _contains(node_text, _GEOMETRY_TOKENS)
        continuous_problem = _contains(node_text, _CONTINUOUS_TOKENS)
        if geometry_problem and continuous_problem:
            # A generic LP/MILP plugin may exist, but straight-line Euclidean
            # lengths make the native formulation nonlinear unless a dedicated
            # reformulation is explicitly supplied. Alias availability alone is
            # therefore insufficient to require an empirical comparison.
            if _contains(candidate, _LINEAR_PROGRAMMING_TOKENS + _INTEGER_PROGRAMMING_TOKENS):
                return False
            return _contains(candidate, _NONLINEAR_GEOMETRY_METHOD_TOKENS)
        if _contains(node_text, _DISCRETE_TOKENS) and not _contains(candidate, _INTEGER_PROGRAMMING_TOKENS + _DISCRETE_TOKENS):
            return False
        return True

    @staticmethod
    def _protocol_comparable(task_family: str, candidate: str) -> bool:
        if task_family == "forecasting":
            return _contains(candidate, _FORECAST_METHOD_TOKENS)
        if task_family == "classification":
            return _contains(candidate, _CLASSIFICATION_METHOD_TOKENS)
        if task_family == "ranking":
            return _contains(candidate, _RANKING_METHOD_TOKENS)
        if task_family == "optimization":
            return _contains(
                candidate,
                _NONLINEAR_GEOMETRY_METHOD_TOKENS
                + _LINEAR_PROGRAMMING_TOKENS
                + _INTEGER_PROGRAMMING_TOKENS
                + ("optimization", "规划", "优化"),
            )
        return True


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("_", " ").replace("-", " ")).strip().lower()


def _contains(text: str, tokens: tuple[str, ...]) -> bool:
    return any(token in text for token in tokens)

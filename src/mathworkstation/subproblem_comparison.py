from __future__ import annotations

import re
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from .io_utils import atomic_write_json, now_iso, read_json
from .problem_graph import ProblemGraphService, SubproblemExperiment
from .solver_engine import SolverEngineService


ComparisonDecision = Literal["KEEP_ACCEPTED", "REVIEW_SWITCH", "NO_VALID_ALTERNATIVE"]


class ComparisonRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str
    solver: str
    metric: str
    value: float
    validation_gate: str
    solver_artifact_id: str
    validation_artifact_id: str
    experiment_id: str


class ComparisonStressRun(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str
    solver: str
    is_accepted: bool = False
    metric_by_test_size: dict[str, float] = Field(default_factory=dict)
    gate_by_test_size: dict[str, str] = Field(default_factory=dict)
    median_value: float
    worst_value: float
    win_rate_vs_accepted: float = 0.0
    median_relative_improvement: float = 0.0
    robustly_better: bool = False


class SubproblemAlternativeComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str
    subproblem_id: str
    task_family: str
    primary_metric: str
    metric_direction: Literal["MINIMIZE", "MAXIMIZE"]
    tolerance: float
    accepted: ComparisonRun
    alternatives: list[ComparisonRun] = Field(default_factory=list)
    best_method: str
    decision: ComparisonDecision
    rationale: str
    stress_test_sizes: list[float] = Field(default_factory=list)
    stress_runs: list[ComparisonStressRun] = Field(default_factory=list)
    robust_best_method: str | None = None
    generated_at: str


class SubproblemAlternativeComparisonService:
    """Run real head-to-head alternatives without silently changing the accepted answer.

    Alternative executions are appended to the subproblem's experiment history.
    The current selected method/answer remains frozen. A materially better
    alternative produces REVIEW_SWITCH, which a later research repair round may
    accept explicitly; comparable or worse alternatives justify KEEP_ACCEPTED.
    """

    TOLERANCE = 0.01

    def __init__(
        self,
        cases: Any,
        artifacts: Any,
        problem_graphs: ProblemGraphService,
        solvers: SolverEngineService | None = None,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.problem_graphs = problem_graphs
        self.solvers = solvers or SolverEngineService(cases, artifacts)

    def compare(
        self,
        case_id: str,
        subproblem_id: str,
        alternative_plans: list[dict[str, Any]],
        *,
        frame: pd.DataFrame,
        source_artifact_ids: list[str] | None = None,
        stress_test_sizes: list[float] | None = None,
    ) -> dict[str, Any]:
        graph = self.problem_graphs.load(case_id)
        node = graph.node(subproblem_id)
        if node.execution_kind == "DELIVERABLE":
            raise ValueError("ALTERNATIVE_COMPARISON_REQUIRES_RESEARCH_NODE")
        if node.state.status != "COMPLETED" or node.answer is None or not node.experiments:
            raise ValueError("ACCEPTED_SUBPROBLEM_EXECUTION_REQUIRED")
        accepted_experiment = node.experiments[0]
        if not accepted_experiment.evidence_artifact_ids:
            raise ValueError("ACCEPTED_SOLVER_EVIDENCE_REQUIRED")
        primary_metric, direction = _comparison_metric(node.task_family)
        accepted_artifact_id = accepted_experiment.evidence_artifact_ids[-1]
        accepted_payload = _solver_payload(self.cases, self.artifacts, case_id, accepted_artifact_id)
        accepted_result = accepted_payload["result"]
        accepted_value = _metric_value(accepted_result, primary_metric)
        accepted_validation_id = (
            accepted_experiment.validation_artifact_ids[-1]
            if accepted_experiment.validation_artifact_ids
            else ""
        )
        accepted_run = ComparisonRun(
            method=str(node.answer.method),
            solver=str(accepted_payload.get("solver") or accepted_payload.get("build", {}).get("solver") or "accepted"),
            metric=primary_metric,
            value=accepted_value,
            validation_gate=_validation_gate(self.cases, self.artifacts, case_id, accepted_validation_id),
            solver_artifact_id=accepted_artifact_id,
            validation_artifact_id=accepted_validation_id,
            experiment_id=accepted_experiment.experiment_id,
        )

        alternatives: list[ComparisonRun] = []
        upstream = [accepted_artifact_id]
        if accepted_validation_id:
            upstream.append(accepted_validation_id)
        for index, plan in enumerate(alternative_plans, start=1):
            plan = dict(plan)
            solver_method = str(plan.get("solver_method") or f"alternative-{index}")
            run_subproblem_id = f"{subproblem_id}-alt-{_slug(solver_method)}"
            executed = self.solvers.execute(
                case_id,
                run_subproblem_id,
                node.task_family,
                plan,
                frame=frame,
                source_artifact_ids=list(source_artifact_ids or []),
            )
            validation = executed["validation"]
            validation_gate = str(validation["assessment"].gate)
            value = _metric_value(executed["result"], primary_metric)
            method = str(
                executed["result"].get("method")
                or executed["result"].get("model")
                or solver_method
            )
            experiment_id = f"{subproblem_id}:{executed['task_run_id']}"
            run = ComparisonRun(
                method=method,
                solver=str(executed["solver"]),
                metric=primary_metric,
                value=value,
                validation_gate=validation_gate,
                solver_artifact_id=executed["artifact"]["artifact_id"],
                validation_artifact_id=validation["artifact"]["artifact_id"],
                experiment_id=experiment_id,
            )
            alternatives.append(run)
            upstream.extend([run.solver_artifact_id, run.validation_artifact_id])
            if not any(item.experiment_id == experiment_id for item in node.experiments):
                node.experiments.append(
                    SubproblemExperiment(
                        experiment_id=experiment_id,
                        subproblem_id=subproblem_id,
                        method=method,
                        status="COMPLETED",
                        validation_protocol=[str(validation["assessment"].protocol_id)],
                        validation_artifact_ids=[run.validation_artifact_id],
                        evidence_artifact_ids=[run.solver_artifact_id],
                    )
                )
                node.state.experiment_ids.append(experiment_id)
                node.state.evidence_artifact_ids.append(run.solver_artifact_id)

        valid_alternatives = [item for item in alternatives if item.validation_gate != "FAIL"]
        if not valid_alternatives:
            decision: ComparisonDecision = "NO_VALID_ALTERNATIVE"
            best = accepted_run
            rationale = "No alternative passed the registered validation gate; keep the accepted method."
        else:
            contenders = [accepted_run, *valid_alternatives]
            best = min(contenders, key=lambda item: item.value) if direction == "MINIMIZE" else max(contenders, key=lambda item: item.value)
            if best.method == accepted_run.method or not _materially_better(best.value, accepted_run.value, direction, self.TOLERANCE):
                decision = "KEEP_ACCEPTED"
                rationale = (
                    f"No validated alternative improves {primary_metric} beyond the {self.TOLERANCE:.0%} materiality tolerance; "
                    "retain the already accepted method and avoid unnecessary complexity."
                )
            else:
                decision = "REVIEW_SWITCH"
                rationale = (
                    f"{best.method} improves {primary_metric} beyond the {self.TOLERANCE:.0%} materiality tolerance. "
                    "The current answer is not changed automatically; route this subproblem to an explicit research review."
                )

        stress_runs: list[ComparisonStressRun] = []
        robust_best_method: str | None = None
        normalized_stress_sizes = _normalize_stress_sizes(stress_test_sizes)
        if normalized_stress_sizes and node.task_family == "forecasting" and alternatives:
            stress_runs, stress_upstream = self._forecast_stress_test(
                case_id,
                subproblem_id,
                accepted_run,
                accepted_payload,
                alternatives,
                alternative_plans,
                frame,
                normalized_stress_sizes,
                source_artifact_ids,
                primary_metric,
                direction,
            )
            upstream.extend(stress_upstream)
            robust_alternatives = [item for item in stress_runs if not item.is_accepted and item.robustly_better]
            if robust_alternatives:
                robust_best = (
                    min(robust_alternatives, key=lambda item: item.median_value)
                    if direction == "MINIMIZE"
                    else max(robust_alternatives, key=lambda item: item.median_value)
                )
                robust_best_method = robust_best.method
                best = next(
                    (item for item in alternatives if item.method == robust_best.method),
                    best,
                )
                decision = "REVIEW_SWITCH"
                rationale = (
                    f"{robust_best.method} is materially better across {robust_best.win_rate_vs_accepted:.0%} "
                    f"of the registered temporal stress splits; median relative improvement is "
                    f"{robust_best.median_relative_improvement:.1%}. Route SP1 to explicit research review."
                )
            else:
                decision = "KEEP_ACCEPTED"
                best = accepted_run
                robust_best_method = accepted_run.method
                rationale = (
                    "No alternative is materially better on at least 75% of the registered temporal stress splits; "
                    "retain the accepted method even if one alternative wins a single holdout."
                )

        comparison = SubproblemAlternativeComparison(
            case_id=case_id,
            subproblem_id=subproblem_id,
            task_family=node.task_family,
            primary_metric=primary_metric,
            metric_direction=direction,
            tolerance=self.TOLERANCE,
            accepted=accepted_run,
            alternatives=alternatives,
            best_method=best.method,
            decision=decision,
            rationale=rationale,
            stress_test_sizes=normalized_stress_sizes,
            stress_runs=stress_runs,
            robust_best_method=robust_best_method,
            generated_at=now_iso(),
        )
        root = self.cases.case_root(case_id)
        path = root / "analysis" / "subproblem_comparisons" / f"{subproblem_id}.json"
        atomic_write_json(path, comparison.model_dump(mode="json"))
        comparison_artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "subproblem_alternative_comparison",
            "subproblem_alternative_comparison",
            upstream=list(dict.fromkeys(upstream)),
            paper_eligible=False,
        )
        _, graph_artifact = self.problem_graphs.save(
            case_id,
            graph,
            [comparison_artifact["artifact_id"], *list(dict.fromkeys(upstream))],
            created_by="subproblem_alternative_comparison",
        )
        return {
            "comparison": comparison,
            "artifact": comparison_artifact,
            "graph_artifact": graph_artifact,
        }

    def _forecast_stress_test(
        self,
        case_id: str,
        subproblem_id: str,
        accepted_run: ComparisonRun,
        accepted_payload: dict[str, Any],
        alternatives: list[ComparisonRun],
        alternative_plans: list[dict[str, Any]],
        frame: pd.DataFrame,
        test_sizes: list[float],
        source_artifact_ids: list[str] | None,
        primary_metric: str,
        direction: Literal["MINIMIZE", "MAXIMIZE"],
    ) -> tuple[list[ComparisonStressRun], list[str]]:
        upstream: list[str] = []
        accepted_plan = _replay_plan_for_solver(
            dict(accepted_payload.get("plan") or {}),
            accepted_run.solver,
        )
        specs: list[tuple[ComparisonRun, dict[str, Any], bool]] = [
            (accepted_run, accepted_plan, True)
        ]
        specs.extend(
            (run, dict(plan), False)
            for run, plan in zip(alternatives, alternative_plans, strict=True)
        )

        raw: list[dict[str, Any]] = []
        for run, base_plan, is_accepted in specs:
            metric_by_size: dict[str, float] = {}
            gate_by_size: dict[str, str] = {}
            for test_size in test_sizes:
                plan = {**base_plan, "test_size": float(test_size)}
                run_id = f"{subproblem_id}-stress-{_slug(run.solver)}-{int(round(test_size * 1000))}"
                executed = self.solvers.execute(
                    case_id,
                    run_id,
                    "forecasting",
                    plan,
                    frame=frame,
                    source_artifact_ids=list(source_artifact_ids or []),
                )
                gate = str(executed["validation"]["assessment"].gate)
                value = _metric_value(executed["result"], primary_metric)
                key = f"{test_size:.3f}"
                metric_by_size[key] = value
                gate_by_size[key] = gate
                upstream.extend(
                    [
                        executed["artifact"]["artifact_id"],
                        executed["validation"]["artifact"]["artifact_id"],
                    ]
                )
            values = list(metric_by_size.values())
            raw.append(
                {
                    "run": run,
                    "is_accepted": is_accepted,
                    "metric_by_size": metric_by_size,
                    "gate_by_size": gate_by_size,
                    "median_value": float(pd.Series(values).median()),
                    "worst_value": (
                        float(max(values)) if direction == "MINIMIZE" else float(min(values))
                    ),
                }
            )

        accepted_stress = next(item for item in raw if item["is_accepted"])
        accepted_by_size = accepted_stress["metric_by_size"]
        result: list[ComparisonStressRun] = []
        for item in raw:
            run = item["run"]
            if item["is_accepted"]:
                win_rate = 0.0
                median_improvement = 0.0
                robust = False
            else:
                relative_improvements: list[float] = []
                wins = 0
                for key, candidate in item["metric_by_size"].items():
                    accepted = float(accepted_by_size[key])
                    denominator = abs(accepted) or 1.0
                    relative = (
                        (accepted - float(candidate)) / denominator
                        if direction == "MINIMIZE"
                        else (float(candidate) - accepted) / denominator
                    )
                    relative_improvements.append(relative)
                    if relative > self.TOLERANCE:
                        wins += 1
                win_rate = wins / len(test_sizes)
                median_improvement = float(pd.Series(relative_improvements).median())
                robust = (
                    win_rate >= 0.75
                    and median_improvement > self.TOLERANCE
                    and all(gate != "FAIL" for gate in item["gate_by_size"].values())
                )
            result.append(
                ComparisonStressRun(
                    method=run.method,
                    solver=run.solver,
                    is_accepted=bool(item["is_accepted"]),
                    metric_by_test_size=item["metric_by_size"],
                    gate_by_test_size=item["gate_by_size"],
                    median_value=float(item["median_value"]),
                    worst_value=float(item["worst_value"]),
                    win_rate_vs_accepted=float(win_rate),
                    median_relative_improvement=float(median_improvement),
                    robustly_better=bool(robust),
                )
            )
        return result, upstream


def _normalize_stress_sizes(values: list[float] | None) -> list[float]:
    if not values:
        return []
    normalized = sorted({round(float(value), 6) for value in values})
    if len(normalized) < 3:
        raise ValueError("FORECAST_STRESS_TEST_REQUIRES_AT_LEAST_3_SPLITS")
    if any(value <= 0.05 or value >= 0.5 for value in normalized):
        raise ValueError("FORECAST_STRESS_TEST_SIZE_OUT_OF_RANGE")
    return normalized


def _replay_plan_for_solver(plan: dict[str, Any], solver: str) -> dict[str, Any]:
    mapping = {
        "gold.forecasting": "ridge_time_trend",
        "gold.holt_exponential_smoothing": "holt_exponential_smoothing",
        "gold.popularity_lifecycle": "popularity_lifecycle",
    }
    if solver in mapping:
        plan["solver_method"] = mapping[solver]
    return plan


def _comparison_metric(family: str) -> tuple[str, Literal["MINIMIZE", "MAXIMIZE"]]:
    mapping: dict[str, tuple[str, Literal["MINIMIZE", "MAXIMIZE"]]] = {
        "forecasting": ("rmse", "MINIMIZE"),
        "distribution_forecasting": ("rmse", "MINIMIZE"),
        "classification": ("balanced_accuracy", "MAXIMIZE"),
    }
    if family not in mapping:
        raise ValueError(f"ALTERNATIVE_COMPARISON_METRIC_UNREGISTERED:{family}")
    return mapping[family]


def _metric_value(result: dict[str, Any], metric: str) -> float:
    value = (result.get("metrics") or {}).get(metric)
    if not isinstance(value, (int, float)):
        raise ValueError(f"COMPARISON_METRIC_MISSING:{metric}")
    return float(value)


def _solver_payload(cases: Any, artifacts: Any, case_id: str, artifact_id: str) -> dict[str, Any]:
    artifact = artifacts.get(case_id, artifact_id)
    payload = read_json(cases.case_root(case_id) / artifact["path"])
    if "result" not in payload:
        raise ValueError("SOLVER_EVIDENCE_RESULT_MISSING")
    return payload


def _validation_gate(cases: Any, artifacts: Any, case_id: str, artifact_id: str) -> str:
    if not artifact_id:
        return "UNKNOWN"
    artifact = artifacts.get(case_id, artifact_id)
    payload = read_json(cases.case_root(case_id) / artifact["path"])
    assessment = payload.get("assessment", payload)
    return str(assessment.get("gate") or "UNKNOWN")


def _materially_better(
    candidate: float,
    accepted: float,
    direction: Literal["MINIMIZE", "MAXIMIZE"],
    tolerance: float,
) -> bool:
    denominator = abs(accepted) or 1.0
    relative = (accepted - candidate) / denominator if direction == "MINIMIZE" else (candidate - accepted) / denominator
    return relative > tolerance


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-") or "alternative"

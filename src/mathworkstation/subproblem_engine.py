from __future__ import annotations

from typing import Any

import pandas as pd

from .io_utils import atomic_write_json
from .problem_graph import (
    ProblemGraphService,
    SubproblemAnswer,
    SubproblemExperiment,
)
from .solver_engine import SolverEngineService


class SubproblemEngineService:
    """Execute one ProblemGraph node without collapsing the whole case to one model.

    The engine is intentionally thin. Solver choice remains in each node plan;
    this service enforces family-specific dispatch, dependency gates, immutable
    evidence registration and graph-state updates. Unsupported families fail
    closed instead of silently falling back to regression.
    """

    def __init__(self, cases: Any, artifacts: Any, problem_graphs: ProblemGraphService) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.problem_graphs = problem_graphs
        self.solvers = SolverEngineService(cases, artifacts)

    def execute_node(
        self,
        case_id: str,
        subproblem_id: str,
        plan: dict[str, Any],
        *,
        frame: pd.DataFrame | None = None,
        source_artifact_ids: list[str] | None = None,
        answer_text: str | None = None,
        limitation: str | None = None,
    ) -> dict[str, Any]:
        graph = self.problem_graphs.load(case_id)
        node = graph.node(subproblem_id)
        if node.execution_kind == "DELIVERABLE":
            raise ValueError("DELIVERABLE_REQUIRES_SYNTHESIS_COMPLETION")
        incomplete = [
            dependency
            for dependency in node.dependencies
            if graph.node(dependency).state.status != "COMPLETED"
        ]
        if incomplete:
            raise ValueError("SUBPROBLEM_DEPENDENCIES_INCOMPLETE:" + ",".join(incomplete))
        family = node.task_family
        execution = self.solvers.execute(
            case_id,
            subproblem_id,
            family,
            plan,
            frame=frame,
            source_artifact_ids=source_artifact_ids,
        )

        result = execution["result"]
        evidence_artifact_id = execution["artifact"]["artifact_id"]
        method = str(
            result.get("method")
            or result.get("model")
            or result.get("solver_method")
            or result.get("protocol", {}).get("method")
            or node.plan.candidate_methods[0]
        )
        node.plan.selected_method = method
        experiment_id = f"{subproblem_id}:{execution['task_run_id']}"
        validation_artifact_ids = []
        validation = execution.get("validation")
        if isinstance(validation, dict) and isinstance(validation.get("artifact"), dict):
            validation_artifact_ids.append(str(validation["artifact"]["artifact_id"]))
        actual_validation_protocol = list(node.plan.validation_protocol)
        if isinstance(validation, dict) and validation.get("assessment") is not None:
            assessment = validation["assessment"]
            protocol_id = getattr(assessment, "protocol_id", None)
            if protocol_id:
                actual_validation_protocol = [str(protocol_id)]
        node.experiments = [
            SubproblemExperiment(
                experiment_id=experiment_id,
                subproblem_id=subproblem_id,
                method=method,
                status="COMPLETED",
                validation_protocol=actual_validation_protocol,
                validation_artifact_ids=validation_artifact_ids,
                evidence_artifact_ids=[evidence_artifact_id],
            )
        ]
        node.state.status = "COMPLETED"
        node.state.experiment_ids = [experiment_id]
        node.state.evidence_artifact_ids = [evidence_artifact_id]
        node.state.answer_id = f"answer-{subproblem_id}"
        node.answer = SubproblemAnswer(
            answer_id=node.state.answer_id,
            subproblem_id=subproblem_id,
            method=method,
            answer=answer_text or _default_answer(subproblem_id, family, result),
            limitation=limitation or "结论仅适用于本节点登记的数据、特征、协议与证据范围。",
            evidence_artifact_ids=[evidence_artifact_id],
        )
        invalidated_dependents = _invalidate_downstream_answers(graph, subproblem_id)
        _, graph_artifact = self.problem_graphs.save(
            case_id,
            graph,
            [evidence_artifact_id],
            created_by="subproblem_engine",
        )
        return {
            "subproblem_id": subproblem_id,
            "family": family,
            "execution": execution,
            "graph_artifact": graph_artifact,
            "research_gate": graph_artifact["research_gate"],
            "invalidated_dependents": invalidated_dependents,
        }

    def complete_synthesis(
        self,
        case_id: str,
        subproblem_id: str,
        answer_text: str,
        *,
        limitation: str = "综合交付内容仅能复述已接受的上游研究证据，不新增未经验证的定量结论。",
    ) -> dict[str, Any]:
        graph = self.problem_graphs.load(case_id)
        node = graph.node(subproblem_id)
        if node.execution_kind != "DELIVERABLE":
            raise ValueError("SYNTHESIS_COMPLETION_REQUIRES_DELIVERABLE_NODE")
        incomplete = [
            dependency
            for dependency in node.dependencies
            if graph.node(dependency).state.status != "COMPLETED"
        ]
        if incomplete:
            raise ValueError("SYNTHESIS_DEPENDENCIES_INCOMPLETE:" + ",".join(incomplete))
        dependency_evidence = [
            artifact_id
            for dependency in node.dependencies
            for artifact_id in graph.node(dependency).state.evidence_artifact_ids
        ]
        root = self.cases.case_root(case_id)
        path = root / "results" / "subproblems" / subproblem_id / "synthesis.json"
        method = "evidence synthesis from accepted subproblem answers"
        atomic_write_json(
            path,
            {
                "schema_version": 1,
                "subproblem_id": subproblem_id,
                "method": method,
                "dependencies": list(node.dependencies),
                "answer": answer_text,
                "source_artifact_ids": dependency_evidence,
            },
        )
        artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "subproblem_synthesis_result",
            "subproblem_engine",
            upstream=dependency_evidence,
            paper_eligible=False,
        )
        node.plan.selected_method = method
        node.state.status = "COMPLETED"
        node.state.evidence_artifact_ids = [artifact["artifact_id"]]
        node.state.answer_id = f"answer-{subproblem_id}"
        node.answer = SubproblemAnswer(
            answer_id=node.state.answer_id,
            subproblem_id=subproblem_id,
            method=method,
            answer=answer_text,
            limitation=limitation,
            evidence_artifact_ids=[artifact["artifact_id"], *dependency_evidence],
        )
        _, graph_artifact = self.problem_graphs.save(
            case_id,
            graph,
            [artifact["artifact_id"], *dependency_evidence],
            created_by="subproblem_engine",
        )
        return {
            "subproblem_id": subproblem_id,
            "artifact": artifact,
            "graph_artifact": graph_artifact,
            "research_gate": graph_artifact["research_gate"],
        }


def _invalidate_downstream_answers(graph: Any, source_subproblem_id: str) -> list[str]:
    """Invalidate accepted descendants when an upstream research node changes."""

    frontier = {source_subproblem_id}
    invalidated: list[str] = []
    while frontier:
        next_frontier: set[str] = set()
        for candidate in graph.nodes:
            if candidate.subproblem_id == source_subproblem_id or candidate.subproblem_id in invalidated:
                continue
            if not any(dependency in frontier for dependency in candidate.dependencies):
                continue
            if candidate.state.status == "COMPLETED" or candidate.answer is not None:
                candidate.state.status = "PLANNED"
                candidate.state.answer_id = None
                candidate.state.evidence_artifact_ids = []
                candidate.state.experiment_ids = []
                candidate.state.blockers = list(
                    dict.fromkeys([*candidate.state.blockers, f"UPSTREAM_RESEARCH_CHANGED:{source_subproblem_id}"])
                )
                candidate.answer = None
                invalidated.append(candidate.subproblem_id)
                next_frontier.add(candidate.subproblem_id)
        frontier = next_frontier
    return invalidated


def _default_answer(subproblem_id: str, family: str, result: dict[str, Any]) -> str:
    metrics = result.get("metrics")
    metric_summary = ""
    if isinstance(metrics, dict) and metrics:
        metric_summary = ", ".join(
            f"{key}={float(value):.6g}"
            for key, value in metrics.items()
            if isinstance(value, (int, float))
        )

    if family == "forecasting" and isinstance(result.get("forecast"), dict):
        forecast = result["forecast"]
        lower, upper = forecast.get("interval", [None, None])
        future_time = str((result.get("protocol") or {}).get("future_time") or "未来目标时点")
        answer = f"{subproblem_id} 对 {future_time} 的点预测为 {float(forecast['point']):.6g}"
        if lower is not None and upper is not None:
            answer += f"，95%预测区间为 [{float(lower):.6g}, {float(upper):.6g}]"
        if metric_summary:
            answer += f"；时间留出验证指标为 {metric_summary}"
        return answer + "。"

    if family == "forecasting" and isinstance(result.get("trend_grid"), list) and result["trend_grid"]:
        trends = result["trend_grid"]
        compact = "; ".join(
            f"{item['entity']} {item['target']} 年趋势={float(item['annual_slope']):.4g} ({item['direction']})"
            for item in trends[:12]
        )
        suffix = "；其余趋势见结果表" if len(trends) > 12 else ""
        metric_text = f"；面板时间留出验证指标为 {metric_summary}" if metric_summary else ""
        return f"{subproblem_id} 的历史画像演化为：{compact}{suffix}{metric_text}。"

    if family == "forecasting" and isinstance(result.get("forecast_grid"), list) and result["forecast_grid"]:
        grid = result["forecast_grid"]
        compact = "; ".join(
            f"{item['entity']} {str(item['future_time'])[:4]} {item['target']}={float(item['point']):.4g}"
            for item in grid[:12]
        )
        suffix = "；其余预测见结果表" if len(grid) > 12 else ""
        metric_text = f"；面板时间留出验证指标为 {metric_summary}" if metric_summary else ""
        return f"{subproblem_id} 已完成多实体未来画像预测：{compact}{suffix}{metric_text}。"

    if family == "classification" and result.get("future_prediction") is not None:
        predicted = str(result["future_prediction"])
        probabilities = result.get("future_probabilities") or {}
        probability_text = ""
        if isinstance(probabilities, dict) and probabilities:
            probability_text = "，类别概率为 " + ", ".join(
                f"{label}={float(value):.3f}" for label, value in probabilities.items()
            )
        metric_text = f"；验证指标为 {metric_summary}" if metric_summary else ""
        return f"{subproblem_id} 对目标样本的分类结果为 {predicted}{probability_text}{metric_text}。"

    if family == "distribution_forecasting" and isinstance(result.get("future_distribution"), dict):
        distribution = result["future_distribution"]
        component_text = ", ".join(
            f"{name}={float(value):.3f}%" for name, value in distribution.items()
        )
        metric_text = f"；时间留出验证指标为 {metric_summary}" if metric_summary else ""
        return f"{subproblem_id} 的目标分布预测为 {component_text}{metric_text}。"

    if family == "explanatory_inference" and result.get("effects"):
        lead = result["effects"][0]
        interval = lead.get("bootstrap_ci_95") or [None, None]
        interval_text = ""
        if interval[0] is not None and interval[1] is not None:
            interval_text = f"，95% bootstrap 区间为 [{float(interval[0]):.4g}, {float(interval[1]):.4g}]"
        metric_text = f"；验证指标为 {metric_summary}" if metric_summary else ""
        return (
            f"{subproblem_id} 中最强标准化关联特征为 {lead['feature']}，系数为 "
            f"{float(lead['standardized_coefficient']):.4g}（{lead['direction']}）{interval_text}{metric_text}。"
        )

    if family == "exploratory_analysis" and isinstance(result.get("profiles"), list) and result["profiles"]:
        profiles = result["profiles"]
        compact = "; ".join(
            f"{item['entity']}: "
            + ", ".join(f"{key}={float(value):.4g}" for key, value in item.get("values", {}).items())
            for item in profiles[:6]
        )
        return f"{subproblem_id} 已建立共同口径的多实体画像：{compact}。"

    if family == "exploratory_analysis":
        return f"{subproblem_id} 已完成独立探索分析：{result.get('headline', '已登记探索发现')}。"

    if family == "optimization":
        solution = result.get("solution") or {}
        if isinstance(solution, dict) and solution:
            compact = "; ".join(
                f"{name}={float(value):.4g}" for name, value in list(solution.items())[:12]
            )
            suffix = "；其余变量见结果表" if len(solution) > 12 else ""
            return (
                f"{subproblem_id} 已完成约束优化，目标值为 {float(result['objective_value']):.6g}；"
                f"解为 {compact}{suffix}。"
            )
        return f"{subproblem_id} 已完成优化求解，目标值为 {float(result['objective_value']):.6g}。"

    if family == "simulation":
        return f"{subproblem_id} 已完成场景仿真并登记不确定性结果。"

    if family == "ranking" and result.get("winner") is not None:
        ranking = result.get("ranking") or []
        order = " > ".join(str(item.get("entity")) for item in ranking[:6])
        stability = (result.get("metrics") or {}).get("winner_retention_rate")
        stability_text = (
            f"，留一指标赢家保持率为 {float(stability):.3f}"
            if isinstance(stability, (int, float))
            else ""
        )
        return f"{subproblem_id} 的多指标评价首位为 {result['winner']}，排序为 {order}{stability_text}。"

    if metric_summary:
        return f"{subproblem_id} 已按 {family} 独立协议完成，验证指标为 {metric_summary}。"
    return f"{subproblem_id} 已按 {family} 独立执行并登记结果。"

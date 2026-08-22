from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .io_utils import atomic_write_json
from .problem_graph import ProblemGraph, SubproblemAnswer, SubproblemExperiment, assess_problem_graph
from .subproblem_executors import (
    execute_classification_with_future,
    execute_distribution_forecasting,
    execute_explanatory_inference,
    execute_exploratory_analysis,
)
from .word_features import augment_word_features, future_word_features, wordle_task_feature_sets
from .solver_engine import HoltForecastSolverPlugin


DISTRIBUTION_COLUMNS = [
    "1 try",
    "2 tries",
    "3 tries",
    "4 tries",
    "5 tries",
    "6 tries",
    "7 or more tries (X)",
]


def prepare_wordle_2023_research(frame: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    """Materialize the real Wordle fields and node-specific plans for Section 1."""
    data = frame.copy()
    data["Date"] = pd.to_datetime(data["Date"], errors="raise")
    data = data.sort_values("Date").reset_index(drop=True)
    data, letter_freq, _word_columns = augment_word_features(data, "Word")
    feature_sets = wordle_task_feature_sets()
    eerie = future_word_features("EERIE", letter_freq)
    data["hard_mode_percentage"] = (
        pd.to_numeric(data["Number in hard mode"], errors="raise")
        / pd.to_numeric(data["Number of  reported results"], errors="raise")
        * 100.0
    )
    tries = data[DISTRIBUTION_COLUMNS].apply(pd.to_numeric, errors="raise").to_numpy(dtype=float)
    weights = np.arange(1.0, 8.0)
    difficulty_score = (tries * weights).sum(axis=1) / np.maximum(tries.sum(axis=1), 1e-12)
    q1, q2 = np.quantile(difficulty_score, [1 / 3, 2 / 3])
    data["difficulty_class"] = np.where(
        difficulty_score <= q1,
        "easy",
        np.where(difficulty_score <= q2, "medium", "hard"),
    )
    plans: dict[str, dict[str, Any]] = {
        "SP1": {
            "solver_method": "holt_exponential_smoothing",
            "time_column": "Date",
            "target_column": "Number of  reported results",
            "feature_columns": feature_sets["SP1"],
            "future_time": "2023-03-01",
            "future_features": {key: value for key, value in eerie.items() if key in feature_sets["SP1"]},
            "test_size": 0.2,
            "bootstrap_runs": 400,
            "random_seed": 42,
            "log_target": True,
        },
        "SP2": {
            "target_column": "hard_mode_percentage",
            "feature_columns": feature_sets["SP2"],
            "split_strategy": "temporal",
            "time_column": "Date",
            "test_size": 0.2,
            "bootstrap_runs": 300,
            "random_seed": 42,
        },
        "SP3": {
            "time_column": "Date",
            "output_columns": DISTRIBUTION_COLUMNS,
            "feature_columns": feature_sets["SP3"],
            "future_features": {key: value for key, value in eerie.items() if key in feature_sets["SP3"]},
            "future_step": 60,
            "test_size": 0.2,
            "bootstrap_runs": 400,
            "random_seed": 42,
            "distribution_total": 100.0,
        },
        "SP4": {
            "target_column": "difficulty_class",
            "feature_columns": feature_sets["SP4"],
            "class_balance": "observed",
            "future_features": {key: value for key, value in eerie.items() if key in feature_sets["SP4"]},
            "test_size": 0.2,
            "random_seed": 42,
        },
        "SP5": {
            "numeric_columns": [
                "Number of  reported results",
                "hard_mode_percentage",
                *DISTRIBUTION_COLUMNS,
                *feature_sets["SP5"],
            ]
        },
    }
    return data, plans


class Wordle2023GateService:
    """Persist the real historical Gate as ordinary Case artifacts.

    The benchmark remains Wordle-specific, but the persistence semantics are the
    same ones Section 1 needs in production: each subproblem owns its own result
    artifact and the graph points to those artifacts instead of a global model
    comparison id.
    """

    def __init__(self, cases: Any, artifacts: Any) -> None:
        self.cases = cases
        self.artifacts = artifacts

    def run(
        self,
        case_id: str,
        frame: pd.DataFrame,
        graph: ProblemGraph,
        source_artifact_ids: list[str] | None = None,
    ) -> tuple[ProblemGraph, dict[str, Any]]:
        completed, report = run_wordle_2023_gate(frame, graph)
        root = self.cases.case_root(case_id)
        evidence_by_subproblem: dict[str, str] = {}
        sources = list(source_artifact_ids or [])
        for subproblem_id, result in report["results"].items():
            path = root / "results" / "subproblems" / subproblem_id / "wordle-2023-gate.json"
            atomic_write_json(
                path,
                {
                    "schema_version": 1,
                    "subproblem_id": subproblem_id,
                    "benchmark": "2023-MCM-C-Wordle",
                    "result": result,
                    "source_artifact_ids": sources,
                },
            )
            artifact = self.artifacts.register_existing(
                case_id,
                path.relative_to(root).as_posix(),
                "subproblem_execution_result",
                "wordle_2023_gate",
                upstream=sources,
                paper_eligible=False,
            )
            evidence_by_subproblem[subproblem_id] = artifact["artifact_id"]

        for subproblem_id in ("SP1", "SP2", "SP3", "SP4", "SP5"):
            node = completed.node(subproblem_id)
            artifact_id = evidence_by_subproblem[subproblem_id]
            node.state.evidence_artifact_ids = [artifact_id]
            node.experiments[0].evidence_artifact_ids = [artifact_id]
            if node.answer is not None:
                node.answer.evidence_artifact_ids = [artifact_id]
        sp6 = completed.node("SP6")
        sp6.state.evidence_artifact_ids = [
            evidence_by_subproblem[subproblem_id] for subproblem_id in sp6.dependencies
        ]
        if sp6.answer is not None:
            sp6.answer.evidence_artifact_ids = list(sp6.state.evidence_artifact_ids)

        graph_path = root / "analysis" / "problem_graph.wordle-2023-gate.json"
        atomic_write_json(graph_path, completed.model_dump(mode="json"))
        graph_artifact = self.artifacts.register_existing(
            case_id,
            graph_path.relative_to(root).as_posix(),
            "problem_graph_gate",
            "wordle_2023_gate",
            upstream=[*sources, *evidence_by_subproblem.values()],
            paper_eligible=False,
        )
        assessment = assess_problem_graph(completed)
        report = {
            **report,
            "assessment": assessment.model_dump(mode="json"),
            "evidence_by_subproblem": evidence_by_subproblem,
            "graph_artifact_id": graph_artifact["artifact_id"],
        }
        return completed, report


def run_wordle_2023_gate(frame: pd.DataFrame, graph: ProblemGraph) -> tuple[ProblemGraph, dict[str, Any]]:
    """Run the 2023 MCM Wordle Section-1 acceptance case on real contest data.

    This is deliberately problem-specific benchmark materialization, not the
    generic production router. It proves that one ProblemGraph can carry six
    genuinely different research semantics without falling back to one global
    regression result.
    """
    data, plans = prepare_wordle_2023_research(frame)

    results: dict[str, dict[str, Any]] = {}
    results["SP1"] = HoltForecastSolverPlugin().solve("forecasting", plans["SP1"], data)
    results["SP2"] = execute_explanatory_inference(data, plans["SP2"])
    results["SP3"] = execute_distribution_forecasting(data, plans["SP3"])
    results["SP4"] = execute_classification_with_future(data, plans["SP4"])
    results["SP5"] = execute_exploratory_analysis(data, plans["SP5"])

    updated = graph.model_copy(deep=True)
    for subproblem_id in ("SP1", "SP2", "SP3", "SP4", "SP5"):
        node = updated.node(subproblem_id)
        result = results[subproblem_id]
        evidence_id = f"wordle-2023-gate:{subproblem_id}"
        node.plan.selected_method = str(result.get("method") or result.get("model") or result.get("protocol", {}).get("method") or node.plan.candidate_methods[0])
        node.experiments = [
            SubproblemExperiment(
                experiment_id=f"wordle-2023-{subproblem_id}",
                subproblem_id=subproblem_id,
                method=node.plan.selected_method,
                status="COMPLETED",
                validation_protocol=list(node.plan.validation_protocol),
                evidence_artifact_ids=[evidence_id],
            )
        ]
        node.state.status = "COMPLETED"
        node.state.experiment_ids = [node.experiments[0].experiment_id]
        node.state.evidence_artifact_ids = [evidence_id]
        node.state.answer_id = f"answer-{subproblem_id}"
        node.answer = SubproblemAnswer(
            answer_id=f"answer-{subproblem_id}",
            subproblem_id=subproblem_id,
            method=node.plan.selected_method,
            answer=_answer_text(subproblem_id, result),
            limitation=_limitation(subproblem_id),
            evidence_artifact_ids=[evidence_id],
        )

    sp6 = updated.node("SP6")
    sp6.state.status = "COMPLETED"
    sp6.state.evidence_artifact_ids = [updated.node(item).state.evidence_artifact_ids[0] for item in sp6.dependencies]
    sp6.state.answer_id = "answer-SP6"
    sp6.plan.selected_method = "evidence synthesis from accepted subproblem answers"
    sp6.answer = SubproblemAnswer(
        answer_id="answer-SP6",
        subproblem_id="SP6",
        method=sp6.plan.selected_method,
        answer="致编辑信仅综合 SP1-SP5 的已验证结论、预测与限制，不训练额外模型。",
        limitation="信函质量仍需在 Paper Engine 阶段按篇幅、受众和引用规则复核。",
        evidence_artifact_ids=list(sp6.state.evidence_artifact_ids),
    )
    assessment = assess_problem_graph(updated)
    return updated, {"results": results, "assessment": assessment.model_dump(mode="json")}


def _answer_text(subproblem_id: str, result: dict[str, Any]) -> str:
    if subproblem_id == "SP1":
        forecast = result["forecast"]
        return f"2023-03-01 报告人数点预测为 {forecast['point']:.0f}，95% 预测区间约为 [{forecast['interval'][0]:.0f}, {forecast['interval'][1]:.0f}]。"
    if subproblem_id == "SP2":
        stable = [item for item in result["effects"] if item["interval_excludes_zero"]]
        lead = stable[0] if stable else result["effects"][0]
        return f"单词属性与 Hard Mode 比例存在可检验的关联；当前最强标准化效应来自 {lead['feature']}，方向为 {lead['direction']}。"
    if subproblem_id == "SP3":
        distribution = result["future_distribution"]
        compact = ", ".join(f"{key}={value:.1f}%" for key, value in distribution.items())
        return f"EERIE 在 2023-03-01 的预测猜测分布为 {compact}，各分量总和受 simplex 约束为 100%。"
    if subproblem_id == "SP4":
        return f"基于显式期望猜测次数构造的三档难度标签，EERIE 被分类为 {result['future_prediction']}。"
    return str(result["headline"])


def _limitation(subproblem_id: str) -> str:
    values = {
        "SP1": "区间来自历史时间留出残差 bootstrap，不能覆盖未来参与机制发生结构突变的风险。",
        "SP2": "效应是关联而非因果，仅使用题目允许的数据与由单词本身构造的特征。",
        "SP3": "多输出 Ridge 是 Section-1 可验证基线，后续 Modeling Brain 仍应比较 compositional/概率模型。",
        "SP4": "难度标签由观测猜测分布构造，分类准确率与类别定义均需在后续轮次继续检验。",
        "SP5": "探索性发现用于生成后续假设，不应未经独立验证直接升级为强结论。",
    }
    return values[subproblem_id]

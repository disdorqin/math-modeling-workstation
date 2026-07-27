from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from mathworkstation.task_executors import (
    TaskExecutionService,
    execute_classification,
    execute_forecasting,
    execute_optimization,
    execute_ranking,
    execute_simulation,
)
from mathworkstation.claims import ClaimRegistry
from mathworkstation.datasets import DatasetRegistry
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.paper_contracts import PaperContractService
from mathworkstation.task_paper_bridge import TaskPaperEvidenceBridge
from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.auto_pipeline import AutoPipelineService


def test_classification_executor_returns_required_metrics_and_confusion_matrix() -> None:
    frame = pd.DataFrame({"x": np.arange(30), "label": ["a" if value < 15 else "b" for value in range(30)]})
    result = execute_classification(frame, {"target_column": "label", "feature_columns": ["x"], "class_balance": "balanced", "random_seed": 7})
    assert result["family"] == "classification"
    assert {"accuracy", "macro_f1", "balanced_accuracy"} <= result["metrics"].keys()
    assert len(result["confusion_matrix"]) == 2


def test_forecasting_executor_enforces_temporal_protocol_and_scores() -> None:
    frame = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=30), "y": np.arange(30, dtype=float)})
    result = execute_forecasting(frame, {"time_column": "date", "target_column": "y", "horizon": 3, "split_strategy": "temporal"})
    assert result["leakage_check"] == "PASS"
    assert result["metrics"]["rmse"] == pytest.approx(0.0)
    with pytest.raises(ValueError, match="TEMPORAL_SPLIT_REQUIRED"):
        execute_forecasting(frame, {"time_column": "date", "target_column": "y", "horizon": 3, "split_strategy": "random"})


def test_optimization_executor_returns_feasible_optimum() -> None:
    result = execute_optimization({
        "variables": [{"name": "x", "lower": 0, "upper": 4, "step": 1}, {"name": "y", "lower": 0, "upper": 4, "step": 1}],
        "objective": {"sense": "max", "coefficients": {"x": 2, "y": 1}},
        "constraints": [{"coefficients": {"x": 1, "y": 1}, "operator": "<=", "rhs": 4}],
    })
    assert result["constraint_status"] == "PASS"
    assert result["solution"] == {"x": 4.0, "y": 0.0}
    with pytest.raises(ValueError, match="NO_FEASIBLE_SOLUTION"):
        execute_optimization({"variables": [{"name": "x", "lower": 0, "upper": 1}], "objective": {"sense": "max", "coefficients": {"x": 1}}, "constraints": [{"coefficients": {"x": 1}, "operator": ">=", "rhs": 2}]})


def test_simulation_executor_is_seed_reproducible() -> None:
    plan = {"parameters": [{"mean": 10, "std": 1}], "replications": 100, "scenarios": [{"name": "base", "multiplier": 1.0}], "seed": 11}
    assert execute_simulation(plan) == execute_simulation(plan)
    assert execute_simulation(plan)["scenarios"]["base"]["p95"] > execute_simulation(plan)["scenarios"]["base"]["p05"]


def test_ranking_executor_reports_grouped_metrics() -> None:
    frame = pd.DataFrame({"query": [1, 1, 1, 2, 2], "item": list("abcde"), "relevance": [3, 0, 1, 0, 2], "score": [0.9, 0.1, 0.8, 0.2, 0.7]})
    result = execute_ranking(frame, {"protocol": "listwise", "items": "item", "metrics": ["ndcg_at_k"], "k": 3})
    assert result["queries"] == 2
    assert 0 <= result["metrics"]["ndcg_at_k"] <= 1
    with pytest.raises(ValueError, match="RANKING_PROTOCOL_REQUIRED"):
        execute_ranking(frame, {"protocol": "unknown", "items": "item", "metrics": ["ndcg_at_k"]})


def test_task_execution_service_persists_registered_result(tmp_path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "task-service")
    service = TaskExecutionService(cases, ArtifactRegistry(cases))
    result = service.execute(
        case["case_id"],
        "optimization",
        {
            "variables": [{"name": "x", "lower": 0, "upper": 2, "step": 1}],
            "objective": {"sense": "max", "coefficients": {"x": 1}},
            "constraints": [{"coefficients": {"x": 1}, "operator": ">=", "rhs": 0}],
        },
    )
    assert result["artifact"]["artifact_type"] == "task_execution_result"
    assert result["result"]["solution"] == {"x": 2.0}


@pytest.mark.parametrize("family,plan,frame", [
    ("forecasting", {"time_column": "date", "target_column": "y", "horizon": 2, "split_strategy": "temporal"}, pd.DataFrame({"date": pd.date_range("2024-01-01", periods=24), "y": np.arange(24, dtype=float)})),
    ("optimization", {"variables": [{"name": "x", "lower": 0, "upper": 2, "step": 1}], "objective": {"sense": "max", "coefficients": {"x": 1}}, "constraints": [{"coefficients": {"x": 1}, "operator": ">=", "rhs": 0}]}, None),
    ("simulation", {"parameters": [{"mean": 5, "std": 1}], "replications": 20, "scenarios": [{"name": "base"}], "seed": 3}, None),
    ("ranking", {"protocol": "listwise", "items": "item", "metrics": ["ndcg_at_k"]}, pd.DataFrame({"query": [1, 1, 2, 2], "item": ["a", "b", "c", "d"], "relevance": [1, 0, 0, 1], "score": [0.8, 0.1, 0.2, 0.9]})),
])
def test_task_paper_bridge_projects_every_family(tmp_path, family, plan, frame) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", f"bridge-{family}")
    artifacts = ArtifactRegistry(cases)
    contracts = PaperContractService(cases, artifacts)
    bridge = TaskPaperEvidenceBridge(
        cases,
        artifacts,
        TaskExecutionService(cases, artifacts),
        contracts,
        ClaimRegistry(cases, artifacts, DatasetRegistry(cases, artifacts)),
        FigureRegistry(cases, artifacts),
    )
    result = bridge.execute_and_register(case["case_id"], family, plan, frame)
    assert result["result_records"]
    assert result["table"].table_id in result["claim"]["table_record_ids"]
    assert result["figure"]["artifact_id"]


def test_task_bridge_persists_family_specific_evidence(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "cases")
    case = cases.create_case("SM", "题型特有证据")
    artifacts = ArtifactRegistry(cases)
    tasks = TaskExecutionService(cases, artifacts)
    contracts = PaperContractService(cases, artifacts)
    claims = ClaimRegistry(cases, artifacts, DatasetRegistry(cases, artifacts))
    figures = FigureRegistry(cases, artifacts)
    bridge = TaskPaperEvidenceBridge(cases, artifacts, tasks, contracts, claims, figures)
    frame = pd.DataFrame({"query": [1, 1, 2, 2], "item": ["a", "b", "a", "b"], "relevance": [2, 0, 0, 1], "score": [0.9, 0.1, 0.2, 0.8]})
    result = bridge.execute_and_register(case["case_id"], "ranking", {"protocol": "pairwise", "items": ["a", "b"], "metrics": ["mrr"], "k": 2}, frame)
    metrics = {item.metric for item in result["result_records"]}
    assert {"mrr", "ndcg_at_k", "pairwise_accuracy", "query_count", "pair_count"} <= metrics


def test_optimization_task_paper_pipeline_completes_contract_and_submission(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "cases")
    case = cases.create_case("SM", "optimization-paper")
    service = AutoPipelineService(cases, None)  # type: ignore[arg-type]
    result = service.run_task_paper_pipeline(
        case["case_id"],
        "optimization",
        {
            "variables": [{"name": "x", "lower": 0, "upper": 2, "step": 1}],
            "objective": {"sense": "max", "coefficients": {"x": 1}},
            "constraints": [{"coefficients": {"x": 1}, "operator": ">=", "rhs": 0}],
        },
        title="优化任务论文",
    )
    root = cases.case_root(case["case_id"])
    paper = (root / "paper" / "final.md").read_text(encoding="utf-8")
    assert result["family"] == "optimization"
    assert result["complete_paper_artifact_id"]
    assert result["submission"]["preflight"]["gate"] == "PASS"
    assert all(title in paper for title in ("摘要", "模型建立", "结果分析", "结论"))
    assert "0.000000" in paper or "2.000000" in paper


@pytest.mark.parametrize("family,plan,frame", [
    ("classification", {"target_column": "label", "feature_columns": ["x"], "class_balance": "balanced", "random_seed": 3}, pd.DataFrame({"x": np.arange(36), "label": ["a" if value < 18 else "b" for value in range(36)]})),
    ("forecasting", {"time_column": "date", "target_column": "y", "horizon": 3, "split_strategy": "temporal"}, pd.DataFrame({"date": pd.date_range("2024-01-01", periods=30), "y": np.arange(30, dtype=float)})),
    ("simulation", {"parameters": [{"mean": 5, "std": 1}], "replications": 30, "scenarios": [{"name": "base"}], "seed": 3}, None),
    ("ranking", {"protocol": "listwise", "items": "item", "metrics": ["ndcg_at_k"], "k": 2}, pd.DataFrame({"query": [1, 1, 2, 2], "item": ["a", "b", "c", "d"], "relevance": [1, 0, 0, 1], "score": [0.8, 0.1, 0.2, 0.9]})),
])
def test_non_tabular_task_paper_pipeline_families(tmp_path: Path, family: str, plan: dict, frame: pd.DataFrame | None) -> None:
    cases = CaseManager(tmp_path / "cases")
    case = cases.create_case("SM", f"{family}-paper")
    service = AutoPipelineService(cases, None)  # type: ignore[arg-type]
    result = service.run_task_paper_pipeline(case["case_id"], family, plan, frame, title=f"{family} 论文")
    assert result["family"] == family
    assert result["submission"]["preflight"]["gate"] == "PASS"


def test_task_paper_pipeline_blocks_invalid_protocol_before_paper(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "cases")
    case = cases.create_case("SM", "invalid-task-paper")
    service = AutoPipelineService(cases, None)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="RANKING_PROTOCOL_REQUIRED"):
        service.run_task_paper_pipeline(
            case["case_id"],
            "ranking",
            {"protocol": "invalid", "items": "item", "metrics": ["ndcg_at_k"]},
            pd.DataFrame({"query": [1], "item": ["a"], "relevance": [1], "score": [0.5]}),
        )
    assert not (cases.case_root(case["case_id"]) / "paper" / "final.md").exists()

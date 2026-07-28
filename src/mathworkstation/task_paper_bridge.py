from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from .claims import ClaimInput, ClaimRegistry
from .figure_registry import FigureRegistry
from .io_utils import atomic_write_text
from .paper_contracts import PaperContractService
from .task_executors import TaskExecutionService


class TaskPaperEvidenceBridge:
    """Projects a task executor result into the common paper evidence layer."""

    def __init__(
        self,
        cases: Any,
        artifacts: Any,
        tasks: TaskExecutionService,
        contracts: PaperContractService,
        claims: ClaimRegistry,
        figures: FigureRegistry,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.tasks = tasks
        self.contracts = contracts
        self.claims = claims
        self.figures = figures

    def execute_and_register(
        self,
        case_id: str,
        family: str,
        plan: dict[str, Any],
        frame: Any | None = None,
        dataset_ids: list[str] | None = None,
        source_artifact_ids: list[str] | None = None,
        created_by: str = "python",
    ) -> dict[str, Any]:
        execution = self.tasks.execute(case_id, family, plan, frame, source_artifact_ids)
        task_artifact_id = execution["artifact"]["artifact_id"]
        result = execution["result"]
        metric_items = _metrics_for_result(family, result)
        records = [
            self.contracts.create_result(
                case_id,
                result_type=_result_type(family),
                metric=metric,
                value=value,
                std=std,
                model_name=result.get("model"),
                dataset_id=(dataset_ids or [None])[0],
                direction="DESCRIPTIVE",
                scope=f"{family} deterministic task execution",
                source_artifact_ids=[task_artifact_id],
                section_ids=["abstract", "model_solution", "results", "sensitivity", "conclusion"],
                metadata=metadata,
            )
            for metric, value, std, metadata in metric_items
        ]
        table, table_artifact = self.contracts.create_table(
            case_id,
            title=f"{family} 执行结果",
            columns=["指标", "数值", "说明"],
            rows=[[item.metric.upper(), f"{item.value:.6f}", item.scope] for item in records],
            result_ids=[item.result_id for item in records],
            source_artifact_ids=[task_artifact_id],
            section_ids=["results", "conclusion"],
        )
        figure = self._create_figure(case_id, family, records, task_artifact_id)
        claim_text = _render_claim(family, result, records, table.table_id)
        claim = self.claims.create(
            case_id,
            ClaimInput(
                text=claim_text,
                claim_type=f"task_{family}",
                evidence_artifact_ids=[task_artifact_id, table_artifact["artifact_id"], figure["artifact_id"]],
                dataset_ids=dataset_ids or [],
                section_hint="results",
                result_record_ids=[item.result_id for item in records],
                table_record_ids=[table.table_id],
            ),
            created_by,
        )
        return {"execution": execution, "result_records": records, "table": table, "table_artifact": table_artifact, "figure": figure, "claim": claim}

    def _create_figure(self, case_id: str, family: str, records: list[Any], source_artifact_id: str) -> dict[str, Any]:
        root = self.cases.case_root(case_id)
        path = root / "figures" / "draft" / f"task-{family}-metrics.png"
        figure, axis = plt.subplots(figsize=(7, 4))
        axis.bar([item.metric for item in records], [item.value for item in records])
        axis.set_title(f"{family} task metrics")
        axis.tick_params(axis="x", rotation=30)
        figure.tight_layout()
        figure.savefig(path, dpi=180, bbox_inches="tight")
        plt.close(figure)
        return self.figures.register(case_id, path.relative_to(root).as_posix(), f"{family} 执行指标", [source_artifact_id], "mathworkstation.task_paper_bridge", {"family": family}, None, status="FINAL")


def _result_type(family: str) -> str:
    return {"forecasting": "FORECAST", "optimization": "OPTIMUM", "simulation": "SIMULATION", "ranking": "RANKING", "classification": "MODEL_COMPARISON"}[family]


def _metrics_for_result(family: str, result: dict[str, Any]) -> list[tuple[str, float, float | None, dict[str, Any]]]:
    if family in {"classification", "forecasting", "ranking"}:
        items = [(metric, float(value), None, {}) for metric, value in result["metrics"].items()]
        if family == "classification":
            for row_index, row in enumerate(result.get("confusion_matrix", [])):
                for column_index, value in enumerate(row):
                    items.append((f"confusion_{row_index}_{column_index}", float(value), None, {"labels": result.get("labels", [])}))
        elif family == "forecasting":
            items.append(("forecast_points", float(len(result.get("predictions", []))), None, {"leakage_check": result.get("leakage_check")}))
        else:
            items.extend([
                ("query_count", float(result.get("queries", 0)), None, {}),
                ("pair_count", float(result.get("pairs", 0)), None, {}),
            ])
        return items
    if family == "optimization":
        items = [("objective_value", float(result["objective_value"]), None, {"constraint_status": result["constraint_status"]})]
        items.extend((f"solution_{name}", float(value), None, {"constraint_status": result["constraint_status"]}) for name, value in result.get("solution", {}).items())
        items.append(("feasible_points", float(result.get("protocol", {}).get("feasible_points", 0)), None, {}))
        return items
    values = []
    for scenario, item in result["scenarios"].items():
        values.extend([
            (f"{scenario}_mean", float(item["mean"]), float(item["std"]), {"scenario": scenario, "p05": item["p05"], "p95": item["p95"]}),
            (f"{scenario}_p05", float(item["p05"]), None, {"scenario": scenario, "interval": "empirical_05_95"}),
            (f"{scenario}_p95", float(item["p95"]), None, {"scenario": scenario, "interval": "empirical_05_95"}),
        ])
    return values


def _render_claim(family: str, result: dict[str, Any], records: list[Any], table_id: str) -> str:
    values = "，".join(f"{item.metric.upper()}={item.value:.6f}" for item in records)
    return f"{family} 执行器在已登记协议下完成确定性计算，结果为 {values}，详见结果表 [{table_id}]；结论受协议、数据范围和执行参数限制。"

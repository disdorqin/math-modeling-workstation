from __future__ import annotations

import re
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .datasets import DatasetRegistry
from .figure_registry import FigureRegistry
from .io_utils import atomic_write_json, atomic_write_text, now_iso
from .paths import resolve_within
from .tabular import read_table


class EDAEngine:
    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        datasets: DatasetRegistry,
        figures: FigureRegistry,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.datasets = datasets
        self.figures = figures

    def run(
        self,
        case_id: str,
        dataset_id: str,
        target_column: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        dataset = self.datasets.get(case_id, dataset_id)
        if dataset["status"] not in {"PROFILED", "VERIFIED"}:
            raise ValueError("dataset must pass profiling before EDA")
        source_artifact = self.artifacts.get(case_id, dataset["artifact_id"])
        case_root = self.cases.case_root(case_id)
        frame = read_table(resolve_within(case_root, source_artifact["path"]))
        numeric = frame.select_dtypes(include=[np.number])
        categorical = frame.select_dtypes(exclude=[np.number])
        if target_column and target_column not in frame.columns:
            raise ValueError(f"target column not found: {target_column}")

        summary = {
            "schema_version": 1,
            "case_id": case_id,
            "dataset_id": dataset_id,
            "source_artifact_id": source_artifact["artifact_id"],
            "generated_at": now_iso(),
            "shape": {"rows": int(frame.shape[0]), "columns": int(frame.shape[1])},
            "numeric_columns": [str(column) for column in numeric.columns],
            "categorical_columns": [str(column) for column in categorical.columns],
            "numeric_summary": _numeric_summary(numeric),
            "categorical_summary": _categorical_summary(categorical),
            "target_column": target_column,
            "figures": [],
        }
        figure_records: list[dict[str, Any]] = []
        figure_directory = case_root / "figures" / "draft"
        slug = _slug(dataset_id)
        if not numeric.empty:
            distribution_path = figure_directory / f"{slug}-numeric-distributions.png"
            selected_columns = [str(column) for column in numeric.columns[:12]]
            _plot_numeric_distributions(numeric[selected_columns], distribution_path)
            figure_records.append(
                self.figures.register(
                    case_id,
                    distribution_path.relative_to(case_root).as_posix(),
                    "数值变量分布",
                    [source_artifact["artifact_id"]],
                    "mathworkstation.eda:_plot_numeric_distributions",
                    {"columns": selected_columns, "dpi": 180},
                    run_id,
                )
            )
        if numeric.shape[1] >= 2:
            correlation_path = figure_directory / f"{slug}-correlation-heatmap.png"
            correlation_columns = [str(column) for column in numeric.columns[:20]]
            _plot_correlation(numeric[correlation_columns], correlation_path)
            figure_records.append(
                self.figures.register(
                    case_id,
                    correlation_path.relative_to(case_root).as_posix(),
                    "数值变量相关性热力图",
                    [source_artifact["artifact_id"]],
                    "mathworkstation.eda:_plot_correlation",
                    {"method": "pearson", "columns": correlation_columns, "dpi": 180},
                    run_id,
                )
            )
        if target_column and pd.api.types.is_numeric_dtype(frame[target_column]):
            target_path = figure_directory / f"{slug}-target-distribution.png"
            _plot_target(frame[target_column], target_path)
            figure_records.append(
                self.figures.register(
                    case_id,
                    target_path.relative_to(case_root).as_posix(),
                    f"目标变量 {target_column} 分布",
                    [source_artifact["artifact_id"]],
                    "mathworkstation.eda:_plot_target",
                    {"target": target_column, "dpi": 180},
                    run_id,
                )
            )
        summary["figures"] = [record["figure_id"] for record in figure_records]
        summary_path = case_root / "results" / "diagnostics" / f"eda-{slug}.json"
        report_path = case_root / "analysis" / f"探索性分析报告-{dataset_id}.md"
        atomic_write_json(summary_path, summary)
        atomic_write_text(report_path, _render_report(dataset, summary, figure_records))
        summary_artifact = self.artifacts.register_existing(
            case_id,
            summary_path.relative_to(case_root).as_posix(),
            "eda_summary",
            "python",
            run_id=run_id,
            upstream=[source_artifact["artifact_id"]],
        )
        report_artifact = self.artifacts.register_existing(
            case_id,
            report_path.relative_to(case_root).as_posix(),
            "eda_report",
            "python",
            run_id=run_id,
            upstream=[source_artifact["artifact_id"], summary_artifact["artifact_id"]],
        )
        return {
            "summary": summary,
            "summary_artifact_id": summary_artifact["artifact_id"],
            "report_artifact_id": report_artifact["artifact_id"],
            "figures": figure_records,
        }


def _numeric_summary(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {}
    described = frame.describe().replace({np.nan: None})
    return {
        str(column): {str(index): _json_number(value) for index, value in described[column].items()}
        for column in described.columns
    }


def _categorical_summary(frame: pd.DataFrame) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for column in frame.columns:
        counts = frame[column].astype("string").value_counts(dropna=True).head(10)
        result[str(column)] = {
            "unique": int(frame[column].nunique(dropna=True)),
            "top_values": {str(key): int(value) for key, value in counts.items()},
        }
    return result


def _plot_numeric_distributions(frame: pd.DataFrame, path) -> None:
    columns = list(frame.columns)
    rows = int(np.ceil(len(columns) / 3))
    figure, axes = plt.subplots(rows, 3, figsize=(12, max(3.5, rows * 3.2)))
    axes_array = np.atleast_1d(axes).ravel()
    for axis, column in zip(axes_array, columns):
        sns.histplot(frame[column].dropna(), kde=True, ax=axis)
        axis.set_title(str(column))
    for axis in axes_array[len(columns):]:
        axis.set_visible(False)
    figure.tight_layout()
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def _plot_correlation(frame: pd.DataFrame, path) -> None:
    correlation = frame.corr(numeric_only=True)
    figure, axis = plt.subplots(figsize=(max(6, len(correlation) * 0.8), max(5, len(correlation) * 0.7)))
    sns.heatmap(correlation, annot=len(correlation) <= 10, cmap="vlag", center=0, ax=axis)
    axis.set_title("Correlation Matrix")
    figure.tight_layout()
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def _plot_target(series: pd.Series, path) -> None:
    figure, axis = plt.subplots(figsize=(7, 4.5))
    sns.histplot(series.dropna(), kde=True, ax=axis)
    axis.set_title(f"Target Distribution: {series.name}")
    figure.tight_layout()
    figure.savefig(path, dpi=180, bbox_inches="tight")
    plt.close(figure)


def _render_report(dataset: dict[str, Any], summary: dict[str, Any], figures: list[dict[str, Any]]) -> str:
    figure_lines = "\n".join(
        f"- `{figure['figure_id']}`：{figure['title']}（`{figure['path']}`）" for figure in figures
    ) or "- 本数据集未生成图表。"
    return (
        f"# 探索性分析报告：{dataset['name']}\n\n"
        f"- Dataset ID：`{dataset['dataset_id']}`\n"
        f"- 数据类型：`{dataset['kind']}`\n"
        f"- 样本规模：`{summary['shape']['rows']} × {summary['shape']['columns']}`\n"
        f"- 数值字段：`{len(summary['numeric_columns'])}`\n"
        f"- 分类字段：`{len(summary['categorical_columns'])}`\n\n"
        "## 已注册图表\n\n"
        f"{figure_lines}\n\n"
        "## 使用约束\n\n"
        "本报告中的统计量和图片由本地 Python 从已登记 Dataset 计算生成；解释性结论需在后续模型和审稿阶段确认。\n"
    )


def _json_number(value: Any) -> int | float | None:
    if value is None or pd.isna(value):
        return None
    number = float(value)
    return int(number) if number.is_integer() else number


def _slug(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]+", "-", value).strip("-")[:80]


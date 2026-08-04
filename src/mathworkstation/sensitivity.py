from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, f1_score, mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline

from .artifact_registry import ArtifactRegistry
from .baseline import _preprocessor, build_candidate_model
from .case_manager import CaseManager
from .datasets import DatasetRegistry
from .experiments import ExperimentRegistry
from .figure_registry import FigureRegistry
from .io_utils import atomic_write_json, atomic_write_text, now_iso
from .model_plan import ModelPlan
from .paths import resolve_within
from .plot_style import apply_style, get_colors, get_line_cycle, get_figsize, save_figure
from .tabular import read_table

apply_style()


class SensitivityEngine:
    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        datasets: DatasetRegistry,
        experiments: ExperimentRegistry,
        figures: FigureRegistry,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.datasets = datasets
        self.experiments = experiments
        self.figures = figures

    def run(
        self,
        case_id: str,
        comparison_experiment_id: str,
        plan: ModelPlan,
        plan_artifact_id: str,
        seeds: list[int] | None = None,
        run_id: str | None = None,
    ) -> dict[str, Any]:
        comparison_experiment = self.experiments.get(case_id, comparison_experiment_id)
        if comparison_experiment["status"] != "SUCCEEDED":
            raise ValueError("comparison experiment must succeed before sensitivity analysis")
        comparison_artifact = self.artifacts.get(case_id, comparison_experiment["comparison_artifact_id"])
        comparison_path = resolve_within(self.cases.case_root(case_id), comparison_artifact["path"])
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        best_model = comparison["best_model"]
        candidate = next(item for item in plan.candidate_models if item.name == best_model)
        dataset = self.datasets.get(case_id, plan.dataset_id)
        source_artifact = self.artifacts.get(case_id, dataset["artifact_id"])
        frame = read_table(resolve_within(self.cases.case_root(case_id), source_artifact["path"]))
        modeling = frame[[*plan.feature_columns, plan.target_column]].dropna(subset=[plan.target_column])
        # Sort by temporal column for time-ordered splitting
        if plan.split_strategy == "time_ordered" and plan.temporal_column and plan.temporal_column in modeling.columns:
            modeling = modeling.sort_values(by=plan.temporal_column, kind="mergesort").reset_index(drop=True)
        features = modeling[plan.feature_columns]
        target = modeling[plan.target_column]
        seeds = seeds or [plan.random_seed, plan.random_seed + 17, plan.random_seed + 41]
        rows: list[dict[str, Any]] = []
        for fraction in plan.sensitivity_fractions:
            for seed in seeds:
                train_size = max(2, int(len(modeling) * fraction * (1 - plan.test_size)))
                test_size = max(1, int(len(modeling) * fraction) - train_size)
                if train_size + test_size > len(modeling):
                    test_size = len(modeling) - train_size
                if test_size < 1:
                    continue
                # For time-ordered split, use sequential split (no shuffle)
                if plan.split_strategy == "time_ordered":
                    split_point = train_size
                    x_train = features.iloc[:split_point]
                    x_test = features.iloc[split_point:split_point + test_size]
                    y_train = target.iloc[:split_point]
                    y_test = target.iloc[split_point:split_point + test_size]
                else:
                    x_train, x_test, y_train, y_test = train_test_split(
                        features,
                        target,
                        train_size=train_size,
                        test_size=test_size,
                        random_state=seed,
                        stratify=_safe_stratify(target, plan.task_type, test_size),
                    )
                pipeline = Pipeline(
                    [
                        ("preprocessor", _preprocessor(features)),
                        ("model", build_candidate_model(plan.task_type, best_model, candidate.parameters, seed)),
                    ]
                )
                pipeline.fit(x_train, y_train)
                predicted = pipeline.predict(x_test)
                metrics = _metrics(plan.task_type, y_test, predicted)
                rows.append(
                    {
                        "fraction": fraction,
                        "seed": seed,
                        "train_rows": len(x_train),
                        "test_rows": len(x_test),
                        **metrics,
                    }
                )
        if not rows:
            raise ValueError("sensitivity configuration produced no valid runs")
        summary = _summarize(plan, best_model, rows)
        root = self.cases.case_root(case_id)
        output_path = root / "results" / "diagnostics" / f"sensitivity-{comparison_experiment_id}.json"
        atomic_write_json(output_path, summary)
        artifact = self.artifacts.register_existing(
            case_id,
            output_path.relative_to(root).as_posix(),
            "sensitivity_results",
            "python",
            run_id=run_id,
            upstream=[source_artifact["artifact_id"], plan_artifact_id, comparison_artifact["artifact_id"]],
        )
        figure_path = root / "figures" / "draft" / f"sensitivity-{comparison_experiment_id}.png"
        _plot_sensitivity(plan, rows, figure_path)
        figure = self.figures.register(
            case_id,
            figure_path.relative_to(root).as_posix(),
            "模型样本比例与随机种子敏感性",
            [artifact["artifact_id"]],
            "mathworkstation.sensitivity:_plot_sensitivity",
            {"primary_metric": plan.primary_metric, "seeds": seeds, "dpi": 180},
            run_id,
        )
        report_path = root / "analysis" / f"敏感性分析报告-{comparison_experiment_id}.md"
        atomic_write_text(report_path, _render_report(summary, figure))
        report_artifact = self.artifacts.register_existing(
            case_id,
            report_path.relative_to(root).as_posix(),
            "sensitivity_report",
            "python",
            run_id=run_id,
            upstream=[artifact["artifact_id"]],
        )
        return {
            "summary": summary,
            "artifact_id": artifact["artifact_id"],
            "figure": figure,
            "report_artifact_id": report_artifact["artifact_id"],
        }


def _safe_stratify(target: pd.Series, task_type: str, test_rows: int):
    if task_type != "classification":
        return None
    counts = target.value_counts()
    return target if counts.min() >= 2 and test_rows >= len(counts) else None


def _metrics(task_type: str, actual, predicted) -> dict[str, float]:
    if task_type == "regression":
        return {
            "mae": float(mean_absolute_error(actual, predicted)),
            "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
            "r2": float(r2_score(actual, predicted)),
        }
    return {
        "accuracy": float(accuracy_score(actual, predicted)),
        "macro_f1": float(f1_score(actual, predicted, average="macro", zero_division=0)),
    }


def _summarize(plan: ModelPlan, best_model: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    frame = pd.DataFrame(rows)
    metric = plan.primary_metric
    grouped = []
    for fraction, group in frame.groupby("fraction"):
        mean = float(group[metric].mean())
        std = float(group[metric].std(ddof=1)) if len(group) > 1 else 0.0
        relative_std = std / (abs(mean) or 1.0)
        grouped.append(
            {
                "fraction": float(fraction),
                "mean": mean,
                "std": std,
                "relative_std": relative_std,
                "runs": len(group),
            }
        )
    full = next(item for item in grouped if item["fraction"] == max(value["fraction"] for value in grouped))
    worst_relative_std = max(item["relative_std"] for item in grouped)
    if metric in {"rmse", "mae"}:
        worst_degradation = max((item["mean"] - full["mean"]) / (abs(full["mean"]) or 1.0) for item in grouped)
    else:
        worst_degradation = max((full["mean"] - item["mean"]) / (abs(full["mean"]) or 1.0) for item in grouped)
    gate = "PASS" if worst_relative_std <= 0.3 and worst_degradation <= 0.5 else "REVIEW"
    return {
        "schema_version": 1,
        "best_model": best_model,
        "primary_metric": metric,
        "grouped": grouped,
        "runs": rows,
        "worst_relative_std": float(worst_relative_std),
        "worst_relative_degradation": float(worst_degradation),
        "gate": gate,
        "generated_at": now_iso(),
    }


def _plot_sensitivity(plan: ModelPlan, rows: list[dict[str, Any]], path: Path) -> None:
    frame = pd.DataFrame(rows)
    colors = get_colors()
    line_cycle = get_line_cycle()
    figsize = get_figsize("sensitivity")
    figure, axis = plt.subplots(figsize=figsize)
    for idx, (seed, group) in enumerate(frame.groupby("seed")):
        ordered = group.sort_values("fraction")
        linestyle, marker = line_cycle[idx % len(line_cycle)]
        color = colors[idx % len(colors)]
        axis.plot(ordered["fraction"], ordered[plan.primary_metric],
                  linestyle=linestyle, marker=marker, label=f"seed={seed}",
                  color=color, linewidth=2.0, markersize=6,
                  markerfacecolor="white", markeredgecolor=color, markeredgewidth=1.5)
    axis.set_xlabel("Data Fraction", fontweight="bold")
    axis.set_ylabel(plan.primary_metric, fontweight="bold")
    axis.set_title("Sensitivity Analysis", fontweight="bold")
    axis.legend(frameon=True, framealpha=0.9, edgecolor="#cccccc")
    axis.grid(True, alpha=0.3, linestyle="--")
    figure.tight_layout()
    save_figure(figure, path)
    plt.close(figure)


def _render_report(summary: dict[str, Any], figure: dict[str, Any]) -> str:
    rows = "\n".join(
        f"| {item['fraction']:.2f} | {item['mean']:.6f} | {item['std']:.6f} | {item['relative_std']:.4f} |"
        for item in summary["grouped"]
    )
    return (
        "# 敏感性分析报告\n\n"
        f"- 最优模型：`{summary['best_model']}`\n"
        f"- 主指标：`{summary['primary_metric']}`\n"
        f"- 稳健性门：**{summary['gate']}**\n"
        f"- 图表：`{figure['figure_id']}`\n\n"
        "| 数据比例 | 指标均值 | 标准差 | 相对波动 |\n|---:|---:|---:|---:|\n"
        f"{rows}\n\n"
        "若门状态为 REVIEW，必须说明样本量或随机划分敏感性，不能直接宣称模型稳健。\n"
    )


from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

import pandas as pd

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .datasets import DatasetRegistry, DatasetStatus
from .io_utils import atomic_write_json, atomic_write_text, now_iso
from .paths import resolve_within
from .tabular import read_table


class QualityGate(StrEnum):
    PASS = "PASS"
    REVIEW = "REVIEW"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class QualityIssue:
    code: str
    severity: str
    message: str
    column: str | None = None


class TabularProfiler:
    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        datasets: DatasetRegistry,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.datasets = datasets

    def profile(
        self,
        case_id: str,
        dataset_id: str,
        target_column: str | None = None,
        sheet_name: str | int | None = 0,
    ) -> dict[str, Any]:
        dataset = self.datasets.get(case_id, dataset_id)
        artifact = self.artifacts.get(case_id, dataset["artifact_id"])
        case_root = self.cases.case_root(case_id)
        source_path = resolve_within(case_root, artifact["path"])
        frame = read_table(source_path, sheet_name)
        issues = _quality_issues(frame, target_column)
        gate = _gate_for(issues)
        columns = [_column_profile(frame[column]) for column in frame.columns]
        profile = {
            "schema_version": 1,
            "case_id": case_id,
            "dataset_id": dataset_id,
            "source_artifact_id": artifact["artifact_id"],
            "generated_at": now_iso(),
            "shape": {"rows": int(frame.shape[0]), "columns": int(frame.shape[1])},
            "duplicate_rows": int(frame.duplicated().sum()),
            "missing_cells": int(frame.isna().sum().sum()),
            "missing_ratio": _finite_float(frame.isna().to_numpy().mean() if frame.size else 0.0),
            "target_column": target_column,
            "columns": columns,
            "quality_gate": gate.value,
            "issues": [asdict(issue) for issue in issues],
        }
        profile_directory = case_root / "data" / "dictionaries"
        profile_directory.mkdir(parents=True, exist_ok=True)
        profile_path = profile_directory / f"{dataset_id}.profile.json"
        atomic_write_json(profile_path, profile)
        report_path = case_root / "analysis" / f"数据质量报告-{dataset_id}.md"
        atomic_write_text(report_path, _render_report(dataset, profile))
        profile_artifact = self.artifacts.register_existing(
            case_id,
            profile_path.relative_to(case_root).as_posix(),
            "data_profile",
            "python",
            upstream=[artifact["artifact_id"]],
            paper_eligible=False,
        )
        report_artifact = self.artifacts.register_existing(
            case_id,
            report_path.relative_to(case_root).as_posix(),
            "data_quality_report",
            "python",
            upstream=[artifact["artifact_id"], profile_artifact["artifact_id"]],
            paper_eligible=False,
        )
        status = DatasetStatus.PROFILED if gate != QualityGate.BLOCK else DatasetStatus.REJECTED
        self.datasets.update_status(case_id, dataset_id, status, f"quality_gate={gate.value}")
        return {
            "profile": profile,
            "profile_artifact_id": profile_artifact["artifact_id"],
            "report_artifact_id": report_artifact["artifact_id"],
        }


def _column_profile(series: pd.Series) -> dict[str, Any]:
    non_null = series.dropna()
    profile: dict[str, Any] = {
        "name": str(series.name),
        "dtype": str(series.dtype),
        "non_null": int(series.notna().sum()),
        "missing": int(series.isna().sum()),
        "missing_ratio": _finite_float(series.isna().mean()),
        "unique": int(series.nunique(dropna=True)),
        "constant": bool(non_null.nunique() <= 1),
    }
    if pd.api.types.is_numeric_dtype(series):
        numeric = pd.to_numeric(non_null, errors="coerce").dropna()
        profile["statistics"] = {
            "min": _finite_float(numeric.min()) if not numeric.empty else None,
            "max": _finite_float(numeric.max()) if not numeric.empty else None,
            "mean": _finite_float(numeric.mean()) if not numeric.empty else None,
            "median": _finite_float(numeric.median()) if not numeric.empty else None,
            "std": _finite_float(numeric.std()) if len(numeric) > 1 else None,
        }
    else:
        samples = [str(value)[:200] for value in non_null.astype(str).drop_duplicates().head(5)]
        profile["sample_values"] = samples
    return profile


def _quality_issues(frame: pd.DataFrame, target_column: str | None) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    if frame.empty:
        issues.append(QualityIssue("EMPTY_DATASET", "BLOCK", "数据集没有可用行。"))
    if frame.shape[1] == 0:
        issues.append(QualityIssue("NO_COLUMNS", "BLOCK", "数据集没有字段。"))
    duplicate_ratio = frame.duplicated().mean() if len(frame) else 0.0
    if duplicate_ratio >= 0.5:
        issues.append(QualityIssue("HIGH_DUPLICATE_RATIO", "REVIEW", "重复行比例不低于 50%。"))
    for column in frame.columns:
        series = frame[column]
        missing_ratio = series.isna().mean()
        if missing_ratio >= 0.9:
            issues.append(QualityIssue("MOSTLY_MISSING", "REVIEW", "字段缺失比例不低于 90%。", str(column)))
        if series.dropna().nunique() <= 1:
            issues.append(QualityIssue("CONSTANT_COLUMN", "REVIEW", "字段为常量或全空。", str(column)))
        if len(series) and series.nunique(dropna=True) == series.notna().sum() and series.notna().sum() > 20:
            issues.append(QualityIssue("POSSIBLE_IDENTIFIER", "INFO", "字段值几乎全部唯一，可能是标识列。", str(column)))
    if target_column:
        if target_column not in frame.columns:
            issues.append(QualityIssue("TARGET_MISSING", "BLOCK", "指定目标变量不存在。", target_column))
        elif frame[target_column].isna().all():
            issues.append(QualityIssue("TARGET_ALL_MISSING", "BLOCK", "目标变量全部缺失。", target_column))
        elif frame[target_column].nunique(dropna=True) <= 1:
            issues.append(QualityIssue("TARGET_CONSTANT", "BLOCK", "目标变量没有有效变化。", target_column))
    return issues


def _gate_for(issues: list[QualityIssue]) -> QualityGate:
    severities = {issue.severity for issue in issues}
    if "BLOCK" in severities:
        return QualityGate.BLOCK
    if "REVIEW" in severities:
        return QualityGate.REVIEW
    return QualityGate.PASS


def _finite_float(value: Any) -> float | None:
    converted = float(value)
    return converted if math.isfinite(converted) else None


def _render_report(dataset: dict[str, Any], profile: dict[str, Any]) -> str:
    issues = profile["issues"]
    issue_lines = "\n".join(_render_issue(issue) for issue in issues) or "- 未发现规则化质量问题。"
    column_lines = "\n".join(
        f"| {column['name']} | {column['dtype']} | {column['missing']} | "
        f"{column['missing_ratio']:.4f} | {column['unique']} |"
        for column in profile["columns"]
    )
    return (
        f"# 数据质量报告：{dataset['name']}\n\n"
        f"- Dataset ID：`{dataset['dataset_id']}`\n"
        f"- 数据类型：`{dataset['kind']}`\n"
        f"- 行数：`{profile['shape']['rows']}`\n"
        f"- 列数：`{profile['shape']['columns']}`\n"
        f"- 质量门：**{profile['quality_gate']}**\n\n"
        "## 质量问题\n\n"
        f"{issue_lines}\n\n"
        "## 字段概览\n\n"
        "| 字段 | 类型 | 缺失数 | 缺失比例 | 唯一值数 |\n"
        "|---|---:|---:|---:|---:|\n"
        f"{column_lines}\n"
    )


def _render_issue(issue: dict[str, Any]) -> str:
    column = f"（{issue['column']}）" if issue.get("column") else ""
    return f"- **{issue['severity']}** `{issue['code']}`{column}：{issue['message']}"

from __future__ import annotations

import re
from typing import Any

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .datasets import DatasetRegistry
from .io_utils import atomic_write_json, atomic_write_text, now_iso
from .paths import resolve_within
from .tabular import read_table


class ResearchAuditService:
    """Turns common modeling risks into explicit, reviewable evidence."""

    def __init__(self, cases: CaseManager, artifacts: ArtifactRegistry, datasets: DatasetRegistry) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.datasets = datasets

    def audit(
        self,
        case_id: str,
        dataset_id: str,
        target_column: str,
        proposed_features: list[str],
        approved_by: str,
    ) -> dict[str, Any]:
        dataset = self.datasets.get(case_id, dataset_id)
        source = self.artifacts.get(case_id, dataset["artifact_id"])
        frame = read_table(resolve_within(self.cases.case_root(case_id), source["path"]))
        issues: list[dict[str, Any]] = []
        identifier_columns: list[str] = []
        temporal_columns = [
            str(column) for column in frame.columns
            if re.search(r"(^|[_-])(date|time|year|month|quarter|timestamp)([_-]|$)", str(column).lower())
        ]
        for column in frame.columns:
            name = str(column)
            if name == target_column:
                continue
            non_null = frame[column].dropna()
            if len(non_null) >= 20 and len(non_null) and non_null.nunique() / len(non_null) >= 0.98:
                identifier_columns.append(name)
        if target_column in proposed_features:
            issues.append({"code": "TARGET_AS_FEATURE", "severity": "BLOCK", "column": target_column})
        selected = [column for column in proposed_features if column in frame.columns and column not in identifier_columns]
        excluded = [column for column in proposed_features if column in identifier_columns]
        if excluded:
            issues.append({
                "code": "IDENTIFIER_LIKE_FEATURE",
                "severity": "REVIEW",
                "columns": excluded,
                "message": "高唯一性字段已从自动基线中排除；若其代表真实时间或空间顺序，需要人工指定专门切分策略。",
            })
        if not selected:
            issues.append({"code": "NO_RECOMMENDED_FEATURES", "severity": "BLOCK", "message": "研究审查后没有可用特征。"})
        if dataset["kind"] == "OBSERVED" and not dataset.get("source_uri"):
            issues.append({
                "code": "SOURCE_URI_MISSING",
                "severity": "REVIEW",
                "message": "观测数据缺少可核验来源 URI，论文不得将其描述为公开可复核来源。",
            })
        # Keep temporal columns for split recommendation even if excluded as identifier-like
        # (e.g., "Date" column is excluded from features but should still drive time_ordered split)
        all_proposed = [column for column in proposed_features if column in frame.columns]
        temporal_columns_for_split = [column for column in temporal_columns if column in all_proposed]
        split_recommendation = "time_ordered" if temporal_columns_for_split else "random"
        temporal_columns_in_features = [column for column in temporal_columns if column in selected]
        if temporal_columns_in_features:
            issues.append({
                "code": "TEMPORAL_SPLIT_REVIEW",
                "severity": "REVIEW",
                "columns": temporal_columns_in_features,
                "message": "检测到时间语义字段，优先考虑按时间顺序切分而非随机切分。",
            })
        severities = {issue["severity"] for issue in issues}
        gate = "BLOCK" if "BLOCK" in severities else "REVIEW" if "REVIEW" in severities else "PASS"
        report = {
            "schema_version": 1,
            "case_id": case_id,
            "dataset_id": dataset_id,
            "target_column": target_column,
            "proposed_feature_columns": proposed_features,
            "recommended_feature_columns": selected,
            "excluded_identifier_like_columns": excluded,
            "temporal_columns": temporal_columns_for_split,
            "split_recommendation": split_recommendation,
            "provenance": {
                "kind": dataset["kind"],
                "source_type": dataset["source_type"],
                "source_uri": dataset.get("source_uri"),
                "license": dataset.get("license"),
                "source_artifact_id": source["artifact_id"],
            },
            "gate": gate,
            "issues": issues,
            "decision": "automatic_identifier_exclusion" if excluded else "retain_proposed_features",
            "approved_by": approved_by,
            "generated_at": now_iso(),
        }
        root = self.cases.case_root(case_id)
        path = root / "analysis" / "research_audit.json"
        atomic_write_json(path, report)
        markdown = root / "analysis" / "研究审查报告.md"
        atomic_write_text(markdown, _render_report(report))
        artifact = self.artifacts.register_existing(case_id, path.relative_to(root).as_posix(), "research_audit", "python", upstream=[source["artifact_id"]])
        report_artifact = self.artifacts.register_existing(case_id, markdown.relative_to(root).as_posix(), "research_audit_report", "python", upstream=[source["artifact_id"], artifact["artifact_id"]])
        return {"report": report, "artifact_id": artifact["artifact_id"], "report_artifact_id": report_artifact["artifact_id"]}


def _render_report(report: dict[str, Any]) -> str:
    issues = "\n".join(
        f"- **{issue['severity']}** `{issue['code']}` {issue.get('message', '')}"
        for issue in report["issues"]
    ) or "- 未发现规则化研究风险。"
    return (
        "# 研究审查报告\n\n"
        f"- Gate：**{report['gate']}**\n"
        f"- 推荐特征：`{', '.join(report['recommended_feature_columns'])}`\n"
        f"- 切分建议：`{report['split_recommendation']}`\n"
        f"- 数据来源：`{report['provenance'].get('source_uri') or '未提供 URI'}`\n\n"
        "## 风险与决策\n\n"
        f"{issues}\n\n"
        f"自动决策：`{report['decision']}`。该决策由 `{report['approved_by']}` 记录，仍需在论文中说明适用边界。\n"
    )

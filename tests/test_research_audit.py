from pathlib import Path

import pandas as pd

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.data_service import DataService
from mathworkstation.datasets import DatasetKind, DatasetRegistry
from mathworkstation.memory_manager import MemoryManager
from mathworkstation.checkpoint_manager import CheckpointManager
from mathworkstation.research_audit import ResearchAuditService
from mathworkstation.run_manager import RunManager
from mathworkstation.workflow_service import WorkflowService
from mathworkstation.data_quality import TabularProfiler


def test_research_audit_excludes_identifier_and_records_temporal_review(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Research audit")
    artifacts = ArtifactRegistry(cases)
    datasets = DatasetRegistry(cases, artifacts)
    workflow = WorkflowService(cases, RunManager(cases), CheckpointManager(cases), MemoryManager(cases, artifacts))
    data = DataService(artifacts, datasets, TabularProfiler(cases, artifacts, datasets), workflow)
    source = tmp_path / "data.csv"
    pd.DataFrame({
        "year": [2000 + i // 3 for i in range(30)],
        "record_id": range(100, 130),
        "feature": [float(i % 5) for i in range(30)],
        "target": [float(i) for i in range(30)],
    }).to_csv(source, index=False)
    registered = data.register_uploaded(
        case["case_id"], source, "观测数据", DatasetKind.OBSERVED, "human", source_uri="https://data.example.test/source"
    )
    result = ResearchAuditService(cases, artifacts, datasets).audit(
        case["case_id"], registered["dataset"]["dataset_id"], "target", ["year", "record_id", "feature"], "human"
    )
    assert result["report"]["recommended_feature_columns"] == ["year", "feature"]
    assert result["report"]["split_recommendation"] == "time_ordered"
    assert {issue["code"] for issue in result["report"]["issues"]} >= {
        "IDENTIFIER_LIKE_FEATURE", "TEMPORAL_SPLIT_REVIEW"
    }
    assert artifacts.get(case["case_id"], result["artifact_id"])["artifact_type"] == "research_audit"


def test_temporal_column_excluded_as_identifier_still_drives_split(tmp_path: Path) -> None:
    """Date-like column excluded as identifier should still trigger time_ordered split."""
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Temporal identifier test")
    artifacts = ArtifactRegistry(cases)
    datasets = DatasetRegistry(cases, artifacts)
    workflow = WorkflowService(cases, RunManager(cases), CheckpointManager(cases), MemoryManager(cases, artifacts))
    data = DataService(artifacts, datasets, TabularProfiler(cases, artifacts, datasets), workflow)
    source = tmp_path / "wordle.csv"
    # Simulate Wordle-like data: Date is unique (identifier) but is a temporal column
    dates = pd.date_range("2023-01-01", periods=25, freq="D")
    pd.DataFrame({
        "Date": dates,
        "Contest number": range(1, 26),
        "tries_1": [float(i % 3) for i in range(25)],
        "tries_2": [float(i % 4) for i in range(25)],
        "target": [float(i) for i in range(25)],
    }).to_csv(source, index=False)
    registered = data.register_uploaded(
        case["case_id"], source, "观测数据", DatasetKind.OBSERVED, "human"
    )
    result = ResearchAuditService(cases, artifacts, datasets).audit(
        case["case_id"], registered["dataset"]["dataset_id"], "target",
        ["Date", "Contest number", "tries_1", "tries_2"], "human"
    )
    # Date excluded as identifier but still drives time_ordered split
    assert "Date" in result["report"]["excluded_identifier_like_columns"]
    assert result["report"]["split_recommendation"] == "time_ordered"
    assert result["report"]["temporal_columns"] == ["Date"]
    # Date is excluded from features, so TEMPORAL_SPLIT_REVIEW should NOT appear
    # (it only reports temporal columns that are in selected features)
    issue_codes = {issue["code"] for issue in result["report"]["issues"]}
    assert "IDENTIFIER_LIKE_FEATURE" in issue_codes

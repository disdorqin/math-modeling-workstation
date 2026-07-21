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

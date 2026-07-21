from pathlib import Path

import pandas as pd

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.data_quality import TabularProfiler
from mathworkstation.datasets import DatasetKind, DatasetRegistry


def _register_csv(tmp_path: Path, frame: pd.DataFrame):
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Quality")
    source = tmp_path / "data.csv"
    frame.to_csv(source, index=False)
    artifacts = ArtifactRegistry(cases)
    artifact = artifacts.ingest_file(case["case_id"], source, "input/data/uploaded", "observed_data")
    datasets = DatasetRegistry(cases, artifacts)
    dataset = datasets.register(
        case["case_id"], "Input", artifact["artifact_id"], DatasetKind.OBSERVED, "uploaded", "human"
    )
    return cases, artifacts, datasets, case, dataset


def test_profiler_generates_evidence_backed_pass_report(tmp_path: Path) -> None:
    cases, artifacts, datasets, case, dataset = _register_csv(
        tmp_path,
        pd.DataFrame({"feature": [1, 2, 3, 4], "target": [2, 4, 6, 8]}),
    )
    result = TabularProfiler(cases, artifacts, datasets).profile(
        case["case_id"], dataset["dataset_id"], target_column="target"
    )
    assert result["profile"]["quality_gate"] == "PASS"
    assert artifacts.get(case["case_id"], result["profile_artifact_id"])["upstream"] == [dataset["artifact_id"]]
    assert datasets.get(case["case_id"], dataset["dataset_id"])["status"] == "PROFILED"


def test_missing_target_blocks_dataset(tmp_path: Path) -> None:
    cases, artifacts, datasets, case, dataset = _register_csv(
        tmp_path,
        pd.DataFrame({"feature": [1, 2, 3]}),
    )
    result = TabularProfiler(cases, artifacts, datasets).profile(
        case["case_id"], dataset["dataset_id"], target_column="missing"
    )
    assert result["profile"]["quality_gate"] == "BLOCK"
    assert datasets.get(case["case_id"], dataset["dataset_id"])["status"] == "REJECTED"


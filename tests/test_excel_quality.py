from pathlib import Path

import pandas as pd

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.data_quality import TabularProfiler
from mathworkstation.datasets import DatasetKind, DatasetRegistry


def test_excel_dataset_is_profiled(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Excel")
    source = tmp_path / "data.xlsx"
    pd.DataFrame({"feature": [1, 2, 3], "target": [2, 3, 5]}).to_excel(source, index=False)
    artifacts = ArtifactRegistry(cases)
    artifact = artifacts.ingest_file(case["case_id"], source, "input/data/uploaded", "observed_data")
    datasets = DatasetRegistry(cases, artifacts)
    dataset = datasets.register(
        case["case_id"], "Excel", artifact["artifact_id"], DatasetKind.OBSERVED, "uploaded", "human"
    )
    profile = TabularProfiler(cases, artifacts, datasets).profile(
        case["case_id"], dataset["dataset_id"], "target"
    )
    assert profile["profile"]["shape"] == {"rows": 3, "columns": 2}
    assert profile["profile"]["quality_gate"] == "PASS"


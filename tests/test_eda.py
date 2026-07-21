from pathlib import Path

import pandas as pd

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.data_quality import TabularProfiler
from mathworkstation.datasets import DatasetKind, DatasetRegistry
from mathworkstation.eda import EDAEngine
from mathworkstation.figure_registry import FigureRegistry


def test_eda_generates_registered_figures_and_report(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "EDA")
    source = tmp_path / "data.csv"
    pd.DataFrame(
        {
            "x1": list(range(30)),
            "x2": [value * 3 for value in range(30)],
            "target": [value * 2 + 1 for value in range(30)],
            "group": ["A", "B", "C"] * 10,
        }
    ).to_csv(source, index=False)
    artifacts = ArtifactRegistry(cases)
    source_artifact = artifacts.ingest_file(
        case["case_id"], source, "input/data/uploaded", "observed_data"
    )
    datasets = DatasetRegistry(cases, artifacts)
    dataset = datasets.register(
        case["case_id"], "EDA Input", source_artifact["artifact_id"], DatasetKind.OBSERVED, "uploaded", "human"
    )
    TabularProfiler(cases, artifacts, datasets).profile(
        case["case_id"], dataset["dataset_id"], "target"
    )
    figures = FigureRegistry(cases, artifacts)
    result = EDAEngine(cases, artifacts, datasets, figures).run(
        case["case_id"], dataset["dataset_id"], "target", "run-eda"
    )
    assert len(result["figures"]) == 3
    assert result["summary"]["shape"] == {"rows": 30, "columns": 4}
    for figure in figures.list_figures(case["case_id"]):
        path = cases.case_root(case["case_id"]) / figure["path"]
        assert path.is_file() and path.stat().st_size > 0
        assert figure["source_artifact_ids"] == [source_artifact["artifact_id"]]
    assert artifacts.verify(case["case_id"])["valid"]


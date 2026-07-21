from pathlib import Path

import pytest

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.datasets import DatasetKind, DatasetRegistry


def test_dataset_kind_and_lineage_are_enforced(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Dataset")
    registry = ArtifactRegistry(cases)
    source = tmp_path / "observed.csv"
    source.write_text("x,y\n1,2\n", encoding="utf-8")
    artifact = registry.ingest_file(case["case_id"], source, "input/data/uploaded", "observed_data")
    datasets = DatasetRegistry(cases, registry)
    observed = datasets.register(
        case["case_id"],
        "Observed",
        artifact["artifact_id"],
        DatasetKind.OBSERVED,
        "uploaded",
        "human",
    )
    assert observed["kind"] == "OBSERVED"

    derived_file = cases.case_root(case["case_id"]) / "data" / "cleaned" / "derived.csv"
    derived_file.write_text("x,y\n1,2\n", encoding="utf-8")
    derived_artifact = registry.register_existing(
        case["case_id"], "data/cleaned/derived.csv", "cleaned_data", "python"
    )
    derived = datasets.register(
        case["case_id"],
        "Derived",
        derived_artifact["artifact_id"],
        DatasetKind.DERIVED,
        "computed",
        "python",
        derived_from=[observed["dataset_id"]],
    )
    assert derived["derived_from"] == [observed["dataset_id"]]

    with pytest.raises(ValueError):
        datasets.register(
            case["case_id"],
            "Fake observed",
            artifact["artifact_id"],
            DatasetKind.OBSERVED,
            "generated",
            "model",
        )


def test_mutable_artifact_versions_supersede_old_hash(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Versions")
    registry = ArtifactRegistry(cases)
    report = cases.case_root(case["case_id"]) / "analysis" / "report.md"
    report.write_text("v1", encoding="utf-8")
    first = registry.register_existing(case["case_id"], "analysis/report.md", "report", "python")
    report.write_text("v2", encoding="utf-8")
    second = registry.register_existing(case["case_id"], "analysis/report.md", "report", "python")
    records = {item["artifact_id"]: item for item in registry.list_artifacts(case["case_id"])}
    assert records[first["artifact_id"]]["status"] == "SUPERSEDED"
    assert records[second["artifact_id"]]["status"] == "ACTIVE"
    assert registry.verify(case["case_id"])["valid"]


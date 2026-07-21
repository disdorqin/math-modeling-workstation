from pathlib import Path

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.experiments import ExperimentRegistry


def test_experiment_freezes_input_and_code(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Experiment")
    source = tmp_path / "data.csv"
    source.write_text("x,target\n1,2\n", encoding="utf-8")
    artifacts = ArtifactRegistry(cases)
    data_artifact = artifacts.ingest_file(case["case_id"], source, "input/data/uploaded", "observed_data")
    registry = ExperimentRegistry(cases, artifacts)
    experiment = registry.create(
        case["case_id"],
        "Baseline",
        "dataset-test",
        data_artifact["artifact_id"],
        "regression",
        "target",
        ["x"],
        {"seed": 42},
        "run-baseline",
    )
    code = tmp_path / "runner.py"
    code.write_text("print('run')\n", encoding="utf-8")
    copied = registry.snapshot_code(case["case_id"], experiment["experiment_id"], [code])
    assert copied[0]["path"] == f"experiments/{experiment['experiment_id']}/code_snapshot/runner.py"
    assert copied[0]["artifact_type"] == "experiment_code_snapshot"
    manifest = cases.case_root(case["case_id"]) / "experiments" / experiment["experiment_id"] / "input_manifest.json"
    assert data_artifact["sha256"] in manifest.read_text(encoding="utf-8")
    assert registry.get(case["case_id"], experiment["experiment_id"])["config_artifact_id"]

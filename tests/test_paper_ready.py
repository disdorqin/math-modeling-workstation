import json
from pathlib import Path

import pytest

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.experiments import ExperimentRegistry
from mathworkstation.paper_ready import PaperReadyGate


def test_paper_ready_requires_passing_sensitivity_and_approval(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Paper Ready")
    artifacts = ArtifactRegistry(cases)
    data = cases.case_root(case["case_id"]) / "input" / "data" / "uploaded" / "data.csv"
    data.write_text("x,target\n1,2\n", encoding="utf-8")
    data_artifact = artifacts.register_existing(
        case["case_id"], "input/data/uploaded/data.csv", "observed_data", "human"
    )
    experiments = ExperimentRegistry(cases, artifacts)
    experiment = experiments.create(
        case["case_id"], "Comparison", "dataset", data_artifact["artifact_id"], "regression", "target", ["x"], {}, None
    )
    comparison_path = cases.case_root(case["case_id"]) / "experiments" / experiment["experiment_id"] / "results" / "comparison.json"
    diagnostics_path = cases.case_root(case["case_id"]) / "experiments" / experiment["experiment_id"] / "results" / "diagnostics.json"
    comparison_path.write_text("{}", encoding="utf-8")
    diagnostics_path.write_text("{}", encoding="utf-8")
    comparison = experiments.register_result(
        case["case_id"], experiment["experiment_id"], "results/comparison.json", "model_comparison", [data_artifact["artifact_id"]]
    )
    diagnostics = experiments.register_result(
        case["case_id"], experiment["experiment_id"], "results/diagnostics.json", "model_diagnostics", [data_artifact["artifact_id"]]
    )
    experiments.update(
        case["case_id"], experiment["experiment_id"], "SUCCEEDED",
        comparison_artifact_id=comparison["artifact_id"], diagnostics_artifact_id=diagnostics["artifact_id"]
    )
    selection_path = cases.case_root(case["case_id"]) / "results" / "parameters" / "selection.json"
    selection_path.write_text("{}", encoding="utf-8")
    selection = artifacts.register_existing(
        case["case_id"], "results/parameters/selection.json", "model_selection", "human"
    )
    sensitivity_path = cases.case_root(case["case_id"]) / "results" / "diagnostics" / "sensitivity.json"
    sensitivity_path.write_text(json.dumps({"gate": "REVIEW"}), encoding="utf-8")
    sensitivity = artifacts.register_existing(
        case["case_id"], "results/diagnostics/sensitivity.json", "sensitivity_results", "python"
    )
    gate = PaperReadyGate(cases, artifacts, experiments)
    assessment = gate.assess(
        case["case_id"], experiment["experiment_id"], selection["artifact_id"], sensitivity["artifact_id"]
    )
    assert not assessment["eligible"]
    with pytest.raises(ValueError):
        gate.approve(
            case["case_id"], experiment["experiment_id"], selection["artifact_id"], sensitivity["artifact_id"], "human", "approve"
        )

    sensitivity_path.write_text(json.dumps({"gate": "PASS"}), encoding="utf-8")
    sensitivity = artifacts.register_existing(
        case["case_id"], "results/diagnostics/sensitivity.json", "sensitivity_results", "python"
    )
    result = gate.approve(
        case["case_id"], experiment["experiment_id"], selection["artifact_id"], sensitivity["artifact_id"], "human", "evidence checked"
    )
    assert artifacts.get(case["case_id"], result["approval_artifact_id"])["paper_eligible"] is True
    assert experiments.get(case["case_id"], experiment["experiment_id"])["status"] == "PAPER_READY"


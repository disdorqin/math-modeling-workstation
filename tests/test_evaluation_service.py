from pathlib import Path

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.checkpoint_manager import CheckpointManager
from mathworkstation.experiments import ExperimentRegistry
from mathworkstation.memory_manager import MemoryManager
from mathworkstation.run_manager import RunManager
from mathworkstation.selection import ModelSelectionRegistry
from mathworkstation.workflow import NodeStatus
from mathworkstation.workflow_service import WorkflowService


def test_dedicated_model_selection_finishes_human_review(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Selection Service")
    artifacts = ArtifactRegistry(cases)
    source = cases.case_root(case["case_id"]) / "input" / "data" / "uploaded" / "data.csv"
    source.write_text("x,target\n1,2\n", encoding="utf-8")
    data_artifact = artifacts.register_existing(
        case["case_id"], "input/data/uploaded/data.csv", "observed_data", "human"
    )
    experiments = ExperimentRegistry(cases, artifacts)
    experiment = experiments.create(
        case["case_id"], "Comparison", "dataset", data_artifact["artifact_id"], "regression", "target", ["x"], {}, None
    )
    comparison_path = cases.case_root(case["case_id"]) / "experiments" / experiment["experiment_id"] / "results" / "comparison.json"
    comparison_path.write_text("{}", encoding="utf-8")
    comparison = experiments.register_result(
        case["case_id"], experiment["experiment_id"], "results/comparison.json", "model_comparison", [data_artifact["artifact_id"]]
    )
    experiments.update(case["case_id"], experiment["experiment_id"], "SUCCEEDED")
    checkpoints = CheckpointManager(cases)
    controller = checkpoints.load(case["case_id"])
    controller.runtimes["experiments"].status = NodeStatus.SUCCEEDED
    checkpoints.save(case["case_id"], controller, "setup")
    workflow = WorkflowService(cases, RunManager(cases), checkpoints, MemoryManager(cases, artifacts))
    from mathworkstation.evaluation_service import EvaluationService

    service = EvaluationService(
        workflow,
        plans=None,
        evaluation=None,
        sensitivity=None,
        selections=ModelSelectionRegistry(cases, artifacts, experiments),
    )
    result = service.select_model(
        case["case_id"],
        experiment["experiment_id"],
        "linear",
        comparison["artifact_id"],
        "human",
        "evidence reviewed",
    )
    assert result["workflow_node"]["status"] == "SUCCEEDED"
    assert checkpoints.load(case["case_id"]).runtimes["model_selection"].review["approved_by"] == "human"


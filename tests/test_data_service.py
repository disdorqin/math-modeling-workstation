from pathlib import Path

import pandas as pd

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.checkpoint_manager import CheckpointManager
from mathworkstation.data_quality import TabularProfiler
from mathworkstation.data_service import DataService
from mathworkstation.datasets import DatasetKind, DatasetRegistry
from mathworkstation.memory_manager import MemoryManager
from mathworkstation.run_manager import RunManager
from mathworkstation.workflow import NodeStatus
from mathworkstation.workflow_service import WorkflowService


def _service(tmp_path: Path):
    cases = CaseManager(tmp_path / "output")
    artifacts = ArtifactRegistry(cases)
    datasets = DatasetRegistry(cases, artifacts)
    checkpoints = CheckpointManager(cases)
    workflow = WorkflowService(
        cases,
        RunManager(cases),
        checkpoints,
        MemoryManager(cases, artifacts),
    )
    data = DataService(
        artifacts,
        datasets,
        TabularProfiler(cases, artifacts, datasets),
        workflow,
    )
    return cases, datasets, checkpoints, workflow, data


def _complete_input_validation(case_id: str, workflow: WorkflowService) -> None:
    workflow.start_node(case_id, "input_validation")
    workflow.succeed_node(case_id, "input_validation")


def test_clean_dataset_advances_quality_gate(tmp_path: Path) -> None:
    cases, datasets, checkpoints, workflow, data = _service(tmp_path)
    case = cases.create_case("SM", "Clean")
    _complete_input_validation(case["case_id"], workflow)
    source = tmp_path / "clean.csv"
    pd.DataFrame({"x": list(range(30)), "target": [value * 2 for value in range(30)]}).to_csv(source, index=False)
    registered = data.register_uploaded(
        case["case_id"], source, "Clean", DatasetKind.OBSERVED, "human"
    )
    data.complete_registration(case["case_id"])
    workflow.approve_node(case["case_id"], "data_registration", "human")
    result = data.profile_dataset(
        case["case_id"], registered["dataset"]["dataset_id"], target_column="target"
    )
    assert result["workflow_action"] == "continue"
    assert checkpoints.load(case["case_id"]).runtimes["data_quality"].status == NodeStatus.SUCCEEDED


def test_blocked_dataset_prevents_eda_until_retry(tmp_path: Path) -> None:
    cases, datasets, checkpoints, workflow, data = _service(tmp_path)
    case = cases.create_case("SM", "Blocked")
    _complete_input_validation(case["case_id"], workflow)
    source = tmp_path / "blocked.csv"
    pd.DataFrame({"x": [1, 2, 3]}).to_csv(source, index=False)
    registered = data.register_uploaded(
        case["case_id"], source, "Blocked", DatasetKind.OBSERVED, "human"
    )
    data.complete_registration(case["case_id"])
    workflow.approve_node(case["case_id"], "data_registration", "human")
    result = data.profile_dataset(
        case["case_id"], registered["dataset"]["dataset_id"], target_column="missing"
    )
    assert result["profile"]["quality_gate"] == "BLOCK"
    controller = checkpoints.load(case["case_id"])
    assert controller.runtimes["data_quality"].status == NodeStatus.FAILED
    assert controller.runtimes["eda"].status == NodeStatus.BLOCKED
    retry = workflow.retry_node(case["case_id"], "data_quality", "human", "replace invalid dataset")
    assert retry["status"] == NodeStatus.RETRYING.value


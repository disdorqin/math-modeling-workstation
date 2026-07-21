from pathlib import Path

import pandas as pd

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.baseline import BaselineEngine
from mathworkstation.case_manager import CaseManager
from mathworkstation.checkpoint_manager import CheckpointManager
from mathworkstation.data_quality import TabularProfiler
from mathworkstation.datasets import DatasetKind, DatasetRegistry
from mathworkstation.eda import EDAEngine
from mathworkstation.experiments import ExperimentRegistry
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.memory_manager import MemoryManager
from mathworkstation.modeling_service import ModelingService
from mathworkstation.run_manager import RunManager
from mathworkstation.workflow import NodeStatus
from mathworkstation.workflow_service import WorkflowService


def test_modeling_service_commits_eda_and_contains_failure(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Modeling Service")
    source = tmp_path / "data.csv"
    pd.DataFrame({"x": range(30), "target": [value * 2 for value in range(30)]}).to_csv(source, index=False)
    artifacts = ArtifactRegistry(cases)
    artifact = artifacts.ingest_file(case["case_id"], source, "input/data/uploaded", "observed_data")
    datasets = DatasetRegistry(cases, artifacts)
    dataset = datasets.register(
        case["case_id"], "Input", artifact["artifact_id"], DatasetKind.OBSERVED, "uploaded", "human"
    )
    TabularProfiler(cases, artifacts, datasets).profile(case["case_id"], dataset["dataset_id"], "target")
    checkpoints = CheckpointManager(cases)
    controller = checkpoints.load(case["case_id"])
    controller.runtimes["data_quality"].status = NodeStatus.SUCCEEDED
    checkpoints.save(case["case_id"], controller, "test_setup")
    figures = FigureRegistry(cases, artifacts)
    workflow = WorkflowService(cases, RunManager(cases), checkpoints, MemoryManager(cases, artifacts))
    service = ModelingService(
        workflow,
        EDAEngine(cases, artifacts, datasets, figures),
        BaselineEngine(cases, artifacts, datasets, ExperimentRegistry(cases, artifacts), figures),
    )
    eda_result = service.run_eda(case["case_id"], dataset["dataset_id"], "target")
    assert eda_result["succeeded"] is True
    assert checkpoints.load(case["case_id"]).runtimes["eda"].status == NodeStatus.SUCCEEDED

    controller = checkpoints.load(case["case_id"])
    controller.runtimes["model_plan"].status = NodeStatus.SUCCEEDED
    checkpoints.save(case["case_id"], controller, "test_model_plan")
    failed = service.run_baseline(case["case_id"], dataset["dataset_id"], "missing")
    assert failed["succeeded"] is False
    assert checkpoints.load(case["case_id"]).runtimes["baseline"].status == NodeStatus.FAILED


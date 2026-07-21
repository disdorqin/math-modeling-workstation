from pathlib import Path

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.checkpoint_manager import CheckpointManager
from mathworkstation.memory_manager import MemoryManager
from mathworkstation.recovery import RecoveryService
from mathworkstation.workflow import FailureCategory, NodeStatus
from mathworkstation.io_utils import read_json
from mathworkstation.run_manager import RunManager


def _advance_data_registration(workflow) -> None:
    workflow.start("input_validation", "run-input")
    workflow.succeed("input_validation")
    workflow.start("data_registration", "run-data")
    workflow.succeed("data_registration")
    workflow.approve("data_registration", "human")


def test_critical_failure_blocks_and_checkpoint_recovers(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("CM", "Failure")
    checkpoints = CheckpointManager(cases)
    workflow = checkpoints.load(case["case_id"])
    _advance_data_registration(workflow)

    workflow.start("data_quality", "run-quality")
    action = workflow.fail(
        "data_quality",
        FailureCategory.DATA_QUALITY,
        {"message": "target column missing"},
    )
    assert action.action == "review"
    assert workflow.runtimes["eda"].status == NodeStatus.BLOCKED

    checkpoints.save(case["case_id"], workflow, "test_failure")
    restored = checkpoints.load(case["case_id"])
    assert restored.runtimes["data_quality"].status == NodeStatus.NEEDS_REVIEW
    assert restored.runtimes["eda"].status == NodeStatus.BLOCKED


def test_optional_failure_degrades_without_becoming_evidence(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("CM", "Degrade")
    workflow = CheckpointManager(cases).load(case["case_id"])

    workflow.runtimes["experiments"].status = NodeStatus.SUCCEEDED
    workflow.start("supplementary_figure", "run-figure")
    action = workflow.fail(
        "supplementary_figure",
        FailureCategory.OPTIONAL_ARTIFACT,
        {"message": "renderer failed"},
    )
    assert action.action == "degrade"
    assert action.paper_eligible is False
    assert workflow.runtimes["supplementary_figure"].status == NodeStatus.DEGRADED


def test_stale_propagates_to_downstream(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Stale")
    workflow = CheckpointManager(cases).load(case["case_id"])
    workflow.runtimes["data_registration"].status = NodeStatus.SUCCEEDED
    workflow.runtimes["data_quality"].status = NodeStatus.SUCCEEDED
    workflow.runtimes["eda"].status = NodeStatus.SUCCEEDED
    workflow.mark_stale("data_registration", "source data changed")
    assert workflow.runtimes["data_registration"].status == NodeStatus.STALE
    assert workflow.runtimes["data_quality"].status == NodeStatus.STALE
    assert workflow.runtimes["eda"].status == NodeStatus.STALE


def test_interrupted_run_becomes_review_and_builds_resume_brief(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Resume")
    checkpoints = CheckpointManager(cases)
    workflow = checkpoints.load(case["case_id"])
    run = RunManager(cases).start_run(case["case_id"], "input_validation")
    workflow.start("input_validation", run["run_id"])
    checkpoints.save(case["case_id"], workflow, "running")

    artifacts = ArtifactRegistry(cases)
    recovery = RecoveryService(
        cases,
        artifacts,
        checkpoints,
        MemoryManager(cases, artifacts),
    )
    report = recovery.inspect(case["case_id"])
    assert report["interrupted_nodes"] == ["input_validation"]
    assert report["interrupted_run_ids"] == [run["run_id"]]
    assert "Resume Brief" in report["brief"]
    restored = checkpoints.load(case["case_id"])
    assert restored.runtimes["input_validation"].status == NodeStatus.NEEDS_REVIEW
    assert read_json(cases.case_root(case["case_id"]) / "status.json")["active_run_id"] is None
    run_record = read_json(cases.case_root(case["case_id"]) / "runs" / run["run_id"] / "run.json")
    assert run_record["status"] == "INTERRUPTED"

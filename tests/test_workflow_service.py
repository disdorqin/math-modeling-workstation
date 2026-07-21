from pathlib import Path

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.checkpoint_manager import CheckpointManager
from mathworkstation.memory_manager import MemoryManager
from mathworkstation.run_manager import RunManager
from mathworkstation.workflow import FailureCategory, NodeStatus
from mathworkstation.workflow_service import WorkflowService


def make_service(tmp_path: Path):
    cases = CaseManager(tmp_path / "output")
    artifacts = ArtifactRegistry(cases)
    checkpoints = CheckpointManager(cases)
    memory = MemoryManager(cases, artifacts)
    return cases, checkpoints, WorkflowService(cases, RunManager(cases), checkpoints, memory)


def test_service_keeps_run_and_checkpoint_in_sync(tmp_path: Path) -> None:
    cases, checkpoints, service = make_service(tmp_path)
    case = cases.create_case("SM", "Orchestration")
    started = service.start_node(case["case_id"], "input_validation")
    run_id = started["run"]["run_id"]
    assert checkpoints.load(case["case_id"]).runtimes["input_validation"].active_run_id == run_id

    finished = service.succeed_node(case["case_id"], "input_validation")
    assert finished["status"] == NodeStatus.SUCCEEDED.value
    run = (cases.case_root(case["case_id"]) / "runs" / run_id / "run.json").read_text(encoding="utf-8")
    assert '"status": "SUCCEEDED"' in run


def test_service_failure_updates_resume_memory(tmp_path: Path) -> None:
    cases, checkpoints, service = make_service(tmp_path)
    case = cases.create_case("SM", "Failure Memory")
    service.start_node(case["case_id"], "input_validation")
    result = service.fail_node(
        case["case_id"],
        "input_validation",
        FailureCategory.CRITICAL,
        "bad input",
    )
    assert result["action"] == "pause"
    brief = (cases.case_root(case["case_id"]) / ".internal" / "resume_brief.md").read_text(encoding="utf-8")
    assert "input_validation" in brief


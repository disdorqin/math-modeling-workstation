from pathlib import Path

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.checkpoint_manager import CheckpointManager
from mathworkstation.memory_manager import MemoryManager
from mathworkstation.orchestration import ControlledOrchestrator, NodeExecutionRequest, NodeExecutionResult
from mathworkstation.run_manager import RunManager
from mathworkstation.workflow import FailureCategory, NodeStatus
from mathworkstation.workflow_service import WorkflowService


class SuccessExecutor:
    def execute(self, request: NodeExecutionRequest) -> NodeExecutionResult:
        return NodeExecutionResult(True, ("artifact-output",))


class FailureExecutor:
    def execute(self, request: NodeExecutionRequest) -> NodeExecutionResult:
        return NodeExecutionResult(False, failure_category=FailureCategory.CRITICAL, message="failed")


def _orchestrator(tmp_path: Path):
    cases = CaseManager(tmp_path / "output")
    artifacts = ArtifactRegistry(cases)
    checkpoints = CheckpointManager(cases)
    workflow = WorkflowService(
        cases,
        RunManager(cases),
        checkpoints,
        MemoryManager(cases, artifacts),
    )
    return cases, checkpoints, ControlledOrchestrator(workflow)


def test_controlled_orchestrator_commits_success(tmp_path: Path) -> None:
    cases, checkpoints, orchestrator = _orchestrator(tmp_path)
    case = cases.create_case("SM", "Adapter")
    request = NodeExecutionRequest(case["case_id"], "input_validation", None, (), {})
    result = orchestrator.execute(request, SuccessExecutor())
    assert result["result"]["succeeded"] is True
    assert checkpoints.load(case["case_id"]).runtimes["input_validation"].status == NodeStatus.SUCCEEDED


def test_controlled_orchestrator_contains_executor_failure(tmp_path: Path) -> None:
    cases, checkpoints, orchestrator = _orchestrator(tmp_path)
    case = cases.create_case("SM", "Adapter Failure")
    request = NodeExecutionRequest(case["case_id"], "input_validation", None, (), {})
    result = orchestrator.execute(request, FailureExecutor())
    assert result["workflow"]["action"] == "pause"
    assert checkpoints.load(case["case_id"]).runtimes["input_validation"].status == NodeStatus.FAILED


from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from .workflow import FailureCategory
from .workflow_service import WorkflowService


@dataclass(frozen=True)
class NodeExecutionRequest:
    case_id: str
    node_id: str
    session_id: str | None
    input_artifact_ids: tuple[str, ...]
    parameters: dict[str, Any]


@dataclass(frozen=True)
class NodeExecutionResult:
    succeeded: bool
    output_artifact_ids: tuple[str, ...] = ()
    failure_category: FailureCategory | None = None
    message: str = ""


class NodeExecutor(Protocol):
    def execute(self, request: NodeExecutionRequest) -> NodeExecutionResult: ...


class ControlledOrchestrator:
    """Runs an external executor without surrendering workflow ownership."""

    def __init__(self, workflow: WorkflowService) -> None:
        self.workflow = workflow

    def execute(self, request: NodeExecutionRequest, executor: NodeExecutor) -> dict[str, Any]:
        started = self.workflow.start_node(request.case_id, request.node_id, request.session_id)
        try:
            result = executor.execute(request)
        except Exception as error:
            failed = self.workflow.fail_node(
                request.case_id,
                request.node_id,
                FailureCategory.CRITICAL,
                f"executor raised {type(error).__name__}: {error}",
            )
            return {"started": started, "result": None, "workflow": failed}
        if result.succeeded:
            state = self.workflow.succeed_node(request.case_id, request.node_id)
        else:
            category = result.failure_category or FailureCategory.CRITICAL
            state = self.workflow.fail_node(
                request.case_id,
                request.node_id,
                category,
                result.message or "executor reported failure",
            )
        return {
            "started": started,
            "result": {
                "succeeded": result.succeeded,
                "output_artifact_ids": list(result.output_artifact_ids),
                "failure_category": result.failure_category.value if result.failure_category else None,
                "message": result.message,
            },
            "workflow": state,
        }


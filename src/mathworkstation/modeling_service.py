from __future__ import annotations

from typing import Any, Callable

from .baseline import BaselineEngine
from .eda import EDAEngine
from .workflow import FailureCategory
from .workflow_service import WorkflowService


class ModelingService:
    def __init__(
        self,
        workflow: WorkflowService,
        eda: EDAEngine,
        baseline: BaselineEngine,
    ) -> None:
        self.workflow = workflow
        self.eda = eda
        self.baseline = baseline

    def run_eda(
        self,
        case_id: str,
        dataset_id: str,
        target_column: str | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        return self._execute_node(
            case_id,
            "eda",
            session_id,
            lambda run_id: self.eda.run(case_id, dataset_id, target_column, run_id),
        )

    def run_baseline(
        self,
        case_id: str,
        dataset_id: str,
        target_column: str,
        feature_columns: list[str] | None = None,
        task_type: str = "auto",
        test_size: float = 0.25,
        random_seed: int = 42,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        return self._execute_node(
            case_id,
            "baseline",
            session_id,
            lambda run_id: self.baseline.run(
                case_id,
                dataset_id,
                target_column,
                feature_columns,
                task_type,
                test_size,
                random_seed,
                run_id,
            ),
        )

    def _execute_node(
        self,
        case_id: str,
        node_id: str,
        session_id: str | None,
        operation: Callable[[str], dict[str, Any]],
    ) -> dict[str, Any]:
        started = self.workflow.start_node(case_id, node_id, session_id)
        run_id = started["run"]["run_id"]
        try:
            result = operation(run_id)
        except Exception as error:
            failure = self.workflow.fail_node(
                case_id,
                node_id,
                FailureCategory.CRITICAL,
                f"{type(error).__name__}: {error}",
            )
            return {
                "succeeded": False,
                "run_id": run_id,
                "error": {"type": type(error).__name__, "message": str(error)},
                "workflow": failure,
            }
        node = self.workflow.succeed_node(case_id, node_id)
        return {"succeeded": True, "run_id": run_id, "result": result, "workflow_node": node}


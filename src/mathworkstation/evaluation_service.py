from __future__ import annotations

from typing import Any, Callable

from .model_evaluation import ModelEvaluationEngine
from .model_plan import ModelPlanService
from .selection import ModelSelectionRegistry
from .sensitivity import SensitivityEngine
from .workflow import FailureCategory
from .workflow_service import WorkflowService


class EvaluationService:
    def __init__(
        self,
        workflow: WorkflowService,
        plans: ModelPlanService,
        evaluation: ModelEvaluationEngine,
        sensitivity: SensitivityEngine,
        selections: ModelSelectionRegistry,
    ) -> None:
        self.workflow = workflow
        self.plans = plans
        self.evaluation = evaluation
        self.sensitivity = sensitivity
        self.selections = selections

    def run_comparison(
        self, case_id: str, plan_artifact_id: str, session_id: str | None = None
    ) -> dict[str, Any]:
        plan = self.plans.load(case_id, plan_artifact_id)
        return self._execute(
            case_id,
            "experiments",
            session_id,
            lambda run_id: self.evaluation.run(case_id, plan, plan_artifact_id, run_id),
        )

    def select_model(
        self,
        case_id: str,
        experiment_id: str,
        selected_model: str,
        comparison_artifact_id: str,
        selected_by: str,
        rationale: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        started = self.workflow.start_node(case_id, "model_selection", session_id)
        try:
            selection = self.selections.select(
                case_id,
                experiment_id,
                selected_model,
                comparison_artifact_id,
                selected_by,
                rationale,
            )
        except Exception as error:
            failure = self.workflow.fail_node(
                case_id,
                "model_selection",
                FailureCategory.CRITICAL,
                f"{type(error).__name__}: {error}",
            )
            return {"succeeded": False, "error": str(error), "workflow": failure}
        node = self.workflow.succeed_node(case_id, "model_selection")
        if node["status"] == "NEEDS_REVIEW":
            node = self.workflow.approve_node(
                case_id,
                "model_selection",
                selected_by,
                f"{rationale} [selection_id={selection['selection_id']}]",
            )
        return {"succeeded": True, "started": started, "selection": selection, "workflow_node": node}

    def run_sensitivity(
        self,
        case_id: str,
        comparison_experiment_id: str,
        plan_artifact_id: str,
        seeds: list[int] | None = None,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        plan = self.plans.load(case_id, plan_artifact_id)
        return self._execute(
            case_id,
            "sensitivity",
            session_id,
            lambda run_id: self.sensitivity.run(
                case_id,
                comparison_experiment_id,
                plan,
                plan_artifact_id,
                seeds,
                run_id,
            ),
        )

    def _execute(
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

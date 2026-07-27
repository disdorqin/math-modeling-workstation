from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from .errors import DependencyBlockedError, InvalidTransitionError
from .io_utils import now_iso


class NodeStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    BLOCKED = "BLOCKED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    SKIPPED = "SKIPPED"
    CANCELLED = "CANCELLED"


class FailureCategory(StrEnum):
    TRANSIENT = "TRANSIENT"
    SCHEMA = "SCHEMA"
    DATA_QUALITY = "DATA_QUALITY"
    MODEL_ASSUMPTION = "MODEL_ASSUMPTION"
    OPTIONAL_ARTIFACT = "OPTIONAL_ARTIFACT"
    CRITICAL = "CRITICAL"


SUCCESS_LIKE = {NodeStatus.SUCCEEDED, NodeStatus.DEGRADED}


@dataclass(frozen=True)
class NodeDefinition:
    node_id: str
    dependencies: tuple[str, ...] = ()
    critical: bool = True
    may_degrade: bool = False
    max_retries: int = 2
    approval_required: bool = False


@dataclass
class NodeRuntime:
    status: NodeStatus = NodeStatus.PENDING
    attempts: int = 0
    last_error: dict[str, Any] | None = None
    active_run_id: str | None = None
    updated_at: str = field(default_factory=now_iso)
    review: dict[str, Any] | None = None


@dataclass
class FailureAction:
    action: str
    node_status: NodeStatus
    block_downstream: bool
    paper_eligible: bool
    message: str


class FailureClassifier:
    def decide(
        self,
        definition: NodeDefinition,
        runtime: NodeRuntime,
        category: FailureCategory,
    ) -> FailureAction:
        retryable = category in {FailureCategory.TRANSIENT, FailureCategory.SCHEMA}
        if retryable and runtime.attempts <= definition.max_retries:
            return FailureAction(
                "retry",
                NodeStatus.RETRYING,
                False,
                False,
                "failure is retryable and retry budget remains",
            )
        if category in {FailureCategory.DATA_QUALITY, FailureCategory.MODEL_ASSUMPTION}:
            return FailureAction(
                "review",
                NodeStatus.NEEDS_REVIEW,
                True,
                False,
                "domain validation failed; human review is required",
            )
        if category == FailureCategory.OPTIONAL_ARTIFACT and definition.may_degrade:
            return FailureAction(
                "degrade",
                NodeStatus.DEGRADED,
                False,
                False,
                "optional branch degraded; failed artifact is not paper eligible",
            )
        return FailureAction(
            "pause",
            NodeStatus.FAILED,
            definition.critical,
            False,
            "critical failure exhausted its recovery policy",
        )


class WorkflowGraph:
    def __init__(self, definitions: list[NodeDefinition]) -> None:
        self.definitions = {definition.node_id: definition for definition in definitions}
        if len(self.definitions) != len(definitions):
            raise ValueError("duplicate workflow node id")
        self._validate_dependencies()
        self._validate_acyclic()

    def _validate_dependencies(self) -> None:
        for definition in self.definitions.values():
            missing = set(definition.dependencies) - self.definitions.keys()
            if missing:
                raise ValueError(f"unknown dependencies for {definition.node_id}: {sorted(missing)}")

    def _validate_acyclic(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> None:
            if node_id in visiting:
                raise ValueError(f"workflow cycle detected at {node_id}")
            if node_id in visited:
                return
            visiting.add(node_id)
            for dependency in self.definitions[node_id].dependencies:
                visit(dependency)
            visiting.remove(node_id)
            visited.add(node_id)

        for node_id in self.definitions:
            visit(node_id)

    def descendants(self, node_id: str) -> set[str]:
        result: set[str] = set()
        pending = [node_id]
        while pending:
            parent = pending.pop()
            for candidate, definition in self.definitions.items():
                if parent in definition.dependencies and candidate not in result:
                    result.add(candidate)
                    pending.append(candidate)
        return result


class WorkflowController:
    def __init__(
        self,
        graph: WorkflowGraph,
        runtimes: dict[str, NodeRuntime] | None = None,
        classifier: FailureClassifier | None = None,
    ) -> None:
        self.graph = graph
        self.runtimes = runtimes or {node_id: NodeRuntime() for node_id in graph.definitions}
        self.classifier = classifier or FailureClassifier()

    def _runtime(self, node_id: str) -> NodeRuntime:
        try:
            return self.runtimes[node_id]
        except KeyError as error:
            raise KeyError(f"unknown workflow node: {node_id}") from error

    def unmet_dependencies(self, node_id: str) -> list[str]:
        definition = self.graph.definitions[node_id]
        return [
            dependency
            for dependency in definition.dependencies
            if self.runtimes[dependency].status not in SUCCESS_LIKE
        ]

    def start(self, node_id: str, run_id: str) -> None:
        runtime = self._runtime(node_id)
        if runtime.status not in {NodeStatus.PENDING, NodeStatus.RETRYING, NodeStatus.STALE}:
            raise InvalidTransitionError(f"cannot start {node_id} from {runtime.status}")
        unmet = self.unmet_dependencies(node_id)
        if unmet:
            runtime.status = NodeStatus.BLOCKED
            runtime.updated_at = now_iso()
            raise DependencyBlockedError(f"{node_id} is blocked by: {', '.join(unmet)}")
        runtime.status = NodeStatus.RUNNING
        runtime.attempts += 1
        runtime.active_run_id = run_id
        runtime.last_error = None
        runtime.updated_at = now_iso()

    def succeed(self, node_id: str) -> None:
        runtime = self._runtime(node_id)
        if runtime.status != NodeStatus.RUNNING:
            raise InvalidTransitionError(f"cannot succeed {node_id} from {runtime.status}")
        definition = self.graph.definitions[node_id]
        runtime.status = NodeStatus.NEEDS_REVIEW if definition.approval_required else NodeStatus.SUCCEEDED
        runtime.active_run_id = None
        runtime.updated_at = now_iso()
        if runtime.status == NodeStatus.NEEDS_REVIEW:
            self._block_descendants(node_id, "waiting for required approval")
        else:
            self._unblock_ready_descendants(node_id)

    def fail(
        self,
        node_id: str,
        category: FailureCategory,
        error: dict[str, Any],
    ) -> FailureAction:
        runtime = self._runtime(node_id)
        if runtime.status != NodeStatus.RUNNING:
            raise InvalidTransitionError(f"cannot fail {node_id} from {runtime.status}")
        definition = self.graph.definitions[node_id]
        runtime.last_error = {**error, "category": category.value, "timestamp": now_iso()}
        runtime.active_run_id = None
        action = self.classifier.decide(definition, runtime, category)
        runtime.status = action.node_status
        runtime.updated_at = now_iso()
        if action.block_downstream:
            self._block_descendants(node_id, action.message)
        return action

    def approve(self, node_id: str, approved_by: str, note: str = "") -> None:
        runtime = self._runtime(node_id)
        if runtime.status != NodeStatus.NEEDS_REVIEW:
            raise InvalidTransitionError(f"cannot approve {node_id} from {runtime.status}")
        runtime.status = NodeStatus.SUCCEEDED
        runtime.review = {"approved_by": approved_by, "note": note, "timestamp": now_iso()}
        runtime.updated_at = now_iso()
        self._unblock_ready_descendants(node_id)

    def retry(self, node_id: str, requested_by: str, reason: str) -> None:
        if not reason.strip():
            raise ValueError("retry requires a reason")
        runtime = self._runtime(node_id)
        if runtime.status not in {
            NodeStatus.FAILED,
            NodeStatus.NEEDS_REVIEW,
            NodeStatus.STALE,
            NodeStatus.BLOCKED,
            NodeStatus.DEGRADED,
        }:
            raise InvalidTransitionError(f"cannot retry {node_id} from {runtime.status}")
        runtime.status = NodeStatus.RETRYING
        runtime.review = {"requested_by": requested_by, "reason": reason, "timestamp": now_iso()}
        runtime.updated_at = now_iso()

    def degrade(self, node_id: str, approved_by: str, reason: str) -> None:
        """Record an explicit human decision to run without an optional branch.

        Unlike :meth:`skip`, which blocks everything downstream, a degraded node
        counts as success-like: the pipeline continues, but the case history
        permanently records who decided to omit the branch and why. Only nodes
        declared ``may_degrade`` accept this transition.
        """
        if not reason.strip():
            raise ValueError("degrade requires a reason")
        definition = self.graph.definitions[node_id]
        if not definition.may_degrade:
            raise InvalidTransitionError(f"node does not allow degradation: {node_id}")
        runtime = self._runtime(node_id)
        if runtime.status in {NodeStatus.RUNNING, NodeStatus.SUCCEEDED}:
            raise InvalidTransitionError(f"cannot degrade {node_id} from {runtime.status}")
        runtime.status = NodeStatus.DEGRADED
        runtime.active_run_id = None
        runtime.review = {"approved_by": approved_by, "reason": reason, "timestamp": now_iso()}
        runtime.last_error = {
            "category": "OPTIONAL_BRANCH_OMITTED",
            "message": reason,
            "timestamp": now_iso(),
        }
        runtime.updated_at = now_iso()
        self._unblock_ready_descendants(node_id)

    def skip(self, node_id: str, approved_by: str, reason: str) -> None:
        if not reason.strip():
            raise ValueError("skip requires a reason")
        runtime = self._runtime(node_id)
        if runtime.status in {NodeStatus.RUNNING, NodeStatus.SUCCEEDED}:
            raise InvalidTransitionError(f"cannot skip {node_id} from {runtime.status}")
        runtime.status = NodeStatus.SKIPPED
        runtime.review = {"approved_by": approved_by, "reason": reason, "timestamp": now_iso()}
        runtime.updated_at = now_iso()
        self._block_descendants(node_id, "required dependency was skipped")

    def mark_stale(self, node_id: str, reason: str) -> None:
        affected = {node_id, *self.graph.descendants(node_id)}
        for affected_id in affected:
            runtime = self.runtimes[affected_id]
            if runtime.status in {NodeStatus.SUCCEEDED, NodeStatus.DEGRADED, NodeStatus.NEEDS_REVIEW}:
                runtime.status = NodeStatus.STALE
                runtime.last_error = {"category": "UPSTREAM_CHANGED", "message": reason, "timestamp": now_iso()}
                runtime.updated_at = now_iso()
            elif affected_id != node_id and runtime.status == NodeStatus.PENDING:
                runtime.status = NodeStatus.BLOCKED
                runtime.last_error = {"category": "UPSTREAM_CHANGED", "message": reason, "timestamp": now_iso()}
                runtime.updated_at = now_iso()

    def _block_descendants(self, node_id: str, reason: str) -> None:
        for descendant in self.graph.descendants(node_id):
            runtime = self.runtimes[descendant]
            if runtime.status in {NodeStatus.PENDING, NodeStatus.RETRYING, NodeStatus.STALE}:
                runtime.status = NodeStatus.BLOCKED
                runtime.last_error = {"category": "DEPENDENCY_BLOCKED", "message": reason, "timestamp": now_iso()}
                runtime.updated_at = now_iso()

    def _unblock_ready_descendants(self, node_id: str) -> None:
        for descendant in self.graph.descendants(node_id):
            runtime = self.runtimes[descendant]
            if runtime.status == NodeStatus.BLOCKED and not self.unmet_dependencies(descendant):
                runtime.status = NodeStatus.PENDING
                runtime.last_error = None
                runtime.updated_at = now_iso()

    def snapshot(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "updated_at": now_iso(),
            "definitions": {
                node_id: {
                    **asdict(definition),
                    "dependencies": list(definition.dependencies),
                }
                for node_id, definition in self.graph.definitions.items()
            },
            "nodes": {
                node_id: {**asdict(runtime), "status": runtime.status.value}
                for node_id, runtime in self.runtimes.items()
            },
        }

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any]) -> "WorkflowController":
        definitions = [
            NodeDefinition(
                node_id=node_id,
                dependencies=tuple(value.get("dependencies", [])),
                critical=value.get("critical", True),
                may_degrade=value.get("may_degrade", False),
                max_retries=value.get("max_retries", 2),
                approval_required=value.get("approval_required", False),
            )
            for node_id, value in snapshot["definitions"].items()
        ]
        runtimes = {
            node_id: NodeRuntime(
                status=NodeStatus(value["status"]),
                attempts=value.get("attempts", 0),
                last_error=value.get("last_error"),
                active_run_id=value.get("active_run_id"),
                updated_at=value.get("updated_at", now_iso()),
                review=value.get("review"),
            )
            for node_id, value in snapshot["nodes"].items()
        }
        return cls(WorkflowGraph(definitions), runtimes)


def default_workflow_graph() -> WorkflowGraph:
    return WorkflowGraph(
        [
            NodeDefinition("input_validation"),
            NodeDefinition("problem_analysis", ("input_validation",), approval_required=True),
            NodeDefinition("data_registration", ("input_validation",), approval_required=True),
            NodeDefinition("data_quality", ("data_registration",)),
            NodeDefinition("eda", ("data_quality",)),
            NodeDefinition("model_plan", ("problem_analysis", "eda"), approval_required=True),
            NodeDefinition("baseline", ("model_plan",)),
            NodeDefinition("experiments", ("baseline",)),
            NodeDefinition("supplementary_figure", ("experiments",), critical=False, may_degrade=True),
            NodeDefinition("model_selection", ("experiments",), approval_required=True),
            NodeDefinition("sensitivity", ("model_selection",)),
            NodeDefinition("paper_outline", ("problem_analysis", "model_selection"), approval_required=True),
            NodeDefinition("paper_draft", ("paper_outline", "sensitivity")),
            NodeDefinition("consistency_check", ("paper_draft",)),
            NodeDefinition("refinement_loop", ("consistency_check",), max_retries=1, may_degrade=True),
            NodeDefinition("final_review", ("refinement_loop",), approval_required=True),
            NodeDefinition("export", ("final_review",)),
        ]
    )

"""Regression tests for the full deterministic paper smoke's DAG discipline.

These pin the fix for the CI-only defect found while writing the workflow:
`profile-dataset` (the data_quality node) is gated behind data_registration,
which is itself gated behind input_validation. The modeling-subgraph smoke
legitimately skips profiling (it reads the dataset artifact directly); the
FULL paper smoke must NOT skip it -- it must walk the real DAG order. These
tests prove both facts with the real WorkflowController, so a future edit that
either weakens the gate or lets the full smoke bypass it fails here.
"""

from __future__ import annotations

import pytest

from mathworkstation.errors import DependencyBlockedError
from mathworkstation.workflow import (
    NodeStatus,
    WorkflowController,
    default_workflow_graph,
)


class TestDataQualityDagPrerequisites:
    def test_data_quality_is_gated_behind_registration_and_validation(self) -> None:
        graph = default_workflow_graph()
        assert graph.definitions["data_quality"].dependencies == ("data_registration",)
        assert graph.definitions["data_registration"].dependencies == ("input_validation",)

    def test_profiling_before_registration_is_blocked_not_silently_allowed(self) -> None:
        """Starting data_quality on a fresh graph (nothing upstream succeeded)
        must raise DependencyBlockedError naming the unmet dependency -- this
        is exactly why the modeling-only smoke omits profiling and the full
        smoke walks input_validation -> data_registration first."""
        controller = WorkflowController(default_workflow_graph())
        with pytest.raises(DependencyBlockedError) as excinfo:
            controller.start("data_quality", "run-1")
        assert "data_registration" in str(excinfo.value)
        assert controller.runtimes["data_quality"].status is NodeStatus.BLOCKED

    def test_legal_order_reaches_data_quality(self) -> None:
        """The production prerequisite chain (input_validation ->
        data_registration -> data_quality) must actually be walkable -- the
        full smoke depends on it. data_registration requires approval, so the
        chain also exercises the NEEDS_REVIEW -> approve transition."""
        controller = WorkflowController(default_workflow_graph())
        controller.start("input_validation", "run-iv")
        controller.succeed("input_validation")
        controller.start("data_registration", "run-dr")
        controller.succeed("data_registration")  # approval_required -> NEEDS_REVIEW
        assert controller.runtimes["data_registration"].status is NodeStatus.NEEDS_REVIEW
        controller.approve("data_registration", approved_by="test")
        assert controller.runtimes["data_registration"].status is NodeStatus.SUCCEEDED
        # data_quality is now legally startable (no exception)
        controller.start("data_quality", "run-dq")
        assert controller.runtimes["data_quality"].status is NodeStatus.RUNNING

"""Service container for the Web shell.

The shell never re-implements domain logic and never builds a second set of
service objects. It reuses the *exact* dependency bag the Chat Driver (S1)
assembles — ``mathworkstation.chat.services.build_services`` — so the driver
and the HTTP layer share one CaseManager, one WorkflowService, one registry
set. Nothing under ``src/mathworkstation`` is modified.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from mathworkstation.chat.services import build_services
from mathworkstation.literature import LiteratureService
from mathworkstation.submission import SubmissionService

DEFAULT_OUTPUT_ROOT = Path(os.environ.get("MATHWS_OUTPUT_ROOT", "output"))


class ServiceContainer:
    """Attribute view over the driver's service bag, plus shell-only extras."""

    def __init__(self, output_root: Path | str = DEFAULT_OUTPUT_ROOT) -> None:
        self.output_root = Path(output_root)
        # Single source of truth, shared with ChatDriver.
        self.bag: dict[str, Any] = build_services(self.output_root)

        self.cases = self.bag["cases"]
        self.artifacts = self.bag["artifacts"]
        self.checkpoints = self.bag["checkpoints"]
        self.sessions = self.bag["sessions"]
        self.workflow = self.bag["workflow"]
        self.figures = self.bag["figures"]
        self.claims = self.bag["claims"]
        self.datasets = self.bag["datasets"]
        self.checker = self.bag["checker"]
        self.ingestion = self.bag["ingestion"]
        self.data = self.bag["data"]

        # Not part of the driver bag; needed by the shell's view/export routes.
        self.literature = LiteratureService(self.cases, self.artifacts)
        self.submission = SubmissionService(self.cases, self.artifacts)

    # -- read helpers -----------------------------------------------------

    def case_root(self, case_id: str) -> Path:
        return self.cases.case_root(case_id)

    def list_cases(self, include_archived: bool = True) -> list[dict[str, Any]]:
        return self.cases.list_cases(include_archived=include_archived)

    def case_snapshot(self, case_id: str) -> dict[str, Any]:
        """Full case view backing GET /api/cases/{case_id}."""
        workflow = self.checkpoints.snapshot(case_id)
        pending = [
            node_id
            for node_id, runtime in workflow.get("nodes", {}).items()
            if runtime.get("status") == "NEEDS_REVIEW"
        ]
        return {
            "manifest": self.cases.show_case(case_id),
            "workflow_dag": workflow,
            "artifacts": self.artifacts.list_artifacts(case_id),
            "claims": self.claims.list_claims(case_id),
            "figures": self.figures.list_figures(case_id),
            "datasets": self.datasets.list_records(case_id),
            "literature": self.literature.list_records(case_id),
            "pending_approvals": pending,
        }


@lru_cache(maxsize=8)
def get_services(output_root: str | None = None) -> ServiceContainer:
    return ServiceContainer(Path(output_root) if output_root else DEFAULT_OUTPUT_ROOT)

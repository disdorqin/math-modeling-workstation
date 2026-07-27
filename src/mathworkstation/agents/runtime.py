"""Entry point that assembles the roster, the adjudicator, and the graph."""

from __future__ import annotations

from typing import Any

from ..artifact_registry import ArtifactRegistry
from ..case_manager import CaseManager
from ..claims import ClaimRegistry
from ..data_quality import TabularProfiler
from ..data_service import DataService
from ..datasets import DatasetRegistry
from ..eda import EDAEngine
from ..figure_registry import FigureRegistry
from ..io_utils import atomic_write_json
from ..paper_consistency import PaperConsistencyChecker
from ..workflow_service import WorkflowService
from .adjudicator import Adjudicator
from .contracts import WorkstationState
from .graph import langgraph_available, run
from .roster import build_default_roster


class AgentPipeline:
    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        datasets: DatasetRegistry,
        figures: FigureRegistry,
        claims: ClaimRegistry,
        workflow: WorkflowService,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.datasets = datasets
        self.figures = figures
        self.claims = claims
        self.workflow = workflow

    def run(
        self,
        case_id: str,
        session_id: str | None = None,
        dataset_id: str | None = None,
        target_column: str | None = None,
        goal: str = "complete the modeling case",
        prefer_langgraph: bool = True,
    ) -> dict[str, Any]:
        profiler = TabularProfiler(self.cases, self.artifacts, self.datasets)
        data = DataService(self.artifacts, self.datasets, profiler, self.workflow)
        eda = EDAEngine(self.cases, self.artifacts, self.datasets, self.figures)
        checker = PaperConsistencyChecker(self.cases, self.artifacts, self.claims, self.figures)

        agents = build_default_roster(
            data=data,
            eda=eda,
            cases=self.cases,
            artifacts=self.artifacts,
            claims=self.claims,
            figures=self.figures,
            checker=checker,
        )
        adjudicator = Adjudicator(self.cases, self.artifacts, self.claims, self.figures)

        state: WorkstationState = {
            "case_id": case_id,
            "session_id": session_id,
            "dataset_id": dataset_id,
            "target_column": target_column,
            "goal": goal,
            "reports": [],
            "verdicts": [],
            "accepted": [],
            "blocked": [],
            "halted": False,
            "halt_reason": "",
        }
        final, runtime = run(agents, adjudicator, state, prefer_langgraph=prefer_langgraph)

        summary = {
            "schema_version": 1,
            "case_id": case_id,
            "runtime": runtime,
            "langgraph_available": langgraph_available(),
            "agents": [agent.name for agent in agents],
            "halted": bool(final.get("halted")),
            "halt_reason": final.get("halt_reason", ""),
            "accepted_count": len(final.get("accepted", [])),
            "verdict_counts": _counts(final.get("verdicts", [])),
            "accepted": final.get("accepted", []),
            "reports": final.get("reports", []),
        }
        path = self.cases.case_root(case_id) / "agents" / "run_summary.json"
        atomic_write_json(path, summary)
        artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(self.cases.case_root(case_id)).as_posix(),
            "agent_run_summary",
            "python",
        )
        return {**summary, "summary_artifact_id": artifact["artifact_id"]}


def _counts(verdicts: list[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for verdict in verdicts:
        result[verdict["status"]] = result.get(verdict["status"], 0) + 1
    return result

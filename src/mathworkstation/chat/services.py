"""Service assembly for the web chat driver.

Bundles the existing workstation services exactly as the Streamlit console does
(``ui_app._services``) so the chat layer talks to the same registries, state
machine, and gates — never a second implementation. Anything new added here must
be a thin composition of existing services, not a parallel store.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from mathworkstation.cli import _load_env_file

from ..artifact_registry import ArtifactRegistry
from ..case_manager import CaseManager
from ..checkpoint_manager import CheckpointManager
from ..claims import ClaimRegistry
from ..data_quality import TabularProfiler
from ..data_service import DataService
from ..datasets import DatasetRegistry
from ..figure_registry import FigureRegistry
from ..memory_manager import MemoryManager
from ..paper_consistency import PaperConsistencyChecker
from ..problem_ingestion import ProblemIngestionService
from ..run_manager import RunManager
from ..session_manager import SessionManager
from ..workflow_service import WorkflowService


def build_services(output_root: str | Path = "output") -> dict[str, Any]:
    """Compose the existing services into a single dependency bag for the chat layer."""
    _load_env_file(Path(".env.local"))
    cases = CaseManager(output_root)
    artifacts = ArtifactRegistry(cases)
    checkpoints = CheckpointManager(cases)
    memory = MemoryManager(cases, artifacts)
    sessions = SessionManager(cases)
    workflow = WorkflowService(cases, RunManager(cases), checkpoints, memory)
    figures = FigureRegistry(cases, artifacts)
    datasets = DatasetRegistry(cases, artifacts)
    claims = ClaimRegistry(cases, artifacts, datasets)
    return {
        "cases": cases,
        "artifacts": artifacts,
        "checkpoints": checkpoints,
        "sessions": sessions,
        "workflow": workflow,
        "figures": figures,
        "claims": claims,
        "datasets": datasets,
        "checker": PaperConsistencyChecker(cases, artifacts, claims, figures),
        "ingestion": ProblemIngestionService(cases, artifacts),
        "data": DataService(artifacts, datasets, TabularProfiler(cases, artifacts, datasets), workflow),
    }

"""M2 — contest-grade, evidence-bounded paper intelligence layer.

Public surface. The layer is provider-neutral (see :mod:`provider`) and ships a
deterministic :class:`FakeProvider` so the whole pipeline runs in CI without an
API key. Every numeric claim in the produced paper is anchored to a registered
evidence artifact; the :class:`EvidenceVerifier` and :class:`ScientificReviewer`
enforce this and the quality :data:`rubric.THRESHOLD`.
"""

from .provider import Provider, FakeProvider, OpenAICompatibleProvider, get_provider
from .context import M2Context, DatasetDescriptor, EvidenceItem
from .paper import Paper, Section, Paragraph, Equation, Figure, Table
from .registry import SymbolRegistry
from .rubric import score_paper, THRESHOLD, RubricResult
from .pipeline import run_pipeline, pipeline_summary
from .benchmark import run_benchmark, build_experiment_specs, BenchmarkResult
from .agents import (
    Agent,
    PaperArchitect,
    ProblemAnalyst,
    ModelArchitect,
    ExperimentPlanner,
    ControlledCodeExecutor,
    VisualDesigner,
    EvidenceBoundedWriter,
    EvidenceVerifier,
    ScientificReviewer,
    RevisionLoop,
)

__all__ = [
    "Provider", "FakeProvider", "OpenAICompatibleProvider", "get_provider",
    "M2Context", "DatasetDescriptor", "EvidenceItem",
    "Paper", "Section", "Paragraph", "Equation", "Figure", "Table",
    "SymbolRegistry", "score_paper", "THRESHOLD", "RubricResult",
    "run_pipeline", "pipeline_summary", "run_benchmark",
    "build_experiment_specs", "BenchmarkResult",
    "Agent", "PaperArchitect", "ProblemAnalyst", "ModelArchitect",
    "ExperimentPlanner", "ControlledCodeExecutor", "VisualDesigner",
    "EvidenceBoundedWriter", "EvidenceVerifier", "ScientificReviewer",
    "RevisionLoop",
]

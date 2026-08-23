"""M2 orchestration: runs B1-B11 in dependency order on a shared context.

The pipeline is deterministic given (dataset, provider, experiment_specs). It
never weakens M1: it does not touch the M1 agent roster or runtimes, and it
produces a paper whose every numeric claim is evidence-anchored.
"""
from __future__ import annotations

from typing import Any, Dict, List

from .agents import (
    ControlledCodeExecutor,
    ExperimentPlanner,
    EvidenceBoundedWriter,
    EvidenceVerifier,
    ModelArchitect,
    PaperArchitect,
    ProblemAnalyst,
    RevisionLoop,
    ScientificReviewer,
    VisualDesigner,
)
from .context import M2Context


def run_pipeline(
    ctx: M2Context,
    experiment_specs: List[Dict[str, str]],
    figures_dir: str | None = None,
    max_revision_iters: int = 4,
) -> M2Context:
    steps = [
        ("B6", PaperArchitect()),
        ("B1", ProblemAnalyst()),
        ("B2", ModelArchitect()),
        ("B3", ExperimentPlanner()),
        ("B4", ControlledCodeExecutor()),
        ("B8", VisualDesigner()),
        ("B9", EvidenceBoundedWriter()),
        ("B5", EvidenceVerifier()),
        ("B10", ScientificReviewer()),
        ("B11", RevisionLoop()),
    ]
    for label, agent in steps:
        if label == "B4":
            agent.run(ctx, specs=experiment_specs)
        elif label == "B8":
            agent.run(ctx, figures_dir=figures_dir)
        elif label == "B11":
            agent.run(ctx, max_iters=max_revision_iters)
        else:
            agent.run(ctx)
    return ctx


def pipeline_summary(ctx: M2Context) -> Dict[str, Any]:
    return {
        "title": ctx.paper.title,
        "candidates": ctx.paper.candidate_families,
        "counts": {
            "figures": ctx.paper.count_figures(),
            "tables": ctx.paper.count_tables(),
            "equations": ctx.paper.count_equations(),
            "candidates": ctx.paper.count_candidates(),
        },
        "evidence_ids": sorted(ctx.evidence.keys()),
        "verifier": ctx.runs.get("B5-evidence-verifier", {}),
        "reviewer": ctx.runs.get("B10-scientific-reviewer", {}),
        "revision": ctx.runs.get("B11-revision-loop", {}),
    }

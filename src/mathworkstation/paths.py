from __future__ import annotations

from pathlib import Path

from .errors import PathViolationError


CASE_DIRECTORIES = (
    ".internal/checkpoints/history",
    "input/problem/original",
    "input/problem/extracted",
    "input/data/uploaded",
    "input/data/external",
    "input/requirements",
    "evidence/sources",
    "evidence/raw_responses",
    "evidence/snapshots",
    "evidence/provenance",
    "data/raw",
    "data/intermediate",
    "data/cleaned",
    "data/features",
    "data/splits",
    "data/dictionaries",
    "analysis",
    "code/models",
    "experiments",
    "figures/draft",
    "figures/final",
    "figures/metadata",
    "tables/draft",
    "tables/final",
    "tables/metadata",
    "results/metrics",
    "results/predictions",
    "results/parameters",
    "results/diagnostics",
    "results/claims",
    "paper/outline",
    "paper/sections",
    "paper/draft",
    "paper/final",
    "paper/markdown",
    "paper/latex",
    "paper/references",
    "paper/versions",
    "paper/patches",
    "refinement/stages",
    "review/structural",
    "review/statistical",
    "review/reproducibility",
    "review/consistency",
    "review/citation",
    "memory",
    "sessions",
    "runs",
    "export/submission_package",
    "export/source_package",
)


def resolve_within(root: Path, relative: str | Path) -> Path:
    root_resolved = root.resolve()
    target = (root_resolved / relative).resolve()
    if not target.is_relative_to(root_resolved):
        raise PathViolationError(f"path escapes case root: {relative}")
    return target


def create_case_tree(case_root: Path) -> None:
    for directory in CASE_DIRECTORIES:
        resolve_within(case_root, directory).mkdir(parents=True, exist_ok=True)

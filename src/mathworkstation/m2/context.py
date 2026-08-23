"""Shared execution context for the M2 paper layer.

``M2Context`` carries everything the B1-B11 agents need: the dataset descriptor,
the in-memory evidence registry (the *only* source of numbers), the structured
:class:`Paper`, the :class:`SymbolRegistry`, and the active :class:`Provider`.
Agents read evidence and write to the paper; they never invent numbers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .paper import Paper
from .provider import Provider
from .registry import SymbolRegistry


@dataclass
class EvidenceItem:
    artifact_id: str
    kind: str  # "dataset" | "metrics" | "experiment_plan" | "model_plan" | "problem"
    text: str = ""
    payload: dict = field(default_factory=dict)


@dataclass
class DatasetDescriptor:
    name: str
    target: str
    features: List[str] = field(default_factory=list)
    n_rows: int = 0
    n_cols: int = 0
    source: str = ""


@dataclass
class M2Context:
    dataset: DatasetDescriptor
    provider: Provider
    paper: Paper = field(default_factory=Paper)
    symbols: SymbolRegistry = field(default_factory=SymbolRegistry)
    evidence: Dict[str, EvidenceItem] = field(default_factory=dict)
    runs: Dict[str, Any] = field(default_factory=dict)  # agent run logs

    def register_evidence(self, item: EvidenceItem) -> EvidenceItem:
        if item.artifact_id in self.evidence:
            raise ValueError(f"duplicate evidence id: {item.artifact_id}")
        self.evidence[item.artifact_id] = item
        return item

    def get_evidence(self, artifact_id: str) -> EvidenceItem:
        ev = self.evidence.get(artifact_id)
        if ev is None:
            raise KeyError(f"unknown evidence id: {artifact_id}")
        return ev

    def log(self, agent: str, data: Any) -> None:
        self.runs[agent] = data

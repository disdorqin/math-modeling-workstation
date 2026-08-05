"""Hierarchical Mathematical Modeling Library (HMML) — fused from MM-Agent.

Source: `usail-hkust/LLM-MM-Agent` (NeurIPS 2025, arXiv 2505.14148),
``MMAgent/HMML/HMML.json`` + ``MMAgent/agent/retrieve_method.py``.
License: CC BY-NC 4.0 (data), see ``config/hmml.json`` header for attribution.

HMML is a tri-level knowledge hierarchy:
  Domains (5) → Subdomains → Method Nodes (97)
each leaf carrying a ``<modeling_method>/<core_idea>/<application>``
description. MM-Agent retrieves modelling strategies through an
actor-critic mechanism: a scorer grades sibling methods per level; a leaf's
final score is a weighted blend of its own score and its ancestors' average.

``MethodScorer`` and ``MethodRetriever`` reproduce the original algorithm
one-to-one (parent_weight/child_weight default 0.5/0.5). Two score functions
are provided:

* ``lexical`` — deterministic token-overlap relevance, an offline stand-in
  for MM-Agent's embedding scorer (torch + transformers are not project
  dependencies; behaviour is deterministic so FakeProvider pipelines stay
  reproducible).
* ``llm`` — the workstation's :class:`StructuredLLM` acts as critic,
  reproducing the five-dimension ``METHOD_CRITIQUE_PROMPT`` (Assumptions /
  Structure / Variables / Dynamics / Solvability, 1..5, mean = method score).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable

from pydantic import BaseModel, ConfigDict, Field

from .io_utils import read_json

#: Default blend weights from MM-Agent's MethodScorer.
PARENT_WEIGHT = 0.5
CHILD_WEIGHT = 0.5

#: A score_func maps candidate methods to per-method dicts, exactly like
#: MM-Agent's ``EmbeddingScorer.score_method`` / ``llm_score_method``:
#: ``[{"method_index": i, "score": float}]``.
ScoreFunc = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]


class HMMLCritiqueScores(BaseModel):
    """Five evaluation dimensions from MM-Agent's METHOD_CRITIQUE_PROMPT."""

    model_config = ConfigDict(extra="forbid")

    Assumptions: float = Field(ge=1, le=5)
    Structure: float = Field(ge=1, le=5)
    Variables: float = Field(ge=1, le=5)
    Dynamics: float = Field(ge=1, le=5)
    Solvability: float = Field(ge=1, le=5)


class HMMLCritiqueItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method_index: int = Field(ge=1)
    scores: HMMLCritiqueScores


class HMMLCritiqueProposal(BaseModel):
    """Structured critic output (JSON), mirroring the prompt's output example."""

    model_config = ConfigDict(extra="forbid")

    methods: list[HMMLCritiqueItem] = Field(min_length=1)


class HMMLMethodLibrary:
    """Load and navigate the HMML tri-level tree from ``config/hmml.json``."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        if config_path is None:
            config_path = Path(__file__).resolve().parents[2] / "config" / "hmml.json"
        self.config_path = Path(config_path)
        self.tree = read_json(self.config_path)
        self._validate()

    def _validate(self) -> None:
        if not isinstance(self.tree, list) or not self.tree:
            raise ValueError(f"HMML config {self.config_path} must be a non-empty JSON list")
        for node in self.tree:
            if "method_class" not in node:
                raise ValueError("HMML top-level entries must have method_class")

    @property
    def domains(self) -> list[str]:
        return [node["method_class"] for node in self.tree]

    @property
    def method_count(self) -> int:
        return sum(1 for _ in self.iter_methods())

    def iter_methods(self):
        """Yield every leaf method node (with ``method`` + ``description``)."""

        def walk(node: dict[str, Any]):
            if "method" in node:
                yield node
            for child in node.get("children", []):
                yield from walk(child)

        for top in self.tree:
            yield from walk(top)

    def leaf_methods(self) -> list[dict[str, Any]]:
        return list(self.iter_methods())


class MethodScorer:
    """Hierarchical method scoring, one-to-one with MM-Agent's MethodScorer.

    ``score_func`` is already bound to the problem description (partial), and
    grades the children of every non-leaf node. A leaf's final score blends
    its own child score with the running average of its ancestors:
    ``final = parent_avg * parent_weight + child_score * child_weight``.
    """

    def __init__(self, score_func: ScoreFunc, parent_weight: float = PARENT_WEIGHT, child_weight: float = CHILD_WEIGHT) -> None:
        self.parent_weight = parent_weight
        self.child_weight = child_weight
        self.score_func = score_func
        self.leaves: list[dict[str, Any]] = []

    def process(self, data: list[dict[str, Any]]) -> list[dict[str, Any]]:
        self.leaves = []
        for root_node in data:
            self._process_node(root_node, parent_scores=[])
        for root_node in data:
            self._collect_leaves(root_node)
        return self.leaves

    def _process_node(self, node: dict[str, Any], parent_scores: list[float]) -> None:
        children = node.get("children", [])
        if not children:
            return
        first_child = children[0]
        if "method_class" in first_child:
            # Non-leaf level: score the subdomains, then recurse carrying this
            # level's score upward as a parent score for the leaves.
            input_for_llm = [{"method": child["method_class"], "description": child.get("description", "")} for child in children]
            llm_result = self.score_func(input_for_llm)
            for idx, child in enumerate(children):
                child["score"] = llm_result[idx]["score"] if idx < len(llm_result) else 0
            current_score = node.get("score")
            new_parent = list(parent_scores)
            if current_score is not None:
                new_parent.append(current_score)
            for child in children:
                self._process_node(child, new_parent)
        else:
            # Leaf level: score the methods, blend with ancestor average.
            input_for_llm = [{"method": child["method"], "description": child.get("description", "")} for child in children]
            llm_result = self.score_func(input_for_llm)
            for idx, child in enumerate(children):
                child_score = llm_result[idx]["score"] if idx < len(llm_result) else 0
                child["score"] = child_score
                parent_avg = sum(parent_scores) / len(parent_scores) if parent_scores else 0
                final_score = parent_avg * self.parent_weight + child_score * self.child_weight
                child["final_score"] = final_score

    def _collect_leaves(self, node: dict[str, Any]) -> None:
        if "children" in node and node["children"]:
            for child in node["children"]:
                self._collect_leaves(child)
        else:
            if "final_score" in node:
                self.leaves.append(
                    {
                        "method": node["method"],
                        "description": node.get("description", ""),
                        "score": node["final_score"],
                    }
                )


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def lexical_score(methods: list[dict[str, Any]], problem: str = "") -> list[dict[str, Any]]:
    """Deterministic token-overlap scorer (offline stand-in for embeddings).

    Signature mirrors ``EmbeddingScorer.score_method``: returns
    ``[{"method_index": i, "score": ...}]``. Relevance = fraction of a
    method's tokens (name + description) present in the problem's token bag.
    """
    problem_tokens = _tokenize(problem) if problem else set()
    result: list[dict[str, Any]] = []
    for index, method in enumerate(methods, start=1):
        if not problem_tokens:
            result.append({"method_index": index, "score": 0.0})
            continue
        method_tokens = _tokenize(f"{method.get('method', '')} {method.get('description', '')}")
        if not method_tokens:
            result.append({"method_index": index, "score": 0.0})
            continue
        overlap = len(method_tokens & problem_tokens)
        result.append({"method_index": index, "score": overlap / len(method_tokens)})
    return result


def llm_score_method(llm: Any, case_id: str, session_id: str, problem_description: str) -> ScoreFunc:
    """Build the critic score_func (MM-Agent ``llm_score_method``).

    Each candidate is scored on the five METHOD_CRITIQUE_PROMPT dimensions
    (1..5) by the workstation's StructuredLLM; the method score is the mean.
    """

    def _score(methods: list[dict[str, Any]]) -> list[dict[str, Any]]:
        methods_str = "\n".join(f"{i + 1}. {m['method']} {m.get('description', '')}" for i, m in enumerate(methods))
        variables = {"problem_description": problem_description, "methods": methods_str}
        proposal, _ = llm.json_call(
            case_id,
            session_id,
            "hmml_method_retrieval",
            "hmml_method_critique",
            variables,
            HMMLCritiqueProposal,
            [],
            max_tokens=3000,
        )
        by_index = {item.method_index: item for item in proposal.methods}
        result: list[dict[str, Any]] = []
        for index, _m in enumerate(methods, start=1):
            item = by_index.get(index)
            if item is None:
                result.append({"method_index": index, "score": 0.0})
                continue
            values = list(item.scores.model_dump().values())
            result.append({"method_index": index, "score": sum(values) / len(values)})
        return result

    return _score


class MethodRetriever:
    """Top-k HMML method retrieval (MM-Agent ``retrieve_meethods``)."""

    def __init__(
        self,
        library: HMMLMethodLibrary | None = None,
        score_func: str = "lexical",
        llm: Any = None,
        case_id: str = "",
        session_id: str = "",
        top_k: int = 6,
    ) -> None:
        self.library = library or HMMLMethodLibrary()
        self.score_func_name = score_func
        self.llm = llm
        self.case_id = case_id
        self.session_id = session_id
        self.top_k = top_k

    def _score_func(self, problem_description: str) -> ScoreFunc:
        if self.score_func_name == "llm":
            if self.llm is None:
                raise ValueError("HMML llm scorer requires a StructuredLLM instance (pass llm=)")
            return llm_score_method(self.llm, self.case_id, self.session_id, problem_description)
        return lambda methods: lexical_score(methods, problem_description)

    def retrieve(self, problem_description: str, top_k: int | None = None) -> list[dict[str, Any]]:
        """Return the top-k leaf methods sorted by descending final score."""
        if not problem_description:
            return []
        limit = top_k if top_k is not None else self.top_k
        score_func = self._score_func(problem_description)
        scored = MethodScorer(score_func).process(self.library.tree)
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]

    def format_methods(self, methods: list[dict[str, Any]]) -> str:
        """Format retrieved methods for prompt injection (MM-Agent format_methods)."""
        return "\n".join(f"**{m['method']}:** {m['description']}" for m in methods)


def load_hmml() -> HMMLMethodLibrary:
    """Convenience loader matching sibling config loaders (e.g. model catalog)."""
    return HMMLMethodLibrary()


_global_library: HMMLMethodLibrary | None = None


def get_library() -> HMMLMethodLibrary:
    """Process-lifetime cached library (mirrors _load_model_catalog caching)."""
    global _global_library
    if _global_library is None:
        _global_library = load_hmml()
    return _global_library

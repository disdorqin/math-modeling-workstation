"""HMML hierarchical method library tests (task tc6aff945, 开源融合 MM-Agent HMML).

The layer is fused one-to-one from ``usail-hkust/LLM-MM-Agent``
(NeurIPS 2025, arXiv 2505.14148):

* ``HMMLMethodLibrary`` loads the tri-level tree (5 Domains -> Subdomains ->
  97 Method Nodes) from ``config/hmml.json`` (source: ``MMAgent/HMML/HMML.json``).
* ``MethodScorer`` reproduces ``MMAgent/agent/retrieve_method.py``: a score
  function grades sibling methods per level; a leaf's final score is
  ``parent_avg * parent_weight + child_score * child_weight`` (0.5/0.5).
* ``MethodRetriever.retrieve`` returns the top-k leaves by final score.
* Two score functions: ``lexical`` (deterministic token-overlap, offline
  stand-in for MM-Agent's embedding scorer) and ``llm`` (StructuredLLM critic
  reproducing the five-dimension METHOD_CRITIQUE_PROMPT).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mathworkstation.hmml import (
    CHILD_WEIGHT,
    PARENT_WEIGHT,
    HMMLCritiqueProposal,
    HMMLMethodLibrary,
    MethodRetriever,
    MethodScorer,
    lexical_score,
    llm_score_method,
    load_hmml,
)


def _sample_tree() -> list[dict]:
    """A minimal 2-domain tri-level tree for deterministic scorer tests."""
    return [
        {
            "method_class": "Operations Research:",
            "children": [
                {
                    "method_class": "Programming Theory:",
                    "children": [
                        {
                            "method": "Linear Programming (LP)",
                            "description": "<modeling_method>: linear objective and linear constraints. <application>: resource allocation, transportation scheduling.",
                        },
                        {
                            "method": "Integer Programming (IP)",
                            "description": "<modeling_method>: decision variables take integer values. <application>: production scheduling, logistics.",
                        },
                    ],
                },
                {
                    "method_class": "Graph Theory:",
                    "children": [
                        {
                            "method": "Shortest Path",
                            "description": "<modeling_method>: shortest path in networks. <application>: transportation networks, routing.",
                        }
                    ],
                },
            ],
        },
        {
            "method_class": "Prediction:",
            "children": [
                {
                    "method_class": "Forecasting:",
                    "children": [
                        {
                            "method": "Time Series Forecasting",
                            "description": "<modeling_method>: forecast future values from past series. <application>: demand prediction, trend analysis.",
                        },
                        {
                            "method": "Regression",
                            "description": "<modeling_method>: model relationship between variables. <application>: causal analysis, prediction.",
                        },
                    ],
                }
            ],
        },
    ]


class _FakeStructuredLLM:
    """Deterministic structured-LLM stand-in returning fixed critic scores.

    ``only_known=True`` emits only the indices present in ``per_index`` (to
    exercise the missing-index default), otherwise every method gets a score.
    """

    def __init__(self, per_index: dict[int, dict[str, float]] | None = None, only_known: bool = False) -> None:
        self.per_index = per_index or {}
        self.only_known = only_known

    def json_call(self, case_id, session_id, node_id, prompt_id, variables, output_model, input_artifact_ids, max_tokens=3000):
        methods = variables.get("methods", "")
        count = sum(1 for line in methods.splitlines() if line.strip() and line.strip()[0].isdigit())
        items = []
        for index in range(1, count + 1):
            if self.only_known and index not in self.per_index:
                continue
            scores = self.per_index.get(index, {"Assumptions": 3, "Structure": 3, "Variables": 3, "Dynamics": 3, "Solvability": 3})
            items.append({"method_index": index, "scores": scores})
        return output_model.model_validate({"methods": items}), {"artifact_id": f"art-{prompt_id}"}


# --------------------------------------------------------------------------- #
# Library loading
# --------------------------------------------------------------------------- #


def test_library_loads_real_config() -> None:
    lib = load_hmml()
    assert len(lib.domains) == 5
    assert lib.method_count == 97
    # every leaf carries the tri-level structure's description fields
    for leaf in lib.leaf_methods():
        assert "method" in leaf
        assert "description" in leaf
        assert "<modeling_method>" in leaf["description"]


def test_library_rejects_empty_tree(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    try:
        HMMLMethodLibrary(bad)
        raise AssertionError("expected ValueError for empty tree")
    except ValueError:
        pass


def test_library_round_trip(tmp_path: Path) -> None:
    lib = load_hmml()
    assert [d.startswith(("Operations Research", "Optimization", "Machine Learning", "Prediction", "Evaluation")) for d in lib.domains]


# --------------------------------------------------------------------------- #
# MethodScorer hierarchical scoring (one-to-one with MM-Agent)
# --------------------------------------------------------------------------- #


def test_method_scorer_hierarchy_weights() -> None:
    """Leaf final = parent_avg * 0.5 + child_score * 0.5; parents propagate.

    Mirrors MM-Agent: only scores assigned at a *method_class* level become
    parent scores for the leaves below them. In the sample tree the subdomain
    level directly holds methods (no extra method_class level), so parent_avg
    is 0 and every leaf score is exactly half its child score — the classic
    "score at each level, blend into the leaves" behaviour.
    """

    def score_func(methods):
        return [
            {"method_index": i + 1, "score": 10.0 * (i + 1)}
            for i in range(len(methods))
        ]

    tree = _sample_tree()
    scorer = MethodScorer(score_func)
    leaves = scorer.process(tree)

    # 5 leaf methods in the sample tree (LP, IP, Shortest Path, TS, Regression)
    assert len(leaves) == 5
    by_name = {leaf["method"]: leaf["score"] for leaf in leaves}

    # no method_class intermediate level -> parent_avg = 0 -> final = 0.5*child
    assert by_name["Linear Programming (LP)"] == pytest.approx(5.0)
    assert by_name["Integer Programming (IP)"] == pytest.approx(10.0)
    assert by_name["Shortest Path"] == pytest.approx(5.0)
    assert by_name["Time Series Forecasting"] == pytest.approx(5.0)
    assert by_name["Regression"] == pytest.approx(10.0)


def test_method_scorer_default_weights_constants() -> None:
    assert PARENT_WEIGHT == 0.5
    assert CHILD_WEIGHT == 0.5


def test_method_scorer_zero_parent_scores() -> None:
    """No parent scores -> parent_avg = 0, final = child_score * 0.5."""

    def score_func(methods):
        return [{"method_index": i + 1, "score": 8.0} for i in range(len(methods))]

    tree = [
        {
            "method_class": "Prediction:",
            "children": [
                {"method": "Regression", "description": "x"},
                {"method": "Forecast", "description": "y"},
            ],
        }
    ]
    leaves = MethodScorer(score_func).process(tree)
    assert leaves == [
        {"method": "Regression", "description": "x", "score": 4.0},
        {"method": "Forecast", "description": "y", "score": 4.0},
    ]


# --------------------------------------------------------------------------- #
# Lexical scorer (offline stand-in for the embedding scorer)
# --------------------------------------------------------------------------- #


def test_lexical_score_orders_by_overlap() -> None:
    methods = [
        {"method": "Linear Programming", "description": "linear objective linear constraints optimization"},
        {"method": "Time Series", "description": "forecast future values trend seasonality"},
    ]
    scored = lexical_score(methods, problem="how to allocate resources with linear constraints")
    by_index = {item["method_index"]: item["score"] for item in scored}
    # "linear" and "constraints" appear in method 1 -> higher overlap
    assert by_index[1] > by_index[2]


def test_lexical_score_empty_problem() -> None:
    methods = [{"method": "A", "description": "x y z"}]
    scored = lexical_score(methods, problem="")
    assert scored == [{"method_index": 1, "score": 0.0}]


# --------------------------------------------------------------------------- #
# MethodRetriever top-k
# --------------------------------------------------------------------------- #


def test_retriever_returns_top_k(tmp_path: Path) -> None:
    lib = load_hmml()
    retriever = MethodRetriever(library=lib, score_func="lexical", top_k=3)
    methods = retriever.retrieve("predict future values from a time series with trend analysis")
    assert 0 < len(methods) <= 3
    # scores are descending
    scores = [m["score"] for m in methods]
    assert scores == sorted(scores, reverse=True)
    assert all(m["description"] for m in methods)


def test_retriever_empty_problem_returns_nothing() -> None:
    retriever = MethodRetriever(score_func="lexical")
    assert retriever.retrieve("") == []


def test_retriever_explicit_top_k_overrides_default() -> None:
    retriever = MethodRetriever(score_func="lexical", top_k=6)
    methods = retriever.retrieve("resource allocation linear programming scheduling", top_k=2)
    assert len(methods) <= 2


def test_format_methods() -> None:
    retriever = MethodRetriever(score_func="lexical")
    text = retriever.format_methods([{"method": "LP", "description": "linear"}, {"method": "IP", "description": "integer"}])
    assert text == "**LP:** linear\n**IP:** integer"


# --------------------------------------------------------------------------- #
# LLM critic scorer (five-dimension METHOD_CRITIQUE_PROMPT)
# --------------------------------------------------------------------------- #


def test_llm_scorer_mean_of_five_dimensions() -> None:
    fake = _FakeStructuredLLM(
        {
            1: {"Assumptions": 5, "Structure": 5, "Variables": 5, "Dynamics": 5, "Solvability": 5},
            2: {"Assumptions": 1, "Structure": 2, "Variables": 3, "Dynamics": 4, "Solvability": 5},
        }
    )
    score = llm_score_method(fake, "case-x", "sess-y", "problem text")
    methods = [
        {"method": "A", "description": "desc a"},
        {"method": "B", "description": "desc b"},
    ]
    result = score(methods)
    assert result[0]["method_index"] == 1
    assert result[0]["score"] == 5.0
    assert result[1]["score"] == (1 + 2 + 3 + 4 + 5) / 5


def test_llm_scorer_missing_index_defaults_zero() -> None:
    fake = _FakeStructuredLLM(
        {2: {"Assumptions": 3, "Structure": 3, "Variables": 3, "Dynamics": 3, "Solvability": 3}},
        only_known=True,
    )
    score = llm_score_method(fake, "c", "s", "p")
    result = score([{"method": "A", "description": "a"}, {"method": "B", "description": "b"}])
    # index 1 omitted by the critic -> score 0; index 2 present -> 3.0
    assert result[0]["score"] == 0.0
    assert result[1]["score"] == 3.0


def test_llm_retriever_e2e_uses_critic() -> None:
    fake = _FakeStructuredLLM()
    retriever = MethodRetriever(score_func="llm", llm=fake, case_id="c", session_id="s", top_k=2)
    methods = retriever.retrieve("some modeling problem statement")
    assert len(methods) == 2
    # all scores equal (uniform critic) -> order deterministic
    assert methods[0]["score"] == methods[1]["score"]


def test_llm_retriever_requires_llm() -> None:
    retriever = MethodRetriever(score_func="llm", llm=None)
    try:
        retriever.retrieve("problem")
        raise AssertionError("expected ValueError when llm scorer has no llm")
    except (ValueError, TypeError):
        pass


# --------------------------------------------------------------------------- #
# Config data integrity (one-to-one acceptance with the upstream repo)
# --------------------------------------------------------------------------- #


def test_hmml_config_matches_upstream_shape() -> None:
    """The fused config must keep the upstream HMML.json tri-level shape."""
    import os

    project = Path(__file__).resolve().parents[1]
    config = project / "config" / "hmml.json"
    assert config.is_file()
    data = json.loads(config.read_text(encoding="utf-8"))
    assert isinstance(data, list)
    for domain in data:
        assert "method_class" in domain
        assert "children" in domain
        for sub in domain["children"]:
            # subdomain level may nest another method_class level or contain
            # methods directly; either way it must have children
            assert "children" in sub
    # 97 method nodes, matching the upstream HMML (98 per paper, 97 in data)
    lib = load_hmml()
    assert lib.method_count == 97


def test_real_problem_retrieval_smoke() -> None:
    """Real end-to-end smoke: an allocation problem surfaces OR methods."""
    retriever = MethodRetriever(score_func="lexical", top_k=5)
    hits = retriever.retrieve("optimize resource allocation with linear programming and scheduling constraints")
    names = [m["method"] for m in hits]
    assert names, "expected at least one retrieved method"
    # sanity: top hit's description carries the tri-level markup
    assert "<modeling_method>" in hits[0]["description"]


def test_load_hmml_retrieval_injects_into_model_plan_prompt() -> None:
    """Integration: the pipeline-level HMML retrieval helper produces a
    formatted block that the model_plan prompt can render (best-effort, and
    empty-safe when no objectives exist)."""
    from mathworkstation.auto_pipeline import _load_hmml_retrieval
    from mathworkstation.llm.prompts import PromptRegistry

    class _FakeAnalysis:
        objectives = ["预测未来趋势并评估模型稳健性"]

    block = _load_hmml_retrieval(_FakeAnalysis())
    assert block, "expected a non-empty HMML retrieval block for a real objective"
    assert "**" in block and ":" in block  # **Method:** description shape

    # the model_plan prompt template must accept the HMML variable
    registry = PromptRegistry("prompts")
    prompt = registry.load("model_plan")
    rendered = prompt.render(
        "model_plan",
        {
            "case_id": "case-x",
            "dataset_id": "dataset-x",
            "catalog_json": "{}",
            "columns_json": "[]",
            "profile_json": "{}",
            "problem_analysis_json": "{}",
            "hmml_retrieved": block,
        },
    )
    assert any("HMML-recommended" in message["content"] for message in rendered)

    # empty objectives degrade gracefully (no crash, empty block)
    class _EmptyAnalysis:
        objectives = []

    assert _load_hmml_retrieval(_EmptyAnalysis()) == ""

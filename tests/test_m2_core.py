"""M2 — contest-grade, evidence-bounded paper layer: fast, offline unit tests.

These exercise the provider-neutral surface (Provider / FakeProvider), the
symbol registry (B7), the structured Paper model, the quality rubric, the
adversarial fixture baseline, and a lightweight partial pipeline (B6->B1->B2->B3)
that needs no subprocess or matplotlib. The heavy end-to-end path lives in
``test_m2_benchmark.py``.
"""
from __future__ import annotations

import pytest

from mathworkstation.m2.provider import FakeProvider, get_provider, CompletionRequest
from mathworkstation.m2.registry import SymbolRegistry
from mathworkstation.m2.paper import Paper
from mathworkstation.m2.rubric import score_paper, THRESHOLD
from mathworkstation.m2.context import M2Context, DatasetDescriptor, EvidenceItem
from mathworkstation.m2.agents import (
    EvidenceVerifier,
    PaperArchitect,
    ProblemAnalyst,
    ModelArchitect,
    ExperimentPlanner,
)
from mathworkstation.m2.fixtures import clean_baseline


# --------------------------------------------------------------------------- #
# Provider-neutral interface
# --------------------------------------------------------------------------- #
def test_fake_provider_deterministic():
    p = FakeProvider(seed=0)
    req = CompletionRequest(task="problem_analysis", prompt="model y",
                             meta={"goal": "model y", "n_variables": 5})
    assert p.complete(req).text == p.complete(req).text
    req2 = CompletionRequest(task="problem_analysis", prompt="different",
                              meta={"goal": "diff", "n_variables": 5})
    assert p.complete(req2).text != p.complete(req).text


def test_fake_provider_task_shapes():
    p = FakeProvider()
    analysis = p.complete_json(CompletionRequest(task="problem_analysis",
                                                  prompt="g", meta={"goal": "g", "n_variables": 3}))
    arch = p.complete_json(CompletionRequest(task="model_architecture", prompt="g"))
    assert "subproblems" in analysis and "summary" in analysis
    assert [f["id"] for f in arch["families"]] == ["linear", "tree", "robust_baseline"]


def test_get_provider_fake():
    p = get_provider("fake")
    assert isinstance(p, FakeProvider)
    assert p.name == "fake"


def test_get_provider_unknown_raises():
    with pytest.raises(ValueError):
        get_provider("nope")


# --------------------------------------------------------------------------- #
# B7 symbol registry
# --------------------------------------------------------------------------- #
def test_symbol_registry_define_use_validate():
    r = SymbolRegistry()
    r.define("y", r"y", "response variable")
    r.use("y", "intro")
    assert r.is_defined("y")
    assert r.validate() == []
    with pytest.raises(KeyError):
        r.use("undefined_symbol", "intro")


# --------------------------------------------------------------------------- #
# Structured Paper model
# --------------------------------------------------------------------------- #
def test_paper_counts():
    paper = Paper()
    paper.add_section("results", "Results")
    for i in range(9):
        paper.add_figure("results", f"f{i}", "line", "cap", "ev")
    for i in range(5):
        paper.add_table("results", f"t{i}", "cap", ["a", "b"], [["1", "2"]], "ev")
    for i in range(12):
        paper.add_equation("results", f"e{i}", r"x", introduced=["x"], used=[])
    paper.candidate_families = ["a", "b", "c"]
    assert paper.count_figures() == 9
    assert paper.count_tables() == 5
    assert paper.count_equations() == 12
    assert paper.count_candidates() == 3


# --------------------------------------------------------------------------- #
# Quality rubric
# --------------------------------------------------------------------------- #
def test_rubric_threshold_constant():
    assert THRESHOLD == 75


def test_rubric_contest_grade_passes():
    paper = Paper()
    for sid, title in [("intro", "Introduction"), ("methods", "Methods"),
                       ("results", "Results"), ("conclusion", "Conclusion")]:
        paper.add_section(sid, title)
    paper.candidate_families = ["linear", "tree", "robust_baseline"]
    for i in range(12):
        paper.add_equation("methods", f"e{i}", r"x", introduced=["x"], used=[])
    for i in range(8):
        paper.add_figure("results", f"f{i}", "line", "cap", "ev")
    for i in range(5):
        paper.add_table("results", f"t{i}", "cap", ["a", "b"], [["1", "2"]], "ev")
    # a numeric claim that cites registered evidence
    paper.add_paragraph("results", "MSE is 0.4200 (R2 0.8100). [cite:ev]", evidence_refs=["ev"])

    reg = SymbolRegistry()
    reg.define("x", r"x", "variable")
    reg.use("x", "methods")

    result = score_paper(paper, reg)
    assert result.passed is True
    assert result.score >= THRESHOLD


# --------------------------------------------------------------------------- #
# Evidence-bounded guarantee (baseline fixture)
# --------------------------------------------------------------------------- #
def test_fixtures_clean_passes_verifier():
    res = EvidenceVerifier().run(clean_baseline())
    assert res["ok"] is True
    assert res["violations"] == []


# --------------------------------------------------------------------------- #
# Lightweight partial pipeline (no subprocess / no matplotlib)
# --------------------------------------------------------------------------- #
def test_partial_pipeline_skeleton():
    ds = DatasetDescriptor(name="t", target="y", features=["x1", "x2"],
                           n_rows=10, n_cols=3, source="")
    ctx = M2Context(dataset=ds, provider=FakeProvider(), paper=Paper(),
                    symbols=SymbolRegistry())
    PaperArchitect().run(ctx)
    ProblemAnalyst().run(ctx)
    ModelArchitect().run(ctx)
    ExperimentPlanner().run(ctx)

    assert ctx.paper.title  # set by B6
    assert len(ctx.paper.sections) >= 10
    assert len(ctx.paper.candidate_families) == 3
    assert ctx.paper.count_equations() >= 12
    assert "model-plan" in ctx.evidence and "problem" in ctx.evidence

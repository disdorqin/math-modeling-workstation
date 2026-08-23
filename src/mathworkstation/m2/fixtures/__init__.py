"""Adversarial fixtures for the M2 evidence-bounded layer.

These build minimal :class:`M2Context` / :class:`Paper` objects that exercise
the layer's refusal-to-fabricate guarantees:

  * fabricated claim  -- a numeric claim with NO evidence citation
  * orphan citation  -- a citation to an evidence id that does not exist
  * contradiction     -- a cited value that disagrees with the evidence payload
  * clean baseline    -- a valid, fully-grounded paper (must pass the verifier)
"""
from __future__ import annotations

from mathworkstation.m2.context import DatasetDescriptor, EvidenceItem, M2Context
from mathworkstation.m2.paper import Paper, Paragraph, Section
from mathworkstation.m2.provider import FakeProvider
from mathworkstation.m2.registry import SymbolRegistry


def _base_ctx() -> M2Context:
    ds = DatasetDescriptor(name="adv", target="y", features=["x1", "x2"],
                           n_rows=10, n_cols=3, source="")
    return M2Context(dataset=ds, provider=FakeProvider(), paper=Paper(),
                     symbols=SymbolRegistry())


def clean_baseline() -> M2Context:
    """A fully evidence-grounded paper; the verifier must accept it."""
    ctx = _base_ctx()
    ctx.paper.add_section("results", "Results")
    ctx.register_evidence(EvidenceItem(artifact_id="metrics-tree", kind="metrics",
                                       payload={"mse": 0.42, "r2": 0.81}))
    ctx.paper.add_paragraph("results",
        "The tree family attained MSE 0.4200 (R2 0.8100). [cite:metrics-tree]",
        evidence_refs=["metrics-tree"])
    return ctx


def fabricated_claim() -> M2Context:
    """A numeric claim with no citation -- must be flagged NO_CITATION."""
    ctx = clean_baseline()
    ctx.paper.add_paragraph("results",
        "The winning model reduces error by 37.5 percent on held-out data.",
        evidence_refs=[])
    return ctx


def orphan_citation() -> M2Context:
    """A citation to a non-existent evidence id -- must be flagged UNKNOWN_EVIDENCE."""
    ctx = clean_baseline()
    ctx.paper.add_paragraph("results",
        "The linear model achieved MSE 0.5000. [cite:metrics-linear]",
        evidence_refs=["metrics-linear"])  # metrics-linear was never registered
    return ctx


def contradiction() -> M2Context:
    """A cited value that contradicts the registered evidence payload."""
    ctx = clean_baseline()
    # Override the grounded claim with a conflicting number but keep the citation.
    ctx.paper.sections[0].paragraphs[0] = Paragraph(
        section_id="results",
        text="The tree family attained MSE 9.9999 (R2 0.8100). [cite:metrics-tree]",
        evidence_refs=["metrics-tree"])  # payload says mse 0.42, not 9.9999
    ctx.paper.metadata["contradiction_target"] = "metrics-tree"
    return ctx

"""Quality rubric for contest-grade papers (B10 scoring logic).

A paper scores 0-100 against five criteria. The bar for "contest grade" is
``THRESHOLD = 75``. Every criterion is computable from the structured
:class:`Paper` + :class:`SymbolRegistry`, so scoring is deterministic and the
revision loop (B11) can improve it without a human or an LLM in the loop.

Criteria
--------
  evidence_grounding   (25) every quantitative claim cites a registered artifact
  notation_consistency (20) all used symbols defined; no undefined symbols
  structure            (20) required sections present + figure/table/equation mass
  visual_richness     (20) >=8 figures and >=5 tables
  candidate_rigor     (15) >=3 candidate families + an explicit comparison
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import List

from .paper import Paper
from .registry import SymbolRegistry

THRESHOLD = 75

NUMERIC = re.compile(r"(?<![A-Za-z0-9_])[-+]?\d+(?:\.\d+)?%?")


@dataclass
class RubricResult:
    score: int
    passed: bool
    subscores: dict = field(default_factory=dict)
    findings: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"score": self.score, "passed": self.passed,
                "subscores": self.subscores, "findings": self.findings, "threshold": THRESHOLD}


def _numeric_claims_without_citation(paper: Paper) -> List[str]:
    """Return texts of paragraphs that contain a number but cite no evidence."""
    bad: List[str] = []
    for s in paper.sections:
        for p in s.paragraphs:
            if NUMERIC.search(p.text) and not p.evidence_refs:
                bad.append(p.text)
    return bad


def score_paper(paper: Paper, registry: SymbolRegistry) -> RubricResult:
    findings: List[str] = []
    subscores: dict = {}

    # 1. evidence grounding (25)
    paras = [p for s in paper.sections for p in s.paragraphs]
    numbered = [p for p in paras if NUMERIC.search(p.text)]
    uncited = _numeric_claims_without_citation(paper)
    if numbered:
        grounded = (len(numbered) - len(uncited)) / len(numbered)
    else:
        grounded = 1.0
    eg = int(round(25 * grounded))
    subscores["evidence_grounding"] = eg
    if uncited:
        findings.append(f"{len(uncited)} quantitative claim(s) without an evidence citation")

    # 2. notation consistency (20)
    defects = registry.validate()
    nc = 20 if not defects else max(0, 20 - 5 * len(defects))
    subscores["notation_consistency"] = nc
    findings.extend(defects)

    # 3. structure (20)
    ids = {s.id for s in paper.sections}
    required = {"intro", "methods", "results", "conclusion"}
    missing = required - ids
    struct = 20
    if missing:
        struct -= 5 * len(missing)
        findings.append(f"missing required sections: {sorted(missing)}")
    if paper.count_equations() < 12:
        struct -= 3
        findings.append("fewer than 12 equations")
    subscores["structure"] = max(0, struct)

    # 4. visual richness (20)
    figs = paper.count_figures()
    tabs = paper.count_tables()
    vr = 20
    if figs < 8:
        vr -= 10
        findings.append(f"only {figs} figures (<8)")
    if tabs < 5:
        vr -= 10
        findings.append(f"only {tabs} tables (<5)")
    subscores["visual_richness"] = max(0, vr)

    # 5. candidate rigor (15)
    cr = 15
    if paper.count_candidates() < 3:
        cr -= 10
        findings.append(f"only {paper.count_candidates()} candidate families (<3)")
    has_comparison = any("comparison" in s.id or "results" in s.id for s in paper.sections)
    if not has_comparison:
        cr -= 5
        findings.append("no explicit candidate comparison section")
    subscores["candidate_rigor"] = max(0, cr)

    score = eg + nc + subscores["structure"] + subscores["visual_richness"] + subscores["candidate_rigor"]
    score = max(0, min(100, score))
    return RubricResult(score=score, passed=score >= THRESHOLD, subscores=subscores, findings=findings)

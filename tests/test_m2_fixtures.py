"""M2 — adversarial fixtures prove the layer's refusal-to-fabricate guarantee.

Each fixture builds a minimal :class:`M2Context` / :class:`Paper` and the
:class:`EvidenceVerifier` (B5) must classify it correctly:

  * ``clean_baseline``   -- fully evidence-grounded paper  -> ``ok=True``
  * ``fabricated_claim`` -- numeric claim with no citation -> ``NO_CITATION``
  * ``orphan_citation``  -- citation to a missing artifact  -> ``UNKNOWN_EVIDENCE``
  * ``contradiction``    -- cited value disagrees w/ payload -> ``CONTRADICTION``

If any of these regresses, the no-fabrication contract is broken and the test
fails loudly. This is the lock-in test for M2's central guarantee.
"""
from __future__ import annotations

from mathworkstation.m2.fixtures import (
    clean_baseline,
    fabricated_claim,
    orphan_citation,
    contradiction,
)
from mathworkstation.m2.agents import EvidenceVerifier


def _violation_types(ctx) -> set:
    return {v["type"] for v in EvidenceVerifier().run(ctx)["violations"]}


def test_clean_baseline_passes():
    res = EvidenceVerifier().run(clean_baseline())
    assert res["ok"] is True
    assert res["violations"] == []


def test_fabricated_claim_flagged():
    res = EvidenceVerifier().run(fabricated_claim())
    assert res["ok"] is False
    assert "NO_CITATION" in _violation_types(fabricated_claim())


def test_orphan_citation_flagged():
    res = EvidenceVerifier().run(orphan_citation())
    assert res["ok"] is False
    assert "UNKNOWN_EVIDENCE" in _violation_types(orphan_citation())


def test_contradiction_flagged():
    res = EvidenceVerifier().run(contradiction())
    assert res["ok"] is False
    assert "CONTRADICTION" in _violation_types(contradiction())


def test_four_fixtures_distinct_outcomes():
    # exactly one of the four must be accepted; the other three must be rejected
    assert EvidenceVerifier().run(clean_baseline())["ok"] is True
    for bad in (fabricated_claim, orphan_citation, contradiction):
        assert EvidenceVerifier().run(bad())["ok"] is False

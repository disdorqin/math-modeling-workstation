"""Real, end-to-end test of the evidence-promotion chain for the modeling
fan-out (requirement #7 of the 2026-07-26 verification pass):

    modeling_protocol -> model_candidate(s) -> model_comparison
        -> ModelJudgeAgent proposes MODEL_SELECTION
        -> Adjudicator writes a DRAFT claim (evidence not yet paper-ready)
        -> ModelingEvidenceGate.assess/approve promotes protocol+comparison+
           candidates via the EXISTING ArtifactRegistry.promote_to_paper
        -> ClaimRegistry.recheck_evidence re-applies create()'s own
           eligibility rule and flips the claim to VERIFIED
        -> exactly one active canonical claim exists for this modeling run

Nothing here is a parallel shortcut: every step calls the same production
code path a human operator or CLI invocation would use
(`assess-modeling-evidence` / `approve-modeling-evidence` /
`recheck-claim-evidence` in cli.py), just driven directly against the real
agents/registries instead of through subprocess CLI calls.
"""

from __future__ import annotations

from mathworkstation.paper_ready import ModelingEvidenceGate
from test_modeling_fanout import _Harness


class TestEvidencePromotionProducesAVerifiedClaim:
    def test_draft_claim_becomes_verified_after_promotion_and_recheck(self, tmp_path) -> None:
        harness = _Harness(tmp_path, n_rows=60)
        protocol_id = harness.build_protocol()["protocol_artifact_id"]
        harness.run_all_candidates(protocol_id)
        eval_report = harness.run_evaluation(protocol_id)
        comparison_id = eval_report.proposals[0].payload["comparison_artifact_id"]

        judge_report = harness.run_judge(comparison_id)
        assert judge_report.proposals, "judge must reach a WINNER/TIE/NO_ACCEPTABLE_WINNER outcome"
        verdicts = [harness.adjudicator.decide(harness.case_id, p) for p in judge_report.proposals]
        winner_verdicts = [v for v in verdicts if v.produced.get("claim_id")]
        assert winner_verdicts, "this synthetic dataset must produce a WINNER outcome"
        verdict = winner_verdicts[0]

        # Before promotion: the claim exists but is DRAFT (evidence not yet
        # paper-ready) -- this is the exact state the 2026-07-26 report
        # complained about for the real diabetes case.
        assert verdict.status.value == "NEEDS_HUMAN"
        claim_id = verdict.produced["claim_id"]
        claim = harness.claims.get(harness.case_id, claim_id)
        assert claim["status"] == "DRAFT"
        assert "evidence_not_paper_ready" in claim["restrictions"]

        gate = ModelingEvidenceGate(harness.cases, harness.artifacts)
        assessment = gate.assess(harness.case_id, protocol_id, comparison_id)
        assert assessment["eligible"], assessment["reasons"]
        assert protocol_id in assessment["required_artifact_ids"]
        assert comparison_id in assessment["required_artifact_ids"]

        approval = gate.approve(
            harness.case_id, protocol_id, comparison_id, approved_by="test_reviewer", note="synthetic-case approval"
        )
        assert approval["promoted_artifact_ids"]
        for artifact_id in approval["promoted_artifact_ids"]:
            assert harness.artifacts.get(harness.case_id, artifact_id)["paper_eligible"] is True

        # Re-deciding the identical judge proposal would just replay the
        # original NEEDS_HUMAN verdict from the decisions.jsonl cache -- the
        # promotion must be surfaced through recheck_evidence, not by
        # resubmitting the proposal.
        replay = harness.adjudicator.decide(harness.case_id, judge_report.proposals[0])
        assert replay.replayed is True
        assert replay.status.value == "NEEDS_HUMAN"  # the historical decision record is untouched

        rechecked = harness.claims.recheck_evidence(harness.case_id, claim_id, checked_by="test_reviewer")
        assert rechecked["status"] == "VERIFIED"
        assert "evidence_not_paper_ready" not in rechecked.get("restrictions", [])

        # exactly one claim exists for this modeling run, and it is the
        # VERIFIED one -- no duplicate claim was created anywhere in this
        # chain (creation, replay, promotion, recheck).
        all_claims = harness.claims.list_claims(harness.case_id)
        assert len(all_claims) == 1
        assert all_claims[0]["claim_id"] == claim_id
        assert all_claims[0]["status"] == "VERIFIED"

        # the VERIFIED claim references the winning candidate's metric, and
        # its own evidence chain still resolves back to the protocol and
        # comparison artifacts that grounded the judge's decision.
        assert rechecked["evidence_artifact_ids"] == [protocol_id, comparison_id]

    def test_recheck_is_a_no_op_before_promotion(self, tmp_path) -> None:
        harness = _Harness(tmp_path, n_rows=60)
        protocol_id = harness.build_protocol()["protocol_artifact_id"]
        harness.run_all_candidates(protocol_id)
        eval_report = harness.run_evaluation(protocol_id)
        comparison_id = eval_report.proposals[0].payload["comparison_artifact_id"]
        judge_report = harness.run_judge(comparison_id)
        verdicts = [harness.adjudicator.decide(harness.case_id, p) for p in judge_report.proposals]
        winner_verdicts = [v for v in verdicts if v.produced.get("claim_id")]
        claim_id = winner_verdicts[0].produced["claim_id"]

        unchanged = harness.claims.recheck_evidence(harness.case_id, claim_id, checked_by="test_reviewer")
        assert unchanged["status"] == "DRAFT"
        assert len(harness.claims.list_claims(harness.case_id)) == 1  # no-op did not append a spurious line

    def test_assess_rejects_a_comparison_from_a_different_protocol(self, tmp_path) -> None:
        harness = _Harness(tmp_path, n_rows=60)
        protocol_id_1 = harness.build_protocol()["protocol_artifact_id"]
        harness.run_all_candidates(protocol_id_1)
        eval1 = harness.run_evaluation(protocol_id_1)
        comparison_id_1 = eval1.proposals[0].payload["comparison_artifact_id"]

        protocol_id_2 = harness.build_protocol(n_splits=4)["protocol_artifact_id"]

        gate = ModelingEvidenceGate(harness.cases, harness.artifacts)
        # comparison_id_1 was produced under protocol_id_1, not protocol_id_2
        assessment = gate.assess(harness.case_id, protocol_id_2, comparison_id_1)
        assert not assessment["eligible"]
        assert "comparison_references_a_different_protocol" in assessment["reasons"]

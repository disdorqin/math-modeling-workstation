"""Tests for the multi-agent layer.

The load-bearing tests are the negative ones. An agent layer is only worth
having if a fabricating agent cannot get a number into the paper, so most of
what is asserted here is what the adjudicator *refuses*.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

import pytest

from mathworkstation.agents.adjudicator import Adjudicator
from mathworkstation.agents.base import Agent, DeterministicAgent
from mathworkstation.agents.contracts import (
    AgentReport,
    AgentRequest,
    EvidenceRef,
    Proposal,
    ProposalKind,
    RejectionCode,
    VerdictStatus,
)
from mathworkstation.agents.graph import run_sequence


class _FakeCases:
    def __init__(self, root) -> None:
        self._root = root

    def case_root(self, case_id: str):
        return self._root


class _FakeArtifacts:
    """Minimal stand-in exposing only what the adjudicator reads."""

    def __init__(self, artifacts: dict[str, dict[str, Any]]) -> None:
        self._artifacts = artifacts

    def get(self, case_id: str, artifact_id: str) -> dict[str, Any]:
        try:
            return self._artifacts[artifact_id]
        except KeyError as error:
            raise KeyError(artifact_id) from error


class _FakeClaims:
    def __init__(self, eligible: set[str]) -> None:
        self.eligible = eligible
        self.created: list[dict[str, Any]] = []

    def list_claims(self, case_id: str) -> list[dict[str, Any]]:
        return list(self.created)

    def get(self, case_id: str, claim_id: str) -> dict[str, Any]:
        for claim in self.created:
            if claim["claim_id"] == claim_id:
                return claim
        raise KeyError(claim_id)

    def create(self, case_id: str, value, created_by: str) -> dict[str, Any]:
        status = (
            "VERIFIED"
            if all(item in self.eligible for item in value.evidence_artifact_ids)
            else "DRAFT"
        )
        claim = {
            "claim_id": f"claim-{len(self.created):012d}",
            "text": value.text,
            "status": status,
            "created_by": created_by,
        }
        self.created.append(claim)
        return claim


class _FakeFigures:
    def __init__(self) -> None:
        self.promoted: list[str] = []
        self._figures: dict[str, dict[str, Any]] = {}

    def get(self, case_id: str, figure_id: str) -> dict[str, Any]:
        try:
            return self._figures[figure_id]
        except KeyError:
            raise KeyError(figure_id) from None

    def promote(self, case_id, figure_id, approval_artifact_id, approved_by, note):
        if not note.strip():
            raise ValueError("figure promotion requires a note")
        self.promoted.append(figure_id)
        figure = {"figure_id": figure_id, "status": "FINAL"}
        self._figures[figure_id] = figure
        return figure


def _adjudicator(tmp_path, *, eligible=("artifact-good0000000",)) -> Adjudicator:
    artifacts = _FakeArtifacts(
        {
            "artifact-good0000000": {"artifact_id": "artifact-good0000000", "paper_eligible": True},
            "artifact-draft000000": {"artifact_id": "artifact-draft000000", "paper_eligible": False},
        }
    )
    return Adjudicator(
        _FakeCases(tmp_path),
        artifacts,  # type: ignore[arg-type]
        _FakeClaims(set(eligible)),  # type: ignore[arg-type]
        _FakeFigures(),  # type: ignore[arg-type]
    )


def _proposal(**overrides: Any) -> Proposal:
    payload = {
        "kind": ProposalKind.CLAIM,
        "agent": "test_agent",
        "summary": "测试结论",
        "payload": {"text": "模型 RMSE 为 54.825。", "claim_type": "model_result"},
        "asserts_numbers": True,
    }
    payload.update(overrides)
    return Proposal(**payload)


class TestEvidenceGate:
    def test_numeric_claim_without_evidence_is_rejected(self, tmp_path) -> None:
        verdict = _adjudicator(tmp_path).decide("case", _proposal())
        assert verdict.status is VerdictStatus.REJECTED
        assert RejectionCode.NO_EVIDENCE in verdict.codes

    def test_numeric_claim_on_unpromoted_evidence_is_rejected(self, tmp_path) -> None:
        proposal = _proposal(evidence=[EvidenceRef(artifact_id="artifact-draft000000")])
        verdict = _adjudicator(tmp_path).decide("case", proposal)
        assert verdict.status is VerdictStatus.REJECTED
        assert RejectionCode.EVIDENCE_NOT_PAPER_READY in verdict.codes

    def test_unknown_artifact_is_rejected(self, tmp_path) -> None:
        proposal = _proposal(evidence=[EvidenceRef(artifact_id="artifact-nonexistent")])
        verdict = _adjudicator(tmp_path).decide("case", proposal)
        assert verdict.status is VerdictStatus.REJECTED
        assert RejectionCode.EVIDENCE_UNKNOWN in verdict.codes

    def test_backed_claim_is_accepted(self, tmp_path) -> None:
        proposal = _proposal(evidence=[EvidenceRef(artifact_id="artifact-good0000000")])
        verdict = _adjudicator(tmp_path).decide("case", proposal)
        assert verdict.status is VerdictStatus.ACCEPTED
        assert verdict.produced["status"] == "VERIFIED"

    def test_duplicate_claim_is_rejected(self, tmp_path) -> None:
        """Two genuinely distinct proposals (different agent) that happen to
        assert the same claim text are a real duplicate-content case, not a
        replay: they must hash to different proposal_ids and both reach
        _handle_claim, where the text-level duplicate check applies."""
        adjudicator = _adjudicator(tmp_path)
        evidence = [EvidenceRef(artifact_id="artifact-good0000000")]
        first = _proposal(evidence=evidence, agent="agent_one")
        second_proposal = _proposal(evidence=evidence, agent="agent_two")
        assert first.proposal_id != second_proposal.proposal_id
        assert adjudicator.decide("case", first).accepted
        second = adjudicator.decide("case", second_proposal)
        assert second.status is VerdictStatus.REJECTED
        assert RejectionCode.DUPLICATE in second.codes
        assert second.replayed is False

    def test_identical_proposal_replays_instead_of_rerunning(self, tmp_path) -> None:
        """The *same* proposal (identical agent/kind/summary/payload/evidence)
        submitted twice — e.g. a crashed run resubmitting, or a graph retry —
        must not create a second claim. It gets the cached verdict back,
        marked replayed, and the claim registry is written to exactly once."""
        adjudicator = _adjudicator(tmp_path)
        evidence = [EvidenceRef(artifact_id="artifact-good0000000")]
        proposal = _proposal(evidence=evidence)
        first = adjudicator.decide("case", proposal)
        assert first.accepted
        assert first.replayed is False

        replay = adjudicator.decide("case", _proposal(evidence=evidence))
        assert replay.accepted
        assert replay.replayed is True
        assert replay.produced == first.produced
        # exactly one claim was ever created, not two
        assert len(adjudicator.claims.created) == 1

        log = (tmp_path / "agents" / "decisions.jsonl").read_text(encoding="utf-8")
        record_types = [json.loads(line)["record_type"] for line in log.splitlines() if line.strip()]
        assert record_types == ["decision", "replay"]

    def test_draft_claim_escalates_instead_of_passing(self, tmp_path) -> None:
        """Evidence the registry will not verify must reach a human, not the paper."""
        adjudicator = _adjudicator(tmp_path, eligible=())
        proposal = _proposal(
            evidence=[EvidenceRef(artifact_id="artifact-good0000000")],
            asserts_numbers=False,
        )
        verdict = adjudicator.decide("case", proposal)
        assert verdict.status is VerdictStatus.NEEDS_HUMAN

    def test_every_decision_is_logged(self, tmp_path) -> None:
        adjudicator = _adjudicator(tmp_path)
        adjudicator.decide("case", _proposal())
        log = tmp_path / "agents" / "decisions.jsonl"
        assert log.is_file()
        assert "NO_EVIDENCE" in log.read_text(encoding="utf-8")


class _FailingClaims(_FakeClaims):
    """Claims registry whose write silently does not persist -- exercises the
    Adjudicator's write-verification path (WRITE_VERIFICATION_FAILED)."""

    def get(self, case_id: str, claim_id: str) -> dict[str, Any]:
        raise KeyError(claim_id)


class TestWriteVerification:
    def test_claim_write_that_does_not_read_back_downgrades_to_write_failure(self, tmp_path) -> None:
        artifacts = _FakeArtifacts(
            {"artifact-good0000000": {"artifact_id": "artifact-good0000000", "paper_eligible": True}}
        )
        adjudicator = Adjudicator(
            _FakeCases(tmp_path),
            artifacts,  # type: ignore[arg-type]
            _FailingClaims({"artifact-good0000000"}),  # type: ignore[arg-type]
            _FakeFigures(),  # type: ignore[arg-type]
        )
        proposal = _proposal(evidence=[EvidenceRef(artifact_id="artifact-good0000000")])
        verdict = adjudicator.decide("case", proposal)
        assert verdict.status is VerdictStatus.REJECTED
        assert RejectionCode.WRITE_VERIFICATION_FAILED in verdict.codes


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_json_artifact(tmp_path, filename: str, content: dict[str, Any]) -> tuple[str, str]:
    path = tmp_path / filename
    path.write_text(json.dumps(content, ensure_ascii=False), encoding="utf-8")
    return str(path), _sha256_bytes(path.read_bytes())


def _model_selection_fixture(tmp_path, *, candidates=None, eligible=True):
    """Build a protocol artifact + comparison artifact + a WINNER-shaped
    payload/evidence pair, wired so the happy path is accepted by default.
    Individual tests mutate the returned dict to trigger one specific
    RejectionCode at a time."""
    protocol_path, protocol_hash = _write_json_artifact(
        tmp_path,
        "protocol.json",
        {"protocol_id": "artifact-protocol001", "dataset_id": "dataset-x", "primary_metric": "rmse"},
    )
    candidates = candidates if candidates is not None else [
        {
            "candidate_id": "candidate-linear",
            "metric_name": "rmse",
            "metric_value": 54.825,
            "metric_direction": "minimize",
            "fold_metric_values": [50.1, 55.2, 58.3],
            "status": "VALID",
        },
        {
            "candidate_id": "candidate-tree",
            "metric_name": "rmse",
            "metric_value": 60.1,
            "metric_direction": "minimize",
            "fold_metric_values": [58.0, 61.0, 62.0],
            "status": "VALID",
        },
    ]
    comparison_path, comparison_hash = _write_json_artifact(
        tmp_path,
        "comparison.json",
        {
            "protocol_id": "artifact-protocol001",
            "protocol_hash": protocol_hash,
            "candidates": candidates,
        },
    )
    artifact_records = {
        "artifact-protocol001": {
            "artifact_id": "artifact-protocol001",
            "paper_eligible": True,
            "path": protocol_path,
            "sha256": protocol_hash,
        },
        "artifact-comparison1": {
            "artifact_id": "artifact-comparison1",
            "paper_eligible": True,
            "path": comparison_path,
            "sha256": comparison_hash,
        },
    }
    eligible_ids = {"artifact-protocol001", "artifact-comparison1"} if eligible else set()
    adjudicator = Adjudicator(
        _FakeCases(tmp_path),
        _FakeArtifacts(artifact_records),  # type: ignore[arg-type]
        _FakeClaims(eligible_ids),  # type: ignore[arg-type]
        _FakeFigures(),  # type: ignore[arg-type]
    )
    payload = {
        "protocol_id": "artifact-protocol001",
        "protocol_hash": protocol_hash,
        "comparison_artifact_id": "artifact-comparison1",
        "outcome": "WINNER",
        "winner_candidate_id": "candidate-linear",
        "claim_text": "在给定协议下，线性模型 RMSE 为 54.825，为当前最优候选。",
        "claim_type": "model_selection",
    }
    evidence = [
        EvidenceRef(artifact_id="artifact-protocol001", role="protocol"),
        EvidenceRef(artifact_id="artifact-comparison1", role="comparison"),
    ]
    return adjudicator, payload, evidence


def _selection_proposal(payload, evidence, **overrides) -> Proposal:
    base = {
        "kind": ProposalKind.MODEL_SELECTION,
        "agent": "model_judge_agent",
        "summary": "模型选择裁决",
        "payload": payload,
        "evidence": evidence,
        "asserts_numbers": True,
    }
    base.update(overrides)
    return Proposal(**base)


class TestModelSelectionGate:
    """Adjudicator._handle_model_selection: every check must fail with the
    precise RejectionCode for that violation, not a generic REJECTED."""

    def test_valid_winner_is_accepted_and_claim_is_verified(self, tmp_path) -> None:
        adjudicator, payload, evidence = _model_selection_fixture(tmp_path)
        verdict = adjudicator.decide("case", _selection_proposal(payload, evidence))
        assert verdict.status is VerdictStatus.ACCEPTED
        assert verdict.produced["winner_candidate_id"] == "candidate-linear"
        assert verdict.produced["status"] == "VERIFIED"

    def test_no_acceptable_winner_is_accepted_without_a_claim(self, tmp_path) -> None:
        adjudicator, payload, evidence = _model_selection_fixture(tmp_path)
        payload = {**payload, "outcome": "NO_ACCEPTABLE_WINNER"}
        verdict = adjudicator.decide("case", _selection_proposal(payload, evidence))
        assert verdict.status is VerdictStatus.ACCEPTED
        assert "claim_id" not in verdict.produced
        assert len(adjudicator.claims.created) == 0

    def test_tie_is_accepted_without_a_single_winner_claim(self, tmp_path) -> None:
        adjudicator, payload, evidence = _model_selection_fixture(tmp_path)
        payload = {
            **payload,
            "outcome": "TIE",
            "tie_candidate_ids": ["candidate-linear", "candidate-tree"],
        }
        verdict = adjudicator.decide("case", _selection_proposal(payload, evidence))
        assert verdict.status is VerdictStatus.ACCEPTED
        assert verdict.produced["outcome"] == "TIE"
        assert len(adjudicator.claims.created) == 0

    def test_stale_protocol_hash_is_rejected(self, tmp_path) -> None:
        adjudicator, payload, evidence = _model_selection_fixture(tmp_path)
        payload = {**payload, "protocol_hash": "0" * 64}
        verdict = adjudicator.decide("case", _selection_proposal(payload, evidence))
        assert verdict.status is VerdictStatus.REJECTED
        assert RejectionCode.STALE_EVIDENCE in verdict.codes
        assert len(adjudicator.claims.created) == 0

    def test_comparison_from_a_different_protocol_is_rejected(self, tmp_path) -> None:
        adjudicator, payload, evidence = _model_selection_fixture(tmp_path)
        # Point comparison_artifact_id at a comparison built under a *different*
        # protocol artifact than the one cited in payload["protocol_id"].
        other_protocol_path, other_protocol_hash = _write_json_artifact(
            tmp_path, "protocol_other.json", {"protocol_id": "artifact-protocol-other"}
        )
        mismatched_path, mismatched_hash = _write_json_artifact(
            tmp_path,
            "comparison_mismatched.json",
            {
                "protocol_id": "artifact-protocol-other",
                "protocol_hash": other_protocol_hash,
                "candidates": [],
            },
        )
        adjudicator.artifacts._artifacts["artifact-comparison1"] = {
            "artifact_id": "artifact-comparison1",
            "paper_eligible": True,
            "path": mismatched_path,
            "sha256": mismatched_hash,
        }
        verdict = adjudicator.decide("case", _selection_proposal(payload, evidence))
        assert verdict.status is VerdictStatus.REJECTED
        assert RejectionCode.PROTOCOL_MISMATCH in verdict.codes
        assert len(adjudicator.claims.created) == 0

    def test_unknown_winner_candidate_is_rejected(self, tmp_path) -> None:
        adjudicator, payload, evidence = _model_selection_fixture(tmp_path)
        payload = {**payload, "winner_candidate_id": "candidate-does-not-exist"}
        verdict = adjudicator.decide("case", _selection_proposal(payload, evidence))
        assert verdict.status is VerdictStatus.REJECTED
        assert RejectionCode.CANDIDATE_UNKNOWN in verdict.codes
        assert len(adjudicator.claims.created) == 0

    def test_invalid_candidate_cannot_win(self, tmp_path) -> None:
        candidates = [
            {
                "candidate_id": "candidate-linear",
                "metric_name": "rmse",
                "metric_value": 54.825,
                "metric_direction": "minimize",
                "fold_metric_values": [50.1, 55.2, 58.3],
                "status": "INVALID",
            }
        ]
        adjudicator, payload, evidence = _model_selection_fixture(tmp_path, candidates=candidates)
        verdict = adjudicator.decide("case", _selection_proposal(payload, evidence))
        assert verdict.status is VerdictStatus.REJECTED
        assert RejectionCode.CANDIDATE_INVALID in verdict.codes
        assert len(adjudicator.claims.created) == 0

    def test_missing_evaluation_fields_is_rejected(self, tmp_path) -> None:
        candidates = [
            {
                "candidate_id": "candidate-linear",
                "metric_name": "rmse",
                "metric_value": 54.825,
                "metric_direction": "minimize",
                "fold_metric_values": [],
                "status": "VALID",
            }
        ]
        adjudicator, payload, evidence = _model_selection_fixture(tmp_path, candidates=candidates)
        verdict = adjudicator.decide("case", _selection_proposal(payload, evidence))
        assert verdict.status is VerdictStatus.REJECTED
        assert RejectionCode.MISSING_EVALUATION_FIELDS in verdict.codes
        assert len(adjudicator.claims.created) == 0

    def test_missing_metric_direction_is_rejected(self, tmp_path) -> None:
        candidates = [
            {
                "candidate_id": "candidate-linear",
                "metric_name": "rmse",
                "metric_value": 54.825,
                "metric_direction": "",
                "fold_metric_values": [50.1, 55.2, 58.3],
                "status": "VALID",
            }
        ]
        adjudicator, payload, evidence = _model_selection_fixture(tmp_path, candidates=candidates)
        verdict = adjudicator.decide("case", _selection_proposal(payload, evidence))
        assert verdict.status is VerdictStatus.REJECTED
        assert RejectionCode.METRIC_DIRECTION_MISSING in verdict.codes
        assert len(adjudicator.claims.created) == 0

    def test_claim_text_not_citing_the_metric_is_ungrounded(self, tmp_path) -> None:
        adjudicator, payload, evidence = _model_selection_fixture(tmp_path)
        payload = {**payload, "claim_text": "线性模型是最优选择。"}
        verdict = adjudicator.decide("case", _selection_proposal(payload, evidence))
        assert verdict.status is VerdictStatus.REJECTED
        assert RejectionCode.SELECTION_UNGROUNDED in verdict.codes
        assert len(adjudicator.claims.created) == 0

    def test_superiority_claim_contradicted_by_the_evidence_is_rejected(self, tmp_path) -> None:
        # candidate-linear "wins" but its own metric (60.1) is worse than the
        # rival's (54.825) under minimize -- the numbers don't support the claim.
        candidates = [
            {
                "candidate_id": "candidate-linear",
                "metric_name": "rmse",
                "metric_value": 60.1,
                "metric_direction": "minimize",
                "fold_metric_values": [58.0, 61.0, 62.0],
                "status": "VALID",
            },
            {
                "candidate_id": "candidate-tree",
                "metric_name": "rmse",
                "metric_value": 54.825,
                "metric_direction": "minimize",
                "fold_metric_values": [50.1, 55.2, 58.3],
                "status": "VALID",
            },
        ]
        adjudicator, payload, evidence = _model_selection_fixture(tmp_path, candidates=candidates)
        payload = {**payload, "claim_text": "线性模型 RMSE 为 60.1，为当前最优候选。"}
        verdict = adjudicator.decide("case", _selection_proposal(payload, evidence))
        assert verdict.status is VerdictStatus.REJECTED
        assert RejectionCode.UNSUPPORTED_SUPERIORITY_CLAIM in verdict.codes
        assert len(adjudicator.claims.created) == 0

    def test_second_conflicting_winner_for_the_same_comparison_is_rejected(self, tmp_path) -> None:
        adjudicator, payload, evidence = _model_selection_fixture(tmp_path)
        first = adjudicator.decide("case", _selection_proposal(payload, evidence))
        assert first.accepted

        conflicting_payload = {
            **payload,
            "winner_candidate_id": "candidate-tree",
            "claim_text": "树模型 RMSE 为 60.1，为当前最优候选。",
        }
        second = adjudicator.decide(
            "case", _selection_proposal(conflicting_payload, evidence, summary="第二次裁决")
        )
        assert second.status is VerdictStatus.REJECTED
        assert RejectionCode.CONFLICTING_SELECTION in second.codes
        # the first, legitimate winner's claim is untouched -- exactly one
        # claim exists, and it is not overwritten by the rejected attempt.
        assert len(adjudicator.claims.created) == 1

    def test_winner_on_unpromoted_evidence_escalates_instead_of_accepting(self, tmp_path) -> None:
        """Mirrors TestEvidenceGate.test_draft_claim_escalates_instead_of_passing:
        a WINNER outcome whose protocol/comparison artifacts are not yet
        paper_eligible must not be reported as a settled ACCEPTED verdict."""
        adjudicator, payload, evidence = _model_selection_fixture(tmp_path, eligible=False)
        verdict = adjudicator.decide("case", _selection_proposal(payload, evidence))
        assert verdict.status is VerdictStatus.NEEDS_HUMAN
        assert verdict.produced["status"] == "DRAFT"
        assert verdict.produced["winner_candidate_id"] == "candidate-linear"

    def test_identical_model_selection_replays(self, tmp_path) -> None:
        adjudicator, payload, evidence = _model_selection_fixture(tmp_path)
        proposal = _selection_proposal(payload, evidence)
        first = adjudicator.decide("case", proposal)
        assert first.accepted and not first.replayed
        replay = adjudicator.decide("case", _selection_proposal(payload, evidence))
        assert replay.accepted and replay.replayed
        assert len(adjudicator.claims.created) == 1


class TestMandate:
    """An agent cannot propose outside the kinds it declares."""

    class _Overreaching(DeterministicAgent):
        name = "overreaching"
        mandate = (ProposalKind.ANALYSIS_ACTION,)

        def run(self, request: AgentRequest) -> AgentReport:
            return AgentReport(agent=self.name)

    def test_out_of_mandate_proposal_raises(self) -> None:
        with pytest.raises(ValueError):
            self._Overreaching().propose(ProposalKind.CLAIM, "越权结论")

    def test_in_mandate_proposal_is_built(self) -> None:
        proposal = self._Overreaching().propose(ProposalKind.ANALYSIS_ACTION, "相关性分析")
        assert proposal.agent == "overreaching"


class TestNumericDetection:
    class _Agent(DeterministicAgent):
        name = "probe"
        mandate = (ProposalKind.ANALYSIS_ACTION,)

        def run(self, request: AgentRequest) -> AgentReport:
            return AgentReport(agent=self.name)

    def test_number_in_summary_sets_the_flag(self) -> None:
        assert self._Agent().propose(ProposalKind.ANALYSIS_ACTION, "RMSE 为 54.825").asserts_numbers

    def test_number_in_payload_text_sets_the_flag(self) -> None:
        proposal = self._Agent().propose(
            ProposalKind.ANALYSIS_ACTION, "结果摘要", payload={"text": "R2 为 0.4793"}
        )
        assert proposal.asserts_numbers

    def test_prose_without_numbers_does_not(self) -> None:
        assert not self._Agent().propose(ProposalKind.ANALYSIS_ACTION, "检出多重共线性").asserts_numbers


class TestGraphExecution:
    class _Ok(DeterministicAgent):
        name = "ok_agent"
        mandate = (ProposalKind.ANALYSIS_ACTION,)

        def run(self, request: AgentRequest) -> AgentReport:
            return AgentReport(
                agent=self.name,
                proposals=[self.propose(ProposalKind.ANALYSIS_ACTION, "分析完成")],
            )

    class _Blocked(DeterministicAgent):
        name = "blocked_agent"
        mandate = ()

        def run(self, request: AgentRequest) -> AgentReport:
            return self.blocked("上游证据缺失")

    def _state(self) -> dict[str, Any]:
        return {"case_id": "case", "goal": "test", "reports": [], "verdicts": [], "accepted": []}

    def test_sequence_accumulates_accepted_proposals(self, tmp_path) -> None:
        final = run_sequence([self._Ok(), self._Ok()], _adjudicator(tmp_path), self._state())
        assert len(final["accepted"]) == 2
        assert not final.get("halted")

    def test_blocked_agent_halts_the_run(self, tmp_path) -> None:
        agents: list[Agent] = [self._Blocked(), self._Ok()]
        final = run_sequence(agents, _adjudicator(tmp_path), self._state())
        assert final["halted"] is True
        assert "上游证据缺失" in final["halt_reason"]
        # the downstream agent must not have run
        assert len(final["reports"]) == 1

    def test_block_severity_finding_halts_for_human_review(self, tmp_path) -> None:
        class _QA(DeterministicAgent):
            name = "qa"
            mandate = (ProposalKind.REVIEW_FINDING,)

            def run(self, request: AgentRequest) -> AgentReport:
                return AgentReport(
                    agent=self.name,
                    proposals=[
                        self.propose(
                            ProposalKind.REVIEW_FINDING,
                            "章节缺少证据",
                            payload={"severity": "BLOCK", "code": "NO_EVIDENCE"},
                        )
                    ],
                )

        final = run_sequence([_QA(), self._Ok()], _adjudicator(tmp_path), self._state())
        assert final["halted"] is True
        assert len(final["reports"]) == 1

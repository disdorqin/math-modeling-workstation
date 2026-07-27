"""The only component in the agent layer permitted to write to a case.

Every proposal passes three stages:

1. **Replay check** — ``proposal_id`` is a content hash (see
   :class:`~mathworkstation.agents.contracts.Proposal`), so a proposal with
   identical agent/kind/summary/payload/evidence submitted twice — after a
   crash, a graph re-run, a retried node — is recognised as the *same*
   proposal. Its side effects run exactly once, at the first decision; every
   later submission gets the cached :class:`Verdict` back with ``replayed``
   set, and a ``replay`` audit record, never a second registry write.
2. **Admissibility** — generic checks that apply to every kind. A proposal
   that asserts numbers without registered, paper-eligible evidence is
   refused here, before any handler runs. This is the mechanical form of
   "No Evidence, No Claim": it does not depend on the proposing model
   behaving well. ``MODEL_SELECTION`` is exempted from the paper-eligible
   check — see the note on that handler for why.
3. **Handler** — a per-kind function that calls the *existing* services. The
   agent layer adds no second way to mutate a case; it reuses the claim
   registry, the figure registry, and the workflow controller, so
   agent-driven runs and manual CLI runs converge on the same audit records.
   Every write a handler makes is immediately read back before the verdict is
   returned ``ACCEPTED`` — see ``_verified_claim`` / ``_verified_figure`` —
   so an ``ACCEPTED`` verdict and a missing registry entry cannot coexist:
   if the read-back fails, the verdict downgrades to
   ``WRITE_VERIFICATION_FAILED`` instead.

Every verdict, accepted, rejected, or replayed, is appended to
``agents/decisions.jsonl``. That file is the durable index: nothing is kept
only in memory, so replay detection survives a process restart.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from ..artifact_registry import ArtifactRegistry
from ..case_manager import CaseManager
from ..claims import ClaimInput, ClaimRegistry
from ..figure_registry import FigureRegistry
from ..io_utils import append_jsonl, read_json
from .contracts import Proposal, ProposalKind, RejectionCode, Verdict, VerdictStatus

#: Kinds whose handler performs its own, more specific evidence validation and
#: is therefore exempt from the blanket "numeric assertion needs paper_eligible
#: evidence" rule. A MODEL_SELECTION proposal cites the *internal* protocol and
#: comparison artifacts that justify a decision, not artifacts a human has
#: already promoted for citation — requiring promotion first would make it
#: impossible for a selection to ever be the reason something gets promoted.
_ADMISSIBILITY_EXEMPT = {ProposalKind.MODEL_SELECTION}


class Adjudicator:
    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        claims: ClaimRegistry,
        figures: FigureRegistry,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.claims = claims
        self.figures = figures
        self._handlers: dict[ProposalKind, Callable[[str, Proposal], Verdict]] = {
            ProposalKind.CLAIM: self._handle_claim,
            ProposalKind.FIGURE_REQUEST: self._handle_figure,
            ProposalKind.REVIEW_FINDING: self._handle_review_finding,
            ProposalKind.MODEL_SELECTION: self._handle_model_selection,
            ProposalKind.DECOMPOSITION: self._handle_advisory,
            ProposalKind.ANALYSIS_ACTION: self._handle_advisory,
            ProposalKind.DATA_ACTION: self._handle_advisory,
            ProposalKind.REPAIR_REQUEST: self._handle_advisory,
        }

    # ------------------------------------------------------------------ public

    def decide(self, case_id: str, proposal: Proposal) -> Verdict:
        original = self._find_original_decision(case_id, proposal.proposal_id)
        if original is not None:
            replay = original.model_copy(update={"replayed": True})
            self._record(case_id, proposal, replay, record_type="replay")
            return replay

        verdict = self._admissibility(case_id, proposal)
        if verdict is None:
            handler = self._handlers.get(proposal.kind)
            if handler is None:
                verdict = Verdict(
                    proposal_id=proposal.proposal_id,
                    status=VerdictStatus.NEEDS_HUMAN,
                    codes=[RejectionCode.APPROVAL_REQUIRED],
                    message=f"no automatic handler for {proposal.kind}; route to a human",
                )
            else:
                verdict = handler(case_id, proposal)
        self._record(case_id, proposal, verdict, record_type="decision")
        return verdict

    def decide_all(self, case_id: str, proposals: list[Proposal]) -> list[Verdict]:
        return [self.decide(case_id, proposal) for proposal in proposals]

    # ----------------------------------------------------------------- replay

    def _find_original_decision(self, case_id: str, proposal_id: str) -> Verdict | None:
        """Return the first non-replay verdict ever recorded for this id, if any."""
        for record in self._load_decisions(case_id):
            if record.get("record_type", "decision") != "decision":
                continue
            if record["proposal"]["proposal_id"] != proposal_id:
                continue
            return Verdict.model_validate(record["verdict"])
        return None

    def _load_decisions(self, case_id: str) -> list[dict[str, Any]]:
        path = self._decisions_path(case_id)
        if not path.is_file():
            return []
        records = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if line:
                    records.append(json.loads(line))
        return records

    def _decisions_path(self, case_id: str) -> Path:
        return self.cases.case_root(case_id) / "agents" / "decisions.jsonl"

    # ----------------------------------------------------------- admissibility

    def _admissibility(self, case_id: str, proposal: Proposal) -> Verdict | None:
        """Return a refusal verdict, or ``None`` when the proposal may proceed."""
        codes: list[RejectionCode] = []
        details: list[str] = []

        known: dict[str, dict[str, Any]] = {}
        for artifact_id in proposal.evidence_artifact_ids:
            try:
                known[artifact_id] = self.artifacts.get(case_id, artifact_id)
            except KeyError:
                codes.append(RejectionCode.EVIDENCE_UNKNOWN)
                details.append(artifact_id)

        if proposal.asserts_numbers and proposal.kind not in _ADMISSIBILITY_EXEMPT:
            if not proposal.evidence:
                codes.append(RejectionCode.NO_EVIDENCE)
                details.append("numeric assertion carries no evidence")
            not_ready = [
                artifact_id
                for artifact_id, artifact in known.items()
                if not artifact.get("paper_eligible", False)
            ]
            if not_ready:
                codes.append(RejectionCode.EVIDENCE_NOT_PAPER_READY)
                details.extend(not_ready)
        elif proposal.kind in _ADMISSIBILITY_EXEMPT and not proposal.evidence:
            # Still not a free pass: a selection with zero cited evidence is
            # meaningless regardless of the paper_eligible exemption.
            codes.append(RejectionCode.NO_EVIDENCE)
            details.append("model selection carries no evidence")

        if not codes:
            return None
        return Verdict(
            proposal_id=proposal.proposal_id,
            status=VerdictStatus.REJECTED,
            codes=sorted(set(codes)),
            message="; ".join(details),
        )

    # ---------------------------------------------------------------- handlers

    def _handle_claim(self, case_id: str, proposal: Proposal) -> Verdict:
        payload = proposal.payload
        text = str(payload.get("text", "")).strip()
        if len(text) < 3:
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.REJECTED,
                codes=[RejectionCode.SCHEMA_INVALID],
                message="claim text is empty",
            )
        if not proposal.evidence:
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.REJECTED,
                codes=[RejectionCode.NO_EVIDENCE],
                message="a claim requires at least one evidence artifact",
            )
        existing = {item["text"] for item in self.claims.list_claims(case_id)}
        if text in existing:
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.REJECTED,
                codes=[RejectionCode.DUPLICATE],
                message="an identical claim is already registered",
            )
        try:
            claim = self.claims.create(
                case_id,
                ClaimInput(
                    text=text,
                    claim_type=str(payload.get("claim_type", "model_result")),
                    evidence_artifact_ids=proposal.evidence_artifact_ids,
                    dataset_ids=list(payload.get("dataset_ids", [])),
                    section_hint=payload.get("section_hint"),
                ),
                created_by=f"agent:{proposal.agent}",
            )
        except Exception as error:  # noqa: BLE001 - surfaced as a stable verdict
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.REJECTED,
                codes=[RejectionCode.SCHEMA_INVALID],
                message=f"{type(error).__name__}: {error}",
            )
        verified = self._verified_claim(case_id, claim["claim_id"], claim["status"])
        if verified is None:
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.REJECTED,
                codes=[RejectionCode.WRITE_VERIFICATION_FAILED],
                message=f"claim {claim['claim_id']} did not read back as {claim['status']} after write",
            )
        # The registry itself decides VERIFIED vs DRAFT from evidence eligibility;
        # a DRAFT claim is surfaced for a human rather than silently accepted.
        if verified["status"] != "VERIFIED":
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.NEEDS_HUMAN,
                codes=[RejectionCode.EVIDENCE_NOT_PAPER_READY],
                message=f"claim registered as {verified['status']}",
                produced={"claim_id": verified["claim_id"], "status": verified["status"]},
            )
        return Verdict(
            proposal_id=proposal.proposal_id,
            status=VerdictStatus.ACCEPTED,
            message="claim registered and verified",
            produced={"claim_id": verified["claim_id"], "status": verified["status"]},
        )

    def _handle_figure(self, case_id: str, proposal: Proposal) -> Verdict:
        figure_id = str(proposal.payload.get("figure_id", ""))
        approval_artifact_id = str(proposal.payload.get("approval_artifact_id", ""))
        if not figure_id or not approval_artifact_id:
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.REJECTED,
                codes=[RejectionCode.SCHEMA_INVALID],
                message="figure promotion needs figure_id and approval_artifact_id",
            )
        try:
            figure = self.figures.promote(
                case_id,
                figure_id,
                approval_artifact_id,
                approved_by=f"agent:{proposal.agent}",
                note=proposal.rationale or proposal.summary,
            )
        except Exception as error:  # noqa: BLE001
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.REJECTED,
                codes=[RejectionCode.SCHEMA_INVALID],
                message=f"{type(error).__name__}: {error}",
            )
        verified = self._verified_figure(case_id, figure["figure_id"], figure["status"])
        if verified is None:
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.REJECTED,
                codes=[RejectionCode.WRITE_VERIFICATION_FAILED],
                message=f"figure {figure['figure_id']} did not read back as {figure['status']} after write",
            )
        return Verdict(
            proposal_id=proposal.proposal_id,
            status=VerdictStatus.ACCEPTED,
            message="figure promoted to paper evidence",
            produced={"figure_id": verified["figure_id"], "status": verified["status"]},
        )

    def _handle_model_selection(self, case_id: str, proposal: Proposal) -> Verdict:
        """Adjudicate a judge's WINNER / TIE / NO_ACCEPTABLE_WINNER verdict.

        This handler, not any modeling agent, is the only place a "model X won"
        claim can enter the case. The judge only *proposes*; every check below
        exists because a plausible-sounding proposal can still be wrong in a
        specific, nameable way, and a generic REJECTED tells nobody which way.

        Expected ``payload`` keys (produced by ``model_judge_agent``, see
        ``agents/modeling.py``):

        - ``protocol_id`` / ``protocol_hash``: the immutable protocol every
          candidate was evaluated under.
        - ``comparison_artifact_id``: the artifact holding all candidates'
          evaluation results (one record per candidate, each carrying its own
          ``protocol_id``/``protocol_hash`` and a ``status`` of ``VALID`` or
          ``INVALID``).
        - ``outcome``: ``"WINNER"``, ``"TIE"``, or ``"NO_ACCEPTABLE_WINNER"``.
        - ``winner_candidate_id`` (outcome WINNER): the accepted candidate.
        - ``tie_candidate_ids`` (outcome TIE): candidates judged equivalent.
        - ``claim_text`` (outcome WINNER only): the exact sentence to register
          as a claim; must reference the winning metric value so the claim is
          traceable back to the evidence that grounds it, not just the judge's
          prose.
        Evidence must include the protocol artifact (role ``protocol``) and the
        comparison artifact (role ``comparison``).
        """
        payload = proposal.payload
        protocol_id = str(payload.get("protocol_id", ""))
        protocol_hash = str(payload.get("protocol_hash", ""))
        comparison_artifact_id = str(payload.get("comparison_artifact_id", ""))
        outcome = str(payload.get("outcome", ""))

        if outcome not in {"WINNER", "TIE", "NO_ACCEPTABLE_WINNER"}:
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.REJECTED,
                codes=[RejectionCode.SCHEMA_INVALID],
                message=f"unknown model-selection outcome: {outcome!r}",
            )
        if not protocol_id or not protocol_hash or not comparison_artifact_id:
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.REJECTED,
                codes=[RejectionCode.SCHEMA_INVALID],
                message="model selection requires protocol_id, protocol_hash, comparison_artifact_id",
            )

        try:
            protocol_artifact = self.artifacts.get(case_id, protocol_id)
        except KeyError:
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.REJECTED,
                codes=[RejectionCode.EVIDENCE_UNKNOWN],
                message=f"protocol artifact not found: {protocol_id}",
            )
        if str(protocol_artifact.get("sha256", protocol_artifact.get("hash", ""))) != protocol_hash:
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.REJECTED,
                codes=[RejectionCode.STALE_EVIDENCE],
                message=f"protocol_hash does not match the currently registered {protocol_id}",
            )

        try:
            comparison_artifact = self.artifacts.get(case_id, comparison_artifact_id)
        except KeyError:
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.REJECTED,
                codes=[RejectionCode.EVIDENCE_UNKNOWN],
                message=f"comparison artifact not found: {comparison_artifact_id}",
            )
        comparison = self._read_artifact_content(case_id, comparison_artifact)
        if comparison is None:
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.REJECTED,
                codes=[RejectionCode.SCHEMA_INVALID],
                message=f"comparison artifact {comparison_artifact_id} is not readable JSON",
            )
        if (
            str(comparison.get("protocol_id", "")) != protocol_id
            or str(comparison.get("protocol_hash", "")) != protocol_hash
        ):
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.REJECTED,
                codes=[RejectionCode.PROTOCOL_MISMATCH],
                message="comparison artifact was produced under a different protocol",
            )

        candidates = {
            str(item.get("candidate_id", "")): item for item in comparison.get("candidates", [])
        }

        if outcome == "NO_ACCEPTABLE_WINNER":
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.ACCEPTED,
                message="no candidate met the protocol's acceptance criteria; no claim written",
                produced={"outcome": outcome, "comparison_artifact_id": comparison_artifact_id},
            )

        if outcome == "TIE":
            tie_ids = [str(cid) for cid in payload.get("tie_candidate_ids", [])]
            if len(tie_ids) < 2:
                return Verdict(
                    proposal_id=proposal.proposal_id,
                    status=VerdictStatus.REJECTED,
                    codes=[RejectionCode.SCHEMA_INVALID],
                    message="a TIE outcome requires at least two tie_candidate_ids",
                )
            for candidate_id in tie_ids:
                bad = self._invalid_candidate_code(candidates.get(candidate_id))
                if bad is not None:
                    return Verdict(
                        proposal_id=proposal.proposal_id,
                        status=VerdictStatus.REJECTED,
                        codes=[bad],
                        message=f"tie candidate {candidate_id} failed validation",
                    )
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.ACCEPTED,
                message="tie recorded; no single winner claim written",
                produced={"outcome": outcome, "tie_candidate_ids": tie_ids},
            )

        # outcome == "WINNER"
        winner_id = str(payload.get("winner_candidate_id", ""))
        candidate = candidates.get(winner_id)
        bad = self._invalid_candidate_code(candidate)
        if bad is not None:
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.REJECTED,
                codes=[bad],
                message=f"winner_candidate_id {winner_id!r} failed validation",
            )

        conflict = self._conflicting_selection(case_id, comparison_artifact_id, winner_id)
        if conflict is not None:
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.REJECTED,
                codes=[RejectionCode.CONFLICTING_SELECTION],
                message=f"comparison {comparison_artifact_id} already has an accepted winner: {conflict}",
            )

        claim_text = str(payload.get("claim_text", "")).strip()
        metric_value = candidate.get("metric_value")
        metric_token = self._format_metric(metric_value)
        if not claim_text or (metric_token and metric_token not in claim_text):
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.REJECTED,
                codes=[RejectionCode.SELECTION_UNGROUNDED],
                message="claim_text does not cite the winning candidate's metric value",
            )

        superiority_error = self._check_superiority_claim(claim_text, candidate, candidates)
        if superiority_error:
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.REJECTED,
                codes=[RejectionCode.UNSUPPORTED_SUPERIORITY_CLAIM],
                message=superiority_error,
            )

        try:
            claim = self.claims.create(
                case_id,
                ClaimInput(
                    text=claim_text,
                    claim_type=str(payload.get("claim_type", "model_selection")),
                    evidence_artifact_ids=proposal.evidence_artifact_ids,
                    dataset_ids=list(payload.get("dataset_ids", [])),
                    section_hint=payload.get("section_hint"),
                ),
                created_by=f"agent:{proposal.agent}",
            )
        except Exception as error:  # noqa: BLE001
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.REJECTED,
                codes=[RejectionCode.SCHEMA_INVALID],
                message=f"{type(error).__name__}: {error}",
            )
        verified = self._verified_claim(case_id, claim["claim_id"], claim["status"])
        if verified is None:
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.REJECTED,
                codes=[RejectionCode.WRITE_VERIFICATION_FAILED],
                message=f"claim {claim['claim_id']} did not read back as {claim['status']} after write",
            )
        # Same rule as _handle_claim: the registry, not this handler, decides
        # VERIFIED vs DRAFT from evidence eligibility. A DRAFT model-selection
        # claim (protocol/comparison artifacts not yet promoted) is surfaced
        # for a human, not reported as a settled ACCEPTED winner.
        if verified["status"] != "VERIFIED":
            return Verdict(
                proposal_id=proposal.proposal_id,
                status=VerdictStatus.NEEDS_HUMAN,
                codes=[RejectionCode.EVIDENCE_NOT_PAPER_READY],
                message=f"model-selection claim registered as {verified['status']}",
                produced={
                    "claim_id": verified["claim_id"],
                    "status": verified["status"],
                    "winner_candidate_id": winner_id,
                    "comparison_artifact_id": comparison_artifact_id,
                },
            )
        return Verdict(
            proposal_id=proposal.proposal_id,
            status=VerdictStatus.ACCEPTED,
            message=f"model selection recorded: {winner_id} wins under protocol {protocol_id}",
            produced={
                "claim_id": verified["claim_id"],
                "status": verified["status"],
                "winner_candidate_id": winner_id,
                "comparison_artifact_id": comparison_artifact_id,
            },
        )

    def _invalid_candidate_code(self, candidate: dict[str, Any] | None) -> RejectionCode | None:
        if candidate is None:
            return RejectionCode.CANDIDATE_UNKNOWN
        if str(candidate.get("status", "")).upper() != "VALID":
            return RejectionCode.CANDIDATE_INVALID
        required = ("metric_name", "metric_value", "fold_metric_values")
        if any(candidate.get(field) in (None, "", []) for field in required):
            return RejectionCode.MISSING_EVALUATION_FIELDS
        if not candidate.get("metric_direction"):
            return RejectionCode.METRIC_DIRECTION_MISSING
        return None

    def _conflicting_selection(
        self, case_id: str, comparison_artifact_id: str, winner_id: str
    ) -> str | None:
        """Return the already-accepted winner for this comparison, if it differs."""
        for record in self._load_decisions(case_id):
            if record.get("record_type", "decision") != "decision":
                continue
            if record.get("kind") != ProposalKind.MODEL_SELECTION.value:
                continue
            verdict = record.get("verdict", {})
            if verdict.get("status") != VerdictStatus.ACCEPTED.value:
                continue
            produced = verdict.get("produced", {})
            if produced.get("comparison_artifact_id") != comparison_artifact_id:
                continue
            other_winner = produced.get("winner_candidate_id")
            if other_winner and other_winner != winner_id:
                return str(other_winner)
        return None

    @staticmethod
    def _format_metric(value: Any) -> str:
        """Render a metric value the same way a claim's prose would cite it.

        ``claim_text`` must contain this exact token — that is the mechanical
        part of "grounded in evidence": a judge cannot write a claim about a
        number it never actually looked up.
        """
        if value is None:
            return ""
        if isinstance(value, float):
            text = f"{value:.3f}"
            return text.rstrip("0").rstrip(".") if "." in text else text
        return str(value)

    #: Relative margin under which a winner is allowed to be marginally worse
    #: than a rival without triggering UNSUPPORTED_SUPERIORITY_CLAIM. A judge
    #: is entitled to apply a "simpler wins under a near-tie" rule (see
    #: ``agents/modeling.py::ModelJudgeAgent``); this check exists to catch a
    #: claim that is *actually* contradicted by the evidence (winner clearly
    #: worse than a rival), not to force every winner to be the strict best.
    _SUPERIORITY_TOLERANCE = 0.01

    def _check_superiority_claim(
        self, claim_text: str, winner: dict[str, Any], candidates: dict[str, dict[str, Any]]
    ) -> str | None:
        """Reject a claim whose winner is *meaningfully* worse than a rival
        under the declared metric direction -- a tie within tolerance is a
        legitimate judge decision; a clear reversal is not."""
        direction = str(winner.get("metric_direction", "")).lower()
        winner_value = winner.get("metric_value")
        if direction not in {"minimize", "maximize"} or not isinstance(winner_value, (int, float)):
            return None
        for candidate_id, candidate in candidates.items():
            if candidate is winner:
                continue
            if str(candidate.get("status", "")).upper() != "VALID":
                continue
            rival_value = candidate.get("metric_value")
            if not isinstance(rival_value, (int, float)):
                continue
            denominator = abs(rival_value) or 1.0
            # positive => winner at least as good as this rival; negative => worse.
            relative_margin = (
                (rival_value - winner_value) / denominator
                if direction == "minimize"
                else (winner_value - rival_value) / denominator
            )
            if relative_margin < -self._SUPERIORITY_TOLERANCE:
                return (
                    f"winner metric_value={winner_value} is meaningfully worse than "
                    f"{candidate_id}'s {rival_value} under direction={direction} "
                    f"(relative_margin={relative_margin:.4f})"
                )
        return None

    def _read_artifact_content(self, case_id: str, artifact: dict[str, Any]) -> dict[str, Any] | None:
        path = artifact.get("path")
        if not path:
            return None
        try:
            content = read_json(self.cases.case_root(case_id) / path)
        except Exception:  # noqa: BLE001 - any read failure means "not usable as evidence"
            return None
        return content if isinstance(content, dict) else None

    # ------------------------------------------------------------ write-verify

    def _verified_claim(self, case_id: str, claim_id: str, expected_status: str) -> dict[str, Any] | None:
        """Read the claim back; return it only if the write is actually visible.

        A registry write that does not read back (crash mid-write, a bug in the
        registry) must never be reported as ACCEPTED — that would be an audited
        claim with nothing behind it, the exact failure this layer exists to
        prevent.
        """
        try:
            claim = self.claims.get(case_id, claim_id)
        except KeyError:
            return None
        if claim.get("status") != expected_status:
            return None
        return claim

    def _verified_figure(self, case_id: str, figure_id: str, expected_status: str) -> dict[str, Any] | None:
        try:
            figure = self.figures.get(case_id, figure_id)
        except KeyError:
            return None
        if figure.get("status") != expected_status:
            return None
        return figure

    def _handle_review_finding(self, case_id: str, proposal: Proposal) -> Verdict:
        """Findings are always recorded; severity decides whether a human is pulled in."""
        severity = str(proposal.payload.get("severity", "REVIEW")).upper()
        status = VerdictStatus.NEEDS_HUMAN if severity == "BLOCK" else VerdictStatus.ACCEPTED
        return Verdict(
            proposal_id=proposal.proposal_id,
            status=status,
            codes=[RejectionCode.APPROVAL_REQUIRED] if status is VerdictStatus.NEEDS_HUMAN else [],
            message=proposal.summary,
            produced={"severity": severity, "code": proposal.payload.get("code", "")},
        )

    def _handle_advisory(self, case_id: str, proposal: Proposal) -> Verdict:
        """Kinds that inform later stages without mutating the case on their own."""
        return Verdict(
            proposal_id=proposal.proposal_id,
            status=VerdictStatus.ACCEPTED,
            message="recorded as advisory input",
            produced=dict(proposal.payload),
        )

    # ----------------------------------------------------------------- logging

    def _record(
        self, case_id: str, proposal: Proposal, verdict: Verdict, *, record_type: str = "decision"
    ) -> None:
        path = self._decisions_path(case_id)
        append_jsonl(
            path,
            {
                "schema_version": 1,
                "record_type": record_type,
                "case_id": case_id,
                "agent": proposal.agent,
                "kind": proposal.kind.value,
                "proposal": proposal.model_dump(mode="json"),
                "verdict": verdict.model_dump(mode="json"),
            },
        )

"""Typed contracts exchanged between agents, the graph, and the adjudicator.

These models are the entire agent API surface. An agent that cannot express what
it wants as a :class:`Proposal` cannot affect the case, which is deliberate: it
keeps the set of things a model can change small enough to audit.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, Literal, TypedDict

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ..io_utils import now_iso


class ProposalKind(StrEnum):
    """What an agent is asking the workstation to do."""

    DECOMPOSITION = "DECOMPOSITION"          # subproblem breakdown of the statement
    DATA_ACTION = "DATA_ACTION"              # profile / clean / re-register a dataset
    ANALYSIS_ACTION = "ANALYSIS_ACTION"      # run EDA or a diagnostic
    MODEL_PLAN = "MODEL_PLAN"                # candidate models and validation protocol
    EXPERIMENT_REQUEST = "EXPERIMENT_REQUEST"  # execute a registered protocol
    FIGURE_REQUEST = "FIGURE_REQUEST"        # render or promote a figure
    CLAIM = "CLAIM"                          # assert a fact backed by evidence
    SECTION_DRAFT = "SECTION_DRAFT"          # prose for one paper section
    REVIEW_FINDING = "REVIEW_FINDING"        # a defect found by a reviewer agent
    REPAIR_REQUEST = "REPAIR_REQUEST"        # upstream work needed before writing
    MODEL_SELECTION = "MODEL_SELECTION"      # a judge's evidence-grounded winner/tie/no-winner verdict


class VerdictStatus(StrEnum):
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    NEEDS_HUMAN = "NEEDS_HUMAN"


class RejectionCode(StrEnum):
    """Stable reasons a proposal was refused. Never free text — these are asserted on."""

    NO_EVIDENCE = "NO_EVIDENCE"                    # numeric assertion with no artifact behind it
    EVIDENCE_NOT_PAPER_READY = "EVIDENCE_NOT_PAPER_READY"
    EVIDENCE_UNKNOWN = "EVIDENCE_UNKNOWN"          # cited artifact id does not exist
    OUT_OF_SCOPE = "OUT_OF_SCOPE"                  # agent proposed outside its mandate
    DEPENDENCY_UNMET = "DEPENDENCY_UNMET"          # required DAG node not success-like
    BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"        # routed to a human, not refused
    DUPLICATE = "DUPLICATE"
    WRITE_VERIFICATION_FAILED = "WRITE_VERIFICATION_FAILED"  # registry write did not read back

    # --- model-selection gate (agents/modeling.py, Adjudicator._handle_model_selection) ---
    PROTOCOL_MISMATCH = "PROTOCOL_MISMATCH"                  # candidates evaluated under different protocols
    CANDIDATE_UNKNOWN = "CANDIDATE_UNKNOWN"                  # selected candidate absent from the comparison
    CANDIDATE_INVALID = "CANDIDATE_INVALID"                  # selected candidate failed evaluation validity
    STALE_EVIDENCE = "STALE_EVIDENCE"                        # referenced artifact hash no longer matches
    METRIC_DIRECTION_MISSING = "METRIC_DIRECTION_MISSING"
    MISSING_EVALUATION_FIELDS = "MISSING_EVALUATION_FIELDS"
    UNSUPPORTED_SUPERIORITY_CLAIM = "UNSUPPORTED_SUPERIORITY_CLAIM"  # claimed delta does not match evidence
    SELECTION_UNGROUNDED = "SELECTION_UNGROUNDED"            # rationale does not cite the comparison evidence
    CONFLICTING_SELECTION = "CONFLICTING_SELECTION"          # a different winner is already decided for this comparison


class EvidenceRef(BaseModel):
    """A pointer to something already registered in the case."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str = Field(min_length=3)
    role: str = Field(default="support", min_length=2)
    excerpt: str = ""


#: Sentinel the default_factory writes; replaced by a content hash post-validation.
#: Any caller that supplies its own non-sentinel proposal_id keeps it verbatim —
#: tests that need two *distinct* proposals with identical content set this
#: explicitly rather than relying on randomness.
_PENDING_ID = "proposal-pending"


class Proposal(BaseModel):
    """One unit of work an agent wants adjudicated.

    ``payload`` stays loosely typed on purpose: each :class:`ProposalKind` has its
    own handler in the adjudicator, and adding a kind must not require changing
    this model. What is *not* loose is ``evidence``: any proposal carrying a
    numeric assertion is rejected without it.

    ``proposal_id`` is a content hash, not a random uuid. Two proposals with the
    same agent, kind, summary, payload, and evidence are the *same proposal* by
    definition — that is what lets the adjudicator recognise a replay (task
    resubmitted after a crash, a graph re-run) and answer it idempotently
    instead of re-running side effects. ``created_at`` is deliberately excluded
    from the hash: it is wall-clock and must not affect identity.
    """

    model_config = ConfigDict(extra="forbid")

    proposal_id: str = Field(default=_PENDING_ID)
    kind: ProposalKind
    agent: str = Field(min_length=2)
    summary: str = Field(min_length=3)
    payload: dict[str, Any] = Field(default_factory=dict)
    evidence: list[EvidenceRef] = Field(default_factory=list)
    asserts_numbers: bool = False
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    rationale: str = ""
    created_at: str = Field(default_factory=now_iso)

    @model_validator(mode="after")
    def _assign_content_id(self) -> "Proposal":
        if self.proposal_id == _PENDING_ID:
            self.proposal_id = f"proposal-{self._content_hash()}"
        return self

    def _content_hash(self) -> str:
        canonical = {
            "kind": self.kind.value,
            "agent": self.agent,
            "summary": self.summary,
            "payload": self.payload,
            "evidence": sorted(f"{item.artifact_id}:{item.role}" for item in self.evidence),
        }
        blob = json.dumps(canonical, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
        return hashlib.sha256(blob).hexdigest()[:16]

    @property
    def evidence_artifact_ids(self) -> list[str]:
        return [item.artifact_id for item in self.evidence]


class Verdict(BaseModel):
    """The adjudicator's decision on one proposal."""

    model_config = ConfigDict(extra="forbid")

    proposal_id: str
    status: VerdictStatus
    codes: list[RejectionCode] = Field(default_factory=list)
    message: str = ""
    produced: dict[str, Any] = Field(default_factory=dict)
    decided_at: str = Field(default_factory=now_iso)
    #: True when this Verdict was served from the replay cache rather than
    #: freshly decided — the proposal's side effects (if any) ran exactly once,
    #: at the original decision.
    replayed: bool = False

    @property
    def accepted(self) -> bool:
        return self.status is VerdictStatus.ACCEPTED


class AgentRequest(BaseModel):
    """Read-only context handed to an agent. Deliberately contains no writers."""

    model_config = ConfigDict(extra="forbid")

    case_id: str
    session_id: str | None = None
    goal: str = Field(min_length=3)
    inputs: dict[str, Any] = Field(default_factory=dict)
    evidence_index: list[dict[str, Any]] = Field(default_factory=list)
    remaining_tokens: int | None = None


class AgentReport(BaseModel):
    """What an agent returns: proposals plus its own account of what it did."""

    model_config = ConfigDict(extra="forbid")

    agent: str
    status: Literal["OK", "BLOCKED", "SKIPPED"] = "OK"
    proposals: list[Proposal] = Field(default_factory=list)
    notes: str = ""
    blocked_reason: str = ""


class WorkstationState(TypedDict, total=False):
    """Graph state.

    Kept flat and JSON-serialisable so the same dict works as LangGraph state, as
    a checkpoint on disk, and as the fallback runner's accumulator.
    """

    case_id: str
    session_id: str | None
    dataset_id: str | None
    target_column: str | None
    goal: str
    reports: list[dict[str, Any]]
    verdicts: list[dict[str, Any]]
    accepted: list[dict[str, Any]]
    blocked: list[str]
    halted: bool
    halt_reason: str

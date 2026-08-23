from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .io_utils import atomic_write_json, now_iso
from .modeling_brain import ModelingBrainDecision
from .model_spine import ModelSpineNode


ConsensusGate = Literal["PASS", "REVIEW", "BLOCKED"]
CandidateDisposition = Literal["EXPERIMENT_PRIORITY", "SHORTLIST", "RESEARCH_GAP", "REJECT"]


class DebateCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    method: str
    source: str
    feasibility: str
    retrieval_score: float = 0.0
    rationale: str = ""


class ModelDebatePacket(BaseModel):
    """Backend-neutral packet for a multi-agent modeling debate.

    The packet deliberately contains no pre-selected winner. It exposes the
    candidate search space, the whole-problem role of the current question and
    the review rubric so cloud agents or local deterministic agents can critique
    the same objects without changing the evidence boundary.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str
    subproblem_id: str
    task_family: str
    question_role: str = ""
    inheritance_kind: str = ""
    inherited_from: list[str] = Field(default_factory=list)
    candidates: list[DebateCandidate] = Field(default_factory=list)
    review_dimensions: dict[str, float]
    agent_roles: list[dict[str, str]]
    principles: list[str]
    generated_at: str


class CandidateDebateReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_id: str = Field(min_length=1)
    reviewer_role: str = Field(min_length=1)
    candidate_id: str = Field(min_length=1)
    scores: dict[str, float]
    complexity_burden: float = Field(ge=0.0, le=1.0)
    objections: list[str] = Field(default_factory=list)
    falsification_test: str = Field(min_length=3)

    @model_validator(mode="after")
    def validate_scores(self) -> "CandidateDebateReview":
        for name, value in self.scores.items():
            if not 0.0 <= float(value) <= 1.0:
                raise ValueError(f"review score out of range: {name}={value}")
        return self


class ConsensusCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    method: str
    feasibility: str
    weighted_score: float | None = None
    complexity_burden: float | None = None
    reviewer_count: int = 0
    disposition: CandidateDisposition
    objections: list[str] = Field(default_factory=list)
    falsification_tests: list[str] = Field(default_factory=list)


class ModelCandidateConsensus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str
    subproblem_id: str
    gate: ConsensusGate
    preferred_experiment_candidate_id: str | None = None
    shortlist_candidate_ids: list[str] = Field(default_factory=list)
    candidates: list[ConsensusCandidate] = Field(default_factory=list)
    distinct_reviewers: list[str] = Field(default_factory=list)
    rationale: str
    generated_at: str


class ModelCandidateConsensusEngine:
    """Aggregate model-agent debate without pretending that debate is evidence.

    This layer answers only: *which executable candidate deserves the next fair
    experiment?* It never changes ProblemGraph.selected_method, never invents a
    metric and never overrides solver/validation results. This separation follows
    the same principle as blind experiment gates in autonomous-research systems:
    ideas may be proposed qualitatively, but adoption requires executed evidence.
    """

    def __init__(self, config_path: str | Path | None = None) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.config_path = Path(config_path) if config_path else (
            repo_root / "config" / "ref_models" / "model_candidate_consensus_v1.json"
        )
        self.policy = json.loads(self.config_path.read_text(encoding="utf-8"))
        if int(self.policy.get("schema_version", 0)) != 1:
            raise ValueError("MODEL_CANDIDATE_CONSENSUS_V1_REQUIRED")
        self.weights = {str(key): float(value) for key, value in (self.policy.get("review_dimensions") or {}).items()}
        if not self.weights or abs(sum(self.weights.values()) - 1.0) > 1e-6:
            raise ValueError("MODEL_CONSENSUS_REVIEW_WEIGHTS_MUST_SUM_TO_ONE")

    def build_packet(
        self,
        decision: ModelingBrainDecision,
        *,
        spine_node: ModelSpineNode | None = None,
    ) -> ModelDebatePacket:
        candidates = [
            DebateCandidate(
                candidate_id=item.candidate_id,
                method=item.method,
                source=item.source,
                feasibility=item.feasibility,
                retrieval_score=float(item.retrieval_score),
                rationale=item.rationale,
            )
            for item in decision.candidates
            if item.feasibility != "REJECT"
        ]
        return ModelDebatePacket(
            case_id=decision.case_id,
            subproblem_id=decision.subproblem_id,
            task_family=decision.task_family,
            question_role=(spine_node.role if spine_node else ""),
            inheritance_kind=(spine_node.inheritance_kind if spine_node else ""),
            inherited_from=(list(spine_node.inherits_from) if spine_node else []),
            candidates=candidates,
            review_dimensions=dict(self.weights),
            agent_roles=[dict(item) for item in self.policy.get("agent_roles", [])],
            principles=[str(item) for item in self.policy.get("principles", [])],
            generated_at=now_iso(),
        )

    def aggregate(
        self,
        packet: ModelDebatePacket,
        reviews: list[CandidateDebateReview],
    ) -> ModelCandidateConsensus:
        known = {item.candidate_id: item for item in packet.candidates}
        valid_reviews = [item for item in reviews if item.candidate_id in known]
        reviewer_ids = sorted({item.reviewer_id for item in valid_reviews})
        minimum_reviewers = int(self.policy.get("minimum_distinct_reviewers", 2))

        by_candidate: dict[str, list[CandidateDebateReview]] = {candidate_id: [] for candidate_id in known}
        for review in valid_reviews:
            missing = [dimension for dimension in self.weights if dimension not in review.scores]
            if missing:
                raise ValueError("MODEL_CONSENSUS_REVIEW_DIMENSIONS_MISSING:" + ",".join(missing))
            by_candidate[review.candidate_id].append(review)

        rows: list[ConsensusCandidate] = []
        eligible: list[ConsensusCandidate] = []
        for candidate in packet.candidates:
            candidate_reviews = by_candidate[candidate.candidate_id]
            objections = list(dict.fromkeys(text for review in candidate_reviews for text in review.objections if text))
            falsifiers = list(dict.fromkeys(review.falsification_test for review in candidate_reviews))
            if candidate.feasibility != "PASS":
                rows.append(
                    ConsensusCandidate(
                        candidate_id=candidate.candidate_id,
                        method=candidate.method,
                        feasibility=candidate.feasibility,
                        reviewer_count=len(candidate_reviews),
                        disposition="RESEARCH_GAP",
                        objections=objections,
                        falsification_tests=falsifiers,
                    )
                )
                continue
            if not candidate_reviews:
                row = ConsensusCandidate(
                    candidate_id=candidate.candidate_id,
                    method=candidate.method,
                    feasibility=candidate.feasibility,
                    reviewer_count=0,
                    disposition="SHORTLIST",
                    objections=objections,
                    falsification_tests=falsifiers,
                )
                rows.append(row)
                eligible.append(row)
                continue
            score = sum(
                self.weights[dimension]
                * (sum(float(review.scores[dimension]) for review in candidate_reviews) / len(candidate_reviews))
                for dimension in self.weights
            )
            complexity = sum(review.complexity_burden for review in candidate_reviews) / len(candidate_reviews)
            row = ConsensusCandidate(
                candidate_id=candidate.candidate_id,
                method=candidate.method,
                feasibility=candidate.feasibility,
                weighted_score=round(score, 6),
                complexity_burden=round(complexity, 6),
                reviewer_count=len(candidate_reviews),
                disposition="SHORTLIST",
                objections=objections,
                falsification_tests=falsifiers,
            )
            rows.append(row)
            eligible.append(row)

        reviewed_eligible = [item for item in eligible if item.weighted_score is not None]
        if len(reviewer_ids) < minimum_reviewers or not reviewed_eligible:
            return ModelCandidateConsensus(
                case_id=packet.case_id,
                subproblem_id=packet.subproblem_id,
                gate="REVIEW" if packet.candidates else "BLOCKED",
                shortlist_candidate_ids=[item.candidate_id for item in eligible],
                candidates=rows,
                distinct_reviewers=reviewer_ids,
                rationale=(
                    f"qualitative debate is incomplete: {len(reviewer_ids)} distinct reviewer(s), "
                    f"minimum required = {minimum_reviewers}; no model winner is inferred"
                ),
                generated_at=now_iso(),
            )

        reviewed_eligible.sort(key=lambda item: float(item.weighted_score or 0.0), reverse=True)
        preferred = reviewed_eligible[0]
        tiebreak = self.policy.get("complexity_tiebreak") or {}
        if bool(tiebreak.get("enabled")) and len(reviewed_eligible) >= 2:
            runner_up = reviewed_eligible[1]
            score_gap = float(preferred.weighted_score or 0.0) - float(runner_up.weighted_score or 0.0)
            band = float(tiebreak.get("equivalence_band", 0.05))
            advantage = float(tiebreak.get("minimum_complexity_advantage", 0.15))
            preferred_complexity = float(preferred.complexity_burden or 0.0)
            runner_complexity = float(runner_up.complexity_burden or 0.0)
            if score_gap <= band and preferred_complexity - runner_complexity >= advantage:
                preferred = runner_up

        for item in rows:
            if item.candidate_id == preferred.candidate_id:
                item.disposition = "EXPERIMENT_PRIORITY"

        return ModelCandidateConsensus(
            case_id=packet.case_id,
            subproblem_id=packet.subproblem_id,
            gate="PASS",
            preferred_experiment_candidate_id=preferred.candidate_id,
            shortlist_candidate_ids=[item.candidate_id for item in reviewed_eligible],
            candidates=rows,
            distinct_reviewers=reviewer_ids,
            rationale=(
                "agent debate selected the next executable experiment to run; final model adoption still requires "
                "same-protocol solver evidence and validation"
            ),
            generated_at=now_iso(),
        )


def build_agent_review_tasks(packet: ModelDebatePacket) -> list[dict[str, Any]]:
    """Create role-specific, backend-neutral review tasks for cloud/local agents.

    Every role receives the same candidate facts and score dimensions.  The
    prompt asks for critique and falsification tests, not predicted benchmark
    numbers.  Any LLM/MCP/agent framework can execute these tasks and return
    ``CandidateDebateReview`` records for deterministic aggregation.
    """

    candidate_payload = [item.model_dump(mode="json") for item in packet.candidates]
    tasks: list[dict[str, Any]] = []
    for role in packet.agent_roles:
        role_name = str(role.get("role") or "reviewer")
        mandate = str(role.get("mandate") or "Review the modeling candidates.")
        tasks.append(
            {
                "task_id": f"{packet.subproblem_id}:{role_name}",
                "role": role_name,
                "mandate": mandate,
                "subproblem_id": packet.subproblem_id,
                "task_family": packet.task_family,
                "question_role": packet.question_role,
                "inheritance_kind": packet.inheritance_kind,
                "inherited_from": list(packet.inherited_from),
                "candidates": candidate_payload,
                "review_dimensions": dict(packet.review_dimensions),
                "instructions": [
                    "Review only the supplied candidates and research context; do not invent benchmark scores or experimental results.",
                    "Score every candidate you review from 0 to 1 on every listed review dimension.",
                    "Report complexity_burden from 0 to 1 as a qualitative implementation/model-structure burden, not as prestige.",
                    "State concrete objections and at least one falsification test that executed evidence could resolve.",
                    "If the question inherits an upstream model, require a concrete reason before recommending a disconnected new model.",
                    "A NEEDS_SOLVER candidate may be recommended for future capability work but not as the accepted paper model.",
                ],
                "output_schema": {
                    "reviewer_id": "string",
                    "reviewer_role": role_name,
                    "candidate_id": "string",
                    "scores": {dimension: "float[0,1]" for dimension in packet.review_dimensions},
                    "complexity_burden": "float[0,1]",
                    "objections": ["string"],
                    "falsification_test": "string",
                },
            }
        )
    return tasks


class ModelCandidateConsensusService:
    """Persist debate packets/results as non-paper research-planning artifacts."""

    def __init__(self, cases: Any, artifacts: Any, engine: ModelCandidateConsensusEngine | None = None) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.engine = engine or ModelCandidateConsensusEngine()

    def create_packet(
        self,
        case_id: str,
        decision: ModelingBrainDecision,
        *,
        spine_node: ModelSpineNode | None = None,
        source_artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        packet = self.engine.build_packet(decision, spine_node=spine_node)
        root = self.cases.case_root(case_id)
        path = root / "analysis" / "model_consensus" / f"{decision.subproblem_id}-debate-packet.json"
        tasks_path = root / "analysis" / "model_consensus" / f"{decision.subproblem_id}-agent-review-tasks.json"
        atomic_write_json(path, packet.model_dump(mode="json"))
        atomic_write_json(tasks_path, {"schema_version": 1, "tasks": build_agent_review_tasks(packet)})
        artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "model_candidate_debate_packet",
            "model_candidate_consensus",
            upstream=list(source_artifact_ids or []),
            paper_eligible=False,
        )
        tasks_artifact = self.artifacts.register_existing(
            case_id,
            tasks_path.relative_to(root).as_posix(),
            "model_candidate_agent_review_tasks",
            "model_candidate_consensus",
            upstream=[artifact["artifact_id"]],
            paper_eligible=False,
        )
        return {"packet": packet, "artifact": artifact, "review_tasks_artifact": tasks_artifact}

    def persist_consensus(
        self,
        case_id: str,
        packet: ModelDebatePacket,
        reviews: list[CandidateDebateReview],
        *,
        source_artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        consensus = self.engine.aggregate(packet, reviews)
        root = self.cases.case_root(case_id)
        path = root / "analysis" / "model_consensus" / f"{packet.subproblem_id}-consensus.json"
        atomic_write_json(path, consensus.model_dump(mode="json"))
        artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "model_candidate_consensus",
            "model_candidate_consensus",
            upstream=list(source_artifact_ids or []),
            paper_eligible=False,
        )
        return {"consensus": consensus, "artifact": artifact}

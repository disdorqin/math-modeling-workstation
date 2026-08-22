from mathworkstation.model_candidate_consensus import (
    CandidateDebateReview,
    ModelCandidateConsensusEngine,
    build_agent_review_tasks,
)
from mathworkstation.model_spine import ModelSpineNode
from mathworkstation.modeling_brain import CandidateStrategy, ModelingBrainDecision
from mathworkstation.io_utils import now_iso


def _decision() -> ModelingBrainDecision:
    return ModelingBrainDecision(
        case_id="case-1",
        subproblem_id="SP2",
        task_family="optimization",
        gate="PASS",
        query="pricing and replenishment",
        candidates=[
            CandidateStrategy(
                candidate_id="native:simple",
                method="simple executable route",
                source="native",
                retrieval_score=0.92,
                feasibility="PASS",
                rationale="registered solver available",
            ),
            CandidateStrategy(
                candidate_id="skill:complex",
                method="richer executable route",
                source="skill",
                retrieval_score=0.91,
                feasibility="PASS",
                rationale="registered solver available",
            ),
            CandidateStrategy(
                candidate_id="hmml:future",
                method="interesting future route",
                source="hmml",
                retrieval_score=0.99,
                feasibility="NEEDS_SOLVER",
                rationale="needs a solver plugin",
            ),
        ],
        selected_candidate_ids=["native:simple", "skill:complex", "hmml:future"],
        selected_methods=["simple executable route", "richer executable route", "interesting future route"],
        generated_at=now_iso(),
    )


def _spine() -> ModelSpineNode:
    return ModelSpineNode(
        subproblem_id="SP2",
        role="CORE_MODEL",
        method="simple executable route",
        task_family="optimization",
        dependencies=["SP1"],
        inherits_from=["SP1"],
        inheritance_kind="EVIDENCE",
        downstream_reach=1,
        core_score=3.0,
        equation_budget=3,
        paper_emphasis=1.3,
        narrative_directive="core",
    )


def _review(reviewer: str, candidate_id: str, score: float, complexity: float) -> CandidateDebateReview:
    return CandidateDebateReview(
        reviewer_id=reviewer,
        reviewer_role="critic" if reviewer.endswith("2") else "modeler",
        candidate_id=candidate_id,
        scores={
            "task_fit": score,
            "data_support": score,
            "interpretability": score,
            "constraint_fit": score,
            "robustness_plan": score,
            "computational_cost": score,
        },
        complexity_burden=complexity,
        objections=[],
        falsification_test="run the same-protocol holdout comparison",
    )


def test_debate_packet_preserves_model_spine_role_without_preselecting_winner() -> None:
    engine = ModelCandidateConsensusEngine()
    packet = engine.build_packet(_decision(), spine_node=_spine())

    assert packet.question_role == "CORE_MODEL"
    assert packet.inheritance_kind == "EVIDENCE"
    assert packet.inherited_from == ["SP1"]
    assert {item.candidate_id for item in packet.candidates} == {
        "native:simple",
        "skill:complex",
        "hmml:future",
    }
    assert abs(sum(packet.review_dimensions.values()) - 1.0) < 1e-9
    tasks = build_agent_review_tasks(packet)
    assert {task["role"] for task in tasks} == {
        "baseline_modeler",
        "alternative_modeler",
        "critic",
        "adjudicator",
    }
    assert all("do not invent benchmark scores" in " ".join(task["instructions"]).lower() for task in tasks)


def test_consensus_requires_multiple_reviewers_and_never_promotes_missing_solver() -> None:
    engine = ModelCandidateConsensusEngine()
    packet = engine.build_packet(_decision(), spine_node=_spine())
    consensus = engine.aggregate(
        packet,
        [
            _review("reviewer-1", "native:simple", 0.85, 0.20),
            _review("reviewer-1", "skill:complex", 0.88, 0.70),
        ],
    )

    assert consensus.gate == "REVIEW"
    assert consensus.preferred_experiment_candidate_id is None
    future = next(item for item in consensus.candidates if item.candidate_id == "hmml:future")
    assert future.disposition == "RESEARCH_GAP"


def test_near_equivalent_debate_prefers_simpler_executable_route_for_next_experiment_only() -> None:
    engine = ModelCandidateConsensusEngine()
    packet = engine.build_packet(_decision(), spine_node=_spine())
    reviews = [
        _review("reviewer-1", "native:simple", 0.86, 0.15),
        _review("reviewer-2", "native:simple", 0.86, 0.20),
        _review("reviewer-1", "skill:complex", 0.89, 0.75),
        _review("reviewer-2", "skill:complex", 0.89, 0.70),
    ]
    consensus = engine.aggregate(packet, reviews)

    assert consensus.gate == "PASS"
    assert consensus.preferred_experiment_candidate_id == "native:simple"
    assert "final model adoption still requires" in consensus.rationale
    chosen = next(item for item in consensus.candidates if item.candidate_id == "native:simple")
    assert chosen.disposition == "EXPERIMENT_PRIORITY"

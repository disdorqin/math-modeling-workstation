from __future__ import annotations

from pathlib import Path

from mathworkstation.c_problem_modeling_priors import CProblemModelingPriorService
from mathworkstation.paper_contracts import SubproblemContract
from mathworkstation.problem_graph import ProblemGraphBuilder


def _service() -> CProblemModelingPriorService:
    return CProblemModelingPriorService.from_default_registry()


def test_forecasting_prior_requires_temporal_validation_without_naming_a_winner() -> None:
    graph = ProblemGraphBuilder().build(
        [
            SubproblemContract(
                subproblem_id="SP1",
                title="Forecast next-week demand",
                objective="Forecast future demand with uncertainty",
            )
        ]
    )
    assessment = _service().assess(graph.node("SP1"), graph)

    assert assessment.scope == "C_PROBLEM_ONLY"
    assert "algorithm_diversity_is_normal" in assessment.prior_names
    assert any("时间顺序验证" in item for item in assessment.validation_obligations)
    assert any("优秀论文" in item and "频率" in item for item in assessment.forbidden_shortcuts)
    assert all("ARIMA" not in item and "LSTM" not in item for item in assessment.research_obligations)


def test_dependent_c_problem_node_receives_question_chain_obligation() -> None:
    graph = ProblemGraphBuilder().build(
        [
            SubproblemContract(
                subproblem_id="SP1",
                title="Analyze historical demand",
                objective="Explore demand patterns",
            ),
            SubproblemContract(
                subproblem_id="SP2",
                title="Write decision memo",
                objective="Synthesize the earlier analysis into a memo",
            ),
        ]
    )
    node = graph.node("SP2")
    assessment = _service().assess(node, graph)

    assert node.dependencies == ["SP1"]
    assert any("上游" in item for item in assessment.research_obligations)
    assert any("accepted evidence" in item for item in assessment.research_obligations)
    assert any("回溯" in item for item in assessment.validation_obligations)

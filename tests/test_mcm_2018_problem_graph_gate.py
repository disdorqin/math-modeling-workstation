from pathlib import Path

from mathworkstation.paper_contracts import SubproblemContract
import pandas as pd

from mathworkstation.problem_graph import ProblemGraphBuilder, assess_problem_graph
from mathworkstation.research_data_coverage import ResearchDataCoverageAuditor


CASE_ROOT = Path("output/mcm-c-2018/v2/20260805-MCM-0001-4DH5")


def _contracts() -> list[SubproblemContract]:
    return [
        SubproblemContract.model_validate_json(line)
        for line in (CASE_ROOT / "results/contracts/subproblems.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_real_2018_energy_problem_routes_to_multi_family_research_graph() -> None:
    graph = ProblemGraphBuilder().build(_contracts())
    families = {node.subproblem_id: node.task_family for node in graph.nodes}

    assert families == {
        "I-A": "exploratory_analysis",
        "I-B": "forecasting",
        "I-C": "ranking",
        "I-D": "forecasting",
        "II-A": "optimization",
        "II-B": "synthesis",
        "III": "synthesis",
    }
    assessment = assess_problem_graph(graph)
    assert assessment.structure_gate == "PASS"
    assert assessment.research_gate == "INCOMPLETE"
    research_ids = ["I-A", "I-B", "I-C", "I-D", "II-A"]
    assert graph.node("II-B").dependencies == research_ids
    assert graph.node("III").dependencies == research_ids
    assert graph.node("II-B").plan.requires_model_execution is False
    assert graph.node("III").plan.requires_model_execution is False


def test_real_2018_current_case_is_blocked_for_missing_three_state_data() -> None:
    problem = (CASE_ROOT / "input/problem/extracted/2018_MCM_Problem_C.md").read_text(encoding="utf-8")
    data_path = CASE_ROOT / "input/data/uploaded/_energy2018_tx.csv"
    frame = pd.read_csv(data_path)

    assessment = ResearchDataCoverageAuditor().audit(
        problem,
        [frame],
        source_names=[data_path.name],
        case_id="2018-energy-v2",
    )

    assert assessment.gate == "BLOCK"
    assert assessment.required_entities == ["CA", "AZ", "NM", "TX"]
    assert assessment.observed_entities == ["TX"]
    assert assessment.findings[0].code == "MULTI_ENTITY_DATA_COVERAGE_MISSING"
    assert assessment.findings[0].repair_phase == "data_registration"


def test_real_2018_energy_problem_does_not_flatten_policy_deliverables_into_regression() -> None:
    graph = ProblemGraphBuilder().build(_contracts())

    assert graph.node("II-B").execution_kind == "DELIVERABLE"
    assert graph.node("III").execution_kind == "DELIVERABLE"
    assert graph.node("I-C").task_family == "ranking"
    assert graph.node("II-A").task_family == "optimization"

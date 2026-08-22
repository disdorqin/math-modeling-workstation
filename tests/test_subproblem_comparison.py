from pathlib import Path

import pandas as pd

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.paper_contracts import PaperContractService, SubproblemContract
from mathworkstation.problem_graph import ProblemGraphService
from mathworkstation.subproblem_comparison import SubproblemAlternativeComparisonService
from mathworkstation.subproblem_engine import SubproblemEngineService
from mathworkstation.wordle_2023_gate import prepare_wordle_2023_research


CASE_ROOT = Path("output/mcm-c-2023/v3/20260805-MCM-0001-EUP7")


def _contracts() -> list[SubproblemContract]:
    return [
        SubproblemContract.model_validate_json(line)
        for line in (CASE_ROOT / "results/contracts/subproblems.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _case(tmp_path: Path):
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "Wordle alternative comparison Gate")
    case_id = case["case_id"]
    artifacts = ArtifactRegistry(cases)
    source = artifacts.ingest_file(
        case_id,
        CASE_ROOT / "input/data/uploaded/_wordle_data_clean.csv",
        "input/data/uploaded",
        "observed_data",
    )
    contracts = PaperContractService(cases, artifacts)
    contracts.persist_subproblems(case_id, _contracts())
    graphs = ProblemGraphService(cases, artifacts)
    graphs.persist(case_id, contracts.list_subproblems(case_id), [source["artifact_id"]])
    engine = SubproblemEngineService(cases, artifacts, graphs)
    frame, plans = prepare_wordle_2023_research(
        pd.read_csv(CASE_ROOT / "input/data/uploaded/_wordle_data_clean.csv")
    )
    for subproblem_id in ("SP1", "SP4"):
        engine.execute_node(
            case_id,
            subproblem_id,
            plans[subproblem_id],
            frame=frame,
            source_artifact_ids=[source["artifact_id"]],
        )
    return cases, artifacts, graphs, frame, plans, case_id, source["artifact_id"]


def test_real_wordle_sp1_ridge_comparison_is_traceable_after_holt_is_accepted(tmp_path: Path) -> None:
    cases, artifacts, graphs, frame, plans, case_id, source_id = _case(tmp_path)
    service = SubproblemAlternativeComparisonService(cases, artifacts, graphs)
    before = graphs.load(case_id).node("SP1")
    accepted_method = before.answer.method
    accepted_answer = before.answer.answer

    result = service.compare(
        case_id,
        "SP1",
        [{**plans["SP1"], "solver_method": "ridge_time_trend"}],
        frame=frame,
        source_artifact_ids=[source_id],
    )
    comparison = result["comparison"]
    after = graphs.load(case_id).node("SP1")

    assert comparison.primary_metric == "rmse"
    assert comparison.metric_direction == "MINIMIZE"
    assert comparison.accepted.solver == "gold.holt_exponential_smoothing"
    assert comparison.alternatives[0].solver == "gold.forecasting"
    assert comparison.alternatives[0].validation_gate in {"PASS", "REVIEW"}
    assert comparison.decision in {"KEEP_ACCEPTED", "REVIEW_SWITCH"}
    assert after.answer.method == accepted_method
    assert after.answer.answer == accepted_answer
    assert len(after.experiments) == 2
    assert result["artifact"]["artifact_type"] == "subproblem_alternative_comparison"
    assert artifacts.verify(case_id)["valid"]


def test_real_wordle_sp1_temporal_stress_keeps_holt_and_rejects_unstable_lifecycle(tmp_path: Path) -> None:
    cases, artifacts, graphs, frame, plans, case_id, source_id = _case(tmp_path)
    service = SubproblemAlternativeComparisonService(cases, artifacts, graphs)

    result = service.compare(
        case_id,
        "SP1",
        [
            {**plans["SP1"], "solver_method": "ridge_time_trend"},
            {**plans["SP1"], "solver_method": "popularity_lifecycle"},
        ],
        frame=frame,
        source_artifact_ids=[source_id],
        stress_test_sizes=[0.15, 0.20, 0.25, 0.30],
    )
    comparison = result["comparison"]
    by_solver = {item.solver: item for item in comparison.stress_runs}

    assert comparison.decision == "KEEP_ACCEPTED"
    assert comparison.accepted.solver == "gold.holt_exponential_smoothing"
    assert comparison.robust_best_method == comparison.accepted.method
    assert comparison.best_method == comparison.accepted.method
    assert by_solver["gold.forecasting"].robustly_better is False
    assert by_solver["gold.forecasting"].win_rate_vs_accepted == 0.0
    assert by_solver["gold.popularity_lifecycle"].robustly_better is False
    assert by_solver["gold.popularity_lifecycle"].win_rate_vs_accepted == 0.5
    assert artifacts.verify(case_id)["valid"]


def test_switching_wordle_sp1_invalidates_and_rebuilds_sp6_synthesis(tmp_path: Path) -> None:
    cases, artifacts, graphs, frame, plans, case_id, source_id = _case(tmp_path)
    engine = SubproblemEngineService(cases, artifacts, graphs)
    for subproblem_id in ("SP2", "SP3", "SP5"):
        engine.execute_node(
            case_id,
            subproblem_id,
            plans[subproblem_id],
            frame=frame,
            source_artifact_ids=[source_id],
        )
    engine.complete_synthesis(
        case_id,
        "SP6",
        "Initial synthesis based on the first accepted SP1-SP5 research state.",
    )
    assert graphs.load(case_id).node("SP6").state.status == "COMPLETED"

    switched = engine.execute_node(
        case_id,
        "SP1",
        {**plans["SP1"], "solver_method": "holt_exponential_smoothing"},
        frame=frame,
        source_artifact_ids=[source_id],
    )
    stale_synthesis = graphs.load(case_id).node("SP6")

    assert switched["invalidated_dependents"] == ["SP6"]
    assert stale_synthesis.state.status == "PLANNED"
    assert stale_synthesis.answer is None
    assert stale_synthesis.state.evidence_artifact_ids == []
    assert switched["research_gate"] == "INCOMPLETE"

    rebuilt = engine.complete_synthesis(
        case_id,
        "SP6",
        "Updated synthesis after the accepted SP1 forecast model changed.",
    )
    assert rebuilt["research_gate"] == "PASS"
    assert graphs.load(case_id).node("SP6").answer.answer.startswith("Updated synthesis")


def test_real_wordle_sp4_random_forest_comparison_uses_balanced_accuracy(tmp_path: Path) -> None:
    cases, artifacts, graphs, frame, plans, case_id, source_id = _case(tmp_path)
    service = SubproblemAlternativeComparisonService(cases, artifacts, graphs)
    before = graphs.load(case_id).node("SP4")
    accepted_method = before.answer.method

    result = service.compare(
        case_id,
        "SP4",
        [{**plans["SP4"], "solver_method": "random_forest_classifier"}],
        frame=frame,
        source_artifact_ids=[source_id],
    )
    comparison = result["comparison"]
    after = graphs.load(case_id).node("SP4")

    assert comparison.primary_metric == "balanced_accuracy"
    assert comparison.metric_direction == "MAXIMIZE"
    assert comparison.alternatives[0].solver == "gold.random_forest_classification"
    assert comparison.alternatives[0].validation_gate in {"PASS", "REVIEW"}
    assert comparison.decision in {"KEEP_ACCEPTED", "REVIEW_SWITCH"}
    assert after.answer.method == accepted_method
    assert len(after.experiments) == 2
    assert artifacts.verify(case_id)["valid"]

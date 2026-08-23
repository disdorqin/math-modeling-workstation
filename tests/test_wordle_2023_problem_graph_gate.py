from pathlib import Path

import pandas as pd

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.claims import ClaimRegistry
from mathworkstation.datasets import DatasetRegistry
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.paper_contracts import PaperContractService, SubproblemContract
from mathworkstation.problem_graph import ProblemGraphBuilder, ProblemGraphService
from mathworkstation.subproblem_engine import SubproblemEngineService
from mathworkstation.subproblem_paper_bridge import SubproblemPaperEvidenceBridge
from mathworkstation.wordle_2023_gate import (
    Wordle2023GateService,
    prepare_wordle_2023_research,
    run_wordle_2023_gate,
)


CASE_ROOT = Path("output/mcm-c-2023/v3/20260805-MCM-0001-EUP7")


def _contracts() -> list[SubproblemContract]:
    path = CASE_ROOT / "results/contracts/subproblems.jsonl"
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(SubproblemContract.model_validate_json(line))
    return rows


def test_real_2023_wordle_problem_graph_reaches_research_pass() -> None:
    data_path = CASE_ROOT / "input/data/uploaded/_wordle_data_clean.csv"
    assert data_path.is_file(), "real Wordle benchmark data is required"
    graph = ProblemGraphBuilder().build(_contracts())
    completed, report = run_wordle_2023_gate(pd.read_csv(data_path), graph)

    assert report["assessment"]["structure_gate"] == "PASS"
    assert report["assessment"]["research_gate"] == "PASS"
    assert [completed.node(f"SP{i}").task_family for i in range(1, 7)] == [
        "forecasting",
        "explanatory_inference",
        "distribution_forecasting",
        "classification",
        "exploratory_analysis",
        "synthesis",
    ]
    methods = {completed.node(f"SP{i}").answer.method for i in range(1, 6)}
    assert len(methods) >= 4
    assert completed.node("SP6").plan.requires_model_execution is False
    assert completed.node("SP6").dependencies == ["SP1", "SP2", "SP3", "SP4", "SP5"]


def test_real_wordle_gate_persists_independent_case_artifacts(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "2023 Wordle Section-1 Gate")
    artifacts = ArtifactRegistry(cases)
    source = artifacts.ingest_file(
        case["case_id"],
        CASE_ROOT / "input/data/uploaded/_wordle_data_clean.csv",
        "input/data/uploaded",
        "observed_data",
    )
    graph = ProblemGraphBuilder().build(_contracts())
    completed, report = Wordle2023GateService(cases, artifacts).run(
        case["case_id"],
        pd.read_csv(CASE_ROOT / "input/data/uploaded/_wordle_data_clean.csv"),
        graph,
        [source["artifact_id"]],
    )

    assert report["assessment"]["research_gate"] == "PASS"
    evidence = report["evidence_by_subproblem"]
    assert len(set(evidence.values())) == 5
    assert all(artifacts.get(case["case_id"], artifact_id)["artifact_type"] == "subproblem_execution_result" for artifact_id in evidence.values())
    assert completed.node("SP6").state.evidence_artifact_ids == [evidence[f"SP{i}"] for i in range(1, 6)]
    assert artifacts.verify(case["case_id"])["valid"]


def test_real_wordle_runs_through_generic_engine_and_paper_evidence(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "2023 Wordle generic subproblem engine Gate")
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
    bridge = SubproblemPaperEvidenceBridge(
        cases,
        artifacts,
        contracts,
        ClaimRegistry(cases, artifacts, DatasetRegistry(cases, artifacts)),
        FigureRegistry(cases, artifacts),
    )
    data, plans = prepare_wordle_2023_research(
        pd.read_csv(CASE_ROOT / "input/data/uploaded/_wordle_data_clean.csv")
    )
    projections = []
    for subproblem_id in ("SP1", "SP2", "SP3", "SP4", "SP5"):
        executed = engine.execute_node(
            case_id,
            subproblem_id,
            plans[subproblem_id],
            frame=data,
            source_artifact_ids=[source["artifact_id"]],
            answer_text=f"{subproblem_id} independent accepted answer for the real Wordle Gate.",
        )
        projections.append(bridge.project(case_id, subproblem_id, executed))
    synthesis = engine.complete_synthesis(
        case_id,
        "SP6",
        "Editor letter synthesizes only SP1-SP5 accepted evidence.",
    )
    bridge.project_synthesis(case_id, "SP6", synthesis)
    active = bridge.activate_if_complete(case_id, generation=1)

    assert active is not None
    assert len(active["table_ids"]) == 5
    assert len(active["result_ids"]) >= 5
    assert graphs.assess(graphs.load(case_id)).research_gate == "PASS"
    conclusion = contracts.build_section_pack(case_id, "conclusion")
    assert {answer.subproblem_id for answer in conclusion.answers} == {f"SP{i}" for i in range(1, 7)}
    assert len({answer.method for answer in conclusion.answers[:5]}) >= 4
    assert {result.result_type for result in conclusion.results} >= {
        "FORECAST",
        "EXPLANATORY",
        "DISTRIBUTION_FORECAST",
        "CLASSIFICATION",
        "EXPLORATORY",
    }
    assert artifacts.verify(case_id)["valid"]


def test_real_wordle_gate_answers_the_requested_future_targets() -> None:
    graph = ProblemGraphBuilder().build(_contracts())
    completed, report = run_wordle_2023_gate(
        pd.read_csv(CASE_ROOT / "input/data/uploaded/_wordle_data_clean.csv"), graph
    )
    sp1 = report["results"]["SP1"]
    sp3 = report["results"]["SP3"]
    sp4 = report["results"]["SP4"]

    lower, upper = sp1["forecast"]["interval"]
    assert lower <= sp1["forecast"]["point"] <= upper
    assert sp1["protocol"]["future_time"].startswith("2023-03-01")
    assert abs(sum(sp3["future_distribution"].values()) - 100.0) < 1e-8
    assert sp3["future_uncertainty_95"]
    assert sp4["future_prediction"] in {"easy", "medium", "hard"}
    assert "EERIE" in completed.node("SP3").answer.answer
    assert "EERIE" in completed.node("SP4").answer.answer

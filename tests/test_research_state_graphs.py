from pathlib import Path

import pandas as pd

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.claims import ClaimRegistry
from mathworkstation.datasets import DatasetRegistry
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.paper_contracts import PaperContractService, SubproblemContract
from mathworkstation.problem_graph import ProblemGraphService
from mathworkstation.research_state_graphs import EvidenceGraphService, ModelGraphService
from mathworkstation.subproblem_engine import SubproblemEngineService
from mathworkstation.subproblem_paper_bridge import SubproblemPaperEvidenceBridge
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
    case = cases.create_case("MCM", "Wordle model/evidence graph Gate")
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
    claims = ClaimRegistry(cases, artifacts, DatasetRegistry(cases, artifacts))
    figures = FigureRegistry(cases, artifacts)
    engine = SubproblemEngineService(cases, artifacts, graphs)
    bridge = SubproblemPaperEvidenceBridge(cases, artifacts, contracts, claims, figures)
    frame, plans = prepare_wordle_2023_research(
        pd.read_csv(CASE_ROOT / "input/data/uploaded/_wordle_data_clean.csv")
    )
    for subproblem_id in ("SP1", "SP2", "SP3", "SP4", "SP5"):
        execution = engine.execute_node(
            case_id,
            subproblem_id,
            plans[subproblem_id],
            frame=frame,
            source_artifact_ids=[source["artifact_id"]],
        )
        bridge.project(case_id, subproblem_id, execution)
    synthesis = engine.complete_synthesis(
        case_id,
        "SP6",
        "The editor letter synthesizes only accepted SP1-SP5 evidence.",
    )
    bridge.project_synthesis(case_id, "SP6", synthesis)
    assert bridge.activate_if_complete(case_id, generation=1)
    return cases, artifacts, contracts, claims, figures, graphs, case_id


def test_real_wordle_model_graph_is_question_specific(tmp_path: Path) -> None:
    cases, artifacts, _contracts_service, _claims, _figures, problem_graphs, case_id = _case(tmp_path)
    service = ModelGraphService(cases, artifacts, problem_graphs)

    graph = service.build(case_id)

    assert graph.gate == "PASS"
    assert graph.problem_graph_gate == "PASS"
    assert len(graph.nodes) == 6
    assert len({graph.node(f"SP{i}").selected_method for i in range(1, 6)}) >= 4
    assert all(graph.node(f"SP{i}").experiment_id for i in range(1, 6))
    assert all(graph.node(f"SP{i}").validation_artifact_ids for i in range(1, 6))
    assert all(graph.node(f"SP{i}").validation_gate in {"PASS", "REVIEW"} for i in range(1, 6))
    assert graph.node("SP6").execution_kind == "DELIVERABLE"
    assert graph.node("SP6").experiment_id is None


def test_real_wordle_evidence_graph_closes_each_question(tmp_path: Path) -> None:
    cases, artifacts, contracts, claims, figures, problem_graphs, case_id = _case(tmp_path)
    models = ModelGraphService(cases, artifacts, problem_graphs)
    evidence = EvidenceGraphService(
        cases,
        artifacts,
        contracts,
        claims,
        figures,
        problem_graphs,
        models,
    )

    graph = evidence.build(case_id, models.build(case_id))

    assert graph.gate == "PASS"
    assert graph.model_graph_gate == "PASS"
    assert graph.active_generation == 1
    for subproblem_id in ("SP1", "SP2", "SP3", "SP4", "SP5"):
        node = graph.node(subproblem_id)
        assert node.gate == "PASS"
        assert node.answer_id
        assert node.result_ids
        assert node.table_ids
        assert node.figure_ids
    assert graph.node("SP6").role == "SYNTHESIS"
    assert graph.node("SP6").dependencies == [f"SP{i}" for i in range(1, 6)]
    assert graph.node("SP6").gate == "PASS"
    assert artifacts.verify(case_id)["valid"]


def test_model_and_evidence_graphs_persist_as_distinct_artifacts(tmp_path: Path) -> None:
    cases, artifacts, contracts, claims, figures, problem_graphs, case_id = _case(tmp_path)
    models = ModelGraphService(cases, artifacts, problem_graphs)
    model_result = models.build_and_persist(case_id)
    evidence = EvidenceGraphService(cases, artifacts, contracts, claims, figures, problem_graphs, models)
    evidence_result = evidence.build_and_persist(case_id, model_result["graph"])

    assert model_result["artifact"]["artifact_type"] == "model_graph"
    assert evidence_result["artifact"]["artifact_type"] == "evidence_graph"
    assert model_result["artifact"]["artifact_id"] != evidence_result["artifact"]["artifact_id"]
    assert artifacts.verify(case_id)["valid"]

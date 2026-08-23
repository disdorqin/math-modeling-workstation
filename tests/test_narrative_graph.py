from pathlib import Path

import pandas as pd

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.claims import ClaimRegistry
from mathworkstation.datasets import DatasetRegistry
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.narrative_graph import NarrativeGraphService, render_narrative_preview
from mathworkstation.paper_contracts import PaperContractService, SubproblemContract
from mathworkstation.problem_graph import ProblemGraphService
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


def _wordle_research_case(tmp_path: Path):
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "2023 Wordle narrative graph Gate")
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
    claims = ClaimRegistry(cases, artifacts, DatasetRegistry(cases, artifacts))
    figures = FigureRegistry(cases, artifacts)
    bridge = SubproblemPaperEvidenceBridge(cases, artifacts, contracts, claims, figures)
    data, plans = prepare_wordle_2023_research(
        pd.read_csv(CASE_ROOT / "input/data/uploaded/_wordle_data_clean.csv")
    )
    for subproblem_id in ("SP1", "SP2", "SP3", "SP4", "SP5"):
        executed = engine.execute_node(
            case_id,
            subproblem_id,
            plans[subproblem_id],
            frame=data,
            source_artifact_ids=[source["artifact_id"]],
        )
        bridge.project(case_id, subproblem_id, executed)
    synthesis = engine.complete_synthesis(
        case_id,
        "SP6",
        "The editor letter synthesizes the accepted findings from SP1 through SP5 without introducing new numerical claims.",
    )
    bridge.project_synthesis(case_id, "SP6", synthesis)
    active = bridge.activate_if_complete(case_id, generation=1)
    assert active is not None
    return cases, artifacts, contracts, claims, figures, graphs, case_id


def test_real_wordle_builds_six_node_narrative_graph(tmp_path: Path) -> None:
    cases, artifacts, contracts, claims, figures, graphs, case_id = _wordle_research_case(tmp_path)
    service = NarrativeGraphService(cases, artifacts, contracts, claims, figures, graphs)

    narrative = service.build(case_id)

    assert narrative.gate == "PASS"
    assert narrative.research_gate == "PASS"
    assert narrative.model_graph_gate == "PASS"
    assert narrative.evidence_graph_gate == "PASS"
    assert narrative.storyline == [f"SP{i}" for i in range(1, 7)]
    assert [n.task_family for n in narrative.nodes] == [
        "forecasting",
        "explanatory_inference",
        "distribution_forecasting",
        "classification",
        "exploratory_analysis",
        "synthesis",
    ]
    assert all(n.gate == "PASS" for n in narrative.nodes)
    assert len({n.method for n in narrative.nodes[:5]}) >= 4
    assert narrative.node("SP6").role == "SYNTHESIS"
    assert narrative.node("SP6").dependencies == [f"SP{i}" for i in range(1, 6)]
    assert all(n.validation_gate in {"PASS", "REVIEW"} for n in narrative.nodes[:5])
    assert "2023-03-01" in narrative.node("SP1").answer
    assert "%" in narrative.node("SP3").answer
    assert any(label in narrative.node("SP4").answer for label in ("easy", "medium", "hard"))


def test_narrative_preview_never_leaks_registry_ids(tmp_path: Path) -> None:
    cases, artifacts, contracts, claims, figures, graphs, case_id = _wordle_research_case(tmp_path)
    service = NarrativeGraphService(cases, artifacts, contracts, claims, figures, graphs)
    persisted = service.build_and_persist(case_id)
    preview = render_narrative_preview(persisted["graph"])
    assert persisted["model_graph"]["artifact"]["artifact_type"] == "model_graph"
    assert persisted["evidence_graph"]["artifact"]["artifact_type"] == "evidence_graph"
    assert persisted["model_graph"]["artifact"]["artifact_id"] in persisted["artifact"]["upstream"]
    assert persisted["evidence_graph"]["artifact"]["artifact_id"] in persisted["artifact"]["upstream"]

    for prefix in ("artifact-", "result-", "table-", "claim-", "figure-"):
        assert prefix not in preview
    assert "SP1" not in persisted["graph"].node("SP1").answer or "artifact-" not in persisted["graph"].node("SP1").answer
    assert artifacts.verify(case_id)["valid"]

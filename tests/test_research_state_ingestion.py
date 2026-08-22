from pathlib import Path

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.io_utils import atomic_write_json
from mathworkstation.paper_contracts import PaperContractService, SubproblemContract
from mathworkstation.problem_graph import ProblemGraphService, assess_problem_graph
from mathworkstation.research_state_graphs import ModelGraphService
from mathworkstation.research_state_ingestion import (
    AcceptedResultSpec,
    AcceptedSubproblemExecution,
    AcceptedTableSpec,
    ResearchStateIngestionService,
)


def test_completed_external_solver_can_enter_canonical_research_state(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case_id = cases.create_case("MCM", "bridge fixture")["case_id"]
    artifacts = ArtifactRegistry(cases)
    contracts = PaperContractService(cases, artifacts)
    contracts.persist_subproblems(
        case_id,
        [
            SubproblemContract(
                subproblem_id="SP1",
                title="Analyze observed structure",
                objective="Estimate a supported descriptive relationship from observed data.",
            )
        ],
    )
    graphs = ProblemGraphService(cases, artifacts)
    graph = graphs.builder.build(contracts.list_subproblems(case_id))
    graphs.save(case_id, graph, created_by="test")

    root = cases.case_root(case_id)
    evidence_path = root / "analysis" / "solver-summary.json"
    atomic_write_json(evidence_path, {"metric": 0.73})
    evidence = artifacts.register_existing(
        case_id,
        evidence_path.relative_to(root).as_posix(),
        "solver_execution_result",
        "test_solver",
    )

    packet = AcceptedSubproblemExecution(
        subproblem_id="SP1",
        method="external descriptive solver",
        solver_evidence_artifact_ids=[evidence["artifact_id"]],
        validation_protocol_id="grouped-holdout-v1",
        validation_summary={"metric": 0.73, "notes": "fixture validation"},
        results=[
            AcceptedResultSpec(
                result_type="EXPLORATORY",
                metric="association_strength",
                value=0.73,
                scope="fixture observations",
            )
        ],
        tables=[
            AcceptedTableSpec(
                title="Accepted evidence summary",
                columns=["metric", "value"],
                rows=[["association_strength", 0.73]],
            )
        ],
        answer="The accepted relationship is positive and supported by the registered validation.",
        limitation="The result is descriptive and is not interpreted as a causal effect.",
    )
    result = ResearchStateIngestionService(cases, artifacts, contracts, graphs).ingest(
        case_id,
        [packet],
        generation=1,
    )

    accepted = result["graph"].node("SP1")
    assert accepted.state.status == "COMPLETED"
    assert accepted.answer is not None
    assert accepted.plan.selected_method == "external descriptive solver"
    assert assess_problem_graph(result["graph"]).research_gate == "PASS"
    assert len(contracts.list_results(case_id, active_only=True)) == 1
    assert len(contracts.list_tables(case_id, active_only=True)) == 1
    assert len(contracts.list_answers(case_id)) == 1

    model_graph = ModelGraphService(cases, artifacts, graphs).build(case_id)
    assert model_graph.gate == "PASS"
    assert model_graph.node("SP1").validation_gate == "PASS"

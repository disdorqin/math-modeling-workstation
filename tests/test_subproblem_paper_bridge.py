from pathlib import Path

import pandas as pd

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.claims import ClaimRegistry
from mathworkstation.datasets import DatasetRegistry
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.paper_contracts import PaperContractService, SubproblemContract
from mathworkstation.problem_graph import ProblemGraphService
from mathworkstation.subproblem_engine import SubproblemEngineService
from mathworkstation.subproblem_paper_bridge import (
    SubproblemPaperEvidenceBridge,
    _markup_response_slope_at_support_midpoint,
    _retail_relationship_table_row,
)


def test_subproblem_projection_creates_active_node_specific_paper_lineage(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "Subproblem paper bridge")
    case_id = case["case_id"]
    artifacts = ArtifactRegistry(cases)
    contracts = PaperContractService(cases, artifacts)
    claims = ClaimRegistry(cases, artifacts, DatasetRegistry(cases, artifacts))
    figures = FigureRegistry(cases, artifacts)
    graphs = ProblemGraphService(cases, artifacts)
    engine = SubproblemEngineService(cases, artifacts, graphs)
    bridge = SubproblemPaperEvidenceBridge(cases, artifacts, contracts, claims, figures)
    contracts.persist_subproblems(
        case_id,
        [
            SubproblemContract(
                subproblem_id="SP1",
                title="Explore interesting patterns",
                objective="Explore other interesting features of the data set",
                status="COMPLETED",
                evidence_artifact_ids=["legacy-placeholder"],
            ),
            SubproblemContract(
                subproblem_id="SP2",
                title="Write summary letter to editor",
                objective="Write a summary letter to editor",
                status="COMPLETED",
                evidence_artifact_ids=["legacy-placeholder"],
            ),
        ],
    )
    graphs.persist(case_id, contracts.list_subproblems(case_id), [])
    frame = pd.DataFrame({"a": range(40), "b": [value * 3 for value in range(40)]})

    executed = engine.execute_node(case_id, "SP1", {"numeric_columns": ["a", "b"]}, frame=frame)
    projection = bridge.project(case_id, "SP1", executed)
    assert projection["answer_record"].subproblem_id == "SP1"
    assert projection["answer_record"].result_record_ids
    assert projection["claim"]["subproblem_ids"] == ["SP1"]
    assert projection["result_records"][0].result_type == "EXPLORATORY"
    assert projection["figure"]["parameters"]["publication_profile"] == "MCM_C"

    synthesis = engine.complete_synthesis(case_id, "SP2", "Editor-facing synthesis from SP1 only.")
    bridge.project_synthesis(case_id, "SP2", synthesis)
    active = bridge.activate_if_complete(case_id, generation=1)
    assert active is not None
    assert active["result_ids"] == [item.result_id for item in projection["result_records"]]
    assert active["table_ids"] == [projection["table"].table_id]
    assert contracts.list_answers(case_id)[-1].subproblem_id == "SP2"
    assert artifacts.verify(case_id)["valid"]


def test_bridge_routes_plot_profile_from_case_manifest(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    for competition, expected in (("CUMCM", "CUMCM_C"), ("MCM", "MCM_C"), ("ICM", "MCM_C"), ("TEST", "SCI_CLEAN")):
        case = cases.create_case(competition, f"{competition} plot profile")
        artifacts = ArtifactRegistry(cases)
        bridge = SubproblemPaperEvidenceBridge(
            cases,
            artifacts,
            PaperContractService(cases, artifacts),
            ClaimRegistry(cases, artifacts, DatasetRegistry(cases, artifacts)),
            FigureRegistry(cases, artifacts),
        )
        assert bridge._publication_profile(case["case_id"]) == expected


def test_retail_relationship_paper_evidence_uses_solver_schema_and_quadratic_response() -> None:
    relationship = {
        "entity": "叶菜",
        "feature_variant": "quadratic_markup",
        "markup_response_coefficient": 2.0,
        "markup_quadratic_coefficient": -3.0,
        "validation_rmse": 1.234,
        "validation_mae": 0.987,
        "historical_markup_range": [0.2, 0.6],
    }
    row = _retail_relationship_table_row(relationship)
    assert row == ["叶菜", "时序校正二次响应", "2.0000", "-3.0000", "1.234", "0.987", "20.0%-60.0%"]
    assert abs(_markup_response_slope_at_support_midpoint(relationship) + 0.4) < 1e-12

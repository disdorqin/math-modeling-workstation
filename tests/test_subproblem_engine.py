from pathlib import Path

import pandas as pd
import pytest

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.paper_contracts import SubproblemContract
from mathworkstation.problem_graph import ProblemGraphService
from mathworkstation.subproblem_engine import SubproblemEngineService


def _engine(tmp_path: Path) -> tuple[CaseManager, ArtifactRegistry, ProblemGraphService, SubproblemEngineService, str]:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "Subproblem engine")
    artifacts = ArtifactRegistry(cases)
    graphs = ProblemGraphService(cases, artifacts)
    engine = SubproblemEngineService(cases, artifacts, graphs)
    return cases, artifacts, graphs, engine, case["case_id"]


def test_engine_executes_node_then_allows_synthesis(tmp_path: Path) -> None:
    _, artifacts, graphs, engine, case_id = _engine(tmp_path)
    contracts = [
        SubproblemContract(
            subproblem_id="SP1",
            title="Explore other interesting features",
            objective="Discover other interesting patterns in the data set",
        ),
        SubproblemContract(
            subproblem_id="SP2",
            title="Write summary letter to editor",
            objective="Write summary letter to editor",
        ),
    ]
    graph, _ = graphs.persist(case_id, contracts, [])
    assert graph.node("SP2").dependencies == ["SP1"]
    frame = pd.DataFrame({"a": range(30), "b": [value * 2 for value in range(30)]})

    first = engine.execute_node(case_id, "SP1", {"numeric_columns": ["a", "b"]}, frame=frame)
    assert first["family"] == "exploratory_analysis"
    assert first["research_gate"] == "INCOMPLETE"
    with pytest.raises(ValueError, match="DELIVERABLE_REQUIRES_SYNTHESIS_COMPLETION"):
        engine.execute_node(case_id, "SP2", {}, frame=frame)

    final = engine.complete_synthesis(case_id, "SP2", "Editor-facing synthesis based only on SP1 evidence.")
    assert final["research_gate"] == "PASS"
    completed = graphs.load(case_id)
    assert completed.node("SP1").state.status == "COMPLETED"
    assert completed.node("SP2").state.status == "COMPLETED"
    synthesis_artifact = artifacts.get(case_id, completed.node("SP2").state.evidence_artifact_ids[0])
    assert synthesis_artifact["artifact_type"] == "subproblem_synthesis_result"
    assert completed.node("SP1").state.evidence_artifact_ids[0] in synthesis_artifact["upstream"]


def test_engine_uses_future_aware_forecasting_path(tmp_path: Path) -> None:
    _, _, graphs, engine, case_id = _engine(tmp_path)
    graphs.persist(
        case_id,
        [
            SubproblemContract(
                subproblem_id="SP1",
                title="Predict future daily results",
                objective="Predict a future daily value with uncertainty",
            )
        ],
        [],
    )
    dates = pd.date_range("2025-01-01", periods=80, freq="D")
    frame = pd.DataFrame({"Date": dates, "x": range(80), "y": [100 + 2 * value for value in range(80)]})
    result = engine.execute_node(
        case_id,
        "SP1",
        {
            "time_column": "Date",
            "target_column": "y",
            "feature_columns": ["x"],
            "future_time": "2025-04-01",
            "future_features": {"x": 90},
            "bootstrap_runs": 50,
        },
        frame=frame,
    )
    assert result["execution"]["result"]["forecast"]["interval"]
    assert result["execution"]["artifact"]["artifact_type"] == "solver_execution_result"
    assert result["execution"]["solver"] == "gold.forecasting"
    experiment = result["graph_artifact"]
    loaded = graphs.load(case_id).node("SP1").experiments[0]
    assert loaded.validation_protocol == ["forecasting.temporal-uncertainty.v1"]
    assert loaded.validation_artifact_ids


def test_engine_refuses_unsupported_generic_modeling_fallback(tmp_path: Path) -> None:
    _, _, graphs, engine, case_id = _engine(tmp_path)
    graphs.persist(
        case_id,
        [
            SubproblemContract(
                subproblem_id="SP1",
                title="Construct a suitable model",
                objective="Construct a suitable model for the question",
            )
        ],
        [],
    )
    with pytest.raises(ValueError, match="SOLVER_PLUGIN_UNAVAILABLE:generic_modeling"):
        engine.execute_node(case_id, "SP1", {"target_column": "y"}, frame=pd.DataFrame({"y": [1, 2, 3]}))

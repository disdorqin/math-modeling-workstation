from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.claims import ClaimRegistry
from mathworkstation.competition_paper_auditor import CompetitionPaperAuditor
from mathworkstation.datasets import DatasetRegistry
from mathworkstation.energy_2018_gate import (
    ENERGY_STATES,
    build_energy_compact_target_plan,
    energy_2009_decision_frame,
    prepare_energy_2018_research,
)
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.narrative_graph import NarrativeGraphService
from mathworkstation.paper_contracts import PaperContractService, SubproblemContract
from mathworkstation.problem_graph import ProblemGraphService
from mathworkstation.research_state_paper import ResearchStatePaperService
from mathworkstation.solver_engine import SolverEngineService
from mathworkstation.subproblem_engine import SubproblemEngineService
from mathworkstation.subproblem_paper_bridge import SubproblemPaperEvidenceBridge


CASE_ROOT = Path("output/mcm-c-2018/v2/20260805-MCM-0001-4DH5")
OFFICIAL_WORKBOOK = Path(
    r"D:\作业\竞赛\大学生数学建模\美赛\备赛\资料\课程课件\美赛历年题目\16-24年美赛题目合集\2018_MCM-ICM_Problems\ProblemCData.xlsx"
)


def _contracts() -> list[SubproblemContract]:
    return [
        SubproblemContract.model_validate_json(line)
        for line in (CASE_ROOT / "results/contracts/subproblems.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _synthetic_seseds() -> pd.DataFrame:
    rows = []
    codes = ("RETCB", "REPRB", "TETCB", "TEPRB", "TETPB", "TPOPP")
    for state_index, state in enumerate(ENERGY_STATES, start=1):
        for year in range(1960, 2010):
            step = year - 1960
            total_consumption = 1000.0 + 100 * state_index + 8.0 * step
            total_production = 900.0 + 120 * state_index + 6.0 * step
            values = {
                "RETCB": total_consumption * (0.04 + 0.004 * state_index + 0.0005 * step),
                "REPRB": total_production * (0.06 + 0.005 * state_index + 0.0007 * step),
                "TETCB": total_consumption,
                "TEPRB": total_production,
                "TETPB": 300.0 - 10.0 * state_index - 0.4 * step,
                "TPOPP": 4000.0 + 500 * state_index + 20.0 * step,
            }
            for code in codes:
                rows.append({"MSN": code, "StateCode": state, "Year": year, "Data": values[code]})
    return pd.DataFrame(rows)


def test_prepare_energy_2018_research_builds_complete_common_profile_schema() -> None:
    panel, plans = prepare_energy_2018_research(_synthetic_seseds())

    assert panel.shape[0] == 200
    assert sorted(panel["StateCode"].unique()) == sorted(ENERGY_STATES)
    assert panel["Year"].min() == 1960
    assert panel["Year"].max() == 2009
    assert not panel[
        [
            "renewable_consumption_share",
            "renewable_production_share",
            "renewable_consumption_per_capita_mmbtu",
            "total_energy_per_capita_mmbtu",
        ]
    ].isna().any().any()
    assert plans["I-A"]["solver_method"] == "panel_profile_summary"
    assert plans["I-B"]["solver_method"] == "panel_trend_characterization"
    assert plans["I-C"]["solver_method"] == "entropy_topsis"
    assert plans["I-D"]["solver_method"] == "panel_holt"


def test_energy_2018_panel_solvers_use_task_specific_validation(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "2018 energy solver protocol Gate")
    artifacts = ArtifactRegistry(cases)
    engine = SolverEngineService(cases, artifacts)
    panel, plans = prepare_energy_2018_research(_synthetic_seseds())

    profile = engine.execute(case["case_id"], "I-A", "exploratory_analysis", plans["I-A"], frame=panel)
    trend = engine.execute(case["case_id"], "I-B", "forecasting", plans["I-B"], frame=panel)
    ranking = engine.execute(
        case["case_id"],
        "I-C",
        "ranking",
        plans["I-C"],
        frame=energy_2009_decision_frame(panel),
    )
    forecast = engine.execute(case["case_id"], "I-D", "forecasting", plans["I-D"], frame=panel)
    target_plan = build_energy_compact_target_plan(panel, forecast["result"])
    targets = engine.execute(case["case_id"], "II-A", "optimization", target_plan, frame=None)

    assert profile["solver"] == "gold.panel_profile_summary"
    assert profile["validation"]["assessment"].protocol_id == "exploration.panel-profile-summary.v1"
    assert profile["validation"]["assessment"].gate == "PASS"
    assert trend["solver"] == "gold.panel_trend_characterization"
    assert trend["validation"]["assessment"].protocol_id == "forecasting.panel-trend-characterization.v1"
    assert trend["validation"]["assessment"].gate == "PASS"
    assert ranking["solver"] == "gold.entropy_topsis"
    assert ranking["validation"]["assessment"].protocol_id == "ranking.entropy-topsis-stability.v1"
    assert ranking["validation"]["assessment"].gate in {"PASS", "REVIEW"}
    assert forecast["solver"] == "gold.panel_holt"
    assert forecast["validation"]["assessment"].protocol_id == "forecasting.panel-temporal-uncertainty.v1"
    assert forecast["validation"]["assessment"].gate == "PASS"
    assert len(forecast["result"]["forecast_grid"]) == 16
    assert targets["solver"] == "gold.linear_programming"
    solution = targets["result"]["solution"]
    for state in ENERGY_STATES:
        assert solution[f"target_{state}_2050"] >= solution[f"target_{state}_2025"] - 1e-12
    assert artifacts.verify(case["case_id"])["valid"]


def test_real_official_2018_energy_data_reaches_cross_problem_research_and_paper_gate(tmp_path: Path) -> None:
    if not OFFICIAL_WORKBOOK.is_file():
        pytest.skip("official 2018 ProblemCData.xlsx is not available on this machine")

    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "2018 energy cross-problem Paper Engine Gate")
    case_id = case["case_id"]
    artifacts = ArtifactRegistry(cases)
    source = artifacts.ingest_file(
        case_id,
        OFFICIAL_WORKBOOK,
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

    seseds = pd.read_excel(OFFICIAL_WORKBOOK, sheet_name="seseds")
    panel, plans = prepare_energy_2018_research(seseds)
    executed: dict[str, dict] = {}
    for subproblem_id, frame in (
        ("I-A", panel),
        ("I-B", panel),
        ("I-C", energy_2009_decision_frame(panel)),
        ("I-D", panel),
    ):
        executed[subproblem_id] = engine.execute_node(
            case_id,
            subproblem_id,
            plans[subproblem_id],
            frame=frame,
            source_artifact_ids=[source["artifact_id"]],
        )
        bridge.project(case_id, subproblem_id, executed[subproblem_id])

    target_plan = build_energy_compact_target_plan(panel, executed["I-D"]["execution"]["result"])
    executed["II-A"] = engine.execute_node(
        case_id,
        "II-A",
        target_plan,
        source_artifact_ids=[source["artifact_id"]],
        limitation=(
            "Compact targets are historically bounded stretch targets over renewable-consumption share; "
            "the supplied dataset does not identify policy cost or causal policy response."
        ),
    )
    bridge.project(case_id, "II-A", executed["II-A"])

    actions = engine.complete_synthesis(
        case_id,
        "II-B",
        (
            "The compact should prioritize closing the state-specific gap between the no-policy renewable-share forecast "
            "and the historically bounded target, track renewable production and consumption shares on the common profile, "
            "and review cross-state coordination measures before adopting any action whose legal or causal effect is not identified by the supplied data."
        ),
    )
    bridge.project_synthesis(case_id, "II-B", actions)
    memo = engine.complete_synthesis(
        case_id,
        "III",
        (
            "The governors' memo should summarize the common 2009 four-state profile, the accepted 2025/2050 no-policy forecasts, "
            "the historically bounded compact targets, and the explicit limitation that policy effects require evidence beyond the supplied SEDS panel."
        ),
    )
    bridge.project_synthesis(case_id, "III", memo)
    active = bridge.activate_if_complete(case_id, generation=1)
    assert active is not None

    graph = graphs.load(case_id)
    assert graph.node("I-C").answer is not None
    assert "CA" in graph.node("I-C").answer.answer
    ranking_payload = executed["I-C"]["execution"]["result"]
    assert ranking_payload["winner"] == "CA"
    assert ranking_payload["metrics"]["winner_retention_rate"] == pytest.approx(1.0)
    assert len(executed["I-D"]["execution"]["result"]["forecast_grid"]) == 16
    solution = executed["II-A"]["execution"]["result"]["solution"]
    for state in ENERGY_STATES:
        assert solution[f"target_{state}_2050"] >= solution[f"target_{state}_2025"] - 1e-12

    narrative = NarrativeGraphService(cases, artifacts, contracts, claims, figures, graphs)
    service = ResearchStatePaperService(
        cases,
        artifacts,
        contracts,
        figures,
        narrative,
        CompetitionPaperAuditor(),
    )
    result = service.generate(
        case_id,
        "A Data-Grounded Four-State Energy Compact",
        competition="MCM",
    )
    assert result["narrative"]["graph"].gate == "PASS"
    assert result["assessment"].block_count == 0
    same_problem = result["same_problem_full_text_assessment"]
    assert same_problem is not None
    assert same_problem.corpus_id == "mcm-2018-c-energy-compact-oaward-v1"
    assert same_problem.gate == "PASS"
    assert same_problem.document_gaps == 0
    assert same_problem.research_gaps == 0
    readiness = result["excellent_readiness"]
    assert readiness.internal_pass is True
    non_pass = [item for item in readiness.dimensions if item.status != "PASS"]
    assert [(item.dimension, item.status, item.repair_type) for item in non_pass] == [
        ("excellent_c_document_density_calibration", "REVIEW", "DOCUMENT"),
        ("blind_human_competition_review", "UNVERIFIED", "EXTERNAL"),
    ]
    text = result["paper_text"]
    assert "CA" in text and "AZ" in text and "NM" in text and "TX" in text
    assert "2025" in text and "2050" in text
    assert "entropy" in text.lower() and "topsis" in text.lower()
    assert "panel" in text.lower()
    assert "Governors' Memo" in text
    assert "Puzzle Editor" not in text
    assert "Wordle dataset" not in text
    assert artifacts.verify(case_id)["valid"]

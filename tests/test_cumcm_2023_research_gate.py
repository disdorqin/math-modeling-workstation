from __future__ import annotations

from pathlib import Path

import pytest

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.claims import ClaimRegistry
from mathworkstation.competition_paper_auditor import CompetitionPaperAuditor
from mathworkstation.cumcm_2023_gate import (
    CUMCM_2023_C_DATA_DIR,
    cumcm_2023_c_contracts,
    link_cumcm_2023_c_dependencies,
    load_cumcm_2023_c_frames,
    prepare_cumcm_2023_c_plans,
    prepare_q3_plan,
    q1_answer,
    q2_answer,
    q3_answer,
    q4_answer,
)
from mathworkstation.datasets import DatasetRegistry
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.narrative_graph import NarrativeGraphService
from mathworkstation.paper_contracts import PaperContractService
from mathworkstation.problem_graph import ProblemGraphService
from mathworkstation.research_state_paper import ResearchStatePaperService
from mathworkstation.subproblem_engine import SubproblemEngineService
from mathworkstation.subproblem_paper_bridge import SubproblemPaperEvidenceBridge


PROBLEM_PDF = CUMCM_2023_C_DATA_DIR / "C题.pdf"
ATTACHMENTS = [CUMCM_2023_C_DATA_DIR / f"附件{index}.xlsx" for index in range(1, 5)]


def test_real_cumcm_2023_c_runs_evidence_locked_paper_with_argument_aware_tables_and_figures(tmp_path: Path) -> None:
    if not PROBLEM_PDF.is_file() or not all(path.is_file() for path in ATTACHMENTS):
        pytest.skip("official CUMCM 2023 C problem and attachments are not available on this machine")

    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("CUMCM", "2023 CUMCM C 蔬菜类商品的自动定价与补货决策")
    case_id = case["case_id"]
    artifacts = ArtifactRegistry(cases)
    sources = [
        artifacts.ingest_file(case_id, PROBLEM_PDF, "input/problem/C题.pdf", "problem_source"),
        *[
            artifacts.ingest_file(case_id, path, f"input/data/附件{index}.xlsx", "observed_data")
            for index, path in enumerate(ATTACHMENTS, start=1)
        ],
    ]
    source_ids = [item["artifact_id"] for item in sources]

    contracts = PaperContractService(cases, artifacts)
    contracts.persist_subproblems(case_id, cumcm_2023_c_contracts())
    graphs = ProblemGraphService(cases, artifacts)
    graph = link_cumcm_2023_c_dependencies(graphs.builder.build(contracts.list_subproblems(case_id)))
    graph, _graph_artifact = graphs.save(case_id, graph, source_ids)
    assert graphs.assess(graph).structure_gate == "PASS"
    assert graph.node("SP2").dependencies == ["SP1"]
    assert graph.node("SP3").dependencies == ["SP2"]
    assert graph.node("SP4").dependencies == ["SP1", "SP2", "SP3"]

    frames = load_cumcm_2023_c_frames()
    plans = prepare_cumcm_2023_c_plans(frames)
    claims = ClaimRegistry(cases, artifacts, DatasetRegistry(cases, artifacts))
    figures = FigureRegistry(cases, artifacts)
    engine = SubproblemEngineService(cases, artifacts, graphs)
    bridge = SubproblemPaperEvidenceBridge(cases, artifacts, contracts, claims, figures)

    q1_exec = engine.execute_node(
        case_id,
        "SP1",
        plans["SP1"],
        frame=frames["q1"],
        source_artifact_ids=source_ids,
        answer_text=q1_answer({})[0],
        limitation=q1_answer({})[1],
    )
    # Replace the provisional deterministic wording with the actual evidence-bearing answer.
    q1_text, q1_limitation = q1_answer(q1_exec["execution"]["result"])
    graph = graphs.load(case_id)
    graph.node("SP1").answer.answer = q1_text  # type: ignore[union-attr]
    graph.node("SP1").answer.limitation = q1_limitation  # type: ignore[union-attr]
    graphs.save(case_id, graph, [q1_exec["execution"]["artifact"]["artifact_id"]], created_by="test_gate")
    q1_projected = bridge.project(case_id, "SP1", q1_exec)
    assert q1_projected["result_records"]

    q2_exec = engine.execute_node(
        case_id,
        "SP2",
        plans["SP2"],
        frame=frames["category_daily"],
        source_artifact_ids=source_ids,
    )
    q2_text, q2_limitation = q2_answer(q2_exec["execution"]["result"])
    graph = graphs.load(case_id)
    graph.node("SP2").answer.answer = q2_text  # type: ignore[union-attr]
    graph.node("SP2").answer.limitation = q2_limitation  # type: ignore[union-attr]
    graphs.save(case_id, graph, [q2_exec["execution"]["artifact"]["artifact_id"]], created_by="test_gate")
    q2_projected = bridge.project(case_id, "SP2", q2_exec)

    q3_plan = prepare_q3_plan(q2_exec["execution"]["result"])
    q3_exec = engine.execute_node(
        case_id,
        "SP3",
        q3_plan,
        frame=frames["item_daily"],
        source_artifact_ids=source_ids,
    )
    q3_text, q3_limitation = q3_answer(q3_exec["execution"]["result"])
    graph = graphs.load(case_id)
    graph.node("SP3").answer.answer = q3_text  # type: ignore[union-attr]
    graph.node("SP3").answer.limitation = q3_limitation  # type: ignore[union-attr]
    graphs.save(case_id, graph, [q3_exec["execution"]["artifact"]["artifact_id"]], created_by="test_gate")
    q3_projected = bridge.project(case_id, "SP3", q3_exec)

    q4_exec = engine.complete_synthesis(case_id, "SP4", q4_answer())
    bridge.project_synthesis(case_id, "SP4", q4_exec)
    active = bridge.activate_if_complete(case_id, generation=1)
    assert active is not None
    assert graphs.assess(graphs.load(case_id)).research_gate == "PASS"

    q2 = q2_exec["execution"]["result"]
    q3 = q3_exec["execution"]["result"]
    assert len(q2["strategy"]) == 42
    assert q2["metrics"]["entity_count"] == pytest.approx(6.0)
    assert len(q2["sensitivity_runs"]) >= 2
    assert 27 <= int(q3["selected_item_count"]) <= 33
    assert q3["metrics"]["category_coverage_count"] == pytest.approx(6.0)
    assert q3["metrics"]["minimum_order_quantity"] >= 2.5

    q2_roles = {item["table"].metadata.get("table_role") for item in q2_projected["auxiliary_tables"]}
    q3_roles = {item["table"].metadata.get("table_role") for item in q3_projected["auxiliary_tables"]}
    assert {"decision_schedule", "relationship_validation"} <= q2_roles
    assert "decision_schedule" in q3_roles
    q3_decision_table = next(
        item["table"]
        for item in q3_projected["auxiliary_tables"]
        if item["table"].metadata.get("table_role") == "decision_schedule"
    )
    assert len(q3_decision_table.rows) == int(q3["selected_item_count"])

    narrative = NarrativeGraphService(cases, artifacts, contracts, claims, figures, graphs)
    paper_service = ResearchStatePaperService(
        cases,
        artifacts,
        contracts,
        figures,
        narrative,
        CompetitionPaperAuditor(),
    )
    paper = paper_service.generate(case_id, "2023 CUMCM C 蔬菜类商品的自动定价与补货决策", competition="CUMCM")
    text = paper["paper_text"]
    assert paper["assessment"].block_count == 0, [
        (item.code, item.message, item.source)
        for item in paper["assessment"].findings
        if item.severity == "BLOCK"
    ]

    # Exact decision tables must survive into the paper, not only summary metrics.
    assert "未来一周各蔬菜品类定价与补货策略" in text
    assert "各蔬菜品类成本加成与销量关系的时间留出估计" in text
    assert "7月1日单品定价与补货执行方案" in text
    assert text.count("| 2023-07-") >= 42
    assert text.count("| 102") >= 27

    # Argument-aware order: mechanism -> decision overview -> decision table -> robustness -> conclusion.
    relation_fig = text.index("各蔬菜品类加价率与需求的关联响应")
    relation_table = text.index("各蔬菜品类成本加成与销量关系的时间留出估计")
    q2_decision_figure = text.index("未来一周各蔬菜品类补货策略")
    q2_decision_table = text.index("未来一周各蔬菜品类定价与补货策略")
    sensitivity = text.index("关键参数扰动") if "关键参数扰动" in text else text.index("sensitivity")
    q2_conclusion = text.index("**本问结论：**", q2_decision_table)
    assert relation_fig < relation_table < q2_decision_figure < q2_decision_table < sensitivity < q2_conclusion

    # Internal registry identifiers remain outside the user-visible paper.
    assert "table-id:" not in text
    assert "table-" not in text
    assert artifacts.verify(case_id)["valid"] is True

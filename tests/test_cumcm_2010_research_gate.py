from __future__ import annotations

from pathlib import Path

import pytest

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.claims import ClaimRegistry
from mathworkstation.competition_paper_auditor import CompetitionPaperAuditor
from mathworkstation.cumcm_2010_gate import (
    answer_texts,
    cumcm_2010_c_contracts,
    link_cumcm_2010_c_dependencies,
    prepare_cumcm_2010_c_plans,
    weighted_urban_surcharge,
)
from mathworkstation.datasets import DatasetRegistry
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.modeling_brain import ModelingBrainService
from mathworkstation.narrative_graph import NarrativeGraphService
from mathworkstation.paper_contracts import PaperContractService
from mathworkstation.problem_graph import ProblemGraphService
from mathworkstation.research_state_paper import ResearchStatePaperService
from mathworkstation.subproblem_engine import SubproblemEngineService
from mathworkstation.subproblem_paper_bridge import SubproblemPaperEvidenceBridge


OFFICIAL_PROBLEM = Path(
    r"D:\作业\竞赛\大学生数学建模\美赛\备赛\资料\论文\高教社论文\I953高教社杯全国大学生数学建模竞赛题目及优秀论文\高教社杯全国大学生数学建模竞赛往届题目\2010高教社杯全国大学生数学建模竞赛题目\2010C\cumcm2010C.doc"
)


def test_real_cumcm_2010_c_reaches_research_validation_and_chinese_paper_gate(tmp_path: Path) -> None:
    if not OFFICIAL_PROBLEM.is_file():
        pytest.skip("official CUMCM 2010 C problem source is not available on this machine")

    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("CUMCM", "2010 CUMCM C 输油管布置")
    case_id = case["case_id"]
    artifacts = ArtifactRegistry(cases)
    source = artifacts.ingest_file(case_id, OFFICIAL_PROBLEM, "input/problem/cumcm2010C.doc", "problem_source")

    contracts = PaperContractService(cases, artifacts)
    contracts.persist_subproblems(case_id, cumcm_2010_c_contracts())
    graphs = ProblemGraphService(cases, artifacts)
    graph = link_cumcm_2010_c_dependencies(graphs.builder.build(contracts.list_subproblems(case_id)))
    graph, graph_artifact = graphs.save(case_id, graph, [source["artifact_id"]])
    assessment = graphs.assess(graph)
    assert assessment.structure_gate == "PASS"
    assert graph.node("SP2").dependencies == ["SP1"]
    assert graph.node("SP3").dependencies == ["SP2"]

    brain = ModelingBrainService(cases, artifacts, graphs)
    for subproblem_id in ("SP1", "SP2", "SP3"):
        deliberation = brain.deliberate(case_id, subproblem_id, source_artifact_ids=[source["artifact_id"]])
        decision = deliberation["decision"]
        assert decision.benchmark_prior_source == "config/ref_models/c_problem_excellent_benchmark_v1.json"
        assert decision.gate != "BLOCKED"
        assert "pipeline layout continuous optimization" in decision.selected_methods

    claims = ClaimRegistry(cases, artifacts, DatasetRegistry(cases, artifacts))
    figures = FigureRegistry(cases, artifacts)
    engine = SubproblemEngineService(cases, artifacts, graphs)
    bridge = SubproblemPaperEvidenceBridge(cases, artifacts, contracts, claims, figures)
    plans = prepare_cumcm_2010_c_plans()
    texts = answer_texts()
    executed: dict[str, dict] = {}
    for subproblem_id in ("SP1", "SP2", "SP3"):
        answer, limitation = texts[subproblem_id]
        executed[subproblem_id] = engine.execute_node(
            case_id,
            subproblem_id,
            plans[subproblem_id],
            source_artifact_ids=[source["artifact_id"]],
            answer_text=answer,
            limitation=limitation,
        )
        projected = bridge.project(case_id, subproblem_id, executed[subproblem_id])
        assert projected["result_records"]
        metrics = [record.metric for record in projected["result_records"]]
        assert len(metrics) == len(set(metrics))
        assert projected["table"].result_ids
        assert executed[subproblem_id]["execution"]["validation"]["assessment"].gate == "PASS"

    active = bridge.activate_if_complete(case_id, generation=1)
    assert active is not None
    final_graph = graphs.load(case_id)
    assert graphs.assess(final_graph).research_gate == "PASS"

    q2 = executed["SP2"]["execution"]["result"]
    q3 = executed["SP3"]["execution"]["result"]
    assert weighted_urban_surcharge() == pytest.approx(21.5)
    assert q2["objective_value"] == pytest.approx(282.6973, abs=1e-3)
    assert q2["solution"]["station_x"] == pytest.approx(5.4494, abs=2e-3)
    assert q3["objective_value"] == pytest.approx(251.9685, abs=1e-3)
    assert q3["no_shared_comparison"]["objective_value"] == pytest.approx(251.9755, abs=2e-3)
    assert 0.0 < q3["metrics"]["shared_cost_advantage"] < 0.02

    narrative = NarrativeGraphService(cases, artifacts, contracts, claims, figures, graphs)
    paper_service = ResearchStatePaperService(
        cases,
        artifacts,
        contracts,
        figures,
        narrative,
        CompetitionPaperAuditor(),
    )
    paper = paper_service.generate(case_id, "2010 CUMCM C 输油管布置", competition="CUMCM")
    text = paper["paper_text"]
    audit = paper["assessment"]

    assert paper["paper_profile"].profile_id == "CUMCM_C"
    assert "# 摘要" in text
    assert "# 1. 问题重述与分析" in text
    assert "# 3. 模型建立、检验与结果" in text
    assert "# 5. 模型评价、稳健性与局限" in text
    assert "数据预处理与特征构造" not in text
    assert "各问综合与交付结果" not in text
    assert "题目指定交付内容" not in text
    assert "# Summary" not in text
    assert "Problem Analysis and Decomposition" not in text
    assert "282.697" in text
    assert "251.969" in text or "251.968" in text
    assert "L(x,y,z)" in text
    assert "连续几何管线布局优化模型" in text
    for leaked in ("accepted Research State", "SolverRegistry", "reported values include", "accepted question-level evidence"):
        assert leaked not in text
    paper_figures = figures.list_figures(case_id)
    question_figures = [item for item in paper_figures if (item.get("parameters") or {}).get("subproblem_id")]
    assert question_figures
    primary_figures = [
        item for item in question_figures
        if (item.get("parameters") or {}).get("paper_role") == "primary"
    ]
    assert len(primary_figures) == 3
    assert all((item.get("parameters") or {}).get("semantic_kind") == "route_layout_geometry" for item in primary_figures)
    semantic_kinds = {(item.get("parameters") or {}).get("semantic_kind") for item in question_figures}
    assert "parameter_sensitivity_curve" in semantic_kinds
    assert "scenario_cost_comparison" in semantic_kinds
    assert not any("compact target" in str(item.get("title", "")).lower() for item in question_figures)
    assert "最优管线布局的关键坐标" in text
    assert "关键参数扰动下的目标函数变化" in text
    assert "共用与非共用方案的最优成本比较" in text
    assert audit.profile_id == "CUMCM_C"
    assert audit.block_count == 0, [(item.code, item.message, item.source) for item in audit.findings if item.severity == "BLOCK"]
    assert not any(item.source == "c_problem_paper_profile" for item in audit.findings)
    assert paper["bibliography_coverage"]["domain_reference_count"] >= 2
    readiness = {item.dimension: item for item in paper["excellent_readiness"].dimensions}
    assert readiness["domain_bibliography_coverage"].status == "PASS"
    assert readiness["full_text_excellent_paper_benchmark"].status == "PASS"
    assert "5 C-problem corpora / 21 excellent papers" in readiness["full_text_excellent_paper_benchmark"].evidence
    assert artifacts.verify(case_id)["valid"] is True

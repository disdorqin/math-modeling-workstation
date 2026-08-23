from __future__ import annotations

from mathworkstation.bibliography import VerifiedReference
from mathworkstation.c_problem_paper_profiles import CProblemPaperProfileRegistry, profile_structure_findings
from mathworkstation.competition_paper_auditor import CompetitionPaperAuditor
from mathworkstation.narrative_graph import NarrativeGraph, NarrativeNode, NarrativeResult
from mathworkstation.research_state_paper import render_research_state_paper


def _graph() -> NarrativeGraph:
    return NarrativeGraph(
        case_id="profile-case",
        gate="PASS",
        research_gate="PASS",
        model_graph_gate="PASS",
        evidence_graph_gate="PASS",
        nodes=[
            NarrativeNode(
                subproblem_id="SP1",
                title="Future demand",
                role="RESEARCH",
                task_family="forecasting",
                objective="forecast next-period demand",
                method="ridge_time_trend",
                answer="Accepted forecast is 12.5 units.",
                limitation="The forecast is conditional on the observed historical window.",
                key_results=[
                    NarrativeResult(
                        metric="future_point",
                        value=12.5,
                        direction="future",
                        model_name="ridge_time_trend",
                        metadata={"future": True},
                    )
                ],
                validation_gate="PASS",
                validation_protocol_id="forecasting.temporal-uncertainty.v1",
                data_columns=["date", "demand"],
                preprocessing_notes=["Chronological order is preserved."],
                gate="PASS",
            )
        ],
        storyline=["SP1 closes the forecasting question."],
        generated_at="2026-08-20T14:00:00+08:00",
    )


def _references() -> list[VerifiedReference]:
    return [
        VerifiedReference(
            key=f"r{index}",
            citation=f"Author {index}. Verified method reference. 200{index}.",
            supports=["ridge", "forecast"],
            available_year=2000 + index,
            verification_url=f"https://example.org/{index}",
            verification_note="test fixture",
        )
        for index in range(1, 4)
    ]


def test_registry_separates_mcm_c_and_cumcm_c() -> None:
    registry = CProblemPaperProfileRegistry()

    assert registry.resolve("MCM").profile_id == "MCM_C"
    assert registry.resolve("CUMCM").profile_id == "CUMCM_C"
    assert registry.resolve("高教社杯国赛").profile_id == "CUMCM_C"


def test_same_research_state_renders_distinct_competition_profiles_without_changing_number() -> None:
    registry = CProblemPaperProfileRegistry()
    graph = _graph()
    refs = _references()

    mcm = render_research_state_paper(
        graph,
        "C Problem",
        refs,
        [],
        profile=registry.resolve("MCM"),
    )
    cumcm = render_research_state_paper(
        graph,
        "C题研究",
        refs,
        [],
        profile=registry.resolve("CUMCM"),
    )

    assert "# Summary" in mcm
    assert "# 1. Problem Analysis and Decomposition" in mcm
    assert "# 摘要" not in mcm
    assert "# 摘要" in cumcm
    assert "# 1. 问题重述与分析" in cumcm
    assert "# 4. 模型建立、检验与结果" in cumcm
    assert "Problem Analysis and Decomposition" not in cumcm
    assert "12.5" in mcm and "12.5" in cumcm
    assert "forecasting.temporal uncertainty.v1" in mcm
    assert "时间留出与预测不确定性检验" in cumcm
    assert "forecasting.temporal uncertainty.v1" not in cumcm


def test_profile_structure_finder_detects_cross_competition_heading_pollution() -> None:
    registry = CProblemPaperProfileRegistry()
    profile = registry.resolve("CUMCM")
    polluted = "# 摘要\n结果。\n# 1. Problem Analysis and Decomposition\nEnglish MCM heading.\n"

    findings = profile_structure_findings(polluted, profile)

    assert any(item["code"] == "COMPETITION_PROFILE_CROSS_CONTAMINATION" for item in findings)


def test_competition_auditor_keeps_profile_defects_in_document_layer() -> None:
    registry = CProblemPaperProfileRegistry()
    graph = _graph()
    refs = _references()
    valid = render_research_state_paper(
        graph,
        "C题研究",
        refs,
        [],
        profile=registry.resolve("CUMCM"),
    )
    auditor = CompetitionPaperAuditor()
    valid_assessment = auditor.audit(valid, graph, case_id="profile-case", competition="CUMCM")

    assert valid_assessment.profile_id == "CUMCM_C"
    assert not any(item.code == "COMPETITION_PROFILE_CROSS_CONTAMINATION" for item in valid_assessment.findings)

    polluted = valid + "\n# Problem Analysis and Decomposition\n"
    polluted_assessment = auditor.audit(polluted, graph, case_id="profile-case", competition="CUMCM")
    finding = next(item for item in polluted_assessment.findings if item.code == "COMPETITION_PROFILE_CROSS_CONTAMINATION")

    assert finding.defect_type == "DOCUMENT"
    assert finding.severity == "BLOCK"
    assert finding.source == "c_problem_paper_profile"


def test_legacy_audit_without_explicit_competition_does_not_invent_profile() -> None:
    assessment = CompetitionPaperAuditor().audit(
        "# Abstract\nQuestion 1 uses ridge and reports 12.5.\n\n# References\n[1] A. 2020.\n[2] B. 2021.\n[3] C. 2022.\n",
        None,
    )

    assert assessment.profile_id is None
    assert not any(item.source == "c_problem_paper_profile" for item in assessment.findings)

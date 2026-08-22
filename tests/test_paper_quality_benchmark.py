from __future__ import annotations

from types import SimpleNamespace

from mathworkstation.excellent_readiness import ExcellentReadinessService
from mathworkstation.paper_quality_benchmark import PaperQualityBenchmarkService


def _dimension(name: str, status: str = "REVIEW") -> SimpleNamespace:
    return SimpleNamespace(dimension=name, status=status)


def test_cumcm_peer_profile_comes_from_c_only_excellent_corpora() -> None:
    service = PaperQualityBenchmarkService()
    peer = service._peer_profile("CUMCM_C")

    assert peer["abstract_units"] > 0
    assert peer["abstract_numeric_tokens"] > 0
    assert peer["figure_mentions"] > 0
    assert peer["table_mentions"] > 0
    assert peer["reference_entries"] == 0
    assert peer["source_corpora"] == ["distilled_prior_bank_v1:competition:CUMCM:C:modern:papers=9:parsed=4"]


def test_thin_cumcm_draft_is_reviewed_without_quota_padding() -> None:
    service = PaperQualityBenchmarkService()
    paper = """# 摘要\n\n本文建立优化模型。结果为 1.23。\n\n# 1. 问题分析\n\n正文。\n\n# 参考文献\n\n[1] 示例。\n"""
    figures = [
        {
            "status": "FINAL",
            "parameters": {"semantic_kind": "research_workflow"},
        }
    ]

    assessment = service.assess(paper, figures, profile_id="CUMCM_C", case_id="case-x")
    gaps = {item.dimension for item in assessment.dimensions if item.status == "REVIEW"}

    assert assessment.gate == "REVIEW"
    assert "excellent_abstract_density" in gaps
    assert "excellent_figure_density" in gaps
    assert any("do not" in item.gap.lower() or "不要" in item.gap for item in assessment.dimensions if item.gap)


def test_mcm_peer_profile_prefers_full_distilled_prior_bank() -> None:
    service = PaperQualityBenchmarkService()
    peer = service._peer_profile("MCM_C")

    assert peer["reference_entries"] == 0
    assert peer["abstract_units"] == 454.0
    assert peer["figure_mentions"] == 24.0
    assert peer["source_corpora"] == ["distilled_prior_bank_v1:competition:MCM:C:modern:papers=82:parsed=59"]


def test_excellent_readiness_routes_new_quality_gates_to_document_review() -> None:
    readiness = ExcellentReadinessService().assess(
        "case-quality",
        narrative=SimpleNamespace(
            gate="PASS",
            research_gate="PASS",
            model_graph_gate="PASS",
            evidence_graph_gate="PASS",
            nodes=[],
        ),
        model_graph=None,
        competition_assessment=SimpleNamespace(
            block_count=0,
            findings=[],
            reference_papers_count=0,
        ),
        bibliography_coverage={"method_gaps": [], "domain_reference_count": 2},
        abstract_quality=SimpleNamespace(
            gate="REVIEW",
            score=72.0,
            dimensions=[_dimension("information_density")],
        ),
        visual_quality=SimpleNamespace(
            gate="REVIEW",
            score=74.0,
            dimensions=[_dimension("semantic_diversity")],
        ),
        paper_quality_benchmark=SimpleNamespace(
            gate="REVIEW",
            score=66.0,
            dimensions=[_dimension("excellent_figure_density")],
            source_corpora=["CUMCM 2018 C", "CUMCM 2023 C"],
        ),
        full_text_corpus_available=False,
        blind_human_review_count=0,
        real_paper_gates_passed=2,
    )
    by_name = {item.dimension: item for item in readiness.dimensions}

    for name in (
        "abstract_competition_quality",
        "visual_argument_quality",
        "excellent_c_document_density_calibration",
    ):
        assert by_name[name].status == "REVIEW"
        assert by_name[name].repair_type == "DOCUMENT"

    assert readiness.internal_pass is True
    assert readiness.verdict == "PROMISING_INTERNAL_PASS_EXTERNAL_VALIDATION_REQUIRED"


def test_excellent_readiness_marks_document_quality_pass_when_all_three_gates_pass() -> None:
    pass_quality = SimpleNamespace(gate="PASS", score=91.0, dimensions=[_dimension("ok", "PASS")])
    readiness = ExcellentReadinessService().assess(
        "case-quality-pass",
        narrative=SimpleNamespace(
            gate="PASS",
            research_gate="PASS",
            model_graph_gate="PASS",
            evidence_graph_gate="PASS",
            nodes=[],
        ),
        model_graph=None,
        competition_assessment=SimpleNamespace(
            block_count=0,
            findings=[],
            reference_papers_count=0,
        ),
        bibliography_coverage={"method_gaps": [], "domain_reference_count": 2},
        abstract_quality=pass_quality,
        visual_quality=pass_quality,
        paper_quality_benchmark=SimpleNamespace(
            gate="PASS",
            score=91.0,
            dimensions=[_dimension("ok", "PASS")],
            source_corpora=["peer"],
        ),
        full_text_corpus_available=False,
        blind_human_review_count=0,
        real_paper_gates_passed=2,
    )
    by_name = {item.dimension: item for item in readiness.dimensions}

    assert by_name["abstract_competition_quality"].status == "PASS"
    assert by_name["visual_argument_quality"].status == "PASS"
    assert by_name["excellent_c_document_density_calibration"].status == "PASS"

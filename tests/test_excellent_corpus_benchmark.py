from pathlib import Path

from mathworkstation.excellent_corpus_benchmark import ExcellentCorpusBenchmarkService
from tests.test_research_state_paper import CASE_ROOT, _service


def test_structured_corpus_extracts_cross_year_standards() -> None:
    service = ExcellentCorpusBenchmarkService()
    standards = service.standards()
    by_aspect = {item.aspect: item for item in standards}

    assert len(standards) >= 16
    assert by_aspect["问题分层递进、逐问求解"].support_count == 11
    assert by_aspect["模型假设先行、逐条列出"].tier == "CORE"
    assert by_aspect["分情形/多方案对比呈现"].repair_type == "RESEARCH"
    assert by_aspect["模型/流程示意图"].repair_type == "DOCUMENT"


def test_wordle_gap_benchmark_separates_research_from_document_gap(tmp_path: Path) -> None:
    _cases, _artifacts, _narrative, _auditor, paper_service, case_id = _service(tmp_path)
    generated = paper_service.generate(case_id, "A Research-State Analysis of Wordle")
    graph = generated["narrative"]["graph"]
    benchmark = ExcellentCorpusBenchmarkService().assess(
        case_id,
        generated["paper_text"],
        graph,
        figures=paper_service.figures.list_figures(case_id),
    )
    by_aspect = {item.aspect: item for item in benchmark.gaps}

    assert by_aspect["问题分层递进、逐问求解"].status == "MET"
    assert by_aspect["结果量化、给出具体数字"].status == "MET"
    assert by_aspect["分情形/多方案对比呈现"].status == "MET"
    assert by_aspect["分情形/多方案对比呈现"].repair_type == "RESEARCH"
    assert by_aspect["分情形/多方案对比呈现"].subproblem_ids == []
    assert "No distinct alternative is explicitly registered as executable PASS" in by_aspect["分情形/多方案对比呈现"].evidence
    assert by_aspect["模型/流程示意图"].status == "MET"
    assert by_aspect["模型/流程示意图"].repair_type == "DOCUMENT"


def test_new_wordle_structured_gap_profile_beats_old_baseline(tmp_path: Path) -> None:
    _cases, _artifacts, _narrative, _auditor, paper_service, case_id = _service(tmp_path)
    generated = paper_service.generate(case_id, "A Research-State Analysis of Wordle")
    graph = generated["narrative"]["graph"]
    figures = paper_service.figures.list_figures(case_id)
    benchmark = ExcellentCorpusBenchmarkService()

    new_assessment = benchmark.assess(case_id, generated["paper_text"], graph, figures=figures)
    old_text = (CASE_ROOT / "paper/final.md").read_text(encoding="utf-8")
    old_assessment = benchmark.assess(case_id, old_text, graph, figures=[])

    assert new_assessment.met_count > old_assessment.met_count
    assert new_assessment.gap_count < old_assessment.gap_count


def test_structured_corpus_benchmark_persists_artifact(tmp_path: Path) -> None:
    cases, artifacts, _narrative, _auditor, paper_service, case_id = _service(tmp_path)
    generated = paper_service.generate(case_id, "A Research-State Analysis of Wordle")
    service = ExcellentCorpusBenchmarkService()
    assessment = service.assess(
        case_id,
        generated["paper_text"],
        generated["narrative"]["graph"],
        figures=paper_service.figures.list_figures(case_id),
    )
    persisted = service.persist(
        cases,
        artifacts,
        case_id,
        assessment,
        source_artifact_ids=[generated["paper_artifact"]["artifact_id"]],
    )

    assert persisted["artifact"]["artifact_type"] == "excellent_corpus_benchmark"
    assert artifacts.verify(case_id)["valid"]

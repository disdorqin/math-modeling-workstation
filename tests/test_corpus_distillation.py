from pathlib import Path

from mathworkstation.corpus_distillation import (
    CorpusPaperFingerprint,
    CorpusPaperSource,
    _persist_fingerprint_cache,
    distill_registered_corpus_cached,
    fingerprint_paper,
    recency_style_weight,
    scan_registered_excellent_papers,
    summarize_fingerprints,
    teacher_packet,
)


def _source(*, paper_id: str, year: int, c_problem: bool, style_weight: float, modeling_weight: float) -> CorpusPaperSource:
    return CorpusPaperSource(
        paper_id=paper_id,
        corpus_id="test",
        competition="MCM" if paper_id.startswith("m") else "CUMCM",
        year=year,
        problem_letter="C" if c_problem else "A",
        award="O_AWARD",
        source_path=f"{paper_id}.pdf",
        title_hint=paper_id,
        file_size=1,
        modified_ns=1,
        source_fingerprint=paper_id,
        duplicate_group=paper_id,
        c_problem=c_problem,
        style_weight=style_weight,
        modeling_weight=modeling_weight,
    )


def _fingerprint(source: CorpusPaperSource, *, figures: int, workflow: bool, purpose: str) -> CorpusPaperFingerprint:
    return CorpusPaperFingerprint(
        source=source,
        status="PARSED",
        backend="pymupdf",
        page_count=20,
        text_characters=20000,
        language="en",
        abstract_units=400,
        abstract_numeric_tokens=12,
        abstract_method_count=4,
        model_sequence_length=5,
        figure_mentions=figures,
        table_mentions=8,
        reference_entries=10,
        workflow_figure_signal=workflow,
        figure_purposes={purpose: 2},
        validation_types=["sensitivity_or_robustness"],
        image_count=12,
        pages_with_images=9,
        image_area_ratio=0.2,
        text_area_ratio=0.55,
        landscape_page_ratio=0.0,
        generated_at="2026-08-21T00:00:00+00:00",
    )


def test_recent_papers_have_higher_style_weight_than_classic_papers() -> None:
    assert recency_style_weight(2025) > recency_style_weight(2023) > recency_style_weight(2018) > recency_style_weight(2010)


def test_registry_scan_understands_recent_mcm_and_cumcm_folder_conventions(tmp_path: Path) -> None:
    root = tmp_path / "kb"
    mcm = root / "mcm"
    cumcm = root / "cumcm"
    mcm_pdf = mcm / "2023年美赛特等奖论文" / "C" / "2300348.pdf"
    mcm_2014 = mcm / "2013-2016美赛优秀论文集" / "2014美赛特等奖原版论文集" / "C题" / "28001.pdf"
    cumcm_pdf = cumcm / "2025年高教社杯全国大学生数学建模竞赛优秀论文" / "2025C：NIPT时点优化.pdf"
    cumcm_2021 = cumcm / "2021年高教社杯全国大学生数学建模竞赛优秀论文" / "C066.pdf"
    cumcm_2024 = cumcm / "2024年高教社全国大学生数学建模竞赛优秀论文" / "2024高教社杯数学建模国赛论文C063.pdf"
    mcm_pdf.parent.mkdir(parents=True)
    mcm_2014.parent.mkdir(parents=True)
    cumcm_pdf.parent.mkdir(parents=True)
    cumcm_2021.parent.mkdir(parents=True)
    cumcm_2024.parent.mkdir(parents=True)
    mcm_pdf.write_bytes(b"pdf")
    mcm_2014.write_bytes(b"pdf")
    cumcm_pdf.write_bytes(b"pdf")
    cumcm_2021.write_bytes(b"pdf")
    cumcm_2024.write_bytes(b"pdf")
    registry = tmp_path / "registry.json"
    registry.write_text(
        """{
          "source_root": "%s",
          "assets": [
            {"asset_id":"mcm","path":"mcm","kind":"excellent_paper_corpus","competition":"MCM_ICM"},
            {"asset_id":"cumcm","path":"cumcm","kind":"excellent_paper_corpus","competition":"CUMCM"}
          ]
        }""" % str(root).replace("\\", "\\\\"),
        encoding="utf-8",
    )
    papers = scan_registered_excellent_papers(registry)
    indexed = {(item.competition, item.year, item.problem_letter) for item in papers}
    assert ("MCM", 2023, "C") in indexed
    assert ("MCM", 2014, "C") in indexed
    assert ("CUMCM", 2021, "C") in indexed
    assert ("CUMCM", 2024, "C") in indexed
    assert ("CUMCM", 2025, "C") in indexed
    assert all(item.c_problem for item in papers)


def test_incremental_cache_reuses_unchanged_fingerprint(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "kb"
    pdf = root / "mcm" / "2025" / "C题" / "2500001.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"fake-pdf")
    registry = tmp_path / "registry.json"
    registry.write_text(
        """{
          "source_root": "%s",
          "assets": [
            {"asset_id":"mcm","path":"mcm","kind":"excellent_paper_corpus","competition":"MCM_ICM"}
          ]
        }""" % str(root).replace("\\", "\\\\"),
        encoding="utf-8",
    )
    source = scan_registered_excellent_papers(registry)[0]
    cached = _fingerprint(source, figures=12, workflow=True, purpose="workflow_or_framework")
    cache = tmp_path / "cache.json"
    _persist_fingerprint_cache(cache, [cached])

    def fail_if_called(_source):
        raise AssertionError("unchanged paper should be reused from cache")

    monkeypatch.setattr("mathworkstation.corpus_distillation.fingerprint_paper", fail_if_called)
    fingerprints, summary, stats = distill_registered_corpus_cached(
        registry,
        cache,
        sources=[source],
    )
    assert len(fingerprints) == 1
    assert summary.parsed_count == 1
    assert stats == {"reused": 1, "parsed_fresh": 0, "selected": 1}


def test_incremental_cache_preserves_disjoint_training_shards(tmp_path: Path, monkeypatch) -> None:
    root = tmp_path / "kb"
    for year, name in ((2024, "2400001.pdf"), (2025, "2500001.pdf")):
        pdf = root / "mcm" / str(year) / "C题" / name
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(f"fake-{year}".encode())
    registry = tmp_path / "registry.json"
    registry.write_text(
        """{
          "source_root": "%s",
          "assets": [
            {"asset_id":"mcm","path":"mcm","kind":"excellent_paper_corpus","competition":"MCM_ICM"}
          ]
        }""" % str(root).replace("\\", "\\\\"),
        encoding="utf-8",
    )
    sources = scan_registered_excellent_papers(registry)
    assert len(sources) == 2
    cache = tmp_path / "cache.json"

    monkeypatch.setattr(
        "mathworkstation.corpus_distillation.fingerprint_paper",
        lambda source: _fingerprint(source, figures=source.year - 2000, workflow=True, purpose="workflow_or_framework"),
    )
    distill_registered_corpus_cached(registry, cache, sources=[sources[0]], write_cache=True)
    distill_registered_corpus_cached(registry, cache, sources=[sources[1]], write_cache=True)

    def fail_if_called(_source):
        raise AssertionError("both shards should be reusable from the merged cache")

    monkeypatch.setattr("mathworkstation.corpus_distillation.fingerprint_paper", fail_if_called)
    fingerprints, _summary, stats = distill_registered_corpus_cached(
        registry,
        cache,
        sources=sources,
    )
    assert len(fingerprints) == 2
    assert stats == {"reused": 2, "parsed_fresh": 0, "selected": 2}


def test_visual_only_pdf_contributes_layout_but_not_modeling_prior(tmp_path: Path, monkeypatch) -> None:
    pdf = tmp_path / "2025" / "C题" / "C023.pdf"
    pdf.parent.mkdir(parents=True)
    pdf.write_bytes(b"fake-pdf")
    source = _source(paper_id="m-visual-only", year=2025, c_problem=True, style_weight=1.25, modeling_weight=1.0).model_copy(
        update={"source_path": str(pdf)}
    )

    monkeypatch.setattr("mathworkstation.corpus_distillation.pdf_page_count", lambda _path: 24)
    monkeypatch.setattr(
        "mathworkstation.corpus_distillation._layout_metrics",
        lambda _path: {
            "image_count": 36,
            "pages_with_images": 18,
            "image_area_ratio": 0.21,
            "text_area_ratio": 0.42,
            "landscape_page_ratio": 0.0,
            "scan_page_ratio": 1.0,
        },
    )
    monkeypatch.setattr(
        "mathworkstation.corpus_distillation.extract_pdf_text",
        lambda _path: (_ for _ in ()).throw(ValueError("PDF_UNICODE_TEXT_LAYER_UNAVAILABLE")),
    )

    fingerprint = fingerprint_paper(source)
    assert fingerprint.status == "VISUAL_ONLY"
    assert fingerprint.image_count == 36
    summary = summarize_fingerprints([fingerprint], source_root="test")
    assert summary.parsed_count == 0
    assert summary.visual_only_count == 1
    assert summary.failed_count == 0
    assert summary.weighted_layout_prior["weighted_median_image_count"] == 36
    assert summary.recent_layout_prior["weighted_median_image_area_ratio"] == 0.21
    assert summary.recent_layout_prior["weighted_median_scan_page_ratio"] == 1.0
    assert summary.weighted_c_modeling_prior == {}
    assert summary.fallback_queue == [str(pdf)]


def test_summary_separates_recent_style_prior_from_c_only_modeling_prior() -> None:
    recent_c = _source(paper_id="m-recent", year=2025, c_problem=True, style_weight=1.25, modeling_weight=1.0)
    old_non_c = _source(paper_id="x-old", year=2018, c_problem=False, style_weight=0.2, modeling_weight=0.0)
    fingerprints = [
        _fingerprint(recent_c, figures=18, workflow=True, purpose="workflow_or_framework"),
        _fingerprint(old_non_c, figures=5, workflow=False, purpose="data_distribution"),
    ]
    summary = summarize_fingerprints(fingerprints, source_root="test")
    assert summary.paper_count == 2
    assert summary.c_problem_count == 1
    assert summary.weighted_style_prior["weighted_median_figure_mentions"] == 18
    assert summary.weighted_c_modeling_prior["paper_count"] == 1
    packet = teacher_packet(summary)
    assert packet["coverage"]["c_problem"] == 1
    assert "style_prior_2023_plus" in packet
    assert any("C-problem modeling priors" in line for line in packet["safety_policy"])

from mathworkstation.corpus_distillation import CorpusPaperFingerprint, CorpusPaperSource
from mathworkstation.corpus_prior_bank import PriorRouter, build_prior_bank


def _source(
    paper_id: str,
    *,
    competition: str,
    year: int,
    c_problem: bool,
    style_weight: float = 1.0,
    modeling_weight: float = 1.0,
) -> CorpusPaperSource:
    return CorpusPaperSource(
        paper_id=paper_id,
        corpus_id="test",
        competition=competition,
        year=year,
        problem_letter="C" if c_problem else "A",
        award="O_AWARD" if competition == "MCM" else "EXCELLENT",
        source_path=f"{paper_id}.pdf",
        title_hint=paper_id,
        file_size=1,
        modified_ns=1,
        source_fingerprint=paper_id,
        duplicate_group=paper_id,
        c_problem=c_problem,
        style_weight=style_weight,
        modeling_weight=modeling_weight if c_problem else 0.0,
    )


def _fingerprint(
    source: CorpusPaperSource,
    *,
    task: str,
    validation: str = "sensitivity_or_robustness",
    figure: str = "result_comparison",
    status: str = "PARSED",
) -> CorpusPaperFingerprint:
    return CorpusPaperFingerprint(
        source=source,
        status=status,
        backend="pymupdf" if status == "PARSED" else "layout_only",
        page_count=20,
        text_characters=20000 if status == "PARSED" else 0,
        language="en" if source.competition == "MCM" else "zh",
        abstract_units=500 if status == "PARSED" else 0,
        abstract_numeric_tokens=12 if status == "PARSED" else 0,
        abstract_method_count=2 if status == "PARSED" else 0,
        model_sequence_length=4 if status == "PARSED" else 0,
        figure_mentions=14 if status == "PARSED" else 0,
        table_mentions=8 if status == "PARSED" else 0,
        workflow_figure_signal=status == "PARSED",
        figure_purposes={figure: 1} if status == "PARSED" else {},
        question_types=[task] if status == "PARSED" else [],
        model_selection_rationales=["data_characteristics"] if status == "PARSED" else [],
        model_transition_patterns=["staged_question_progression"] if status == "PARSED" else [],
        validation_types=[validation] if status == "PARSED" else [],
        image_count=8,
        pages_with_images=6,
        text_area_ratio=0.4 if status == "PARSED" else 0.0,
        scan_page_ratio=0.0 if status == "PARSED" else 1.0,
        generated_at="2026-08-22T00:00:00+08:00",
    )


def _training_items() -> list[CorpusPaperFingerprint]:
    values = []
    for competition in ("MCM", "CUMCM"):
        for index in range(4):
            source = _source(
                f"{competition}-c-{index}",
                competition=competition,
                year=2025,
                c_problem=True,
            )
            values.append(_fingerprint(source, task="optimization"))
        for index in range(4):
            source = _source(
                f"{competition}-a-{index}",
                competition=competition,
                year=2025,
                c_problem=False,
                modeling_weight=0.0,
            )
            values.append(_fingerprint(source, task="forecasting"))
    return values


def test_prior_bank_keeps_competitions_and_c_problem_as_separate_slices() -> None:
    bank = build_prior_bank(_training_items(), min_slice_papers=3)
    assert "competition:MCM:C:modern" in bank.slices
    assert "competition:CUMCM:C:modern" in bank.slices
    assert "problem:C" in bank.slices
    assert "task:optimization" in bank.slices
    assert "global_style" not in bank.slices
    assert bank.policies["no_global_style_monopoly"] is True


def test_non_c_papers_never_create_modeling_prior() -> None:
    bank = build_prior_bank(_training_items(), min_slice_papers=3)
    mcm = bank.slices["competition:MCM"]
    assert mcm.modeling_metrics["paper_count"] == 4.0
    assert mcm.style_metrics["paper_count"] == 8.0


def test_prior_router_selects_competition_modern_c_and_task_slices() -> None:
    bank = build_prior_bank(_training_items(), min_slice_papers=3)
    route = PriorRouter(bank).route("CUMCM_C", task_families=["optimization"])
    assert route.competition == "CUMCM"
    assert "competition:CUMCM:C" in route.selected_slice_ids
    assert "competition:CUMCM:C:modern" in route.selected_slice_ids
    assert "competition:CUMCM:modern" in route.selected_slice_ids
    assert "task:optimization" in route.selected_slice_ids
    assert not any(value.startswith("competition:MCM") for value in route.selected_slice_ids)
    assert any("Abstract calibration" in value for value in route.guidance)


def test_visual_only_paper_contributes_layout_but_not_text_or_modeling() -> None:
    items = _training_items()
    scan_source = _source("cumcm-scan", competition="CUMCM", year=2025, c_problem=True)
    items.extend(_fingerprint(scan_source.model_copy(update={"paper_id": f"cumcm-scan-{i}"}), task="optimization", status="VISUAL_ONLY") for i in range(3))
    bank = build_prior_bank(items, min_slice_papers=3)
    cumcm = bank.slices["competition:CUMCM"]
    assert cumcm.visual_only_count == 3
    assert cumcm.layout_metrics["paper_count"] == 11.0
    assert cumcm.style_metrics["paper_count"] == 8.0
    assert cumcm.modeling_metrics["paper_count"] == 4.0

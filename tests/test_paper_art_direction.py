from __future__ import annotations

from mathworkstation.competition_latex_export import CompetitionLatexExporter
from mathworkstation.paper_art_direction import PaperArtDirector


def test_art_director_varies_figure_footprint_by_semantic_role() -> None:
    figures = [
        {
            "figure_id": "workflow",
            "path": "figures/workflow.png",
            "status": "FINAL",
            "parameters": {"semantic_kind": "research_workflow", "paper_role": "primary"},
        },
        {
            "figure_id": "heatmap",
            "path": "figures/heatmap.png",
            "status": "FINAL",
            "parameters": {"semantic_kind": "correlation_heatmap", "paper_role": "primary"},
        },
        {
            "figure_id": "panel",
            "path": "figures/panel.png",
            "status": "FINAL",
            "parameters": {"semantic_kind": "panel_forecast_intervals", "paper_role": "primary"},
        },
    ]

    plan = PaperArtDirector().plan("case", profile_id="CUMCM_C", figures=figures)

    workflow = plan.figure_for_path("../../figures/workflow.png")
    heatmap = plan.figure_for_path("../../figures/heatmap.png")
    panel = plan.figure_for_path("../../figures/panel.png")
    assert workflow is not None and heatmap is not None and panel is not None
    assert workflow.width_fraction == 0.84
    assert heatmap.width_fraction == 0.78
    assert panel.width_fraction == 0.96
    assert len({workflow.width_fraction, heatmap.width_fraction, panel.width_fraction}) == 3


def test_latex_export_consumes_soft_page_composition(tmp_path) -> None:
    source_dir = tmp_path / "paper" / "research_state"
    figure_dir = tmp_path / "figures"
    source_dir.mkdir(parents=True)
    figure_dir.mkdir(parents=True)
    (figure_dir / "workflow.png").write_bytes(b"fake-png-for-copy-test")
    markdown = source_dir / "draft.md"
    markdown.write_text(
        "# Test\n\n# 摘要\n\n摘要。\n\n# 1. 分析\n\n"
        "图用于说明全文结构。\n\n"
        "![图1  研究技术路线](../../figures/workflow.png)\n\n"
        "图后继续解释。\n",
        encoding="utf-8",
    )
    plan = PaperArtDirector().plan(
        "case",
        profile_id="CUMCM_C",
        figures=[
            {
                "figure_id": "workflow",
                "path": "figures/workflow.png",
                "status": "FINAL",
                "parameters": {"semantic_kind": "research_workflow"},
            }
        ],
    )

    result = CompetitionLatexExporter().export(
        markdown,
        tmp_path / "out" / "main.tex",
        competition="CUMCM",
        composition_plan=plan,
    )
    tex = result.tex_path.read_text(encoding="utf-8")

    assert r"width=0.84\textwidth" in tex
    assert r"height=0.30\textheight" in tex
    assert r"\MathWSNeedspace{6\baselineskip}" in tex
    assert r"\newcommand{\MathWSNeedspace}" in tex
    assert r"\begin{minipage}{0.98\textwidth}" in tex
    assert r"{\small 研究技术路线}" in tex
    assert r"\renewcommand{\figurename}{图}" in tex
    assert r"\renewcommand{\floatpagefraction}{0.72}" in tex
    assert r"\setcounter{totalnumber}{4}" in tex

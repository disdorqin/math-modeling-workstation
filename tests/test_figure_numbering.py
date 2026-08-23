"""Figure numbering & consistency tests (task td87392cd, 图表编号/一致性机制).

The layer is fused from Sphinx ``numfig`` (automatic sequential numbering in
document order, cross-references resolved to the same number, warnings for
unresolved references) and SciencePlots rendering conventions:

* ``build_numbering`` numbers figures by order of first appearance across the
  outline sections (Sphinx numfig semantics) — stable across re-runs.
* ``render_figure_block`` / ``render_figure_reference`` emit the 图N caption /
  in-text reference plus an invisible figure_id anchor for the evidence gate.
* ``check_figure_numbering`` mirrors Sphinx build warnings: orphan figures
  (never referenced), unresolved 图N labels, numbering gaps and duplicates.
"""

from __future__ import annotations

import json
from pathlib import Path

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.auto_pipeline import AutoPipelineService
from mathworkstation.case_manager import CaseManager
from mathworkstation.datasets import DatasetKind
from mathworkstation.figure_numbering import (
    ANCHOR_ATTR,
    assign_figure_numbers,
    build_numbering,
    check_figure_numbering,
    load_figure_numbering,
    render_figure_block,
    render_figure_reference,
    write_numbering_report,
)
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.refinement import RefinementConfig

import pandas as pd

from test_auto_pipeline_e2e import DeterministicStructuredLLM


def _figure(figure_id: str, title: str, path: str = "figures/fig.png") -> dict:
    return {"figure_id": figure_id, "title": title, "path": path}


def test_build_numbering_document_order() -> None:
    sections = [
        {"section_id": "data_analysis", "figure_ids": ["figure-aaa", "figure-bbb"]},
        {"section_id": "results", "figure_ids": ["figure-bbb", "figure-ccc"]},
    ]
    figures = {
        "figure-aaa": _figure("figure-aaa", "特征分布"),
        "figure-bbb": _figure("figure-bbb", "模型对比"),
        "figure-ccc": _figure("figure-ccc", "敏感性"),
    }
    numbering, unnumbered = build_numbering(sections, figures)

    assert unnumbered == []
    assert numbering["figure-aaa"]["number"] == 1
    assert numbering["figure-aaa"]["label"] == "图1"
    assert numbering["figure-bbb"]["number"] == 2
    assert numbering["figure-ccc"]["number"] == 3
    # document order follows the outline sections, not registration order
    assert list(numbering) == ["figure-aaa", "figure-bbb", "figure-ccc"]
    assert numbering["figure-bbb"]["section_id"] == "data_analysis"


def test_build_numbering_figure_in_multiple_sections_keeps_first_number() -> None:
    sections = [
        {"section_id": "results", "figure_ids": ["figure-ccc", "figure-aaa"]},
        {"section_id": "data_analysis", "figure_ids": ["figure-aaa"]},
    ]
    figures = {"figure-aaa": _figure("figure-aaa", "A"), "figure-ccc": _figure("figure-ccc", "C")}
    numbering, _ = build_numbering(sections, figures)
    # first appearance decides the number even though the figure repeats later
    assert numbering["figure-aaa"]["number"] == 2
    assert numbering["figure-aaa"]["label"] == "图2"
    assert numbering["figure-ccc"]["number"] == 1


def test_build_numbering_marks_unnumbered_figures() -> None:
    sections = [{"section_id": "results", "figure_ids": ["figure-aaa"]}]
    figures = {
        "figure-aaa": _figure("figure-aaa", "A"),
        "figure-orphan": _figure("figure-orphan", "从未放入章节"),
    }
    numbering, unnumbered = build_numbering(sections, figures)
    assert unnumbered == ["figure-orphan"]
    assert "figure-orphan" not in numbering


def test_assign_figure_numbers_persists_single_source_of_truth(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "编号持久化")
    artifacts = ArtifactRegistry(cases)
    figures = FigureRegistry(cases, artifacts)
    case_id = case["case_id"]

    source = tmp_path / "source.txt"
    source.write_text("evidence", encoding="utf-8")
    source_artifact = artifacts.ingest_file(case_id, source, "input", "source")
    root = cases.case_root(case_id)
    (root / "figures").mkdir(parents=True, exist_ok=True)
    (root / "figures" / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    registered = figures.register(
        case_id, "figures/a.png", "特征分布", [source_artifact["artifact_id"]],
        "mathworkstation.eda", {}, None,
    )

    outline_sections = [
        {"section_id": "data_analysis", "figure_ids": [registered["figure_id"]]},
    ]
    numbering, _ = assign_figure_numbers(case_id, outline_sections, figures)

    path = root / "paper" / "figure_numbering.json"
    assert path.is_file()
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["numbering"][registered["figure_id"]]["label"] == "图1"

    loaded = load_figure_numbering(case_id, cases)
    assert loaded == numbering

    # a case that exists but never ran figure numbering has an empty map
    other_case = cases.create_case("SM", "未生成编号")
    assert load_figure_numbering(other_case["case_id"], cases) == {}


def test_render_figure_reference() -> None:
    numbering = {"figure-aaa": {"label": "图1"}}
    assert render_figure_reference("figure-aaa", numbering) == "图1"
    # unnumbered figure falls back to the raw id (no silent blank)
    assert render_figure_reference("figure-bbb", numbering) == "figure-bbb"
    assert render_figure_reference("figure-bbb", {}) == "figure-bbb"


def test_render_figure_block_emits_numbered_caption_and_anchor() -> None:
    numbering = {"figure-aaa": {"figure_id": "figure-aaa", "label": "图1"}}
    block = render_figure_block(_figure("figure-aaa", "特征分布", "figures/a.png"), numbering)

    assert "![特征分布](../figures/a.png)" in block
    assert "**图1：特征分布**" in block
    assert f'{ANCHOR_ATTR}="figure-aaa"' in block
    # caption is below the image (CUMCM/MCM requirement)
    assert block.index("![") < block.index("**图1")


def test_check_figure_numbering_pass(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "编号检查通过")
    numbering = {
        "figure-aaa": {"figure_id": "figure-aaa", "number": 1, "label": "图1", "section_id": "data_analysis"},
    }
    paper = "# 摘要\n\n如图1所示，分布集中。\n\n![特征分布](../figures/a.png)\n\n**图1：特征分布**\n"
    report = check_figure_numbering(case["case_id"], paper, numbering)
    assert report["gate"] == "PASS"
    assert report["findings"] == []
    assert report["numbered_figures"] == 1


def test_check_figure_numbering_orphan() -> None:
    numbering = {
        "figure-aaa": {"figure_id": "figure-aaa", "number": 1, "label": "图1", "section_id": "data_analysis"},
    }
    # paper never mentions 图1 → the figure is registered but unused
    report = check_figure_numbering("case-x", "没有任何图表引用的正文", numbering)
    assert report["gate"] == "REVIEW"
    codes = [item["code"] for item in report["findings"]]
    assert "ORPHAN_FIGURE" in codes
    orphan = next(item for item in report["findings"] if item["code"] == "ORPHAN_FIGURE")
    assert orphan["section_id"] == "data_analysis"


def test_check_figure_numbering_unresolved_label() -> None:
    numbering = {"figure-aaa": {"figure_id": "figure-aaa", "number": 1, "label": "图1", "section_id": "data_analysis"}}
    paper = "正如图9所示，结果稳定。"  # 图9 is not in the numbering map
    report = check_figure_numbering("case-x", paper, numbering)
    assert report["gate"] == "BLOCK"
    assert any(item["code"] == "UNRESOLVED_FIGURE_LABEL" for item in report["findings"])


def test_check_figure_numbering_gap() -> None:
    # manual map with a gap (图1 and 图3, missing 图2)
    numbering = {
        "figure-aaa": {"figure_id": "figure-aaa", "number": 1, "label": "图1", "section_id": "data_analysis"},
        "figure-ccc": {"figure_id": "figure-ccc", "number": 3, "label": "图3", "section_id": "results"},
    }
    paper = "图1 和 图3 都被引用。\n\n![A](../a.png)\n\n**图1：A**\n\n![C](../c.png)\n\n**图3：C**\n"
    report = check_figure_numbering("case-x", paper, numbering)
    assert any(item["code"] == "NUMBERING_GAP" for item in report["findings"])


def test_check_figure_numbering_duplicate_label() -> None:
    numbering = {
        "figure-aaa": {"figure_id": "figure-aaa", "number": 1, "label": "图1", "section_id": "data_analysis"},
        "figure-bbb": {"figure_id": "figure-bbb", "number": 1, "label": "图1", "section_id": "results"},
    }
    paper = "图1 在两个章节出现。"
    report = check_figure_numbering("case-x", paper, numbering)
    assert report["gate"] == "BLOCK"
    assert any(item["code"] == "NUMBERING_DUPLICATE" for item in report["findings"])


def test_write_numbering_report_registers_artifact(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "编号报告")
    artifacts = ArtifactRegistry(cases)
    figures = FigureRegistry(cases, artifacts)
    case_id = case["case_id"]

    report = {"schema_version": 1, "case_id": case_id, "gate": "PASS", "findings": [], "numbered_figures": 0}
    result = write_numbering_report(case_id, report, figures)

    root = cases.case_root(case_id)
    assert (root / "review" / "figure_numbering" / "paper_figure_numbering.json").is_file()
    assert (root / "review" / "figure_numbering" / "paper_figure_numbering.md").is_file()
    assert result["report_artifact_id"]
    artifact = artifacts.get(case_id, result["report_artifact_id"])
    assert artifact["artifact_type"] == "figure_numbering_report"


def test_pipeline_injects_numbered_figures(tmp_path: Path) -> None:
    """End-to-end: the assembled paper carries 图N captions, the numbering map is
    persisted, and the numbering consistency report is written — all without
    breaking the evidence-first pipeline."""
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "图号端到端")
    service = AutoPipelineService(cases, None, coherence=False)  # type: ignore[arg-type]
    service.llm = DeterministicStructuredLLM(service)  # type: ignore[assignment]
    session = service.sessions.create_session(case["case_id"])

    problem = tmp_path / "problem.md"
    problem.write_text(
        "# 需求预测题\n\n根据给定观测数据建立预测模型，比较候选方法并分析结果稳健性。\n",
        encoding="utf-8",
    )
    data = tmp_path / "observed.csv"
    rows = list(range(72))
    feature_a = [20 + value % 8 for value in rows]
    feature_b = [40 + (value * 3) % 10 for value in rows]
    pd.DataFrame(
        {
            "feature_a": feature_a,
            "feature_b": feature_b,
            "target": [1.5 * a + 0.8 * b + (index % 3) * 0.1 for index, (a, b) in enumerate(zip(feature_a, feature_b))],
        }
    ).to_csv(data, index=False)

    result = service.run(
        case["case_id"],
        session["session_id"],
        problem,
        data,
        "观测需求数据",
        "target",
        "e2e-human",
        "SM",
        data_kind=DatasetKind.OBSERVED,
        source_uri="https://example.org/datasets/figure-numbering",
        license_name="CC BY 4.0",
        data_description="固定端到端验收数据",
        refinement_config=RefinementConfig(max_stages=1, min_stages=0, max_changed_ratio=0.5),
    )

    root = cases.case_root(case["case_id"])
    final_text = (root / "paper" / "final.md").read_text(encoding="utf-8")
    figures = service.figures.list_figures(case["case_id"])

    # numbering map persisted
    numbering = load_figure_numbering(case["case_id"], cases)
    assert numbering, "figure numbering must be assigned during section generation"
    for entry in numbering.values():
        assert entry["label"].startswith("图")

    # every FINAL figure placed in the paper gets a numbered caption
    placed = {figure_id for figure_id, entry in numbering.items()}
    assert placed
    for figure_id in placed:
        assert f"**{numbering[figure_id]['label']}：" in final_text
        assert f'{ANCHOR_ATTR}="{figure_id}"' in final_text

    # numbering consistency report written without blocking the pipeline
    report_path = root / "review" / "figure_numbering" / "paper_figure_numbering.json"
    assert report_path.is_file()
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["gate"] in ("PASS", "REVIEW", "BLOCK")
    assert result.get("figure_numbering_report_artifact_id")

    # no regression: figures are FINAL and paper_ready approved
    approval_id = result["paper_ready_artifact_id"]
    for figure in figures:
        assert figure["status"] == "FINAL"
        assert figure["paper_ready_approval_id"] == approval_id

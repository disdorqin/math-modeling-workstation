"""Figure analysis paragraph engine tests (task t8859f1f6, 图表说明/分析段落).

The layer fuses three open-source design patterns (license-checked, no code
copied — see docs/figure-improvement-plan-2026-08-05.md §3.2):

* SciencePlots  — annotation completeness conventions (labels/legend/units).
* Data Formulator — title-keyword → chart-type → description-pattern routing.
* Chart-to-text — caption sufficiency dimensions / O-award paragraph template.

Covers the O-award four elements: lead sentence, observation, data
interpretation, conclusion-oriented takeaway.
"""

from __future__ import annotations

import json
from pathlib import Path

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.figure_analysis import (
    CHART_DESCRIPTION_PATTERN,
    SECTION_FIGURE_REQUIREMENTS,
    check_figure_analysis_paragraphs,
    check_figure_annotations,
    check_figure_id_tracking,
    coherence_findings,
    generate_figure_analysis_template,
    report_figure_coverage,
    write_analysis_report,
)
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.paper_coherence import PaperCoherenceChecker

GOOD_PARAGRAPH = (
    "如图1所示，三个候选模型的 RMSE 对比清晰可见：线性回归为 0.42，"
    "决策树为 0.35，随机森林最低达 0.31。随机森林较基线下降约 26%，"
    "且在测试集上波动最小，这一观察支持了集成方法在小样本下更稳健的假设。"
)


def _section_with_figure(after: str = "", caption: str | None = None) -> str:
    cap = caption or "**图1：模型对比**"
    return f"![模型对比](../figures/compare.png)\n\n{cap}\n\n{after}"


# ---------------------------------------------------------------------------
# 1. 各节分析段落检查(正常/缺少/过短)
# ---------------------------------------------------------------------------
def test_check_analysis_paragraphs_all_sections() -> None:
    sections = {
        "data_analysis": _section_with_figure(GOOD_PARAGRAPH),
        "results": _section_with_figure(""),  # 无分析段落
        "sensitivity": _section_with_figure("图3 显示变化不大。"),  # 过短
    }
    report = check_figure_analysis_paragraphs(sections)

    assert report["gate"] == "REVIEW"
    codes = [item["code"] for item in report["findings"]]
    assert "FIG_ANALYSIS_MISSING" in codes  # results 缺段落
    assert "FIG_ANALYSIS_TOO_SHORT" in codes  # sensitivity 过短
    # data_analysis 达标 → 无该图 finding
    assert not any(
        item["code"] in ("FIG_ANALYSIS_MISSING", "FIG_ANALYSIS_TOO_SHORT")
        and item["section_id"] == "data_analysis"
        for item in report["findings"]
    )

    coverage = report["coverage"]
    assert coverage["total_figures"] == 3
    assert coverage["covered_figures"] == 2
    assert coverage["coverage_percent"] == round(2 / 3 * 100, 1)


def test_check_analysis_paragraphs_accepts_full_o_award_paragraph() -> None:
    sections = {"results": _section_with_figure(GOOD_PARAGRAPH)}
    report = check_figure_analysis_paragraphs(sections)
    assert report["gate"] == "PASS"
    assert report["findings"] == []


def test_check_analysis_paragraphs_min_chars_per_section() -> None:
    # results 门槛 100 字,data_analysis 门槛 80 字
    assert SECTION_FIGURE_REQUIREMENTS["results"]["min_chars"] >= 100
    assert SECTION_FIGURE_REQUIREMENTS["data_analysis"]["min_chars"] >= 80
    # 构造 80 ≤ len < 100 的段落: data_analysis 通过,results 过短
    para = (
        "如图1所示，模型对比结果显示随机森林误差最低，线性回归次之，"
        "误差分别约为 0.42、0.35 和 0.31，随机森林较线性回归下降约 26%，"
        "这一观察支持集成方法更稳健的假设。"
    )
    assert 80 <= len(para) < 100
    data_report = check_figure_analysis_paragraphs({"data_analysis": _section_with_figure(para)})
    results_report = check_figure_analysis_paragraphs({"results": _section_with_figure(para)})
    assert not any(item["code"] == "FIG_ANALYSIS_TOO_SHORT" for item in data_report["findings"])
    assert any(item["code"] == "FIG_ANALYSIS_TOO_SHORT" for item in results_report["findings"])


# ---------------------------------------------------------------------------
# 2. 标注完整性检查(全/缺轴标签/缺图例)
# ---------------------------------------------------------------------------
def test_check_figure_annotations_complete() -> None:
    figures = [
        {"figure_id": "figure-aaa", "title": "候选模型 RMSE 对比", "parameters": {"xlabel": "模型", "ylabel": "RMSE", "legend": "数据集"}},
        {"figure_id": "figure-bbb", "title": "Figure 1", "parameters": {"xlabel": "", "legend": ""}},
    ]
    paper = "**图1：候选模型 RMSE 对比**"
    report = check_figure_annotations(figures, paper)

    assert report["gate"] == "REVIEW"
    codes = [item["code"] for item in report["findings"]]
    assert "FIG_TITLE_PLACEHOLDER" in codes  # "Figure 1" 占位图题
    assert "FIG_AXIS_LABEL_EMPTY" in codes  # xlabel 为空
    assert "FIG_LEGEND_EMPTY" in codes  # 图例为空
    # 达标图不应有 finding
    assert not any(item["code"] == "FIG_CAPTION_NOT_IN_PAPER" and "figure-aaa" in item["detail"] for item in report["findings"])


def test_check_figure_annotations_clean() -> None:
    figures = [
        {"figure_id": "figure-aaa", "title": "候选模型 RMSE 对比", "parameters": {"xlabel": "模型", "ylabel": "RMSE"}},
    ]
    paper = "**图1：候选模型 RMSE 对比**"
    report = check_figure_annotations(figures, paper)
    assert report["gate"] == "PASS"


# ---------------------------------------------------------------------------
# 3. 为各节生成分析模板
# ---------------------------------------------------------------------------
def test_generate_template_for_sections() -> None:
    template = generate_figure_analysis_template("候选模型 RMSE 对比柱状图", "results", "测试数据")
    assert "候选模型 RMSE 对比柱状图" in template
    assert "[TODO:" in template  # 需填充处显式标注
    assert "柱状图" in template  # 类型路由命中 bar
    assert "结论" in template or "表明" in template
    assert f"≥{SECTION_FIGURE_REQUIREMENTS['results']['min_chars']} 字" in template


def test_generate_template_chart_type_routing() -> None:
    line = generate_figure_analysis_template("损失函数随时间的变化趋势", "results")
    assert "折线图" in line or "趋势" in CHART_DESCRIPTION_PATTERN["line"]
    heat = generate_figure_analysis_template("特征相关性热力图", "data_analysis")
    assert "热力图" in heat


# ---------------------------------------------------------------------------
# 4. 图表覆盖度报告
# ---------------------------------------------------------------------------
def test_report_figure_coverage() -> None:
    sections = {
        "data_analysis": _section_with_figure(GOOD_PARAGRAPH),
        "results": _section_with_figure(""),
    }
    report = report_figure_coverage(sections)

    assert report["coverage"]["total_figures"] == 2
    assert report["overall_percent"] == 50.0
    assert "results" in report["missing_sections"]
    assert "data_analysis" not in report["missing_sections"]
    assert report["per_section"]["data_analysis"]["chars"]


# ---------------------------------------------------------------------------
# 5. 分析段落中的 figure_id 追踪
# ---------------------------------------------------------------------------
def test_figure_id_tracking_in_analysis() -> None:
    numbering = {
        "figure-aaa": {"figure_id": "figure-aaa", "label": "图1", "section_id": "data_analysis"},
        "figure-orphan": {"figure_id": "figure-orphan", "label": "图2", "section_id": "results"},
    }
    sections = {
        "data_analysis": (
            "![A](../a.png)\n\n**图1：A**\n\n<!-- data-figure-id=\"figure-aaa\" -->\n\n" + GOOD_PARAGRAPH
        ),
    }
    report = check_figure_id_tracking(sections, numbering)
    assert report["gate"] == "REVIEW"
    assert "figure-aaa" in report["tracked_figures"]
    assert any(item["code"] == "FIG_ID_NOT_TRACKED" for item in report["findings"])


# ---------------------------------------------------------------------------
# 6. O 奖标准四要素检查
# ---------------------------------------------------------------------------
def test_o_award_standard_compliance() -> None:
    # 四要素齐全 → PASS
    sections = {"results": _section_with_figure(GOOD_PARAGRAPH)}
    assert check_figure_analysis_paragraphs(sections)["gate"] == "PASS"

    # 缺引导句(段落不引用图号)
    no_lead = (
        "三个候选模型的 RMSE 对比清晰可见：线性回归为 0.42，决策树为 0.35，"
        "随机森林最低达 0.31，波动最小，这一观察支持集成方法更稳健的假设。"
    )
    report = check_figure_analysis_paragraphs({"results": _section_with_figure(no_lead)})
    assert any(item["code"] == "FIG_MISSING_LEAD" for item in report["findings"])

    # 缺结论导向(无结论词)
    no_takeaway = (
        "如图1所示，三个候选模型的 RMSE 对比：线性回归为 0.42，决策树为 0.35，"
        "随机森林最低达 0.31，随机森林较基线下降约 26%。"
    )
    report = check_figure_analysis_paragraphs({"results": _section_with_figure(no_takeaway)})
    assert any(item["code"] == "FIG_MISSING_TAKEAWAY" for item in report["findings"])


# ---------------------------------------------------------------------------
# 7. 与现有连贯性检查器的集成
# ---------------------------------------------------------------------------
def test_integration_with_paper_coherence() -> None:
    sections = {
        "abstract": "本文建立模型,采用方法,通过算法求解,突出特色,给出结果误差。",
        "conclusion": "模型结果误差可控,方法结论建议展望。",
        "data_analysis": _section_with_figure(""),  # 缺分析段落
    }
    checker = PaperCoherenceChecker()
    findings = checker.check(sections)

    # figure_analysis 的 finding 已并入 coherence 统一流(P2 语义)
    codes = {item["code"] for item in findings}
    assert "FIG_ANALYSIS_MISSING" in codes
    figure_findings = [item for item in findings if item["dimension"] == "figure_alignment"]
    assert figure_findings
    assert all(item["severity"] == "P2" for item in figure_findings)

    # coherence_findings 独立入口也工作
    direct = coherence_findings({"data_analysis": _section_with_figure("")})
    assert any(item["code"] == "FIG_ANALYSIS_MISSING" for item in direct)


# ---------------------------------------------------------------------------
# 8. 不破坏既有测试 / 报告落盘
# ---------------------------------------------------------------------------
def test_write_analysis_report_registers_artifact(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "图表分析报告")
    artifacts = ArtifactRegistry(cases)
    figures = FigureRegistry(cases, artifacts)
    case_id = case["case_id"]

    report = check_figure_analysis_paragraphs({"results": _section_with_figure(GOOD_PARAGRAPH)})
    result = write_analysis_report(case_id, report, figures, kind="paragraphs")

    root = cases.case_root(case_id)
    assert (root / "review" / "figure_analysis" / "paper_figure_paragraphs.json").is_file()
    assert (root / "review" / "figure_analysis" / "paper_figure_paragraphs.md").is_file()
    assert result["report_artifact_id"]
    artifact = artifacts.get(case_id, result["report_artifact_id"])
    assert artifact["artifact_type"] == "figure_analysis_report"


def test_empty_sections_pass() -> None:
    report = check_figure_analysis_paragraphs({})
    assert report["gate"] == "PASS"
    assert report["coverage"]["total_figures"] == 0
    coverage = report_figure_coverage({})
    assert coverage["overall_percent"] == 100.0

from __future__ import annotations

from mathworkstation.paper_humanization import PaperHumanizationAdapter


def test_chinese_paper_prose_hides_internal_research_protocol_terms() -> None:
    raw = (
        "SP2使登记模型下收益最大。实际求解协议比较simple_markup、linear_markup和quadratic_markup，"
        "并把retail_category_pricing_replenishment作为已登记的核心模型；继承SP1的已接受参数。"
    )
    polished = PaperHumanizationAdapter.sanitize(raw, language="zh")

    for leaked in (
        "SP1",
        "SP2",
        "登记模型",
        "已登记的",
        "已接受参数",
        "simple_markup",
        "linear_markup",
        "quadratic_markup",
        "retail_category_pricing_replenishment",
    ):
        assert leaked not in polished
    assert "问题2" in polished
    assert "简约加价响应" in polished
    assert "时间校正线性响应" in polished
    assert "时间校正二次响应" in polished
    assert "品类需求响应—定价补货联合优化模型" in polished
    assert "经检验的参数" in polished


def test_humanization_never_mutates_markdown_image_or_link_destinations() -> None:
    raw = (
        "SP1结果如下。\n\n"
        "![SP1 evidence](../../figures/draft/subproblem-SP1-evidence.png)\n\n"
        "参见[SP2 source](https://example.org/files/SP2-report.pdf)。"
    )
    polished = PaperHumanizationAdapter.sanitize(raw, language="zh")

    assert "问题1结果如下" in polished
    assert "![问题1 evidence]" in polished
    assert "../../figures/draft/subproblem-SP1-evidence.png" in polished
    assert "https://example.org/files/SP2-report.pdf" in polished
    assert "subproblem-问题1-evidence.png" not in polished

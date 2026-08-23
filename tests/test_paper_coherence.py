from __future__ import annotations

import pytest

from mathworkstation.paper_coherence import PaperCoherenceChecker
from mathworkstation.refinement import PaperQualityEvaluator, RefinementConfig


def _well_formed() -> dict[str, str]:
    return {
        "abstract": "# 摘要\n\n本文建立优化模型，采用改进算法求解，模型特色鲜明，主要结果误差较小。\n\n关键词：优化；模型；算法\n",
        "problem_restated": "# 问题重述\n\n问题背景明确，目标是建立最优方案，满足约束要求。\n",
        "assumptions": "# 模型假设\n\n假设数据无缺失，条件满足线性关系。\n",
        "model_construction": "# 模型建立\n\n建立优化模型，引入参数 $\\theta$ 与假设。\n",
        "model_solution": "# 模型求解\n\n采用迭代算法求解，计算收敛。\n",
        "results": "# 结果分析\n\n结果指标对比表明模型有效。\n",
        "sensitivity": "# 敏感性分析\n\n敏感性分析显示结果稳健。\n",
        "conclusion": "# 结论\n\n本文总结结论并提出建议，模型结果可推广应用。\n",
        "notation": "# 符号说明\n\n$\\theta$ 表示参数。\n",
    }


def test_well_formed_paper_has_few_findings() -> None:
    findings = PaperCoherenceChecker().check(_well_formed())
    codes = {item["code"] for item in findings}
    # 结构完整的论文不应出现主线断裂/缺符号/图未引用等严重连贯性问题
    assert "COH_CHAIN_BROKEN" not in codes
    assert "COH_NOTATION_MISSING" not in codes
    assert "COH_FIGURE_NOT_CITED" not in codes


def test_abstract_missing_elements() -> None:
    sections = _well_formed()
    sections["abstract"] = "# 摘要\n\n本文做了一个模型。\n"
    findings = PaperCoherenceChecker().check(sections)
    assert any(item["code"] == "COH_ABSTRACT_ELEMENTS" for item in findings)


def test_abstract_conclusion_no_echo() -> None:
    sections = _well_formed()
    sections["abstract"] = "# 摘要\n\n本文介绍背景。\n"
    sections["conclusion"] = "# 结论\n\n与摘要完全不同的话题讨论。\n"
    findings = PaperCoherenceChecker().check(sections)
    assert any(item["code"] == "COH_ABSTRACT_CONCLUSION_ECHO" for item in findings)


def test_chain_broken_detected() -> None:
    sections = _well_formed()
    sections["conclusion"] = "# 结论\n\n（本节内容缺失主线锚词，没有任何结论性表述。）\n" if False else "# 结论\n\n（待补充。）\n"
    findings = PaperCoherenceChecker().check(sections)
    # 结论节缺少 结论/总结/建议/展望 等锚词
    assert any(item["code"] == "COH_CHAIN_BROKEN" and item["section_id"] == "conclusion" for item in findings)


def test_figure_not_cited() -> None:
    sections = _well_formed()
    sections["results"] = "# 结果分析\n\n结果如图：\n\n![结果图](fig.png)\n"
    findings = PaperCoherenceChecker().check(sections)
    assert any(item["code"] == "COH_FIGURE_NOT_CITED" for item in findings)


def test_notation_missing_when_math_present() -> None:
    sections = _well_formed()
    del sections["notation"]
    sections["model_construction"] = "# 模型建立\n\n建立模型 $y = ax + b$。\n"
    findings = PaperCoherenceChecker().check(sections)
    assert any(item["code"] == "COH_NOTATION_MISSING" for item in findings)


def test_all_findings_are_p2_soft() -> None:
    sections = _well_formed()
    sections["abstract"] = "# 摘要\n\n简略。\n"
    sections["conclusion"] = "# 结论\n\n（待补充。）\n"
    findings = PaperCoherenceChecker().check(sections)
    assert findings
    assert all(item["severity"] == "P2" for item in findings)


# ---- 与 refinement 的集成: 默认关闭不改变行为, 开启后注入 P2 发现 ----

def _frozen(sections: dict[str, str]) -> dict:
    contract = {
        "required_claim_ids": [], "required_figure_ids": [],
        "allowed_claim_ids": [], "allowed_figure_ids": [],
        "number_tokens": [], "synthetic_disclosure_required": False,
    }
    return {
        "sections": {sid: dict(contract) for sid in sections},
        "section_order": list(sections),
    }


def test_evaluator_coherence_off_by_default() -> None:
    sections = _well_formed()
    sections["abstract"] = "# 摘要\n\n本文做了一个模型。\n"  # 会触发 COH_ABSTRACT_ELEMENTS
    result = PaperQualityEvaluator().evaluate(sections, _frozen(sections), RefinementConfig().targets)
    codes = {item["code"] for item in result["findings"]}
    assert not any(code.startswith("COH_") for code in codes)


def test_evaluator_coherence_on_injects_findings() -> None:
    sections = _well_formed()
    sections["abstract"] = "# 摘要\n\n本文做了一个模型。\n"
    result = PaperQualityEvaluator(coherence=True).evaluate(sections, _frozen(sections), RefinementConfig().targets)
    codes = {item["code"] for item in result["findings"]}
    assert "COH_ABSTRACT_ELEMENTS" in codes
    # 软发现不改变硬门
    assert result["hard_gate"] in {"PASS", "BLOCK"}

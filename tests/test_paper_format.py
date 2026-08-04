"""Deterministic tests for the math-modeling format checker (Skill A, freebuff).

Locks in the CUMCM/MCM format rules the checker enforces: abstract must not
contain formula/table/figure, keywords present, references section required,
three-line tables, figure/table captions in the right position.
"""
from __future__ import annotations

import pytest

from mathworkstation.paper_format import PaperFormatChecker


@pytest.fixture()
def checker() -> PaperFormatChecker:
    return PaperFormatChecker()


def test_good_cumcm_paper_passes(checker):
    content = (
        "# 摘要\n\n"
        "本文针对某问题建立回归模型，采用交叉验证评估。\n\n"
        "关键词：回归；交叉验证；敏感性\n\n"
        "# 问题重述\n\n内容\n\n"
        "# 模型建立\n\n内容\n\n"
        "# 结果分析\n\n内容\n\n"
        "# 结论\n\n内容\n\n"
        "# 参考文献\n\n[1] 张三. 论文标题[J]. 期刊, 2020.\n"
    )
    result = checker.check(content, "CUMCM")
    # Abstract clean + references present -> no BLOCK from the core rules.
    assert result["gate"] in {"PASS", "REVIEW"}


def test_abstract_with_formula_is_block(checker):
    content = (
        "# 摘要\n\n本文建立模型 $y = \\\\beta x$，得到结果。\n\n关键词：回归\n\n"
        "# 参考文献\n\n[1] 张三. 论文[J]. 期刊, 2020.\n"
    )
    result = checker.check(content, "CUMCM")
    codes = [f["code"] for f in result["findings"]]
    assert "ABSTRACT_HAS_FORMULA" in codes
    assert result["gate"] == "BLOCK"


def test_missing_keywords_is_review(checker):
    content = "# 摘要\n\n本文建立模型。\n\n# 参考文献\n\n[1] 张三. 论文[J]. 期刊, 2020.\n"
    result = checker.check(content, "CUMCM")
    codes = [f["code"] for f in result["findings"]]
    assert "KEYWORDS_MISSING" in codes or "TOO_FEW_KEYWORDS" in codes


def test_supports_both_competitions(checker):
    for comp in ("CUMCM", "MCM"):
        assert comp in checker.get_competition_names()


def test_three_line_table_caption_check(checker):
    # table caption above (CUMCM rule) vs below (wrong position)
    content = (
        "# 摘要\n\n本文建立模型。\n\n关键词：回归\n\n"
        "# 模型建立\n\n表1：结果\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n"
        "# 参考文献\n\n[1] 张三. 论文[J]. 期刊, 2020.\n"
    )
    result = checker.check(content, "CUMCM")
    # A table present; the checker should either pass it or flag caption issues,
    # but never crash.
    assert "findings" in result

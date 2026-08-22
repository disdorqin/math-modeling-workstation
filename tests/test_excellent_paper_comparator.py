"""Deterministic tests for ExcellentPaperComparator (C题优秀论文对照层).

Covers:
  * 对照库加载(≥10篇, 跨年份, 覆盖4类题型)
  * 泛化判定: 跨≥2不同年份的强点缺失 → generalized issue
  * 单年份亮点 → 不强制改(泛化阈值)
  * 已具备强点 → 不误报
  * 缺失对照库/空库 → 不崩溃
  * 报告/统计接口可注入打磨循环
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from mathworkstation.excellent_paper_comparator import (
    GENERALIZATION_THRESHOLD,
    VALID_FOCUS,
    ExcellentPaperComparator,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REAL_LIB = PROJECT_ROOT / "config" / "ref_models" / "excellent_c7"


def _write_lib(tmp_path: Path, files: dict[str, str]) -> Path:
    lib = tmp_path / "excellent_c7"
    lib.mkdir(parents=True, exist_ok=True)
    for name, content in files.items():
        (lib / name).write_text(content, encoding="utf-8")
    return lib


def _ref_md(year: int, strong_points: list[str]) -> str:
    lines = ["---", f"year: {year}", "topic: t", "type: t", "models:", "  - m", "strong_points:"]
    for sp in strong_points:
        lines.append(f'  - "{sp}"')
    lines += ["source: x", "---", "# body"]
    return "\n".join(lines)


# ------------------------------------------------------------ 真实对照库


@pytest.mark.parametrize(
    "focus", ["coherence", "humanize", "figures_and_tables", "notation_and_latex", "final_polish"]
)
def test_real_library_generalized_issues_on_bare_paper(focus: str):
    """真实对照库: 一篇无任何强点内容的论文在每个 focus 维度都应有泛化问题。"""
    cmp = ExcellentPaperComparator(REAL_LIB)
    issues = cmp.compare("本文介绍方法。结论:我们得到结果。", focus)
    assert issues, f"bare paper should trigger issues for focus={focus}"
    for issue in issues:
        assert issue.focus == focus
        assert len(issue.ref_years) >= GENERALIZATION_THRESHOLD
        assert issue.keywords


def test_real_library_size_and_coverage():
    """验收标准: 对照库 ≥10 篇, 跨 ≥10 个不同年份, 覆盖4类题型。"""
    cmp = ExcellentPaperComparator(REAL_LIB)
    stats = cmp.stats()
    assert stats["total_papers"] >= 10, "对照库应 ≥10 篇"
    assert stats["distinct_years"] >= 10, "应跨 ≥10 个不同年份"
    assert len(stats["type_coverage"]) >= 4, "应覆盖4类C题题型"


def test_real_library_paper_already_has_strong_points():
    """一篇已含全部核心强点的论文不应报 coherence 类泛化问题。"""
    cmp = ExcellentPaperComparator(REAL_LIB)
    good = (
        "摘要:针对问题一,我们建立模型,先做假设。针对问题二,建立公式推导。"
        "针对问题三,对比不同方案,给出误差与敏感性分析,图1和表1展示结果,"
        "最后评价优缺点并提出建议。"
    )
    issues = cmp.compare(good, "final_polish")
    assert not issues


# ------------------------------------------------------------ 泛化阈值逻辑


def test_generalization_requires_two_years(tmp_path: Path):
    """单年份亮点: 即便当前论文缺失也不强制改(泛化阈值=2)。"""
    lib = _write_lib(
        tmp_path,
        {
            "2020-only.md": _ref_md(2020, ["coherence|仅2020年特有做法|独有词A"]),
            "2021-only.md": _ref_md(2021, ["coherence|仅2021年特有做法|独有词B"]),
        },
    )
    cmp = ExcellentPaperComparator(lib)
    assert cmp.compare("缺少所有标记的论文", "coherence") == []


def test_generalized_issue_crosses_two_years(tmp_path: Path):
    """同一强点在≥2个不同年份反复出现且当前论文缺失 → 泛化问题, 带年份佐证。"""
    lib = _write_lib(
        tmp_path,
        {
            "2020-a.md": _ref_md(2020, ["coherence|跨年共有强点|共有词"]),
            "2021-b.md": _ref_md(2021, ["coherence|跨年共有强点|共有词"]),
        },
    )
    cmp = ExcellentPaperComparator(lib)
    issues = cmp.compare("缺少所有标记的论文", "coherence")
    assert len(issues) == 1
    assert issues[0].aspect == "跨年共有强点"
    assert issues[0].ref_years == (2020, 2021)


def test_present_strong_point_not_reported(tmp_path: Path):
    """论文已具备该强点(关键词命中) → 不报泛化问题。"""
    lib = _write_lib(
        tmp_path,
        {
            "2020-a.md": _ref_md(2020, ["coherence|跨年共有强点|共有词"]),
            "2021-b.md": _ref_md(2021, ["coherence|跨年共有强点|共有词"]),
        },
    )
    cmp = ExcellentPaperComparator(lib)
    assert cmp.compare("论文里出现了共有词", "coherence") == []


# ------------------------------------------------------------ 健壮性


def test_missing_library_is_safe(tmp_path: Path):
    """对照库缺失/为空 → compare 返回空列表, 不崩溃(打磨循环照常运行)。"""
    cmp = ExcellentPaperComparator(tmp_path / "nonexistent")
    assert cmp.compare("任意文本", "coherence") == []
    assert cmp.stats()["total_papers"] == 0


def test_report_and_stats_interface(tmp_path: Path):
    """report() 输出打磨循环可注入的 JSON 结构。"""
    lib = _write_lib(
        tmp_path,
        {
            "2020-a.md": _ref_md(2020, ["coherence|跨年共有强点|共有词"]),
            "2021-b.md": _ref_md(2021, ["coherence|跨年共有强点|共有词"]),
        },
    )
    cmp = ExcellentPaperComparator(lib)
    report = cmp.report("缺少所有标记的论文", "coherence")
    assert report["focus"] == "coherence"
    assert report["generalized_issues"]
    assert report["ref_papers_count"] == 2
    assert all("focus" in i and "aspect" in i and "ref_years" in i for i in report["generalized_issues"])


def test_invalid_focus_falls_back_to_coherence(tmp_path: Path):
    lib = _write_lib(tmp_path, {"2020-a.md": _ref_md(2020, ["coherence|跨年共有强点|共有词"])})
    cmp = ExcellentPaperComparator(lib)
    assert VALID_FOCUS
    # 非法 focus 不崩溃(回退 coherence 后正常返回列表)
    assert isinstance(cmp.compare("x", "bogus_focus"), list)


def test_frontmatter_missing_returns_none(tmp_path: Path):
    lib = _write_lib(tmp_path, {"no-frontmatter.md": "# 正文\n无 frontmatter\n"})
    cmp = ExcellentPaperComparator(lib)
    assert cmp.ref_papers() == []

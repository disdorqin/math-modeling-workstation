"""ExcellentPaperComparator — 优秀论文对照层(C题).

给打磨循环注入"外部优秀论文对照"信号: 把当前论文与高教社 C 题优秀论文
提炼稿对照, 找出**泛化问题**(在 ≥2 个不同年份优秀论文中反复出现、而当前
论文缺失的点), 供 ``refinement._propose_refinement`` 使用。

设计依据: ``docs/refine-vs-excellent-papers-design-2026-08-06.md``。

判定逻辑(确定性、不依赖 LLM):
  1. 加载 ``config/ref_models/excellent_c7/`` 下的提炼稿, 每篇含 YAML
     frontmatter, 其中 ``stages_strong_points`` 按 5 个 focus 维度记录该年
     优秀论文的强点。每个强点格式为 ``"规范短句|关键词1,关键词2"``:
     - 规范短句: 跨论文复用的"泛化维度"表述(相同短句跨年份聚合计数);
     - 关键词: 判定当前论文是否具备该强点的确定性规则(全部命中=具备)。
  2. 对给定 focus 维度, 按规范短句聚合"出现在哪些不同年份"。
  3. 当前论文关键词缺失, 且该短句出现在 ≥2 个不同年份 → 泛化问题。
     只出现在 1 个年份(或我们已具备) → 亮点差异, 不强制改。
  4. 无关键词的强点(纯特色亮点)不参与泛化判定, 天然"保持亮点"。

接口(导师指定):
    ``compare(paper_text, stage_focus) -> list[GeneralizedIssue]``
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .io_utils import read_json

#: 与 refinement_hidden_state.FOCUS_CURRICULUM 对齐的 5 个 focus 维度
VALID_FOCUS: tuple[str, ...] = (
    "coherence",
    "humanize",
    "figures_and_tables",
    "notation_and_latex",
    "final_polish",
)

#: 泛化阈值: 某强点在 ≥ 该数量个不同年份优秀论文中反复出现才算泛化
GENERALIZATION_THRESHOLD = 2

_DEFAULT_CONFIG_DIR = Path(__file__).resolve().parents[2] / "config" / "ref_models" / "excellent_c7"


@dataclass(frozen=True)
class GeneralizedIssue:
    """一个泛化问题: 优秀论文普遍具备而当前论文缺失的点。"""

    focus: str                      # 所属打磨维度 (VALID_FOCUS 之一)
    aspect: str                     # 规范短句(跨年份泛化维度)
    reason: str                     # 判定理由(带年份佐证)
    ref_years: tuple[int, ...]      # 哪些年份的优秀论文具备该强点
    keywords: tuple[str, ...] = ()  # 判定关键词(全部缺失 → 判定缺失)

    def to_dict(self) -> dict[str, Any]:
        return {
            "focus": self.focus,
            "aspect": self.aspect,
            "reason": self.reason,
            "ref_years": list(self.ref_years),
            "keywords": list(self.keywords),
        }


@dataclass
class StrongPoint:
    """提炼稿中的一条结构化强点(一个 focus 维度的一条)。"""

    focus: str
    aspect: str
    year: int
    keywords: tuple[str, ...] = ()

    def hit(self, text: str) -> bool:
        """当前论文文本是否具备该强点(任一关键词命中即视为具备)。

        注意: compare() 中已按 ``keywords`` 是否非空过滤, 此处仅用于
        单点语义, OR 语义保证不因个别词缺失而误判。
        """
        if not self.keywords:
            return False  # 无关键词的强点不参与判定(纯亮点, 保持)
        lowered = text.lower()
        return any(kw.lower() in lowered for kw in self.keywords)


@dataclass
class RefPaper:
    """一篇优秀论文提炼稿(解析 frontmatter 后的结构化表示)。"""

    year: int
    topic: str
    file: str
    strong_points: dict[str, list[StrongPoint]] = field(default_factory=dict)
    raw_text: str = ""

    def strong_points_for(self, focus: str) -> list[StrongPoint]:
        return self.strong_points.get(focus, [])


class ExcellentPaperComparator:
    """把当前论文与优秀论文对照库比较, 找出泛化问题。"""

    def __init__(self, config_dir: Path | None = None) -> None:
        self.config_dir = Path(config_dir) if config_dir else _DEFAULT_CONFIG_DIR
        self._ref_papers: list[RefPaper] | None = None

    # ------------------------------------------------------------ 加载对照库

    def ref_papers(self) -> list[RefPaper]:
        """惰性加载提炼稿库(带缓存)。"""
        if self._ref_papers is not None:
            return self._ref_papers
        papers: list[RefPaper] = []
        if self.config_dir.is_dir():
            for path in sorted(self.config_dir.glob("*.md")):
                paper = self._parse_ref_paper(path)
                if paper is not None:
                    papers.append(paper)
        self._ref_papers = papers
        return papers

    def _parse_ref_paper(self, path: Path) -> RefPaper | None:
        text = path.read_text(encoding="utf-8")
        front = _parse_frontmatter(text)
        if not front:
            return None
        year = int(front.get("year", 0))
        strong: dict[str, list[StrongPoint]] = {}
        for entry in front.get("strong_points", []):
            focus, _, remainder = entry.partition("|")
            if focus not in VALID_FOCUS:
                continue
            aspect, _, kw_str = remainder.partition("|")
            aspect = aspect.strip()
            if not aspect:
                continue
            keywords = tuple(k.strip() for k in kw_str.split(",") if k.strip()) if kw_str else ()
            strong.setdefault(focus, []).append(
                StrongPoint(focus=focus, aspect=aspect, year=year, keywords=keywords)
            )
        return RefPaper(
            year=year,
            topic=str(front.get("topic", "")),
            file=path.name,
            strong_points=strong,
            raw_text=text,
        )

    # ------------------------------------------------------------ 对照判定

    def compare(self, paper_text: str, stage_focus: str) -> list[GeneralizedIssue]:
        """主入口: 对照优秀论文, 返回当前论文的泛化问题清单。

        参数:
            paper_text: 当前论文全文(对其做关键词缺失判定)。
            stage_focus: 当前打磨 focus 维度(见 VALID_FOCUS)。

        返回:
            generalized_issues 列表; 若对照库缺失/该维度无数据则返回空列表
            (不崩溃, 打磨循环照常以内部自检推进)。
        """
        if stage_focus not in VALID_FOCUS:
            stage_focus = "coherence"
        papers = self.ref_papers()
        if not papers:
            return []

        # 1) 该维度下所有强点 → 按"规范短句"聚合 {关键词, 出现年份}
        by_aspect: dict[str, dict[str, Any]] = {}
        for paper in papers:
            for sp in paper.strong_points_for(stage_focus):
                if not sp.keywords:
                    continue  # 无关键词 → 纯亮点, 不参与泛化
                entry = by_aspect.setdefault(sp.aspect, {"keywords": sp.keywords, "years": set()})
                entry["keywords"] = sp.keywords
                entry["years"].add(sp.year)

        # 2) 缺失判定 + 泛化过滤(≥2 个不同年份)
        issues: list[GeneralizedIssue] = []
        for aspect, entry in by_aspect.items():
            years_sorted = tuple(sorted(entry["years"]))
            if len(years_sorted) < GENERALIZATION_THRESHOLD:
                continue  # 只出现在 ≤1 年份 → 亮点差异, 不强制改
            keywords = entry["keywords"]
            if any(kw.lower() in paper_text.lower() for kw in keywords):
                continue  # 当前论文已具备该点(任一关键词命中即可)
            issues.append(
                GeneralizedIssue(
                    focus=stage_focus,
                    aspect=aspect,
                    reason=(
                        f"优秀论文在 {len(years_sorted)} 个不同年份反复具备该点"
                        f"(参考年份: {'/'.join(map(str, years_sorted))}), 当前论文缺失"
                    ),
                    ref_years=years_sorted,
                    keywords=keywords,
                )
            )
        return issues

    # ------------------------------------------------------------ 辅助/报告

    def report(self, paper_text: str, stage_focus: str) -> dict[str, Any]:
        """把 compare() 结果包装为打磨循环可注入的 JSON 字典。"""
        issues = self.compare(paper_text, stage_focus)
        return {
            "schema_version": 1,
            "focus": stage_focus,
            "generalized_issues": [issue.to_dict() for issue in issues],
            "ref_papers_used": [p.file for p in self.ref_papers()],
            "ref_papers_count": len(self.ref_papers()),
        }

    def stats(self) -> dict[str, Any]:
        """对照库规模统计(用于验证 ≥10 篇验收标准)。"""
        papers = self.ref_papers()
        by_year = sorted(p.year for p in papers)
        by_type: dict[str, list[str]] = {}
        if self.config_dir.is_dir():
            index_path = self.config_dir / "index.json"
            if index_path.is_file():
                index = read_json(index_path)
                by_type = index.get("type_coverage", {})
        return {
            "total_papers": len(papers),
            "years": by_year,
            "distinct_years": len(set(by_year)),
            "type_coverage": by_type,
        }


# ---------------------------------------------------------------- frontmatter 解析


def _parse_frontmatter(text: str) -> dict[str, Any] | None:
    """解析 YAML frontmatter(--- 之间的简单键值/列表)。

    仅支持本项目提炼稿的子集:
      - ``key: value`` 标量(含 ``year: int``);
      - 顶层 ``key:`` 空值后跟 ``- item`` 列表(如 ``models`` / ``stages_strong_points``)。
    """
    if not text.startswith("---"):
        return None
    lines = text.splitlines()
    if len(lines) < 2 or lines[1].strip() == "---":
        return None
    end = None
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            end = idx
            break
    if end is None:
        return None
    data: dict[str, Any] = {}
    current_key: str | None = None
    for line in lines[1:end]:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*:\s*$", stripped):
            current_key = stripped[:-1].strip()
            data.setdefault(current_key, [])
            continue
        if stripped.startswith("- ") and current_key:
            item = stripped[2:].strip()
            if len(item) >= 2 and item[0] == item[-1] and item[0] in "\"'":
                item = item[1:-1]
            data[current_key].append(item)
            continue
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)$", stripped)
        if match:
            key, value = match.groups()
            value = value.strip()
            if key == "year":
                try:
                    value = int(value)
                except ValueError:
                    pass
            data[key] = value
            current_key = None
    if not data.get("strong_points"):
        return None
    return data

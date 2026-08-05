from __future__ import annotations

import re
from typing import Any

from .figure_analysis import coherence_findings

# ---------------------------------------------------------------------------
# 数学建模论文连贯性检查器 (Skill C)
#
# 设计来源: docs/mathmodel-paper-skill-design.md → Skill C (mathmodel-coherence)
# 目标: 从摘要到结论一条主线, 符合数模"连贯 > 严谨"。
# 输出: 与 PaperQualityEvaluator 一致的 finding 格式
#       {severity: P0/P1/P2, section_id, code, detail, dimension}
#       全部使用 P2(软发现) → 成为 refinement 的 issue 驱动多 Stage 打磨,
#       但绝不硬阻塞证据门(硬门只认 P0/P1)。
# 纯确定性、正则/关键词启发式, 零 LLM 依赖。
# ---------------------------------------------------------------------------


# 摘要五要素(CUMCM): 模型归类 / 建模思想 / 算法思想 / 模型特色 / 主要结果
ABSTRACT_ELEMENTS: list[tuple[str, ...]] = [
    ("模型",),
    ("思想", "方法"),
    ("算法",),
    ("特色", "创新"),
    ("结果", "误差", "精度"),
]

# 摘要与结论应呼应的共享主题词
ECHO_KEYWORDS = ("模型", "结果", "方法", "算法", "数据", "误差", "预测", "优化", "结论", "指标")

# 各章节"主线锚词"(any-of): 该节存在但一个锚词都没有 → 主线断点
CHAIN_ANCHORS: dict[str, tuple[str, ...]] = {
    "problem_restated": ("问题", "目标", "背景", "要求"),
    "assumptions": ("假设", "假定", "条件"),
    "model_construction": ("模型", "建立", "参数", "假设"),
    "model_solution": ("求解", "算法", "解", "计算", "迭代"),
    "results": ("结果", "指标", "分析", "对比", "比较"),
    "sensitivity": ("敏感性", "稳健", "鲁棒", "扰动"),
    "conclusion": ("结论", "总结", "建议", "展望", "不足", "限制"),
}

# 节首过短 / 以列表开头的突兀开头
BULLET_OPEN = re.compile(r"^\s*[-*•]")
# 数学符号
MATH_TOKEN = re.compile(r"\$[^$\n]+\$|\\begin\{[^}]*\}")
# 图片定义
IMAGE_DEF = re.compile(r"!\[.*?\]\(.*?\)")
# 图引用(中文"图1"/英文"Figure 1")
FIGURE_REF = re.compile(r"(图\s*\d+|Figure\s*\d+)", re.IGNORECASE)
# 符号说明章节的候选标题
NOTATION_HEADING = re.compile(r"^#+\s*(符号|记号|notation|symbols|变量说明)", re.IGNORECASE | re.MULTILINE)


def _body_lines(content: str) -> list[str]:
    """去掉 markdown 标题行。"""
    return [line for line in content.splitlines() if not line.lstrip().startswith("#")]


def _first_paragraph(content: str) -> str:
    text = "\n".join(_body_lines(content)).strip()
    if not text:
        return ""
    return re.split(r"\n\s*\n", text)[0].strip()


def _finding(severity: str, section_id: str, code: str, detail: str, dimension: str | None = None) -> dict[str, Any]:
    return {"severity": severity, "section_id": section_id, "code": code, "detail": detail, "dimension": dimension}


class PaperCoherenceChecker:
    """数模论文连贯性检查器。

    ``check(sections)`` 接收 ``{section_id: markdown}``(与 refinement 的
    sections 结构一致), 返回 finding 列表。所有 finding 均为 P2(软发现),
    进入 refinement issue 驱动多 Stage 打磨。
    """

    def __init__(self) -> None:
        self.sections: dict[str, str] = {}

    def check(self, sections: dict[str, str]) -> list[dict[str, Any]]:
        self.sections = sections
        findings: list[dict[str, Any]] = []
        findings.extend(self._abstract_elements())
        findings.extend(self._abstract_conclusion_echo())
        findings.extend(self._chain_anchors())
        findings.extend(self._section_openings())
        findings.extend(self._notation_presence())
        findings.extend(self._figures_cited())
        # 图表分析段落质量(O 奖四要素, figure_analysis 层, P2 软发现)
        findings.extend(coherence_findings(sections))
        return findings

    # -- 1. 摘要五要素覆盖 ------------------------------------------------
    def _abstract_elements(self) -> list[dict[str, Any]]:
        abstract = self.sections.get("abstract", "")
        if not abstract.strip():
            return []  # 缺失由 evaluator 的 SECTION_MISSING 负责
        missing = [",".join(alt) for alt in ABSTRACT_ELEMENTS if not any(k in abstract for k in alt)]
        if len(missing) >= 2:
            return [_finding(
                "P2", "abstract", "COH_ABSTRACT_ELEMENTS",
                f"摘要缺少以下要素: {'; '.join(missing)}(期望覆盖模型归类/建模思想/算法思想/模型特色/主要结果)",
                dimension="abstract_quality",
            )]
        return []

    # -- 2. 摘要与结论呼应 -------------------------------------------------
    def _abstract_conclusion_echo(self) -> list[dict[str, Any]]:
        abstract = self.sections.get("abstract", "")
        conclusion = self.sections.get("conclusion", "")
        if not abstract.strip() or not conclusion.strip():
            return []
        shared = [kw for kw in ECHO_KEYWORDS if kw in abstract and kw in conclusion]
        if len(shared) < 2:
            return [_finding(
                "P2", "abstract", "COH_ABSTRACT_CONCLUSION_ECHO",
                f"摘要与结论呼应不足(共同主题词仅 {len(shared)} 个, 期望≥2)", dimension="abstract_quality",
            )]
        return []

    # -- 3. 逐层衔接: 各节应有主线锚词 ------------------------------------
    def _chain_anchors(self) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for section_id, anchors in CHAIN_ANCHORS.items():
            content = self.sections.get(section_id, "")
            if not content.strip():
                continue  # 缺失由 evaluator 负责
            body = "\n".join(_body_lines(content))  # 锚词只查正文, 标题本身不算
            if not any(anchor in body for anchor in anchors):
                findings.append(_finding(
                    "P2", section_id, "COH_CHAIN_BROKEN",
                    f"章节 {section_id} 未出现主线锚词 {anchors}, 与前文衔接断裂", dimension="writing_quality",
                ))
        return findings

    # -- 4. 节首承上启下 ---------------------------------------------------
    def _section_openings(self) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for section_id, content in self.sections.items():
            if not content.strip():
                continue
            para = _first_paragraph(content)
            if not para:
                continue
            if BULLET_OPEN.match(para) or len(para) < 20:
                findings.append(_finding(
                    "P2", section_id, "COH_SECTION_OPENING",
                    f"章节 {section_id} 开头突兀(以列表/过短句子起笔), 缺少承上启下", dimension="writing_quality",
                ))
        return findings

    # -- 5. 符号一致性: 有公式但缺符号说明 ----------------------------------
    def _notation_presence(self) -> list[dict[str, Any]]:
        has_math = any(MATH_TOKEN.search(self.sections.get(section_id, ""))
                       for section_id in ("model_construction", "model_solution"))
        notation = self.sections.get("notation", "")
        if has_math and not notation.strip():
            return [_finding(
                "P2", "notation", "COH_NOTATION_MISSING",
                "正文含数学公式但缺少符号说明章节(符号需统一定义)", dimension="writing_quality",
            )]
        return []

    # -- 6. 图表引用: 图不能孤立存在 -----------------------------------------
    def _figures_cited(self) -> list[dict[str, Any]]:
        findings: list[dict[str, Any]] = []
        for section_id, content in self.sections.items():
            images = IMAGE_DEF.findall(content)
            if not images:
                continue
            other = "".join(text for sid, text in self.sections.items() if sid != section_id)
            if not FIGURE_REF.search(other):
                findings.append(_finding(
                    "P2", section_id, "COH_FIGURE_NOT_CITED",
                    f"章节 {section_id} 含 {len(images)} 张图但正文其他章节未引用(图需在正文被引用而非孤立存在)",
                    dimension="figure_alignment",
                ))
        return findings

    def check_assembled(self, content: str, section_order: list[str]) -> list[dict[str, Any]]:
        """便捷入口: 传入整篇 markdown 与章节顺序, 按标题切分后检查。"""
        sections: dict[str, str] = {}
        remaining = content
        for section_id in section_order:
            # 找到对应标题的起始
            match = re.search(rf"^#+\s*{re.escape(section_id)}\b", remaining, re.MULTILINE | re.IGNORECASE)
            if not match:
                sections[section_id] = ""
                continue
            start = match.start()
            next_head = re.search(r"^#+\s+", remaining[match.end():], re.MULTILINE)
            end = match.end() + (next_head.start() if next_head else len(remaining) - match.end())
            sections[section_id] = remaining[start:end]
            remaining = remaining[end:]
        return self.check(sections)

"""图表编号 / 一致性层(融合 Sphinx numfig)

Sphinx 的 ``numfig`` 机制按"首次出现顺序"给图表自动编号,并把正文里的
``:numref:`` 引用解析到同一个编号;未解析的标签会产生构建警告。本模块把同一套
机制应用到手工作站的 FigureRegistry:

* ``build_numbering`` / ``assign_figure_numbers``:按论文章节顺序(大纲文档顺序,
  同章节内按注册顺序)给每张图分配稳定的「图N」编号,写入
  ``paper/figure_numbering.json`` 作为唯一事实源。
* ``render_figure_block`` / ``render_figure_reference``:把注册表记录渲染成
  论文里的「图N」图题 / 正文「图N」引用。
* ``check_figure_numbering``:复刻 Sphinx 未解析/重复引用警告——孤立图(已注册
  但未进论文)、正文出现未编号的「图N」引用、编号跳号/重号都作为 finding 上报。

融合来源(许可合规):
* Sphinx ``numfig`` / ``:numref:``(https://www.sphinx-doc.org, BSD-2-Clause)
* SciencePlots(https://github.com/garrettj403/SciencePlots, MIT)——图题/编号
  渲染约定与统一风格(编号与风格分属两层,风格层已由 plot_style 实现)。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .case_manager import CaseManager
from .figure_registry import FigureRegistry
from .io_utils import atomic_write_json, atomic_write_text, now_iso, read_json

#: 论文正文里的「图N」/「Figure N」引用(含图题里的编号)。
LABEL_REF = re.compile(r"(图\s*(\d+)|Figure\s*(\d+))", re.IGNORECASE)
#: 已渲染图块里保留的不可见图锚点(供证据门 figure_id 追踪)。
ANCHOR_ATTR = "data-figure-id"

#: 编号报告输出目录(review 层,与 consistency 同级)。
REPORT_DIR = "review/figure_numbering"


def build_numbering(
    sections: list[dict[str, Any]],
    figures: dict[str, dict[str, Any]],
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """按文档顺序给图表分配「图N」编号。

    Args:
        sections: 大纲章节,按论文出现顺序排列,每个含 ``section_id`` 与
            ``figure_ids`` 列表。
        figures: ``{figure_id: FigureRegistry 记录}``。

    Returns:
        (numbering, unnumbered):
            numbering —— ``{figure_id: 条目}``,条目含 ``number`` / ``label``
            (「图N」) / ``title`` / ``path`` / ``section_id`` / ``figure_id``;
            unnumbered —— 未出现在任何章节的 figure_id(已注册但未放入论文)。

    编号规则(Sphinx numfig 语义):按章节顺序逐章扫描 figure_ids,首次出现的图
    依次获得 图1、图2、…;同一张图在多章出现只记第一次编号,保证正文引用一致。
    """
    numbering: dict[str, dict[str, Any]] = {}
    seen: set[str] = set()
    for section in sections:
        section_id = section.get("section_id", "")
        for figure_id in section.get("figure_ids", []):
            if figure_id in seen:
                continue
            seen.add(figure_id)
            record = figures.get(figure_id)
            if record is None:
                continue
            number = len(numbering) + 1
            numbering[figure_id] = {
                "figure_id": figure_id,
                "number": number,
                "label": f"图{number}",
                "title": record.get("title", ""),
                "path": record.get("path", ""),
                "section_id": section_id,
            }
    unnumbered = [figure_id for figure_id in figures if figure_id not in numbering]
    return numbering, unnumbered


def assign_figure_numbers(
    case_id: str,
    outline_sections: list[dict[str, Any]],
    figures: FigureRegistry,
) -> tuple[dict[str, dict[str, Any]], list[str]]:
    """计算并持久化编号到 ``paper/figure_numbering.json``(唯一事实源)。"""
    known = {item["figure_id"]: item for item in figures.list_figures(case_id)}
    numbering, unnumbered = build_numbering(outline_sections, known)
    payload = {
        "schema_version": 1,
        "case_id": case_id,
        "numbering": numbering,
        "unnumbered_figure_ids": unnumbered,
        "generated_at": now_iso(),
    }
    path = figures.cases.case_root(case_id) / "paper" / "figure_numbering.json"
    atomic_write_json(path, payload)
    return numbering, unnumbered


def load_figure_numbering(case_id: str, cases: CaseManager) -> dict[str, dict[str, Any]]:
    """读取已持久化的编号映射;未生成时返回空映射。"""
    path = cases.case_root(case_id) / "paper" / "figure_numbering.json"
    if not path.is_file():
        return {}
    payload = read_json(path)
    return payload.get("numbering", {}) or {}


def render_figure_reference(figure_id: str, numbering: dict[str, dict[str, Any]]) -> str:
    """返回正文里的「图N」引用;未编号时回退为原始 figure_id。"""
    entry = numbering.get(figure_id)
    return entry["label"] if entry else figure_id


def render_figure_block(
    figure: dict[str, Any],
    numbering: dict[str, dict[str, Any]],
    path_prefix: str = "../",
) -> str:
    """把一张图渲染成带「图N」图题的 markdown 图块。

    图块由三行组成:
        1. 图片 + 「图N」alt(alt 在 markdown 渲染时不可见)
        2. 图题 ``**图 N：标题**``(对齐 paper_format 的 FIGURE_CAPTION_BELOW)
        3. 不可见 HTML 注释锚点 ``<!-- data-figure-id="..." -->``,保留
           figure_id 供证据门(PaperConsistencyChecker 的 FIGURE_REF)追踪,
           同时不污染成稿正文。

    Args:
        figure: FigureRegistry 记录(figure_id / title / path)。
        numbering: 编号映射。
        path_prefix: 图片路径前缀。章节草稿相对 case 根用 ``../``;若渲染到
            已装配的成稿(同一目录),传 ``""``。
    """
    figure_id = figure["figure_id"]
    title = figure.get("title", figure_id)
    label = render_figure_reference(figure_id, numbering)
    relative_path = figure.get("path", "")
    image = f"![{title}]({path_prefix}{relative_path})"
    caption = f"**{label}：{title}**"
    anchor = f"<!-- {ANCHOR_ATTR}=\"{figure_id}\" -->"
    return f"\n\n{image}\n\n{caption}\n\n{anchor}\n"


def check_figure_numbering(
    case_id: str,
    paper_text: str,
    numbering: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """复刻 Sphinx 未解析/重复引用警告,检查论文图号一致性。

    Findings(镜像 Sphinx 的构建警告语义):
        ORPHAN_FIGURE —— 分配了「图N」的图从未在论文中出现(孤立图,Sphinx 中
            对应"已编号但未被 :numref: 引用");
        UNRESOLVED_FIGURE_LABEL —— 论文正文出现「图N」但编号映射里不存在
            (泄漏引用,Sphinx 中对应 unresolved reference 警告);
        NUMBERING_GAP —— 编号不连续(图1、图3 缺图2);
        NUMBERING_DUPLICATE —— 两张不同的图共用同一「图N」(正常流程不应发生,
            防御性检查)。

    不抛异常;结果写入 ``review/figure_numbering/`` 下 json + markdown。
    """
    findings: list[dict[str, str]] = []
    # Normalize by number so "图1" / "图 1" / "Figure 1" resolve to the same key.
    raw_matches = [match for match in LABEL_REF.finditer(paper_text)]
    numbers_in_text = {int(match.group(2) or match.group(3)) for match in raw_matches if match.group(2) or match.group(3)}
    numbered = list(numbering.values())

    # 编号连续性与重号
    numbers = sorted(entry["number"] for entry in numbered)
    if numbers and numbers != list(range(1, len(numbers) + 1)):
        findings.append(
            {
                "severity": "REVIEW",
                "section_id": "global",
                "code": "NUMBERING_GAP",
                "detail": f"图号不连续: {numbers}",
            }
        )
    by_number: dict[int, list[str]] = {}
    for entry in numbered:
        by_number.setdefault(int(entry["number"]), []).append(entry["figure_id"])
    for number, figure_ids in by_number.items():
        if len(figure_ids) > 1:
            findings.append(
                {
                    "severity": "BLOCK",
                    "section_id": "global",
                    "code": "NUMBERING_DUPLICATE",
                    "detail": f"图{number} 被多张图共用: {', '.join(figure_ids)}",
                }
            )

    # 孤立图(已编号但正文未引用)
    for entry in numbered:
        if int(entry["number"]) not in numbers_in_text:
            findings.append(
                {
                    "severity": "REVIEW",
                    "section_id": entry.get("section_id", ""),
                    "code": "ORPHAN_FIGURE",
                    "detail": f"{entry['label']} {entry['figure_id']} 未在论文正文被引用",
                }
            )

    # 泄漏引用(正文出现未映射的「图N」)
    for number in numbers_in_text:
        if number not in by_number:
            findings.append(
                {
                    "severity": "BLOCK",
                    "section_id": "global",
                    "code": "UNRESOLVED_FIGURE_LABEL",
                    "detail": f"论文引用了不存在的图号 图{number}",
                }
            )

    severities = {finding["severity"] for finding in findings}
    gate = "BLOCK" if "BLOCK" in severities else "REVIEW" if "REVIEW" in severities else "PASS"
    report = {
        "schema_version": 1,
        "case_id": case_id,
        "gate": gate,
        "findings": findings,
        "numbered_figures": len(numbered),
        "labels_in_paper": sorted(numbers_in_text),
        "generated_at": now_iso(),
    }
    return report


def write_numbering_report(
    case_id: str,
    report: dict[str, Any],
    figures: FigureRegistry,
) -> dict[str, Any]:
    """把编号检查报告写入 review 目录并注册为 artifact。"""
    root = figures.cases.case_root(case_id)
    report_dir = root / REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "paper_figure_numbering.json"
    markdown_path = report_dir / "paper_figure_numbering.md"
    atomic_write_json(json_path, report)
    findings = "\n".join(
        f"- **{item['severity']}** `{item['section_id']}` `{item['code']}` {item['detail']}"
        for item in report["findings"]
    ) or "- 未发现图号一致性问题。"
    atomic_write_text(
        markdown_path,
        (
            "# 图表编号一致性检查\n\n"
            f"- Gate：**{report['gate']}**\n"
            f"- 已编号图表：`{report['numbered_figures']}`\n\n"
            "## Findings\n\n"
            f"{findings}\n"
        ),
    )
    artifact = figures.artifacts.register_existing(
        case_id,
        json_path.relative_to(root).as_posix(),
        "figure_numbering_report",
        "python",
        paper_eligible=report["gate"] == "PASS",
    )
    return {"report": report, "report_artifact_id": artifact["artifact_id"]}

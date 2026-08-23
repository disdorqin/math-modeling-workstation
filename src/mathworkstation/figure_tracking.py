"""图表注册/追踪层(融合 PaperQA 的 Source/引用追踪机制)

融合来源(许可合规,已在融合前检索确认):
* Future-House/paper-qa (https://github.com/Future-House/paper-qa, Apache-2.0)
  —— PaperQA 把每个答案组织成 ``Context`` → 每条 Context 都挂着对应的
  ``Source``(文档名 + 段落引用),回答里逐条标注来源,保证「每个结论都能追到
  证据」。本模块把同一套"结论↔证据"追踪机制应用到 FigureRegistry:
  - ``attach_figure_source`` / ``source_path``:每张图挂 `sources[]`(上游证据
    artifact + 论文位置锚点),对应 PaperQA 的 ``Source`` 类。
  - ``figure_description`` / ``figure_analysis``:给每张图生成可审计的说明段
    (含 figure_id / label / sources 引用),对应 PaperQA 的 Context→answer 段落。
  - ``list_figure_sources`` / ``find_figures_by_source``:图→证据 / 证据→图
    双向追查,对应 PaperQA 的引用追踪(citations 反查)。
  - ``check_figure_tracking``:复刻 PaperQA 的引用完整性检查——孤立图、引用
    悬空、source 空指针都以 finding 上报,不静默。
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .case_manager import CaseManager
from .figure_numbering import ANCHOR_ATTR, LABEL_REF, load_figure_numbering
from .figure_registry import FigureRegistry
from .io_utils import atomic_write_json, atomic_write_text, now_iso

#: 追踪检查报告目录(review 层,与 figure_numbering 同级)。
REPORT_DIR = "review/figure_tracking"


def source_path(case_id: str, source_artifact_ids: list[str]) -> str:
    """把来源 artifact 列表合并成一个可读的追踪路径(PaperQA Source 名)。

    Args:
        case_id: 案例 id。
        source_artifact_ids: 来源 artifact id 列表(可为空)。

    Returns:
        形如 ``artifact-xxxx / artifact-yyyy`` 的路径串,或 ``(无来源)``。
    """
    if not source_artifact_ids:
        return "(none)"
    return " / ".join(source_artifact_ids)


def attach_figure_source(
    figures: FigureRegistry,
    case_id: str,
    figure_id: str,
    source_artifact_id: str,
    context: str,
    section_id: str = "",
) -> dict[str, Any]:
    """给一张图挂一条来源记录(对应 PaperQA 的 ``Source``)。

    每次调用把一条 ``{source_artifact_id, context, section_id, attached_at}``
    追加到图的 `sources[]`,并把图记录落回注册表 JSONL(末条为当前态)。

    Args:
        figures: FigureRegistry。
        case_id: 案例 id。
        figure_id: 要挂来源的图 id。
        source_artifact_id: 来源 artifact id(必须已注册)。
        context: 这段来源支撑图里的哪部分(对应 PaperQA 的 Context)。
        section_id: 论文章节 id(锚点用,可为空)。

    Returns:
        更新后的图记录。

    Raises:
        KeyError: figure 或 source artifact 不存在。
    """
    figure = figures.get(case_id, figure_id)
    figures.artifacts.get(case_id, source_artifact_id)
    sources = list(figure.get("sources", []))
    sources.append(
        {
            "source_artifact_id": source_artifact_id,
            "context": context,
            "section_id": section_id,
            "attached_at": now_iso(),
        }
    )
    updated = {**figure, "sources": sources, "updated_at": now_iso()}
    from .io_utils import append_jsonl

    append_jsonl(figures.registry_path(case_id), updated)
    return updated


def list_figure_sources(figures: FigureRegistry, case_id: str, figure_id: str) -> list[dict[str, Any]]:
    """列出某张图的全部来源(PaperQA 的 Source 列表)。"""
    return list(figures.get(case_id, figure_id).get("sources", []))


def find_figures_by_source(figures: FigureRegistry, case_id: str, source_artifact_id: str) -> list[dict[str, Any]]:
    """反查:某条证据被哪些图引用(PaperQA 的 citations 反查)。"""
    return [
        figure
        for figure in figures.list_figures(case_id)
        if any(source["source_artifact_id"] == source_artifact_id for source in figure.get("sources", []))
    ]


def figure_description(
    figure: dict[str, Any],
    numbering: dict[str, dict[str, Any]],
    max_sources: int = 3,
) -> str:
    """生成一张图的可审计说明段(PaperQA 的 Context→answer 段落渲染)。

    说明段包含:图号 label、figure_id 锚点、标题、来源路径与来源 artifact 列表。
    ``max_sources`` 截断来源列表,避免过长段落。

    Args:
        figure: FigureRegistry 图记录。
        numbering: ``figure_id -> 编号条目``(缺省时退化为"图?")。
        max_sources: 最多列出几条来源。

    Returns:
        Markdown 说明段文本。
    """
    entry = numbering.get(figure.get("figure_id", ""), {})
    label = entry.get("label", "图?")
    title = figure.get("title", "")
    sources = figure.get("sources", [])
    source_text = source_path(figure.get("case_id", ""), [s["source_artifact_id"] for s in sources[:max_sources]])
    lines = [
        f"**{label}：{title}**",
        f"- Figure id: `{figure.get('figure_id', '')}`",
        f"- 来源: {source_text}",
    ]
    if sources:
        listed = sources[:max_sources]
        if len(sources) > max_sources:
            listed = listed + [{"context": f"... 另 {len(sources) - max_sources} 条来源"}]
        lines.append("- 引用: ")
        lines.extend(f"  - `{s['source_artifact_id']}` — {s.get('context', '')}" for s in listed)
    return "\n".join(lines)


def figure_analysis(
    figure: dict[str, Any],
    numbering: dict[str, dict[str, Any]],
    sentence: str,
) -> str:
    """给一张图写一句「图说明/分析」(对标 O 奖论文的图表分析段落)。

    Args:
        figure: FigureRegistry 图记录。
        numbering: ``figure_id -> 编号条目``。
        sentence: 说明该图说明了什么的一句话(来自确定性引擎,不靠幻觉)。

    Returns:
        Markdown 分析段文本。
    """
    entry = numbering.get(figure.get("figure_id", ""), {})
    label = entry.get("label", "图?")
    title = figure.get("title", "")
    return f"**{label}：{title}** — {sentence}"
def check_figure_tracking(
    case_id: str,
    paper_text: str,
    figures: FigureRegistry,
) -> dict[str, Any]:
    """复刻 PaperQA 引用完整性检查:不静默,把每个问题报为 finding。

    检查项:
    - BLOCK: ``图N`` 标签指向的 figure 不在注册表(引用悬空)。
    - BLOCK: 图的来源 artifact 指针未注册(sources 空指针)。
    - REVIEW: 图已注册但没有 sources(孤立图,无证据链)。
    - REVIEW: 图已 FINAL 但正文未被「图N」引用。

    Args:
        case_id: 案例 id。
        paper_text: 论文正文(未渲染的纯文本即可)。
        figures: FigureRegistry。

    Returns:
        ``{schema_version, case_id, gate, findings, tracked_figures, generated_at}``。
    """
    findings: list[dict[str, Any]] = []
    records = figures.list_figures(case_id)
    numbering = load_figure_numbering(case_id, figures.cases)
    # 「图N」标签 → figure_id 映射(编号地图的 label → figure_id)
    labels_to_ids: dict[str, str] = {}
    for figure_id, entry in numbering.items():
        labels_to_ids.setdefault(str(entry.get("label", "")), figure_id)
    referenced_numbers = {
        int(match.group(2) or match.group(3)) for match in LABEL_REF.finditer(paper_text)
    }
    referenced_labels = {f"图{number}" for number in referenced_numbers}

    registered_ids = {record["figure_id"] for record in records}
    for label in sorted(referenced_labels):
        target_id = labels_to_ids.get(label)
        if target_id is None or target_id not in registered_ids:
            findings.append(
                {
                    "severity": "BLOCK",
                    "section_id": "global",
                    "code": "UNRESOLVED_FIGURE_TRACKING",
                    "detail": f"正文引用了 {label},但注册表/编号地图没有对应 figure_id",
                }
            )

    for record in records:
        figure_id = record["figure_id"]
        label = numbering.get(figure_id, {}).get("label", "图?")
        sources = record.get("sources", [])
        if not sources:
            findings.append(
                {
                    "severity": "REVIEW",
                    "section_id": numbering.get(figure_id, {}).get("section_id", ""),
                    "code": "FIGURE_WITHOUT_SOURCE",
                    "detail": f"{label} {figure_id} 没有来源记录(无证据链)",
                }
            )
        for source in sources:
            artifact_id = source.get("source_artifact_id", "")
            try:
                figures.artifacts.get(case_id, artifact_id)
            except KeyError:
                findings.append(
                    {
                        "severity": "BLOCK",
                        "section_id": numbering.get(figure_id, {}).get("section_id", ""),
                        "code": "SOURCE_ARTIFACT_MISSING",
                        "detail": f"{label} {figure_id} 引用的来源 artifact 不存在: {artifact_id}",
                    }
                )
        number = numbering.get(figure_id, {}).get("number")
        if record.get("status") == "FINAL" and number is not None and int(number) not in referenced_numbers:
            findings.append(
                {
                    "severity": "REVIEW",
                    "section_id": numbering.get(figure_id, {}).get("section_id", ""),
                    "code": "FINAL_FIGURE_UNREFERENCED",
                    "detail": f"{label} {figure_id} 已 FINAL 但正文未引用",
                }
            )

    severities = {finding["severity"] for finding in findings}
    gate = "BLOCK" if "BLOCK" in severities else "REVIEW" if "REVIEW" in severities else "PASS"
    return {
        "schema_version": 1,
        "case_id": case_id,
        "gate": gate,
        "findings": findings,
        "tracked_figures": len(records),
        "generated_at": now_iso(),
    }


def write_tracking_report(
    case_id: str,
    report: dict[str, Any],
    figures: FigureRegistry,
) -> dict[str, Any]:
    """把追踪检查报告写入 review 目录并注册为 artifact。"""
    root = figures.cases.case_root(case_id)
    report_dir = root / REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / "figure_tracking_report.json"
    markdown_path = report_dir / "figure_tracking_report.md"
    atomic_write_json(json_path, report)
    findings = "\n".join(
        f"- **{item['severity']}** `{item['section_id']}` `{item['code']}` {item['detail']}"
        for item in report["findings"]
    ) or "- 未发现追踪/引用问题。"
    atomic_write_text(
        markdown_path,
        (
            "# 图表追踪一致性检查\n\n"
            f"- Gate：**{report['gate']}**\n"
            f"- 已追踪图表：`{report['tracked_figures']}`\n\n"
            "## Findings\n\n"
            f"{findings}\n"
        ),
    )
    artifact = figures.artifacts.register_existing(
        case_id,
        json_path.relative_to(root).as_posix(),
        "figure_tracking_report",
        "python",
        paper_eligible=report["gate"] == "PASS",
    )
    return {"report": report, "report_artifact_id": artifact["artifact_id"]}


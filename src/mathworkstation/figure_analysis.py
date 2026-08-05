"""图表分析段落引擎(融合 SciencePlots / Data Formulator / Chart-to-text)

O 奖(MCM/ICM Outstanding Winner)论文里,每张图不仅有图题,还有一段
充分的分析文字: 引导句 → 观察描述 → 数据解读 → 结论导向。本模块把这一
标准落成确定性检查器与模板生成器,挂在 PaperCoherenceChecker /
PaperConsistencyChecker 上,保证每张进入论文的图都有达标解读。

融合来源(许可合规,仅设计模式参考、不复制代码):
* SciencePlots (https://github.com/garrettj403/SciencePlots, MIT)
  —— 学术图表标注完整性约定: label/legend/unit 齐全、图题描述性强。
* Data Formulator (https://github.com/microsoft/data-formulator, MIT)
  —— 图表类型分类法: 标题关键词 → 图表类型 → 描述模式 的路由。
* Chart-to-text (https://github.com/vis-nlp/Chart-to-text, CC BY-NC-SA 4.0)
  —— 仅评估方法论: caption 充分性维度、O 奖描述段落的结构化模板。
"""

from __future__ import annotations

import re
from typing import Any

from .figure_numbering import LABEL_REF
from .io_utils import atomic_write_json, atomic_write_text, now_iso

#: 分析报告输出目录(review 层,与 consistency / figure_numbering 同级)。
REPORT_DIR = "review/figure_analysis"

#: 每节的最小分析段落长度(设计文档: data_analysis/sensitivity ≥80, results ≥100)。
SECTION_FIGURE_REQUIREMENTS: dict[str, dict[str, Any]] = {
    "data_analysis": {"min_chars": 80, "notes": "EDA 图需覆盖形态/分布/异常"},
    "results": {"min_chars": 100, "notes": "结果图需给出关键数值与比较"},
    "sensitivity": {"min_chars": 80, "notes": "敏感性图需解读变化范围"},
    "model_construction": {"min_chars": 80, "notes": "模型结构图需说明设计动机"},
    "model_solution": {"min_chars": 80, "notes": "求解图需说明算法行为"},
    "momentum_analysis": {"min_chars": 80, "notes": "动量分析图需解读统计检验含义"},
    "timeseries_analysis": {"min_chars": 80, "notes": "时序图需解读趋势/自相关/平稳性"},
    "conclusion": {"min_chars": 80, "notes": "结论图需回扣模型结论"},
}

#: 未在表内的章节默认最小长度。
DEFAULT_MIN_CHARS = 80

#: markdown 图片定义(与 coherence 一致)。
IMAGE_DEF = re.compile(r"!\[.*?\]\(.*?\)")
#: 图题行 ``**图1：标题**`` / ``**图 1: Title**``。
CAPTION_LINE = re.compile(r"^\s*\*\*图\s*\d+\s*[：:].*?\*\*\s*$", re.MULTILINE)
#: 图号引用锚点注释 ``<!-- data-figure-id="..." -->``。
ANCHOR_COMMENT = re.compile(r"<!--\s*data-figure-id\s*=\s*\"[^\"]*\"\s*-->")

#: 数值信号(百分比/小数/整数)。
NUMBER_TOKEN = re.compile(r"\d+(?:\.\d+)?%?")
#: 数据解读信号词(趋势/比较/形态)。
INTERPRETATION_WORDS = (
    "上升", "下降", "增长", "减少", "显著", "集中", "分散", "占比", "高于", "低于",
    "相比", "对比", "波动", "平稳", "趋势", "峰值", "谷值", "均值", "中位数",
    "递增", "递减", "拐点", "转折", "稳定", "接近", "超过", "最大", "最小",
)
#: 结论导向信号词(分析指向论文论点)。
CONCLUSION_WORDS = (
    "表明", "说明", "支持", "验证", "印证", "证实", "因此", "这说明", "该观察",
    "这一结果", "上述", "印证了", "支持了", "符合", "体现", "反映", "据此",
)

#: 图表类型分类(Data Formulator 语义: 标题关键词 → 图表类型)。
CHART_TYPE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "heatmap": ("热力", "相关矩阵", "heatmap", "correlation"),
    "bar": ("柱状", "占比", "对比图", "bar", "柱形"),
    "line": ("趋势", "时序", "变化曲线", "line", "曲线"),
    "scatter": ("散点", "scatter", "分布关系"),
    "box": ("箱线", "box", "分布范围"),
    "histogram": ("直方", "hist", "频数分布"),
    "errorbar": ("误差棒", "置信区间", "errorbar"),
    "pie": ("饼图", "pie"),
}

#: 图表类型 → 描述模式(O 奖段落骨架,来自 Chart-to-text 的方法论)。
CHART_DESCRIPTION_PATTERN: dict[str, str] = {
    "bar": "柱状图直观呈现各分组之间的量级对比;重点关注最高/最低组及其差距。",
    "line": "折线图刻画指标随时间/迭代的演变轨迹;重点关注整体趋势方向与转折点。",
    "scatter": "散点图揭示两变量之间的相关形态;重点关注是否线性及离群点。",
    "heatmap": "热力图以颜色深浅呈现矩阵取值;重点关注高亮区域(强相关/高密度)。",
    "box": "箱线图展示分布的位置与离散程度;重点关注中位数与箱体跨度。",
    "histogram": "直方图展示取值频数分布;重点关注中心位置与偏态。",
    "errorbar": "误差棒图展示估计值与不确定性;重点关注误差范围是否重叠。",
    "pie": "饼图展示构成占比;重点关注占比最大/最小的部分。",
    "generic": "本图展示相应指标的分布与形态;重点关注整体规律与局部异常。",
}


def _detect_chart_type(title: str) -> str:
    """按标题关键词路由到图表类型(Data Formulator 分类逻辑的模式参考)。"""
    lowered = title.lower()
    for chart_type, keywords in CHART_TYPE_KEYWORDS.items():
        if any(kw in lowered or kw in title for kw in keywords):
            return chart_type
    return "generic"


def _first_analysis_paragraph(after: str) -> str:
    """取图片块之后的第一个正文段落(跳过图题行与锚点注释)。"""
    cleaned = CAPTION_LINE.sub("", after)
    cleaned = ANCHOR_COMMENT.sub("", cleaned)
    cleaned = IMAGE_DEF.sub("", cleaned)
    for para in re.split(r"\n\s*\n", cleaned):
        para = para.strip()
        if not para:
            continue
        if para.startswith("#"):
            continue
        return para
    return ""


def _min_chars_for(section_id: str) -> int:
    return SECTION_FIGURE_REQUIREMENTS.get(section_id, {}).get("min_chars", DEFAULT_MIN_CHARS)


def _o_award_element_issues(para: str, min_chars: int) -> list[dict[str, str]]:
    """按 O 奖四要素检查一个分析段落,返回缺失项列表。"""
    issues: list[dict[str, str]] = []
    # 1. 引导句: 段落内必须出现「图N」/「Figure N」引用
    if not LABEL_REF.search(para):
        issues.append({"code": "FIG_MISSING_LEAD", "detail": "分析段落缺少引导句(未引用「图N」/Figure N)"})
    # 2. 数据解读: 数值 或 趋势/比较词 至少其一
    has_number = bool(NUMBER_TOKEN.search(para))
    has_interpretation = any(word in para for word in INTERPRETATION_WORDS)
    if not (has_number or has_interpretation):
        issues.append({"code": "FIG_MISSING_INTERPRETATION", "detail": "分析段落缺少数据解读(无数值/趋势/比较信号)"})
    # 3. 结论导向: 出现结论导向词
    if not any(word in para for word in CONCLUSION_WORDS):
        issues.append({"code": "FIG_MISSING_TAKEAWAY", "detail": "分析段落缺少结论导向(未说明支持论文的哪个论点)"})
    # 4. 充分性: 长度门槛
    if len(para) < min_chars:
        issues.append({"code": "FIG_ANALYSIS_TOO_SHORT", "detail": f"分析段落仅 {len(para)} 字,低于本节的 {min_chars} 字门槛"})
    return issues


def check_figure_analysis_paragraphs(sections: dict[str, str]) -> dict[str, Any]:
    """检查每张图在论文中是否有充分的分析段落。

    Args:
        sections: ``{section_id: markdown}``(与 PaperCoherenceChecker 输入一致)。

    Returns:
        report: 含 ``gate`` / ``findings`` / ``coverage`` 的检查报告。
        每张图: 图块后的第一个正文段落视为该图的分析段落,按 O 奖四要素
        (引导句 / 数据解读 / 结论导向 / 长度门槛)逐项检查,缺失项记为
        ``REVIEW`` finding。所有 finding 均为软发现(不阻塞证据门)。
    """
    findings: list[dict[str, Any]] = []
    per_section: dict[str, dict[str, Any]] = {}
    total_figures = 0
    covered_figures = 0

    for section_id, content in sections.items():
        images = list(IMAGE_DEF.finditer(content))
        if not images:
            continue
        section_total = 0
        section_covered = 0
        min_chars = _min_chars_for(section_id)
        for index, image in enumerate(images):
            total_figures += 1
            section_total += 1
            segment_end = images[index + 1].start() if index + 1 < len(images) else len(content)
            para = _first_analysis_paragraph(content[image.end():segment_end])
            label = _figure_label_near(content, image.start())
            if para:
                covered_figures += 1
                section_covered += 1
                for issue in _o_award_element_issues(para, min_chars):
                    findings.append({
                        "severity": "REVIEW",
                        "section_id": section_id,
                        "code": issue["code"],
                        "detail": f"{label} {issue['detail']}",
                    })
            else:
                findings.append({
                    "severity": "REVIEW",
                    "section_id": section_id,
                    "code": "FIG_ANALYSIS_MISSING",
                    "detail": f"{label} 缺少分析段落(图后无正文文字)",
                })
        per_section[section_id] = {
            "figures": section_total,
            "covered": section_covered,
            "coverage_percent": round(section_covered / section_total * 100, 1) if section_total else 0.0,
        }

    coverage_percent = round(covered_figures / total_figures * 100, 1) if total_figures else 100.0
    gate = "PASS" if not findings else "REVIEW"
    return {
        "schema_version": 1,
        "gate": gate,
        "findings": findings,
        "coverage": {
            "total_figures": total_figures,
            "covered_figures": covered_figures,
            "coverage_percent": coverage_percent,
            "per_section": per_section,
        },
        "generated_at": now_iso(),
    }


def _figure_label_near(content: str, image_start: int) -> str:
    """尽力从图块**之后**提取「图N」标签,取不到时返回『某图』。

    只搜索图块后方(图题固定在图下方),避免匹配到正文里对前一张图的引用。
    """
    window = content[image_start:image_start + 400]
    match = LABEL_REF.search(window)
    if match and (match.group(2) or match.group(3)):
        return match.group(0).strip()
    return "某图"


def generate_figure_analysis_template(
    title: str,
    section_id: str = "data_analysis",
    source: str = "",
) -> str:
    """为一张图生成结构化分析段落模板(O 奖四要素骨架)。

    Args:
        title: 图题。
        section_id: 所属章节(决定长度门槛与关注点)。
        source: 数据来源说明(可选,填充进引导句)。

    Returns:
        str: 可直接粘贴到论文的分析段落模板,``[TODO]`` 处需人工/LLM 填充。
    """
    chart_type = _detect_chart_type(title)
    pattern = CHART_DESCRIPTION_PATTERN.get(chart_type, CHART_DESCRIPTION_PATTERN["generic"])
    min_chars = _min_chars_for(section_id)
    lead_source = f"(数据来源: {source})" if source else ""
    return (
        f"如图[TODO: 编号]所示,{title} {lead_source}。\n\n"
        f"{pattern}\n"
        f"具体来看,[TODO: 给出关键数值/趋势/比较,如占比 33%、较基线上升 15%]。\n\n"
        f"这一观察表明,[TODO: 说明该结果支持论文的哪个论点/假设]。\n\n"
        f"*[提示: 本模板由 figure_analysis 生成,目标分析段落 ≥{min_chars} 字,"
        f"覆盖 引导句 → 观察描述 → 数据解读 → 结论导向 四要素。]*"
    )


def check_figure_annotations(
    figures: list[dict[str, Any]],
    paper_text: str,
    numbering: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """检查图表标注完整性(SciencePlots 约定: label/legend/unit + 描述性图题)。

    Args:
        figures: FigureRegistry 记录列表(每条含 figure_id / title / parameters)。
        paper_text: 装配后的论文正文(用于确认图题真实出现在论文里)。
        numbering: 可选的真实编号映射(figure_numbering 的唯一事实源);缺省时
            按记录顺序推导轻量编号(standalone 场景)。

    Returns:
        report: 标注完整性报告,含 ``gate`` 与逐图 findings。
    """
    findings: list[dict[str, Any]] = []

    numbering = numbering if numbering is not None else load_figure_numbering_from_records(figures)
    for figure in figures:
        figure_id = figure.get("figure_id", "")
        title = figure.get("title", "")
        if not title.strip():
            findings.append({
                "severity": "REVIEW",
                "section_id": figure.get("section_id", ""),
                "code": "FIG_TITLE_EMPTY",
                "detail": f"{figure_id} 图题为空",
            })
        else:
            lowered = title.lower()
            if lowered in ("figure", "fig", "figure1", "fig1") or lowered.startswith("figure ") or re.fullmatch(r"图\s*\d+", title):
                findings.append({
                    "severity": "REVIEW",
                    "section_id": figure.get("section_id", ""),
                    "code": "FIG_TITLE_PLACEHOLDER",
                    "detail": f"{figure_id} 图题为占位符「{title}」,缺少描述性标题",
                })
            label = (numbering.get(figure_id) or {}).get("label")
            caption_marker = f"**{label}：{title}**" if label else title
            if caption_marker not in paper_text:
                findings.append({
                    "severity": "REVIEW",
                    "section_id": figure.get("section_id", ""),
                    "code": "FIG_CAPTION_NOT_IN_PAPER",
                    "detail": f"{figure_id} 图题「{title}」未出现在论文中",
                })
        parameters = figure.get("parameters") or {}
        for axis in ("xlabel", "ylabel"):
            value = parameters.get(axis, "")
            if axis in parameters and not str(value).strip():
                findings.append({
                    "severity": "REVIEW",
                    "section_id": figure.get("section_id", ""),
                    "code": "FIG_AXIS_LABEL_EMPTY",
                    "detail": f"{figure_id} 轴标签 {axis} 为空(期望 轴名+单位)",
                })
        legend = parameters.get("legend")
        if legend is not None and not str(legend).strip():
            findings.append({
                "severity": "REVIEW",
                "section_id": figure.get("section_id", ""),
                "code": "FIG_LEGEND_EMPTY",
                "detail": f"{figure_id} 图例为空",
            })

    gate = "PASS" if not findings else "REVIEW"
    return {
        "schema_version": 1,
        "gate": gate,
        "findings": findings,
        "annotated_figures": len(figures),
        "generated_at": now_iso(),
    }


def load_figure_numbering_from_records(figures: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """从 FigureRegistry 记录里恢复 图N 标签(无 case 根目录时的轻量路径)。"""
    numbering: dict[str, dict[str, Any]] = {}
    # 记录里可能携带渲染时写入的 label(见 render_figure_block 的调用方);没有则按序补。
    for figure in figures:
        figure_id = figure.get("figure_id", "")
        if not figure_id:
            continue
        entry = figure.get("numbering") or {}
        numbering[figure_id] = {
            "figure_id": figure_id,
            "label": entry.get("label") or f"图{len(numbering) + 1}",
            "title": figure.get("title", ""),
        }
    return numbering


def report_figure_coverage(sections: dict[str, str]) -> dict[str, Any]:
    """生成图表覆盖度报告(哪些图有分析段落、字数统计、覆盖百分比)。"""
    analysis = check_figure_analysis_paragraphs(sections)
    per_section: dict[str, dict[str, Any]] = {}
    for section_id, content in sections.items():
        images = list(IMAGE_DEF.finditer(content))
        if not images:
            continue
        section_stats = {"figures": len(images), "with_analysis": 0, "chars": []}
        for index, image in enumerate(images):
            segment_end = images[index + 1].start() if index + 1 < len(images) else len(content)
            para = _first_analysis_paragraph(content[image.end():segment_end])
            if para:
                section_stats["with_analysis"] += 1
                section_stats["chars"].append(len(para))
        section_stats["coverage_percent"] = (
            round(section_stats["with_analysis"] / section_stats["figures"] * 100, 1)
            if section_stats["figures"]
            else 100.0
        )
        section_stats["min_chars"] = _min_chars_for(section_id)
        per_section[section_id] = section_stats

    coverage = analysis["coverage"]
    return {
        "schema_version": 1,
        "coverage": coverage,
        "per_section": per_section,
        "overall_percent": coverage["coverage_percent"],
        "missing_sections": [sid for sid, stats in per_section.items() if stats["with_analysis"] < stats["figures"]],
        "generated_at": now_iso(),
    }


def coherence_findings(sections: dict[str, str]) -> list[dict[str, Any]]:
    """供 PaperCoherenceChecker 集成的 finding 列表(P2 语义,软发现)。

    把 figure_analysis 的 ``REVIEW`` findings 转成 coherence 的 ``P2`` 格式,
    由 ``PaperCoherenceChecker.check()`` 合并进统一 finding 流,进入 refinement
    的 issue 驱动打磨;不阻塞证据门。
    """
    report = check_figure_analysis_paragraphs(sections)
    findings: list[dict[str, Any]] = []
    for item in report["findings"]:
        findings.append({
            "severity": "P2",
            "section_id": item["section_id"],
            "code": item["code"],
            "detail": item["detail"],
            "dimension": "figure_alignment",
        })
    return findings


def check_figure_id_tracking(
    sections: dict[str, str],
    numbering: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """分析段落中的 figure_id 追踪: 每张已编号的图都应能通过锚点定位到段落。

    Args:
        sections: ``{section_id: markdown}``。
        numbering: figure_numbering 生成的 ``{figure_id: 条目}``。

    Returns:
        report: 追踪报告,含 ``tracked_figures`` / ``untracked``。
    """
    findings: list[dict[str, Any]] = []
    body = "\n\n".join(sections.values())
    tracked: list[str] = []
    for figure_id, entry in (numbering or {}).items():
        anchor = f'data-figure-id="{figure_id}"'
        if anchor not in body:
            findings.append({
                "severity": "REVIEW",
                "section_id": entry.get("section_id", ""),
                "code": "FIG_ID_NOT_TRACKED",
                "detail": f"{figure_id} 未在论文中找到 {anchor} 锚点,无法追踪分析段落",
            })
        else:
            tracked.append(figure_id)
    untracked = [figure_id for figure_id in (numbering or {}) if figure_id not in tracked]
    gate = "PASS" if not findings else "REVIEW"
    return {
        "schema_version": 1,
        "gate": gate,
        "findings": findings,
        "tracked_figures": tracked,
        "untracked_figures": untracked,
        "generated_at": now_iso(),
    }


def write_analysis_report(
    case_id: str,
    report: dict[str, Any],
    figures: Any,
    kind: str = "paragraphs",
) -> dict[str, Any]:
    """把分析报告写入 ``review/figure_analysis/`` 并注册为 artifact。

    Args:
        case_id: 案例 ID。
        report: 检查报告(check_figure_analysis_paragraphs / check_figure_annotations
            等的返回值)。
        figures: FigureRegistry 实例(用于注册 artifact)。
        kind: 报告种类(paragraphs / annotations / coverage),决定文件名。

    Returns:
        {"report": report, "report_artifact_id": artifact_id}
    """
    root = figures.cases.case_root(case_id)
    report_dir = root / REPORT_DIR
    report_dir.mkdir(parents=True, exist_ok=True)
    json_path = report_dir / f"paper_figure_{kind}.json"
    markdown_path = report_dir / f"paper_figure_{kind}.md"
    atomic_write_json(json_path, report)
    findings = "\n".join(
        f"- **{item['severity']}** `{item['section_id']}` `{item['code']}` {item['detail']}"
        for item in report.get("findings", [])
    ) or "- 未发现问题。"
    coverage = report.get("coverage", {})
    coverage_line = (
        f"- 覆盖度: `{coverage.get('coverage_percent', '—')}%`"
        f"({coverage.get('covered_figures', 0)}/{coverage.get('total_figures', 0)})\n"
        if coverage
        else ""
    )
    atomic_write_text(
        markdown_path,
        (
            "# 图表分析段落检查\n\n"
            f"- Gate: **{report.get('gate', 'PASS')}**\n"
            f"{coverage_line}"
            "- 标准: O 奖四要素(引导句 / 观察描述 / 数据解读 / 结论导向)\n\n"
            "## Findings\n\n"
            f"{findings}\n"
        ),
    )
    artifact = figures.artifacts.register_existing(
        case_id,
        json_path.relative_to(root).as_posix(),
        "figure_analysis_report",
        "python",
        paper_eligible=report.get("gate") == "PASS",
    )
    return {"report": report, "report_artifact_id": artifact["artifact_id"]}

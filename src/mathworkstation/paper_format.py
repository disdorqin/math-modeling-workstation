from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .io_utils import read_json


# ---------------------------------------------------------------------------
# Config loading
# ---------------------------------------------------------------------------

def _load_format_config() -> dict[str, Any]:
    """Load the mathmodel-format.json configuration."""
    config_path = Path(__file__).resolve().parent.parent.parent / "config" / "mathmodel-format.json"
    if not config_path.is_file():
        raise FileNotFoundError(f"Format config not found: {config_path}")
    return read_json(config_path)


# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# Abstract section: detects "摘要", "Abstract", "Summary" in markdown headings
ABSTRACT_SECTION = re.compile(
    r"^#+\s*(摘要|Abstract|Summary)\b", re.IGNORECASE | re.MULTILINE
)
CUMCM_ABSTRACT_START = re.compile(r"^#+\s*摘要\b", re.MULTILINE)
MCM_ABSTRACT_START = re.compile(r"^#+\s*(Abstract|Summary)\b", re.IGNORECASE | re.MULTILINE)

# Forbidden items in abstract
DISPLAY_FORMULA = re.compile(
    r"\$\$.*?\$\$|\\begin\{[^}]*\}.*?\\end\{[^}]*\}", re.DOTALL
)
INLINE_FORMULA = re.compile(r"\$(?!\$)[^$\n]+?\$")
MARKDOWN_TABLE = re.compile(r"\|.*\|")
MARKDOWN_IMAGE = re.compile(r"!\[.*?\]\(.*?\)")

# Three-line table patterns
TABLE_CAPTION_ABOVE = re.compile(
    r"(表\s*\d+|Table\s*\d+)[\s\S]*?\n\s*\|", re.IGNORECASE
)
TABLE_CAPTION_BELOW = re.compile(
    r"\|\s*\n\s*(表\s*\d+|Table\s*\d+)", re.IGNORECASE
)

# Figure detection and citation
FIGURE_DEFINITION = re.compile(r"!\[(.*?)\]\((.*?)\)")
FIGURE_REFERENCE = re.compile(r"(图\s*\d+|Figure\s*\d+)", re.IGNORECASE)
FIGURE_CAPTION_BELOW = re.compile(
    r"!\[.*?\]\(.*?\)\s*\n\s*(图\s*\d+|Figure\s*\d+)", re.IGNORECASE
)
FIGURE_CAPTION_ABOVE = re.compile(
    r"(图\s*\d+|Figure\s*\d+)[\s\S]*?\n\s*!\[.*?\]", re.IGNORECASE
)

# Reference type patterns
REF_TYPE_PATTERN = re.compile(r"\[([JMD])\]")
REF_EBOL_PATTERN = re.compile(r"\[EB/OL\]")
CHINESE_REF_PUNCTUATION = re.compile(r"[，。；：、！？]")

# Page estimation: roughly 40 lines/page for a typical LaTeX document
LINES_PER_PAGE = 40

# Section heading pattern for counting
SECTION_HEADING = re.compile(r"^#+\s+", re.MULTILINE)


def _extract_abstract(content: str) -> str | None:
    """Extract the abstract section content from a markdown document.

    Returns the abstract text (between the abstract heading and the next heading),
    or None if no abstract section is found.
    """
    # Find abstract heading
    m = ABSTRACT_SECTION.search(content)
    if not m:
        return None

    start_pos = m.end()
    # Find next heading after abstract
    remaining = content[start_pos:]
    next_heading = SECTION_HEADING.search(remaining)
    if next_heading:
        end_pos = start_pos + next_heading.start()
    else:
        end_pos = len(content)

    return content[start_pos:end_pos].strip()


def _extract_sections(content: str) -> list[dict[str, Any]]:
    """Extract all sections with their content from a markdown document."""
    sections = []
    headings = list(SECTION_HEADING.finditer(content))
    for i, m in enumerate(headings):
        title = content[m.end():].split("\n", 1)[0].strip()
        start = m.end() + len(title)
        if i + 1 < len(headings):
            end = headings[i + 1].start()
        else:
            end = len(content)
        sections.append({
            "section_id": title,
            "content": content[start:end].strip(),
            "heading_level": m.group().count("#"),
        })
    return sections


def _count_pages(content: str) -> int:
    """Estimate page count from content lines."""
    lines = content.count("\n") + 1
    return (lines + LINES_PER_PAGE - 1) // LINES_PER_PAGE


def _check_abstract_violations(abstract: str, competition: str, spec: dict) -> list[dict[str, str]]:
    """Check abstract for forbidden elements.

    BLOCK if:
    - Abstract contains formulas ($...$, $$...$$, \\begin{...})
    - Abstract contains tables (|...|)
    - Abstract contains images (![...](...))
    """
    findings = []
    forbidden = spec.get("forbidden_items", [])

    for item_type in forbidden:
        if item_type == "formula":
            display = DISPLAY_FORMULA.findall(abstract)
            inline = INLINE_FORMULA.findall(abstract)
            if display or inline:
                detail = spec.get("forbidden_descriptions", {}).get(
                    "formula", "摘要中不得出现公式"
                )
                findings.append(_finding("BLOCK", "abstract", "ABSTRACT_HAS_FORMULA", detail))
        elif item_type == "table":
            if MARKDOWN_TABLE.search(abstract):
                detail = spec.get("forbidden_descriptions", {}).get(
                    "table", "摘要中不得出现表格"
                )
                findings.append(_finding("BLOCK", "abstract", "ABSTRACT_HAS_TABLE", detail))
        elif item_type == "figure":
            if MARKDOWN_IMAGE.search(abstract):
                detail = spec.get("forbidden_descriptions", {}).get(
                    "figure", "摘要中不得出现图片"
                )
                findings.append(_finding("BLOCK", "abstract", "ABSTRACT_HAS_FIGURE", detail))

    return findings


def _check_abstract_page(abstract: str, content: str, spec: dict) -> list[dict[str, str]]:
    """Check if abstract fits within the page limit.

    REVIEW if abstract is estimated to exceed 1 page.
    """
    findings = []
    max_pages = spec.get("max_pages", 1)
    abstract_lines = abstract.count("\n") + 1 if abstract else 0
    estimated_pages = (abstract_lines + LINES_PER_PAGE - 1) // LINES_PER_PAGE
    if estimated_pages > max_pages:
        findings.append(_finding(
            "REVIEW", "abstract", "ABSTRACT_OVER_PAGE",
            f"摘要估计 {estimated_pages} 页，超过 {max_pages} 页限制"
        ))
    return findings


def _check_three_line_tables(content: str, spec: dict) -> list[dict[str, str]]:
    """Check that tables follow three-line table format.

    REVIEW if:
    - Tables are detected in markdown (cannot verify LaTeX three-line at this stage)
    - Table caption position is wrong (should be above)
    """
    findings = []
    # In markdown, tables are rendered with pipes. In the final LaTeX, they
    # should use booktabs (\\toprule, \\midrule, \\bottomrule) and no vertical lines.
    tables = MARKDOWN_TABLE.findall(content)
    if not tables:
        return findings

    has_caption_above = TABLE_CAPTION_ABOVE.search(content)
    has_caption_below = TABLE_CAPTION_BELOW.search(content)

    # In markdown, table captions should be above the table
    if has_caption_above and not has_caption_below:
        pass  # correct format
    elif has_caption_below and not has_caption_above:
        findings.append(_finding(
            "REVIEW", "tables", "TABLE_CAPTION_BELOW",
            "表题应在表格上方（CUMCM/MCM 规范要求表题在上）"
        ))
    elif has_caption_below and has_caption_above:
        findings.append(_finding(
            "REVIEW", "tables", "TABLE_CAPTION_MIXED",
            "部分表题位置不规范，应统一在表格上方"
        ))
    else:
        findings.append(_finding(
            "REVIEW", "tables", "TABLE_CAPTION_MISSING",
            "表格缺少表题或编号（表题应在表格上方，格式：表1 标题）"
        ))

    # Check for three-line table structure in LaTeX
    # In markdown, we can only flag that tables exist and should be three-line
    findings.append(_finding(
        "REVIEW", "tables", "THREE_LINE_TABLE_NEEDED",
        "Markdown中的表格需在LaTeX中转换为三线表格式（顶线/栏目线/底线1.5磅，无竖线）"
    ))

    return findings


def _check_figures(content: str, spec: dict) -> list[dict[str, str]]:
    """Check figure caption position and citation requirements.

    BLOCK if figures are not cited in text.
    REVIEW if figure caption position is wrong.
    """
    findings = []
    figures = FIGURE_DEFINITION.findall(content)
    if not figures:
        return findings

    # Check if all figures are referenced in text
    figure_refs = FIGURE_REFERENCE.findall(content)
    figure_count = len(figures)

    if not figure_refs:
        findings.append(_finding(
            "BLOCK", "figures", "FIGURES_NOT_CITED",
            f"文中有 {figure_count} 张图但未在正文中引用"
        ))
    elif len(set(figure_refs)) < figure_count:
        findings.append(_finding(
            "REVIEW", "figures", "SOME_FIGURES_NOT_CITED",
            f"部分图片可能未在正文中引用 ({len(set(figure_refs))}/{figure_count})"
        ))

    # Check figure caption position
    # In markdown, figure captions should be below the figure: ![caption](path)
    has_caption_below = FIGURE_CAPTION_BELOW.search(content)
    has_caption_above = FIGURE_CAPTION_ABOVE.search(content)

    if has_caption_above and not has_caption_below:
        findings.append(_finding(
            "REVIEW", "figures", "FIGURE_CAPTION_ABOVE",
            "图题应在图片下方（CUMCM/MCM 规范要求图题在下）"
        ))
    elif not content.strip().startswith("!["):
        # In markdown, by default `![caption](path)` places caption as alt text
        # which renders below the image - this is correct
        pass

    # Check for 600 DPI and grayscale requirement
    findings.append(_finding(
        "REVIEW", "figures", "IMAGE_QUALITY_VERIFY",
        "请确认图片满足 600dpi、黑白可区分（使用线型+图例，非颜色）要求"
    ))

    return findings


def _check_references(content: str, spec: dict, competition: str) -> list[dict[str, str]]:
    """Check reference format compliance.

    REVIEW if:
    - Reference count is out of [min_count, max_count] range
    - Reference types don't match allowed types (CUMCM)
    - Chinese punctuation detected in references (CUMCM)
    """
    findings = []
    # Get the references section
    sections = _extract_sections(content)
    ref_section = None
    for sec in sections:
        if re.search(r"参考|reference|文献|bibliography", sec["section_id"], re.IGNORECASE):
            ref_section = sec["content"]
            break

    if not ref_section:
        findings.append(_finding(
            "REVIEW", "references", "NO_REFERENCE_SECTION",
            "未找到参考文献章节"
        ))
        return findings

    # Count reference entries (numbered list items or bracket-numbered)
    ref_entries = re.findall(r"(?:^\d+[\.\、\)]|\s*\[\d+\])", ref_section, re.MULTILINE)
    ref_count = len(ref_entries)

    min_refs = spec.get("min_count", 5)
    max_refs = spec.get("max_count", 10)

    if ref_count < min_refs:
        findings.append(_finding(
            "REVIEW", "references", "TOO_FEW_REFERENCES",
            f"参考文献 {ref_count} 篇，少于要求的 {min_refs}-{max_refs} 篇"
        ))
    elif ref_count > max_refs:
        findings.append(_finding(
            "REVIEW", "references", "TOO_MANY_REFERENCES",
            f"参考文献 {ref_count} 篇，超过建议的 {max_refs} 篇上限"
        ))

    # For CUMCM, check reference types [J]/[M]/[D]/[EB/OL]
    if competition == "CUMCM":
        allowed_types = set(spec.get("allowed_types", []))
        found_types = set()
        for m in REF_TYPE_PATTERN.finditer(ref_section):
            found_types.add(f"[{m.group(1)}]")
        if REF_EBOL_PATTERN.search(ref_section):
            found_types.add("[EB/OL]")

        unknown_types = found_types - allowed_types
        if unknown_types:
            findings.append(_finding(
                "REVIEW", "references", "UNKNOWN_REF_TYPE",
                f"参考文献中出现非标准类型: {', '.join(sorted(unknown_types))}。允许: {', '.join(sorted(allowed_types))}"
            ))

        # Check for Chinese punctuation in references (should use English punctuation)
        if CHINESE_REF_PUNCTUATION.search(ref_section):
            findings.append(_finding(
                "REVIEW", "references", "CHINESE_PUNCTUATION_IN_REF",
                "参考文献中使用了中文标点，应使用英文标点+空格格式"
            ))

    return findings


def _check_page_limit(content: str, spec: dict) -> list[dict[str, str]]:
    """Check that the paper body does not exceed the page limit.

    REVIEW if estimated body pages exceed the limit.
    """
    findings = []
    body_max_pages = spec.get("page", {}).get("body_max_pages", 20)

    # Remove abstract from body for counting
    abstract = _extract_abstract(content)
    body = content
    if abstract:
        # Find and remove the abstract section
        abs_match = ABSTRACT_SECTION.search(body)
        if abs_match:
            abs_start = abs_match.start()
            remaining = body[abs_match.end():]
            next_heading = SECTION_HEADING.search(remaining)
            if next_heading:
                abs_end = abs_match.end() + next_heading.start()
            else:
                # Try to find where the next heading would be after the abstract content
                abs_end = abs_match.end() + len(_extract_abstract(body))
            body = body[:abs_start] + body[abs_end:]

    estimated_pages = _count_pages(body)
    if estimated_pages > body_max_pages:
        findings.append(_finding(
            "REVIEW", "global", "BODY_OVER_PAGE_LIMIT",
            f"正文估计 {estimated_pages} 页，超过 {body_max_pages} 页限制"
        ))

    return findings


def _check_keywords(content: str, spec: dict, competition: str) -> list[dict[str, str]]:
    """Check abstract keyword count.

    REVIEW if keyword count is outside [min, max] range.
    """
    findings = []
    abstract = _extract_abstract(content)
    if not abstract:
        return findings

    # Look for keywords section in the abstract
    keyword_match = re.search(
        r"(关键词|Keywords|keywords)\s*[：:]\s*(.*?)(?:\n|$)",
        abstract, re.IGNORECASE
    )
    if not keyword_match:
        findings.append(_finding(
            "REVIEW", "abstract", "KEYWORDS_MISSING",
            "摘要中未找到关键词（格式：关键词：xxx；xxx；xxx）"
        ))
        return findings

    kw_min = spec.get("keywords_min", 3)
    kw_max = spec.get("keywords_max", 5)

    keywords_text = keyword_match.group(2)
    # Split by common delimiters: ；; , 、 space
    keywords = re.split(r"[；;；,，、\s]+", keywords_text.strip())
    keywords = [kw for kw in keywords if kw]

    if len(keywords) < kw_min:
        findings.append(_finding(
            "REVIEW", "abstract", "TOO_FEW_KEYWORDS",
            f"关键词 {len(keywords)} 个，少于要求的 {kw_min}-{kw_max} 个"
        ))
    elif len(keywords) > kw_max:
        findings.append(_finding(
            "REVIEW", "abstract", "TOO_MANY_KEYWORDS",
            f"关键词 {len(keywords)} 个，超过要求的 {kw_max} 个上限"
        ))

    return findings


def _finding(severity: str, section_id: str, code: str, detail: str) -> dict[str, str]:
    """Create a finding dictionary consistent with PaperConsistencyChecker format."""
    return {"severity": severity, "section_id": section_id, "code": code, "detail": detail}


# ---------------------------------------------------------------------------
# Main checker class
# ---------------------------------------------------------------------------

class PaperFormatChecker:
    """Deterministic format checker for math modeling competition papers.

    Checks markdown content against CUMCM (Chinese) or MCM (English) format
    rules. Produces BLOCK/REVIEW findings consistent with the
    ``PaperConsistencyChecker`` mechanism.

    Usage::

        checker = PaperFormatChecker()
        result = checker.check(content, competition="CUMCM")
        # result["gate"] is one of "BLOCK", "REVIEW", "PASS"
        # result["findings"] is a list of {severity, section_id, code, detail}
    """

    def __init__(self) -> None:
        self._config = _load_format_config()

    def check(self, content: str, competition: str = "CUMCM") -> dict[str, Any]:
        """Run all format checks on the given markdown content.

        Args:
            content: Markdown paper content to check.
            competition: Competition format to validate against ("CUMCM" or "MCM").

        Returns:
            A dict with ``gate``, ``findings``, ``competition``, and per-check detail.
        """
        if competition not in self._config["competitions"]:
            raise ValueError(
                f"Unknown competition '{competition}'. "
                f"Available: {list(self._config['competitions'].keys())}"
            )

        spec = self._config["competitions"][competition]
        findings: list[dict[str, str]] = []

        # Extract abstract
        abstract = _extract_abstract(content)

        # Run all checks
        if abstract:
            findings.extend(_check_abstract_violations(abstract, competition, spec["abstract"]))
            findings.extend(_check_abstract_page(abstract, content, spec["abstract"]))
            findings.extend(_check_keywords(content, spec["abstract"], competition))
        else:
            findings.append(_finding(
                "BLOCK", "abstract", "ABSTRACT_MISSING",
                "未找到摘要章节（需要以 # 摘要 或 # Summary 开头）"
            ))

        findings.extend(_check_three_line_tables(content, spec["three_line_table"]))
        findings.extend(_check_figures(content, spec["figure"]))
        findings.extend(_check_references(content, spec["references"], competition))
        findings.extend(_check_page_limit(content, spec))

        # Determine gate
        severities = {finding["severity"] for finding in findings}
        gate = "BLOCK" if "BLOCK" in severities else "REVIEW" if "REVIEW" in severities else "PASS"

        return {
            "schema_version": 1,
            "gate": gate,
            "competition": competition,
            "findings": findings,
            "findings_count": len(findings),
            "block_count": sum(1 for f in findings if f["severity"] == "BLOCK"),
            "review_count": sum(1 for f in findings if f["severity"] == "REVIEW"),
        }

    def check_file(self, path: Path | str, competition: str = "CUMCM") -> dict[str, Any]:
        """Run format checks on a markdown file.

        Args:
            path: Path to the markdown file.
            competition: Competition format to validate against.

        Returns:
            Check result dict with ``gate``, ``findings``, and ``file`` path.
        """
        path = Path(path)
        content = path.read_text(encoding="utf-8")
        result = self.check(content, competition)
        result["file"] = str(path)
        return result

    def get_competition_names(self) -> list[str]:
        """Return available competition names."""
        return list(self._config["competitions"].keys())

    def get_format_rules(self, competition: str) -> dict[str, Any]:
        """Return the format rules for a competition."""
        return self._config["competitions"].get(competition, {})

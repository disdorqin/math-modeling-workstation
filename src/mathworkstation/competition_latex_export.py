from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .paper_art_direction import PageCompositionPlan
from .paper_layout_ir import PaperLayoutIR, PaperLayoutIRBuilder


@dataclass(frozen=True)
class LatexExportResult:
    tex_path: Path
    asset_dir: Path
    figure_count: int
    table_count: int


class CompetitionLatexExporter:
    """Convert the evidence-locked Markdown draft into a self-contained CUMCM/MCM LaTeX paper.

    This is deliberately a document-layer transformation.  It never creates new
    claims, numbers, models, tables, or figures; it only typesets the already
    accepted paper content and copies referenced raster figures beside the TeX.
    """

    IMAGE_RE = re.compile(r"^!\[(?P<alt>.*?)\]\((?P<path>.*?)\)\s*$")
    HEADING_RE = re.compile(r"^(?P<level>#{1,4})\s+(?P<title>.+?)\s*$")

    def export(
        self,
        markdown_path: str | Path,
        output_tex: str | Path,
        *,
        competition: str = "CUMCM",
        control_number: str = "",
        composition_plan: PageCompositionPlan | dict[str, Any] | None = None,
    ) -> LatexExportResult:
        md_path = Path(markdown_path).resolve()
        tex_path = Path(output_tex).resolve()
        tex_path.parent.mkdir(parents=True, exist_ok=True)
        asset_dir = tex_path.parent / "figures"
        asset_dir.mkdir(parents=True, exist_ok=True)

        markdown = md_path.read_text(encoding="utf-8")
        language = "zh" if competition.upper().startswith("CUMCM") else "en"
        active_composition = (
            composition_plan
            if isinstance(composition_plan, PageCompositionPlan)
            else PageCompositionPlan.model_validate(composition_plan)
            if composition_plan is not None
            else None
        )
        layout_ir = PaperLayoutIRBuilder().build(markdown, composition_plan=active_composition)
        title = layout_ir.title
        body, figure_count, table_count = self._convert_ir(
            layout_ir,
            md_path=md_path,
            asset_dir=asset_dir,
            language=language,
        )
        tex = self._preamble(
            title=title,
            competition=competition,
            control_number=control_number,
            language=language,
        ) + body + "\n\\end{document}\n"
        tex_path.write_text(tex, encoding="utf-8")
        return LatexExportResult(tex_path, asset_dir, figure_count, table_count)

    def _document_title(self, lines: list[str]) -> str:
        for line in lines:
            match = self.HEADING_RE.match(line)
            if match and len(match.group("level")) == 1:
                return match.group("title").strip()
        return "Mathematical Modeling Paper"

    def _preamble(self, *, title: str, competition: str, control_number: str, language: str) -> str:
        is_zh = language == "zh"
        control_label = "Team Control Number"
        safe_title = _latex_inline(title)
        safe_control = _latex_inline(control_number or "__________")
        identity_line = "" if is_zh else rf"  {{\small {control_label}: {safe_control}}}\\[0.3em]"
        caption_names = r"\renewcommand{\figurename}{图}\renewcommand{\tablename}{表}" if is_zh else ""
        paper_option = "a4paper" if is_zh else "letterpaper"
        main_font = "Noto Serif SC" if is_zh else "Times New Roman"
        heading_font = "Microsoft YaHei" if is_zh else "Times New Roman"
        linebreak_setup = '\\XeTeXlinebreaklocale "zh"\n\\XeTeXlinebreakskip = 0pt plus 1pt' if is_zh else ""
        if is_zh:
            page_geometry = r"""% A4: national CUMCM hard rule requires every margin >= 2.5 cm.
\setlength{\textwidth}{16.0cm}
\setlength{\textheight}{23.7cm}
\setlength{\oddsidemargin}{-0.04cm}
\setlength{\evensidemargin}{-0.04cm}
\setlength{\topmargin}{-0.04cm}"""
        else:
            page_geometry = r"""% MCM: Letter paper with approximately 1-inch margins.
\setlength{\textwidth}{6.50in}
\setlength{\textheight}{9.00in}
\setlength{\oddsidemargin}{0in}
\setlength{\evensidemargin}{0in}
\setlength{\topmargin}{0in}"""
        return rf"""\documentclass[12pt,{paper_option}]{{article}}
\usepackage{{fontspec}}
\usepackage{{amsmath,amssymb,bm}}
\usepackage{{graphicx}}
\usepackage{{longtable,array}}
\setmainfont[AutoFakeBold=2.0,AutoFakeSlant=0.15]{{{main_font}}}
\newfontfamily\headingfont{{{heading_font}}}
{linebreak_setup}
\emergencystretch=2em
\linespread{{1.20}}
\setlength{{\tabcolsep}}{{2.2pt}}
{page_geometry}
\setlength{{\headheight}}{{0pt}}
\setlength{{\headsep}}{{0pt}}
\setlength{{\footskip}}{{0.9cm}}
\setlength{{\parindent}}{{2em}}
\setlength{{\parskip}}{{0.12em}}
\setlength{{\textfloatsep}}{{9pt plus 2pt minus 2pt}}
\setlength{{\floatsep}}{{7pt plus 2pt minus 2pt}}
\setlength{{\intextsep}}{{7pt plus 2pt minus 2pt}}
% Keep evidence figures close to the paragraph that interprets them.  A float-only
% page is permitted only when figures genuinely occupy most of the page; this
% avoids separating two medium evidence plots from all explanatory prose.
\renewcommand{{\topfraction}}{{0.88}}
\renewcommand{{\bottomfraction}}{{0.78}}
\renewcommand{{\textfraction}}{{0.10}}
\renewcommand{{\floatpagefraction}}{{0.72}}
\setcounter{{topnumber}}{{3}}
\setcounter{{bottomnumber}}{{2}}
\setcounter{{totalnumber}}{{4}}
\renewcommand{{\arraystretch}}{{1.15}}
\setlength{{\abovecaptionskip}}{{4pt}}
\setlength{{\belowcaptionskip}}{{2pt}}
{caption_names}
\newcommand{{\MathWSNeedspace}}[1]{{\par}}
\pagestyle{{plain}}
\begin{{document}}
\begin{{center}}
  {{\headingfont\fontsize{{18pt}}{{22pt}}\selectfont\bfseries {safe_title}}}\\[0.5em]
{identity_line}\end{{center}}
\vspace{{0.2em}}
"""

    def _convert_ir(
        self,
        layout_ir: PaperLayoutIR,
        *,
        md_path: Path,
        asset_dir: Path,
        language: str,
    ) -> tuple[str, int, int]:
        out: list[str] = []
        figure_count = 0
        table_count = 0
        skipped_title = False
        abstract_seen = False
        body_started = False
        references_mode = False

        for block in layout_ir.blocks:
            if block.kind == "heading":
                level = block.level
                text = block.text.strip()
                if level == 1 and not skipped_title:
                    skipped_title = True
                    continue
                if level == 1:
                    is_references = text.lower() in {"references", "reference", "bibliography"} or text in {"参考文献"}
                    if references_mode and not is_references:
                        out.append("\\normalsize")
                        references_mode = False
                    if is_references and not references_mode:
                        out.append("\\small")
                        references_mode = True
                if level == 1 and text in {"摘要", "Summary", "Abstract"}:
                    abstract_seen = True
                    out.extend(["\\begin{center}", "{\\headingfont\\fontsize{14pt}{18pt}\\selectfont\\bfseries " + _latex_inline(text) + "}", "\\end{center}"])
                elif level == 1 and text.lower() in {"contents", "table of contents"}:
                    if abstract_seen and not body_started:
                        out.append("\\clearpage")
                        body_started = True
                    out.extend(["\\tableofcontents", "\\clearpage"])
                elif level == 1:
                    if abstract_seen and not body_started:
                        out.append("\\clearpage")
                        body_started = True
                    if text.startswith("附录") or text.lower().startswith("appendix"):
                        out.append("\\clearpage")
                    out.append("\\MathWSNeedspace{6\\baselineskip}")
                    out.append("\\section*{\\headingfont " + _latex_inline(text) + "}")
                    out.append("\\addcontentsline{toc}{section}{" + _latex_inline(text) + "}")
                elif level == 2:
                    out.append("\\MathWSNeedspace{5\\baselineskip}")
                    out.append("\\subsection*{\\headingfont " + _latex_inline(text) + "}")
                else:
                    out.append("\\MathWSNeedspace{4\\baselineskip}")
                    out.append("\\subsubsection*{\\headingfont " + _latex_inline(text) + "}")
                continue

            if block.kind == "display_math":
                out.extend(["\\[", block.text, "\\]"])
                continue

            if block.kind == "figure":
                figure_count += 1
                copied = self._copy_image(md_path, block.path, asset_dir, figure_count)
                caption = self._clean_caption(block.alt, language=language)
                width = block.intent.width_fraction or 0.92
                height = block.intent.max_height_fraction or 0.43
                placement = block.intent.placement or "htbp"
                if placement == "inline":
                    out.extend(
                        [
                            "\\par\\medskip",
                            "\\begin{center}",
                            "\\begin{minipage}{0.98\\textwidth}",
                            "\\centering",
                            rf"\includegraphics[width={width:.2f}\textwidth,height={height:.2f}\textheight,keepaspectratio]{{figures/{_latex_path(copied.name)}}}",
                            "\\par\\smallskip",
                            rf"{{\small {_latex_inline(caption)}}}",
                            "\\end{minipage}",
                            "\\end{center}",
                            "\\medskip",
                        ]
                    )
                else:
                    out.extend(
                        [
                            rf"\begin{{figure}}[{placement}]",
                            "\\centering",
                            rf"\includegraphics[width={width:.2f}\textwidth,height={height:.2f}\textheight,keepaspectratio]{{figures/{_latex_path(copied.name)}}}",
                            rf"{{\small\caption{{{_latex_inline(caption)}}}}}",
                            "\\end{figure}",
                        ]
                    )
                continue

            if block.kind == "table":
                table_count += 1
                out.extend(self._table_to_latex(block.rows, table_count=table_count, language=language))
                continue

            if block.kind == "bullet_list":
                out.append("\\begin{itemize}")
                out.extend("\\item " + _latex_inline(item) for item in block.items)
                out.append("\\end{itemize}")
                continue

            if block.kind == "blank":
                out.append("")
                continue

            if block.kind == "paragraph":
                stripped = block.text.strip()
                if stripped.startswith("**") and stripped.endswith("**") and stripped.count("**") == 2:
                    out.append("\\noindent\\textbf{" + _latex_inline(stripped[2:-2].strip()) + "}\\par")
                else:
                    out.append(_latex_inline(block.text) + "\\par")

        return "\n".join(out) + "\n", figure_count, table_count

    def _convert_body(
        self,
        lines: list[str],
        *,
        md_path: Path,
        asset_dir: Path,
        language: str,
        composition_plan: PageCompositionPlan | None = None,
    ) -> tuple[str, int, int]:
        out: list[str] = []
        figure_count = 0
        table_count = 0
        index = 0
        skipped_title = False
        in_display_math = False
        abstract_seen = False
        body_started = False

        while index < len(lines):
            raw = lines[index]
            stripped = raw.strip()

            if stripped == "$$":
                out.append("\\[") if not in_display_math else out.append("\\]")
                in_display_math = not in_display_math
                index += 1
                continue
            if in_display_math:
                out.append(raw)
                index += 1
                continue

            heading = self.HEADING_RE.match(raw)
            if heading:
                level = len(heading.group("level"))
                text = heading.group("title").strip()
                if level == 1 and not skipped_title:
                    skipped_title = True
                    index += 1
                    continue
                if level == 1 and text in {"摘要", "Summary", "Abstract"}:
                    abstract_seen = True
                    out.extend(["\\begin{center}", "{\\headingfont\\fontsize{14pt}{18pt}\\selectfont\\bfseries " + _latex_inline(text) + "}", "\\end{center}"])
                elif level == 1:
                    if abstract_seen and not body_started:
                        out.append("\\clearpage")
                        body_started = True
                    if text.startswith("附录") or text.lower().startswith("appendix"):
                        out.append("\\clearpage")
                    out.append("\\MathWSNeedspace{6\\baselineskip}")
                    out.append("\\section*{\\headingfont " + _latex_inline(text) + "}")
                elif level == 2:
                    out.append("\\MathWSNeedspace{5\\baselineskip}")
                    out.append("\\subsection*{\\headingfont " + _latex_inline(text) + "}")
                else:
                    out.append("\\MathWSNeedspace{4\\baselineskip}")
                    out.append("\\subsubsection*{\\headingfont " + _latex_inline(text) + "}")
                index += 1
                continue

            image = self.IMAGE_RE.match(raw)
            if image:
                figure_count += 1
                copied = self._copy_image(md_path, image.group("path"), asset_dir, figure_count)
                caption = self._clean_caption(image.group("alt"), language=language)
                composition = composition_plan.figure_for_path(image.group("path")) if composition_plan is not None else None
                width = composition.width_fraction if composition is not None else 0.92
                height = composition.max_height_fraction if composition is not None else 0.43
                placement = composition.placement if composition is not None else "htbp"
                out.extend(
                    [
                        rf"\begin{{figure}}[{placement}]",
                        "\\centering",
                        rf"\includegraphics[width={width:.2f}\textwidth,height={height:.2f}\textheight,keepaspectratio]{{figures/{_latex_path(copied.name)}}}",
                        rf"{{\small\caption{{{_latex_inline(caption)}}}}}",
                        "\\end{figure}",
                    ]
                )
                index += 1
                continue

            if stripped.startswith("|") and index + 1 < len(lines) and _is_markdown_separator(lines[index + 1]):
                table_lines: list[str] = []
                while index < len(lines) and lines[index].strip().startswith("|"):
                    table_lines.append(lines[index])
                    index += 1
                table_count += 1
                out.extend(self._table_to_latex(table_lines, table_count=table_count, language=language))
                continue

            if stripped.startswith("- "):
                items: list[str] = []
                while index < len(lines) and lines[index].strip().startswith("- "):
                    items.append(lines[index].strip()[2:].strip())
                    index += 1
                out.append("\\begin{itemize}")
                out.extend("\\item " + _latex_inline(item) for item in items)
                out.append("\\end{itemize}")
                continue

            if not stripped:
                out.append("")
                index += 1
                continue

            if stripped.startswith("**") and stripped.endswith("**") and stripped.count("**") == 2:
                out.append("\\noindent\\textbf{" + _latex_inline(stripped[2:-2].strip()) + "}\\par")
            else:
                out.append(_latex_inline(raw) + "\\par")
            index += 1

        return "\n".join(out) + "\n", figure_count, table_count

    def _copy_image(self, md_path: Path, raw_path: str, asset_dir: Path, number: int) -> Path:
        source = (md_path.parent / raw_path).resolve()
        if not source.is_file():
            raise FileNotFoundError(f"paper figure missing: {source}")
        suffix = source.suffix.lower() or ".png"
        destination = asset_dir / f"figure-{number:02d}{suffix}"
        shutil.copy2(source, destination)
        return destination

    def _clean_caption(self, value: str, *, language: str) -> str:
        text = " ".join(value.split())
        if language == "zh":
            text = re.sub(r"^图\s*\d+\s*[：:.]?\s*", "", text)
        else:
            text = re.sub(r"^Figure\s*\d+\s*[：:.]?\s*", "", text, flags=re.IGNORECASE)
        return text.strip() or ("证据图" if language == "zh" else "Evidence figure")

    def _table_to_latex(self, rows: list[str], *, table_count: int, language: str) -> list[str]:
        parsed = [_split_markdown_row(row) for row in rows]
        if len(parsed) < 3:
            return []
        headers = parsed[0]
        data_rows = parsed[2:]
        columns = max(1, len(headers))
        width = min(0.23, max(0.082, 0.82 / columns))
        colspec = "".join(
            rf">{{\raggedright\arraybackslash}}p{{{width:.3f}\textwidth}}"
            for _ in range(columns)
        )
        continuation = "续表" if language == "zh" else "continued"
        row_end = r" \\"
        table_font = r"\scriptsize" if columns >= 6 else r"\small"
        output = [
            r"\begingroup",
            table_font,
            r"\sloppy",
            rf"\begin{{longtable}}{{{colspec}}}",
            r"\hline",
            " & ".join(_latex_table_cell(value) for value in headers) + row_end,
            r"\hline",
            r"\endfirsthead",
            rf"\multicolumn{{{columns}}}{{c}}{{\small {continuation}}}" + row_end,
            r"\hline",
            " & ".join(_latex_table_cell(value) for value in headers) + row_end,
            r"\hline",
            r"\endhead",
            r"\hline",
            rf"\multicolumn{{{columns}}}{{r}}{{\small {continuation}}}" + row_end,
            r"\endfoot",
            r"\hline",
            r"\endlastfoot",
        ]
        for row in data_rows:
            padded = row + [""] * (columns - len(row))
            output.append(" & ".join(_latex_table_cell(value) for value in padded[:columns]) + row_end)
        output.extend([r"\end{longtable}", r"\endgroup"])
        return output


def _is_markdown_separator(line: str) -> bool:
    cells = _split_markdown_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def _split_markdown_row(line: str) -> list[str]:
    text = line.strip().strip("|")
    return [cell.strip() for cell in text.split("|")]


def _latex_table_cell(text: str) -> str:
    """Escape a table cell and add legal line-break points for long identifiers."""
    value = str(text)
    escaped = _latex_inline(value)
    escaped = escaped.replace(r"\_", r"\_\allowbreak{}")

    def break_long_token(match: re.Match[str]) -> str:
        token = match.group(0)
        chunks = [token[index:index + 7] for index in range(0, len(token), 7)]
        return r"\allowbreak{}".join(chunks)

    return re.sub(r"[A-Za-z0-9]{10,}", break_long_token, escaped)


def _latex_inline(text: str) -> str:
    """Escape prose while preserving $...$ inline math and **bold** spans."""
    if not text:
        return ""
    math_parts = re.split(r"(\$[^$]+\$)", text)
    output: list[str] = []
    for part in math_parts:
        if part.startswith("$") and part.endswith("$"):
            output.append(part)
            continue
        escaped = _escape_latex(part)
        escaped = re.sub(r"\\textbackslash\{\}\\textbackslash\{\}([^\n]+?)\\textbackslash\{\}\\textbackslash\{\}", r"\\textbf{\1}", escaped)
        # Lightweight Markdown emphasis conversion is easier and safer before escaping.
        if "*" in part:
            escaped = _escape_latex_with_bold(part)
        output.append(escaped)
    return "".join(output)


def _escape_latex_with_bold(text: str) -> str:
    parts = re.split(r"(\*\*[^*]+\*\*|\*[^*]+\*)", text)
    output: list[str] = []
    for part in parts:
        if part.startswith("**") and part.endswith("**"):
            output.append("\\textbf{" + _escape_latex(part[2:-2]) + "}")
        elif part.startswith("*") and part.endswith("*"):
            output.append("\\emph{" + _escape_latex(part[1:-1]) + "}")
        else:
            output.append(_escape_latex(part))
    return "".join(output)


def _escape_latex(text: str) -> str:
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    return "".join(replacements.get(char, char) for char in text)


def _latex_path(value: str) -> str:
    return value.replace("\\", "/")

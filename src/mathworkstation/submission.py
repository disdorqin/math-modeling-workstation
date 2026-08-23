from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .io_utils import atomic_write_json, atomic_write_text, now_iso


@dataclass(frozen=True)
class SubmissionProfile:
    name: str
    document_class: str = "article"
    paper_title: str = "数学建模论文"
    max_pages: int | None = None
    required_sections: tuple[str, ...] = ()


# Language aliases for required section names.
# When a Chinese-language paper is submitted under an English-named profile (MCM/ICM),
# the preflight check should also recognise Chinese section headings.
_SECTION_CN_ALIASES: dict[str, str] = {
    "Abstract": "摘要",
    "Model": "模型建立",
    "Results": "结果分析",
    "Conclusion": "结论",
}


PROFILES = {
    "SM": SubmissionProfile("SM", paper_title="数学建模论文", required_sections=("摘要", "模型建立", "结果分析", "结论")),
    "CUMCM": SubmissionProfile("CUMCM", paper_title="数学建模论文", required_sections=("摘要", "模型建立", "结果分析", "结论")),
    "MCM": SubmissionProfile("MCM", paper_title="Mathematical Modeling Paper", required_sections=("Abstract", "Model", "Results", "Conclusion")),
    "ICM": SubmissionProfile("ICM", paper_title="Mathematical Modeling Paper", required_sections=("Abstract", "Model", "Results", "Conclusion")),
}


class SubmissionService:
    """Converts the accepted paper and records deterministic submission checks."""

    def __init__(self, cases: CaseManager, artifacts: ArtifactRegistry) -> None:
        self.cases = cases
        self.artifacts = artifacts

    def prepare(self, case_id: str, profile_name: str = "SM", compile_pdf: bool = False) -> dict[str, Any]:
        root = self.cases.case_root(case_id)
        # Accept C-type competition spellings (MCM-C / MCM_C) by falling back
        # to the base family profile when the exact name is not registered.
        normalized = profile_name.upper()
        profile = PROFILES.get(normalized)
        if profile is None:
            base = normalized.removesuffix("-C").removesuffix("_C").removesuffix("C")
            profile = PROFILES.get(base)
        if profile is None:
            raise ValueError(f"unsupported submission profile: {profile_name}")
        paper_path = root / "paper" / "final.md"
        if not paper_path.is_file():
            raise FileNotFoundError("paper/final.md is required")
        markdown = paper_path.read_text(encoding="utf-8-sig")
        clean_markdown = sanitize_submission_markdown(markdown)
        clean_path = root / "paper" / "markdown" / "submission.md"
        atomic_write_text(clean_path, clean_markdown)
        clean_artifact = self.artifacts.register_existing(case_id, clean_path.relative_to(root).as_posix(), "submission_markdown", "python")
        latex = markdown_to_latex(clean_markdown, profile)
        latex_path = root / "paper" / "latex" / "main.tex"
        atomic_write_text(latex_path, latex)
        latex_artifact = self.artifacts.register_existing(case_id, latex_path.relative_to(root).as_posix(), "submission_latex", "python", upstream=[clean_artifact["artifact_id"]])
        report = self.preflight(case_id, clean_markdown, latex, profile)
        report_path = root / "review" / "structural" / "submission-preflight.json"
        atomic_write_json(report_path, report)
        report_artifact = self.artifacts.register_existing(case_id, report_path.relative_to(root).as_posix(), "submission_preflight", "python", upstream=[latex_artifact["artifact_id"]])
        result: dict[str, Any] = {"profile": profile.name, "markdown_artifact_id": clean_artifact["artifact_id"], "latex_artifact_id": latex_artifact["artifact_id"], "preflight_artifact_id": report_artifact["artifact_id"], "preflight": report}
        if compile_pdf and report["gate"] == "PASS":
            result["compile"] = self.compile(case_id, profile)
        return result

    def preflight(self, case_id: str, markdown: str, latex: str, profile: SubmissionProfile) -> dict[str, Any]:
        root = self.cases.case_root(case_id)
        findings: list[dict[str, str]] = []
        for section in profile.required_sections:
            if section not in markdown:
                cn_alias = _SECTION_CN_ALIASES.get(section)
                if cn_alias is None or cn_alias not in markdown:
                    findings.append({"code": "REQUIRED_SECTION_MISSING", "severity": "P1", "message": section})
        if re.search(r"\[(?:CLAIM|FIGURE|ARTIFACT|RESULT)[-_][A-Za-z0-9]+\]", markdown, re.I):
            findings.append({"code": "INTERNAL_REFERENCE_LEAK", "severity": "P1", "message": "internal evidence marker remains in final paper"})
        if "[SECTION_DRAFT_PENDING]" in markdown or "[NEEDS_EVIDENCE]" in markdown:
            findings.append({"code": "P1_PLACEHOLDER", "severity": "P1", "message": "paper contains an unresolved placeholder"})
        if re.search(r"\\cite\{[^}]*\}\s*\\cite\{", latex):
            findings.append({"code": "DUPLICATE_CITATION", "severity": "P2", "message": "adjacent duplicate citations"})
        for image in re.findall(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}", latex):
            # Artifact paths are stored POSIX-style; `Path` joins them correctly on
            # every platform. Rewriting separators to backslashes collapsed the whole
            # relative path into one filename on Linux and macOS, so every embedded
            # figure was reported missing.
            image_path = root.joinpath(*PurePosixPath(image).parts)
            if not image_path.suffix:
                image_path = image_path.with_suffix(".png")
            if not image_path.is_file():
                findings.append({"code": "FIGURE_MISSING", "severity": "P1", "message": image})
        return {"schema_version": 1, "case_id": case_id, "profile": profile.name, "gate": "BLOCK" if findings else "PASS", "findings": findings, "checked_at": now_iso()}

    def compile(self, case_id: str, profile: SubmissionProfile) -> dict[str, Any]:
        root = self.cases.case_root(case_id)
        latex_dir = root / "paper" / "latex"
        executable = shutil.which("latexmk") or shutil.which("pdflatex")
        if not executable:
            payload = {"status": "BLOCKED", "code": "LATEX_ENGINE_MISSING", "message": "latexmk or pdflatex is not installed"}
            path = root / "paper" / "latex" / "compile-result.json"
            atomic_write_json(path, payload)
            artifact = self.artifacts.register_existing(case_id, path.relative_to(root).as_posix(), "submission_compile_result", "python")
            return {**payload, "artifact_id": artifact["artifact_id"]}
        command = [executable, "-interaction=nonstopmode", "-halt-on-error", "main.tex"] if Path(executable).name.lower() == "pdflatex.exe" else [executable, "-pdf", "-interaction=nonstopmode", "main.tex"]
        completed = subprocess.run(command, cwd=latex_dir, text=True, capture_output=True, timeout=120, check=False)
        log_path = latex_dir / "compile.log"
        atomic_write_text(log_path, completed.stdout + "\n" + completed.stderr)
        pdf_path = latex_dir / "main.pdf"
        payload = {"status": "PASS" if completed.returncode == 0 and pdf_path.is_file() else "BLOCKED", "returncode": completed.returncode, "pdf_path": pdf_path.relative_to(root).as_posix() if pdf_path.is_file() else None, "log_path": log_path.relative_to(root).as_posix()}
        result_path = latex_dir / "compile-result.json"
        atomic_write_json(result_path, payload)
        artifact = self.artifacts.register_existing(case_id, result_path.relative_to(root).as_posix(), "submission_compile_result", "python")
        return {**payload, "artifact_id": artifact["artifact_id"]}


IMAGE_LINE = re.compile(r"!\[([^]]*)\]\(([^)]+)\)")


def markdown_to_latex(markdown: str, profile: SubmissionProfile) -> str:
    lines = markdown.replace("\r\n", "\n").splitlines()
    output = [f"\\documentclass{{{profile.document_class}}}", "\\usepackage[UTF8]{ctex}", "\\usepackage{amsmath,amssymb,graphicx,booktabs,hyperref}", "\\begin{document}"]
    for line in lines:
        if line.startswith("# "):
            output.append(f"\\title{{{_escape(line[2:].strip())}}}")
            output.append("\\maketitle")
        elif line.startswith("## "):
            output.append(f"\\section{{{_escape(line[3:].strip())}}}")
        elif line.startswith("### "):
            output.append(f"\\subsection{{{_escape(line[4:].strip())}}}")
        elif not line.strip():
            output.append("")
        elif IMAGE_LINE.match(line.strip()):
            match = IMAGE_LINE.match(line.strip())
            assert match is not None
            caption, target = match.group(1), match.group(2)
            output.append("\\begin{figure}[htbp]")
            output.append("\\centering")
            output.append(f"\\includegraphics[width=0.85\\textwidth]{{{target}}}")
            if caption.strip():
                output.append(f"\\caption{{{_escape(caption.strip())}}}")
            output.append("\\end{figure}")
        elif line.startswith("- "):
            output.append("\\begin{itemize}" if not output or output[-1] != "\\begin{itemize}" else "")
            output.append(f"\\item {_inline(line[2:])}")
        else:
            output.append(_inline(line))
    if "\\begin{itemize}" in output:
        output.append("\\end{itemize}")
    output.append("\\end{document}")
    return "\n".join(output) + "\n"


def sanitize_submission_markdown(markdown: str) -> str:
    """Remove internal evidence anchors from the user-facing manuscript copy."""
    cleaned = re.sub(r"<!-- data-figure-id=\"[^\"]*\" -->", "", markdown)
    cleaned = re.sub(r"\[(?:claim|figure|artifact|result|table|answer-subproblem)-[A-Za-z0-9_-]+\]", "", markdown, flags=re.I)
    cleaned = re.sub(r"\[数学建模研究工作流总览\]|\[数值变量分布\]|\[数值变量相关性热力图\]|\[目标变量[^]]*\]|\[候选模型[^]]*\]|\[Baseline[^]]*\]|\[模型样本比例[^]]*\]", "", cleaned)
    return re.sub(r"[ \t]{2,}", " ", cleaned)


def _inline(value: str) -> str:
    protected: list[str] = []
    def keep(match: re.Match[str]) -> str:
        protected.append(match.group(0))
        return f"@@MATH{len(protected)-1}@@"
    value = re.sub(r"\$[^$]+\$|\\\[[\s\S]*?\\\]", keep, value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"\\textbf{\1}", value)
    value = _escape(value)
    for index, item in enumerate(protected):
        value = value.replace(f"@@MATH{index}@@", item)
    return value


def _escape(value: str) -> str:
    return re.sub(r"([{}%&_#])", r"\\\1", value)

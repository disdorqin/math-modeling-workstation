from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .claims import ClaimRegistry
from .figure_registry import FigureRegistry
from .io_utils import atomic_write_json, atomic_write_text, now_iso, read_json
from .paper_outline import section_contract


CLAIM_REF = re.compile(r"claim-[a-f0-9]{12}")
FIGURE_REF = re.compile(r"figure-[a-f0-9]{12}")
NUMBER = re.compile(r"(?<![A-Za-z0-9_-])[-+]?\d+(?:\.\d+)?%?")
#: Dates / years / case-ids are metadata, not empirical results — scanning them
#: as unattributed numbers produces pure false positives (e.g. the date embedded
#: in a case id like 20260804-SM-...). These are stripped before the number scan.
DATE_OR_YEAR = re.compile(r"\b(?:19|20)\d{2}(?:[-\d]{0,8})\b")
#: Structural numbering (assumption 1, constraint 2, step 3, condition 4, 假设 1,
#: 约束 2, 条件 3 ...) is enumeration, not an empirical value — likewise stripped
#: before the unattributed-number scan.
STRUCTURAL_ORDINAL = re.compile(
    r"(?:假设|约束|条件|步骤|阶段|问题|问|条件|编号|第)\s*\d+|\b(?:assumption|constraint|step|condition|phase|item|section|q)\s*\d+\b",
    re.IGNORECASE,
)
PLACEHOLDER = re.compile(r"\[(?:SECTION_DRAFT_PENDING|NEEDS_EVIDENCE|TODO|TBD)\]")
# Inline and display math carry structural digits (subscripts, exponents, norms
# such as $L_2$ or $\lVert\beta\rVert_1$) that are notation, not empirical
# results. Scanning them for unattributed numbers produces pure false positives,
# so math spans are removed before the number scan.
MATH_SPAN = re.compile(
    r"\$\$.*?\$\$|\$[^$\n]*\$|\\begin\{[^}]*\}.*?\\end\{[^}]*\}",
    re.DOTALL,
)
INTERNAL_ARTIFACT_REF = re.compile(r"\bartifact-[a-f0-9]{12}\b")
BOILERPLATE = "本节暂无已登记证据"


class PaperConsistencyChecker:
    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        claims: ClaimRegistry,
        figures: FigureRegistry,
        strict: bool = False,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.claims = claims
        self.figures = figures
        self.strict = strict

    def check(self, case_id: str) -> dict[str, Any]:
        root = self.cases.case_root(case_id)
        manifest_path = root / "paper" / "sections" / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError("paper sections manifest not found")
        manifest = read_json(manifest_path)
        known_claims = {item["claim_id"]: item for item in self.claims.list_claims(case_id)}
        known_figures = {item["figure_id"]: item for item in self.figures.list_figures(case_id)}
        findings: list[dict[str, Any]] = []
        section_results: list[dict[str, Any]] = []
        for section in manifest["sections"]:
            section_id = section["section_id"]
            context = read_json(root / "paper" / "sections" / section_id / "context.json")
            draft_path = root / "paper" / "sections" / section_id / "draft.md"
            content = draft_path.read_text(encoding="utf-8")
            allowed_claim_ids = {item["claim_id"] for item in context["allowed_claims"]}
            allowed_figure_ids = {item["figure_id"] for item in context["allowed_figures"]}
            cited_claims = set(CLAIM_REF.findall(content))
            cited_figures = set(FIGURE_REF.findall(content))
            placeholders = PLACEHOLDER.findall(content)
            if self.strict:
                missing_contracts = [
                    "/".join(group)
                    for group in section_contract(section_id).get("required_any", [])
                    if not any(token in content for token in group)
                ]
                if missing_contracts:
                    findings.append(_finding("BLOCK", section_id, "SECTION_CONTRACT_MISSING", "; ".join(missing_contracts)))
            if self.strict and not content.lstrip().startswith("#"):
                findings.append(_finding("BLOCK", section_id, "SECTION_HEADING_MISSING", ""))
            if self.strict and section_id in {"model_construction", "model_solution"}:
                if "$" not in content and "\\begin{" not in content:
                    findings.append(_finding("BLOCK", section_id, "MODEL_FORMULA_MISSING", ""))
            body_for_number_scan = "\n".join(
                line for line in content.splitlines() if not line.lstrip().startswith("#")
            )
            body_for_number_scan = DATE_OR_YEAR.sub(" ", body_for_number_scan)
            body_for_number_scan = STRUCTURAL_ORDINAL.sub(" ", body_for_number_scan)
            numbers = NUMBER.findall(MATH_SPAN.sub(" ", body_for_number_scan))
            for claim_id in sorted(cited_claims):
                if claim_id not in known_claims:
                    findings.append(_finding("BLOCK", section_id, "UNKNOWN_CLAIM", claim_id))
                elif claim_id not in allowed_claim_ids:
                    findings.append(_finding("BLOCK", section_id, "CLAIM_OUT_OF_SCOPE", claim_id))
                elif known_claims[claim_id]["status"] != "VERIFIED":
                    findings.append(_finding("BLOCK", section_id, "CLAIM_NOT_VERIFIED", claim_id))
            for figure_id in sorted(cited_figures):
                if figure_id not in known_figures:
                    findings.append(_finding("BLOCK", section_id, "UNKNOWN_FIGURE", figure_id))
                elif figure_id not in allowed_figure_ids:
                    findings.append(_finding("BLOCK", section_id, "FIGURE_OUT_OF_SCOPE", figure_id))
                else:
                    artifact = self.artifacts.get(case_id, known_figures[figure_id]["artifact_id"])
                    if not artifact.get("paper_eligible", False):
                        findings.append(_finding("BLOCK", section_id, "FIGURE_NOT_PAPER_READY", figure_id))
            for placeholder in placeholders:
                findings.append(_finding("BLOCK", section_id, "PLACEHOLDER_REMAINS", placeholder))
            if numbers and not cited_claims and section_id not in {"notation", "references"}:
                findings.append(
                    _finding(
                        "REVIEW",
                        section_id,
                        "UNATTRIBUTED_NUMBERS",
                        ", ".join(numbers[:10]),
                    )
                )
            if any("synthetic_data_claim" in claim.get("restrictions", []) for claim in context["allowed_claims"]):
                if "SYNTHETIC" not in content.upper() and "合成" not in content:
                    findings.append(_finding("BLOCK", section_id, "SYNTHETIC_DISCLOSURE_MISSING", ""))
            if self.strict and context["allowed_figures"] and not cited_figures:
                findings.append(_finding("BLOCK", section_id, "FIGURE_CITATION_MISSING", ""))
            section_results.append(
                {
                    "section_id": section_id,
                    "cited_claim_ids": sorted(cited_claims),
                    "cited_figure_ids": sorted(cited_figures),
                    "number_tokens": numbers,
                    "placeholders": placeholders,
                }
            )
        integrity = self.artifacts.verify(case_id)
        if not integrity["valid"]:
            findings.append(_finding("BLOCK", "global", "ARTIFACT_INTEGRITY_FAILED", str(integrity)))
        if self.strict:
            paper_text = "\n".join(
                (root / "paper" / "sections" / item["section_id"] / "draft.md").read_text(encoding="utf-8")
                for item in manifest["sections"]
            )
            internal_refs = sorted(set(INTERNAL_ARTIFACT_REF.findall(paper_text)))
            if internal_refs:
                findings.append(_finding("BLOCK", "global", "INTERNAL_ARTIFACT_REFERENCE", ", ".join(internal_refs)))
            boilerplate_count = paper_text.count(BOILERPLATE)
            if boilerplate_count:
                findings.append(_finding("BLOCK", "global", "REPEATED_BOILERPLATE", str(boilerplate_count)))
        bib_path = root / "paper" / "references" / "references.bib"
        citation_report_path = root / "review" / "citation" / "citation_verification.json"
        if bib_path.is_file() and bib_path.read_text(encoding="utf-8").strip():
            if not citation_report_path.is_file():
                findings.append(_finding("BLOCK", "references", "CITATION_VERIFICATION_MISSING", ""))
            else:
                citation_report = read_json(citation_report_path)
                missing = [item["doi"] for item in citation_report.get("results", []) if not item.get("exists")]
                if missing:
                    findings.append(_finding("BLOCK", "references", "CITATION_NOT_VERIFIED", ", ".join(missing)))
        severities = {finding["severity"] for finding in findings}
        gate = "BLOCK" if "BLOCK" in severities else "REVIEW" if "REVIEW" in severities else "PASS"
        report = {
            "schema_version": 1,
            "case_id": case_id,
            "gate": gate,
            "findings": findings,
            "sections": section_results,
            "artifact_integrity": integrity,
            "generated_at": now_iso(),
        }
        output_path = root / "review" / "consistency" / "paper_consistency.json"
        markdown_path = root / "review" / "consistency" / "paper_consistency.md"
        atomic_write_json(output_path, report)
        atomic_write_text(markdown_path, _render_report(report))
        report_artifact = self.artifacts.register_existing(
            case_id,
            output_path.relative_to(root).as_posix(),
            "paper_consistency_report",
            "python",
            upstream=[manifest["outline_artifact_id"]],
            paper_eligible=gate == "PASS",
        )
        return {"report": report, "report_artifact_id": report_artifact["artifact_id"]}


def _finding(severity: str, section_id: str, code: str, detail: str) -> dict[str, str]:
    return {"severity": severity, "section_id": section_id, "code": code, "detail": detail}


def _render_report(report: dict[str, Any]) -> str:
    findings = "\n".join(
        f"- **{item['severity']}** `{item['section_id']}` `{item['code']}` {item['detail']}"
        for item in report["findings"]
    ) or "- 未发现一致性问题。"
    return (
        "# 论文一致性检查\n\n"
        f"- Gate：**{report['gate']}**\n"
        f"- 检查章节：`{len(report['sections'])}`\n\n"
        "## Findings\n\n"
        f"{findings}\n"
    )

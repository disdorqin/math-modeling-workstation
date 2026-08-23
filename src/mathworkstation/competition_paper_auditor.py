from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .c_problem_paper_profiles import CProblemPaperProfileRegistry, profile_structure_findings
from .excellent_paper_comparator import ExcellentPaperComparator, VALID_FOCUS
from .io_utils import atomic_write_json, now_iso
from .narrative_graph import NarrativeGraph
from .paper_humanization import PaperHumanizationAdapter


DefectType = Literal["DOCUMENT", "RESEARCH"]
Severity = Literal["BLOCK", "REVIEW"]
AuditGate = Literal["PASS", "REVIEW", "BLOCK"]

_INTERNAL_ID_PATTERNS = (
    re.compile(r"\bartifact-[A-Za-z0-9_-]+\b", re.IGNORECASE),
    re.compile(r"\bresult-[A-Za-z0-9_-]+\b", re.IGNORECASE),
    re.compile(r"\btable-[A-Za-z0-9_-]+\b", re.IGNORECASE),
    re.compile(r"\bclaim-[A-Za-z0-9_-]+\b", re.IGNORECASE),
    re.compile(r"\bfigure-[A-Za-z0-9_-]+\b", re.IGNORECASE),
)


class PaperAuditFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    defect_type: DefectType
    severity: Severity
    code: str
    message: str
    section: str = "global"
    subproblem_id: str | None = None
    repair_phase: str | None = None
    ref_years: list[int] = Field(default_factory=list)
    source: str


class CompetitionPaperAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str | None = None
    gate: AuditGate
    findings: list[PaperAuditFinding]
    document_defects: int
    research_defects: int
    block_count: int
    review_count: int
    reference_papers_count: int
    reference_note: str
    profile_id: str | None = None
    checked_at: str


class CompetitionPaperAuditor:
    """Competition-oriented audit over paper text + accepted Research State.

    The excellent-paper library currently contains extracted summaries, not
    verified full texts. Their recurring strong points are therefore advisory
    priors only. Hard BLOCK findings come from traceability/research invariants
    or obvious document contamination, never from the summary corpus alone.
    """

    def __init__(self, ref_config_dir: Path | None = None) -> None:
        self.comparator = ExcellentPaperComparator(ref_config_dir)
        self.paper_profiles = CProblemPaperProfileRegistry()

    def audit(
        self,
        paper_text: str,
        narrative: NarrativeGraph | None = None,
        *,
        case_id: str | None = None,
        competition: str | None = None,
    ) -> CompetitionPaperAssessment:
        findings: list[PaperAuditFinding] = []
        paper_profile = self.paper_profiles.resolve(competition) if competition else None
        if narrative is not None:
            findings.extend(self._research_findings(narrative))
            findings.extend(self._coverage_findings(paper_text, narrative))
            findings.extend(self._domain_pollution_findings(paper_text, narrative))
            findings.extend(self._abstract_findings(paper_text, narrative))
        findings.extend(self._internal_id_findings(paper_text))
        findings.extend(self._reference_findings(paper_text))
        findings.extend(self._presentation_findings(paper_text))
        findings.extend(self._excellent_summary_findings(paper_text))
        if paper_profile is not None:
            for item in profile_structure_findings(paper_text, paper_profile):
                findings.append(
                    PaperAuditFinding(
                        defect_type="DOCUMENT",
                        severity=(
                            "BLOCK"
                            if item["code"] == "COMPETITION_PROFILE_CROSS_CONTAMINATION"
                            else "REVIEW"
                        ),
                        code=item["code"],
                        message=item["message"],
                        section=item["section"],
                        source="c_problem_paper_profile",
                    )
                )
        findings = _dedupe(findings)

        severities = {item.severity for item in findings}
        gate: AuditGate = "BLOCK" if "BLOCK" in severities else "REVIEW" if findings else "PASS"
        stats = self.comparator.stats()
        return CompetitionPaperAssessment(
            case_id=case_id,
            gate=gate,
            findings=findings,
            document_defects=sum(item.defect_type == "DOCUMENT" for item in findings),
            research_defects=sum(item.defect_type == "RESEARCH" for item in findings),
            block_count=sum(item.severity == "BLOCK" for item in findings),
            review_count=sum(item.severity == "REVIEW" for item in findings),
            reference_papers_count=int(stats.get("total_papers", 0)),
            reference_note=(
                "excellent_c7 entries are extracted summaries used as structural/narrative priors; "
                "they are not treated as full-paper external benchmark evidence"
            ),
            profile_id=(paper_profile.profile_id if paper_profile is not None else None),
            checked_at=now_iso(),
        )

    def persist(
        self,
        cases: Any,
        artifacts: Any,
        case_id: str,
        assessment: CompetitionPaperAssessment,
        *,
        source_artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        root = cases.case_root(case_id)
        path = root / "review" / "competition" / "paper_assessment.json"
        atomic_write_json(path, assessment.model_dump(mode="json"))
        artifact = artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "competition_paper_assessment",
            "competition_paper_auditor",
            upstream=list(source_artifact_ids or []),
            paper_eligible=False,
        )
        return {"assessment": assessment, "artifact": artifact}

    def _research_findings(self, narrative: NarrativeGraph) -> list[PaperAuditFinding]:
        findings: list[PaperAuditFinding] = []
        if narrative.research_gate != "PASS":
            findings.append(
                PaperAuditFinding(
                    defect_type="RESEARCH",
                    severity="BLOCK",
                    code="RESEARCH_GATE_NOT_PASS",
                    message=f"Research State gate is {narrative.research_gate}; paper generation must stop.",
                    repair_phase="problem_graph",
                    source="narrative_graph",
                )
            )
        for node in narrative.nodes:
            if node.gate != "PASS":
                phase = _repair_phase(node.blockers)
                findings.append(
                    PaperAuditFinding(
                        defect_type="RESEARCH",
                        severity="BLOCK",
                        code="NARRATIVE_NODE_BLOCKED",
                        message=f"{node.subproblem_id} cannot enter the paper: {', '.join(node.blockers)}",
                        subproblem_id=node.subproblem_id,
                        repair_phase=phase,
                        source="narrative_graph",
                    )
                )
            elif node.role == "RESEARCH" and node.validation_gate == "REVIEW":
                findings.append(
                    PaperAuditFinding(
                        defect_type="RESEARCH",
                        severity="REVIEW",
                        code="VALIDATION_REVIEW_REMAINS",
                        message=f"{node.subproblem_id} validation is REVIEW; robustness should be strengthened before competition polish.",
                        subproblem_id=node.subproblem_id,
                        repair_phase="validation",
                        source="narrative_graph",
                    )
                )
        return findings

    def _coverage_findings(self, text: str, narrative: NarrativeGraph) -> list[PaperAuditFinding]:
        findings: list[PaperAuditFinding] = []
        lowered = text.lower()
        for index, node in enumerate(narrative.nodes, start=1):
            question_markers = (
                f"question {index}",
                f"problem {index}",
                f"part {index}",
                f"问题{index}",
                f"问题 {index}",
            )
            result_markers = _result_markers(node)
            method_tokens = _method_tokens(node.method)
            question_present = any(marker.lower() in lowered for marker in question_markers)
            evidence_present = any(marker in lowered for marker in result_markers) if result_markers else node.role == "SYNTHESIS"
            method_present = any(token in lowered for token in method_tokens)
            if not question_present and not (method_present and evidence_present):
                findings.append(
                    PaperAuditFinding(
                        defect_type="DOCUMENT",
                        severity="BLOCK",
                        code="SUBPROBLEM_NARRATIVE_MISSING",
                        message=f"Paper does not visibly close {node.subproblem_id} as an independent narrative unit.",
                        section="body",
                        subproblem_id=node.subproblem_id,
                        source="narrative_coverage",
                    )
                )
                continue
            if node.role == "RESEARCH" and node.key_results and not evidence_present:
                findings.append(
                    PaperAuditFinding(
                        defect_type="DOCUMENT",
                        severity="REVIEW",
                        code="SUBPROBLEM_QUANTITATIVE_RESULT_NOT_VISIBLE",
                        message=f"{node.subproblem_id} has accepted numeric evidence but no recognizable key value appears in the paper.",
                        section="results",
                        subproblem_id=node.subproblem_id,
                        source="narrative_coverage",
                    )
                )
        return findings

    def _domain_pollution_findings(self, text: str, narrative: NarrativeGraph) -> list[PaperAuditFinding]:
        findings: list[PaperAuditFinding] = []
        domain = " ".join(
            [
                *(node.title for node in narrative.nodes),
                *(node.objective for node in narrative.nodes),
                *(node.method for node in narrative.nodes),
            ]
        ).lower()
        paper_lower = text.lower()
        energy_domain = any(token in domain for token in ("energy", "electric", "power", "load", "电力", "能源", "功率"))
        currency_domain = any(
            token in domain
            for token in (
                "price", "cost", "profit", "currency", "revenue", "loan", "credit",
                "价格", "成本", "收益", "利润", "费用", "造价", "金额", "销售额",
                "售价", "定价", "贷款", "信贷", "补偿费", "附加费",
            )
        )
        if not energy_domain and re.search(r"\b(?:kwh|kw|mwh|mw)\b", paper_lower):
            findings.append(
                PaperAuditFinding(
                    defect_type="DOCUMENT",
                    severity="BLOCK",
                    code="FOREIGN_ENERGY_UNIT_POLLUTION",
                    message="Energy units appear although the accepted Research State has no energy/power semantics.",
                    section="notation",
                    source="pollution_guard",
                )
            )
        if not currency_domain and re.search(r"\b(?:cny|rmb)\b|人民币|元/", paper_lower):
            findings.append(
                PaperAuditFinding(
                    defect_type="DOCUMENT",
                    severity="BLOCK",
                    code="FOREIGN_CURRENCY_UNIT_POLLUTION",
                    message="Currency units appear although the accepted Research State has no pricing/cost semantics.",
                    section="notation",
                    source="pollution_guard",
                )
            )
        state_space_method = any(
            token in domain
            for token in (
                "state space", "state-space", "state transition", "state-transition",
                "transition matrix", "probabilistic state", "kalman", "markov",
                "状态空间", "状态转移", "转移矩阵", "卡尔曼", "马尔可夫",
            )
        )
        if not state_space_method and (
            re.search(r"\bA_t\b|\bB_t\b", text)
            or re.search(r"x_\{?t\}?\s*=", text)
        ):
            findings.append(
                PaperAuditFinding(
                    defect_type="DOCUMENT",
                    severity="BLOCK",
                    code="GENERIC_STATE_SPACE_FORMULA_POLLUTION",
                    message="State-space notation appears without a corresponding accepted state-space/Markov solver.",
                    section="model",
                    source="pollution_guard",
                )
            )
        return findings

    def _abstract_findings(self, text: str, narrative: NarrativeGraph) -> list[PaperAuditFinding]:
        abstract = _extract_section(text, ("abstract", "summary", "摘要"))
        if not abstract:
            return [
                PaperAuditFinding(
                    defect_type="DOCUMENT",
                    severity="BLOCK",
                    code="ABSTRACT_MISSING",
                    message="Competition paper has no abstract/summary section.",
                    section="abstract",
                    source="paper_structure",
                )
            ]
        research_nodes = [node for node in narrative.nodes if node.role == "RESEARCH"]
        method_hits = sum(
            any(
                token in abstract.lower()
                for token in [
                    *_method_tokens(node.method),
                    *_method_tokens(PaperHumanizationAdapter.method_label(node.method, language="zh")),
                    *_method_tokens(PaperHumanizationAdapter.method_label(node.method, language="en")),
                ]
            )
            for node in research_nodes
        )
        quantitative_hits = sum(
            any(marker in abstract.lower() for marker in _result_markers(node))
            for node in research_nodes
            if node.key_results
        )
        required_methods = max(1, math.ceil(len(research_nodes) / 2))
        required_numbers = max(1, math.ceil(len(research_nodes) / 2))
        findings: list[PaperAuditFinding] = []
        if method_hits < required_methods:
            findings.append(
                PaperAuditFinding(
                    defect_type="DOCUMENT",
                    severity="REVIEW",
                    code="ABSTRACT_METHOD_COVERAGE_WEAK",
                    message=f"Abstract exposes methods for only {method_hits}/{len(research_nodes)} research nodes.",
                    section="abstract",
                    source="narrative_coverage",
                )
            )
        if quantitative_hits < required_numbers:
            findings.append(
                PaperAuditFinding(
                    defect_type="DOCUMENT",
                    severity="REVIEW",
                    code="ABSTRACT_RESULT_COVERAGE_WEAK",
                    message=f"Abstract exposes recognizable quantitative results for only {quantitative_hits}/{len(research_nodes)} research nodes.",
                    section="abstract",
                    source="narrative_coverage",
                )
            )
        return findings

    def _internal_id_findings(self, text: str) -> list[PaperAuditFinding]:
        leaked = sorted({match.group(0) for pattern in _INTERNAL_ID_PATTERNS for match in pattern.finditer(text)})
        if not leaked:
            return []
        return [
            PaperAuditFinding(
                defect_type="DOCUMENT",
                severity="BLOCK",
                code="INTERNAL_REGISTRY_ID_LEAK",
                message=f"User-visible paper leaks internal registry ids ({len(leaked)} unique occurrences).",
                section="global",
                source="traceability_boundary",
            )
        ]

    def _reference_findings(self, text: str) -> list[PaperAuditFinding]:
        references = _extract_section(text, ("references", "bibliography", "参考文献"))
        if not references:
            return [
                PaperAuditFinding(
                    defect_type="DOCUMENT",
                    severity="BLOCK",
                    code="VERIFIED_REFERENCES_MISSING",
                    message="No bibliographic reference section is present; references may not be invented by the writer.",
                    section="references",
                    source="bibliography_guard",
                )
            ]
        lowered = references.lower()
        if any(token in lowered for token in ("no specific", "methodological framework", "待补", "pending", "placeholder", "暂无具体")):
            return [
                PaperAuditFinding(
                    defect_type="DOCUMENT",
                    severity="BLOCK",
                    code="REFERENCE_PLACEHOLDER_FORBIDDEN",
                    message="References section contains placeholder/meta-language instead of concrete bibliographic entries.",
                    section="references",
                    source="bibliography_guard",
                )
            ]
        entries = re.findall(r"(?m)^\s*(?:\[\d+\]|\d+[.)])\s+.+$", references)
        if len(entries) < 3:
            return [
                PaperAuditFinding(
                    defect_type="DOCUMENT",
                    severity="REVIEW",
                    code="REFERENCE_COVERAGE_THIN",
                    message=f"Only {len(entries)} concrete-looking reference entries were detected.",
                    section="references",
                    source="bibliography_guard",
                )
            ]
        return []

    def _presentation_findings(self, text: str) -> list[PaperAuditFinding]:
        findings: list[PaperAuditFinding] = []
        if not re.search(r"(?m)^\s*\|.+\|\s*$", text):
            findings.append(
                PaperAuditFinding(
                    defect_type="DOCUMENT",
                    severity="REVIEW",
                    code="RESULT_TABLE_ABSENT",
                    message="No Markdown result table detected; excellent-paper summaries repeatedly use tables to carry quantitative conclusions.",
                    section="results",
                    source="presentation_guard",
                )
            )
        if not re.search(r"!\[[^\]]*\]\([^\)]+\)", text):
            findings.append(
                PaperAuditFinding(
                    defect_type="DOCUMENT",
                    severity="REVIEW",
                    code="FIGURE_EVIDENCE_ABSENT",
                    message="No embedded figure detected; add only figures that answer a concrete modeling/result question.",
                    section="results",
                    source="presentation_guard",
                )
            )
        return findings

    def _excellent_summary_findings(self, text: str) -> list[PaperAuditFinding]:
        findings: list[PaperAuditFinding] = []
        for focus in VALID_FOCUS:
            for issue in self.comparator.compare(text, focus):
                if _summary_prior_semantically_present(text, issue.aspect):
                    continue
                findings.append(
                    PaperAuditFinding(
                        defect_type="DOCUMENT",
                        severity="REVIEW",
                        code=f"EXCELLENT_PRIOR_{_slug(focus)}_{_slug(issue.aspect)[:36]}",
                        message=f"Recurring extracted-summary prior missing: {issue.aspect}. {issue.reason}",
                        section=focus,
                        ref_years=list(issue.ref_years),
                        source="excellent_c7_extracted_summary_prior",
                    )
                )
        return findings


def _summary_prior_semantically_present(text: str, aspect: str) -> bool:
    """Bridge Chinese extracted-summary labels to equivalent English paper signals.

    The reference summaries are predominantly Chinese while MCM papers are
    English. This is deliberately a conservative proxy: it can suppress a
    false missing-keyword REVIEW, but it never creates a PASS competition score.
    """

    lowered = text.lower()
    rules: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
        (("问题分层", "逐问求解"), ("question 1", "question 2", "problem decomposition", "问题1", "问题2", "问题3", "问题重述与分析")),
        (("模型假设", "假设先行"), ("assumptions", "assumption", "scope")),
        (("模型评价", "改进讨论"), ("strength", "limitation", "evaluation", "improvement")),
        (("子问题间逻辑衔接",), ("depends on", "synthesis", "therefore", "cross-question")),
        (
            ("现实背景", "交代动机"),
            ("background", "problem analysis", "motivation", "现实背景", "建模动机", "问题重述与分析", "经营矛盾"),
        ),
        (("分情形", "多方案对比"), ("scenario", "alternative", "comparison", "case", "对照实验", "方案比较", "敏感性", "成本扰动")),
        (("业务", "策略建议"), ("recommendation", "strategy", "decision")),
        (("图表编号", "引用规范"), ("figure 1", "table 1", "figure 2", "table 2")),
        (("结果用图表承载",), ("| metric | value |", "![figure")),
        (("模型/流程示意图", "流程图"), ("flowchart", "workflow", "model framework")),
        (("变量符号", "符号统一"), ("notation", "symbol", "model equations")),
        (("公式推导", "公式"), ("model equations", "$$", "arg\\min", "probability")),
        (("统计量", "误差指标"), ("rmse", "mae", "validation", "error", "accuracy")),
        (("结果量化", "具体数字"), ("reported values include", "accepted quantitative results", "quantitative results")),
        (("敏感性", "灵敏度"), ("sensitivity", "robustness", "bootstrap", "uncertainty")),
        (("优缺点", "不足", "改进"), ("strength", "limitation", "weakness", "improvement")),
    )
    for aspect_tokens, paper_tokens in rules:
        if not any(token in aspect for token in aspect_tokens):
            continue
        if any(token in lowered for token in paper_tokens):
            return True
        if any(token in aspect for token in ("结果量化", "具体数字")):
            return _has_structured_quantitative_results(text)
        return False
    return False


def _has_structured_quantitative_results(text: str) -> bool:
    """Recognize real numerical result evidence without requiring template prose.

    Paper rendering may legitimately humanize a table caption, so an excellent-
    summary prior must not depend on the historical literal phrase ``accepted
    quantitative results``. A Markdown table with a numeric body row is sufficient
    evidence that concrete values are being carried in the paper; this detector
    does not judge whether those values are scientifically correct.
    """

    lines = text.splitlines()
    for index, line in enumerate(lines):
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            continue
        if index + 1 >= len(lines):
            continue
        divider = lines[index + 1].strip()
        if not (divider.startswith("|") and "---" in divider):
            continue
        for row in lines[index + 2:index + 12]:
            value = row.strip()
            if not (value.startswith("|") and value.endswith("|")):
                break
            if re.search(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?%?", value):
                return True
    return False


def _extract_section(text: str, names: tuple[str, ...]) -> str:
    escaped = "|".join(re.escape(name) for name in names)
    match = re.search(rf"(?im)^#+\s*(?:{escaped})\b[^\n]*\n", text)
    if not match:
        return ""
    rest = text[match.end():]
    next_heading = re.search(r"(?m)^#+\s+", rest)
    return rest[: next_heading.start()] if next_heading else rest


def _method_tokens(method: str) -> list[str]:
    normalized = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", " ", method.lower()).strip()
    tokens = [token for token in normalized.split() if len(token) >= 3]
    if normalized:
        tokens.insert(0, normalized)
    return list(dict.fromkeys(tokens[:6]))


def _result_markers(node: Any) -> list[str]:
    markers: list[str] = []
    for result in node.key_results[:5]:
        value = float(result.value)
        markers.extend(
            [
                f"{value:.6g}".lower(),
                f"{value:.4f}".rstrip("0").rstrip(".").lower(),
                f"{value:.3f}".rstrip("0").rstrip(".").lower(),
            ]
        )
    return [item for item in dict.fromkeys(markers) if item]


def _repair_phase(blockers: list[str]) -> str:
    joined = " ".join(blockers)
    if "VALIDATION" in joined:
        return "validation"
    if "RESULT" in joined:
        return "experiment"
    if "ANSWER" in joined:
        return "evidence"
    if "DEPENDENCY" in joined:
        return "synthesis"
    return "research"


def _slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_") or "issue"


def _dedupe(findings: list[PaperAuditFinding]) -> list[PaperAuditFinding]:
    seen: set[tuple[str, str, str | None]] = set()
    values: list[PaperAuditFinding] = []
    for item in findings:
        key = (item.code, item.section, item.subproblem_id)
        if key in seen:
            continue
        seen.add(key)
        values.append(item)
    return values

from __future__ import annotations

import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .excellent_paper_comparator import ExcellentPaperComparator
from .io_utils import atomic_write_json, now_iso


GapStatus = Literal["MET", "GAP", "UNVERIFIED"]
RepairType = Literal["DOCUMENT", "RESEARCH", "EXTERNAL"]


class CorpusStandard(BaseModel):
    model_config = ConfigDict(extra="forbid")

    standard_id: str
    focus: str
    aspect: str
    support_count: int
    support_ratio: float
    years: list[int]
    tier: Literal["CORE", "COMMON", "RECURRING"]
    repair_type: RepairType


class CorpusGap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    standard_id: str
    focus: str
    aspect: str
    status: GapStatus
    repair_type: RepairType
    support_count: int
    support_ratio: float
    evidence: str
    gap: str = ""
    subproblem_ids: list[str] = Field(default_factory=list)


class ExcellentCorpusBenchmarkAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str
    corpus_kind: Literal["EXTRACTED_SUMMARIES", "FULL_TEXT"]
    corpus_papers: int
    standards_considered: int
    met_count: int
    gap_count: int
    unverified_count: int
    gaps: list[CorpusGap]
    checked_at: str


class ExcellentCorpusBenchmarkService:
    """Structured benchmark against recurring excellent-paper patterns.

    The current repository corpus is explicitly a set of extracted summaries,
    not full papers. This service therefore treats the corpus as a structural
    prior. It never turns a recurring pattern into a fabricated experiment: each
    gap is classified as DOCUMENT, RESEARCH, or EXTERNAL so the caller knows
    whether prose/layout can fix it, upstream research must be extended, or the
    available corpus is insufficient to judge it.
    """

    def __init__(self, config_dir: Path | None = None, *, min_support: int = 2) -> None:
        self.comparator = ExcellentPaperComparator(config_dir)
        self.min_support = max(2, int(min_support))

    def standards(self) -> list[CorpusStandard]:
        papers = self.comparator.ref_papers()
        if not papers:
            return []
        support: dict[tuple[str, str], set[int]] = defaultdict(set)
        for paper in papers:
            for focus, points in paper.strong_points.items():
                for point in points:
                    support[(focus, point.aspect)].add(int(paper.year))
        total = len(papers)
        standards: list[CorpusStandard] = []
        for (focus, aspect), years in support.items():
            if len(years) < self.min_support:
                continue
            ratio = len(years) / total
            tier: Literal["CORE", "COMMON", "RECURRING"]
            if ratio >= 0.8:
                tier = "CORE"
            elif ratio >= 0.5:
                tier = "COMMON"
            else:
                tier = "RECURRING"
            standards.append(
                CorpusStandard(
                    standard_id=_standard_id(focus, aspect),
                    focus=focus,
                    aspect=aspect,
                    support_count=len(years),
                    support_ratio=round(ratio, 6),
                    years=sorted(years),
                    tier=tier,
                    repair_type=_repair_type(aspect),
                )
            )
        return sorted(
            standards,
            key=lambda item: (-item.support_count, item.focus, item.aspect),
        )

    def assess(
        self,
        case_id: str,
        paper_text: str,
        narrative: Any,
        *,
        figures: list[dict[str, Any]] | None = None,
        comparison_subproblem_ids: list[str] | None = None,
        full_text: bool = False,
    ) -> ExcellentCorpusBenchmarkAssessment:
        standards = self.standards()
        gaps: list[CorpusGap] = []
        for standard in standards:
            status, evidence, affected = _assess_standard(
                standard,
                paper_text,
                narrative,
                figures or [],
                comparison_subproblem_ids=set(comparison_subproblem_ids or []),
                full_text=full_text,
            )
            gaps.append(
                CorpusGap(
                    standard_id=standard.standard_id,
                    focus=standard.focus,
                    aspect=standard.aspect,
                    status=status,
                    repair_type=("EXTERNAL" if status == "UNVERIFIED" else standard.repair_type),
                    support_count=standard.support_count,
                    support_ratio=standard.support_ratio,
                    evidence=evidence,
                    gap=(
                        ""
                        if status == "MET"
                        else _gap_message(standard, status)
                    ),
                    subproblem_ids=affected,
                )
            )
        return ExcellentCorpusBenchmarkAssessment(
            case_id=case_id,
            corpus_kind="FULL_TEXT" if full_text else "EXTRACTED_SUMMARIES",
            corpus_papers=len(self.comparator.ref_papers()),
            standards_considered=len(standards),
            met_count=sum(item.status == "MET" for item in gaps),
            gap_count=sum(item.status == "GAP" for item in gaps),
            unverified_count=sum(item.status == "UNVERIFIED" for item in gaps),
            gaps=gaps,
            checked_at=now_iso(),
        )

    def persist(
        self,
        cases: Any,
        artifacts: Any,
        case_id: str,
        assessment: ExcellentCorpusBenchmarkAssessment,
        *,
        source_artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        root = cases.case_root(case_id)
        path = root / "review" / "competition" / "excellent_corpus_benchmark.json"
        atomic_write_json(path, assessment.model_dump(mode="json"))
        artifact = artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "excellent_corpus_benchmark",
            "excellent_corpus_benchmark",
            upstream=list(source_artifact_ids or []),
            paper_eligible=False,
        )
        return {"assessment": assessment, "artifact": artifact}


def _assess_standard(
    standard: CorpusStandard,
    text: str,
    narrative: Any,
    figures: list[dict[str, Any]],
    *,
    comparison_subproblem_ids: set[str],
    full_text: bool,
) -> tuple[GapStatus, str, list[str]]:
    aspect = standard.aspect
    nodes = list(getattr(narrative, "nodes", []))
    research_nodes = [item for item in nodes if getattr(item, "role", "") == "RESEARCH"]
    lowered = text.lower()

    if aspect == "问题分层递进、逐问求解":
        ok = len(nodes) >= 2 and all(f"question {index}" in lowered for index in range(1, len(nodes) + 1))
        return _binary(ok, f"narrative nodes={len(nodes)}; explicit Question coverage={ok}")
    if aspect == "模型假设先行、逐条列出":
        ok = "assumptions and scope" in lowered and all(getattr(node, "limitation", "") for node in research_nodes)
        return _binary(ok, f"assumption section present={ 'assumptions and scope' in lowered }; research limitations={sum(bool(getattr(n, 'limitation', '')) for n in research_nodes)}/{len(research_nodes)}")
    if aspect == "模型评价与改进讨论":
        ok = "robustness and limitations" in lowered and all(getattr(node, "limitation", "") for node in research_nodes)
        return _binary(ok, "robustness/limitations section plus node-specific limitations")
    if aspect == "子问题间逻辑衔接":
        dependency_count = sum(bool(getattr(node, "dependencies", [])) for node in nodes)
        ok = dependency_count > 0 and ("depends on question" in lowered or "synthes" in lowered)
        return _binary(ok, f"dependency-bearing narrative nodes={dependency_count}")
    if aspect == "图表编号引用规范":
        figure_refs = len(re.findall(r"\bFigure\s+\d+\b", text, flags=re.IGNORECASE))
        table_refs = len(re.findall(r"\bTable\s+\d+\b", text, flags=re.IGNORECASE))
        ok = figure_refs + table_refs > 0
        return _binary(ok, f"numbered figure refs={figure_refs}; table refs={table_refs}")
    if aspect == "结果用图表承载":
        with_results = [node for node in research_nodes if getattr(node, "key_results", [])]
        semantic = [
            item for item in figures
            if item.get("status") == "FINAL" and (item.get("parameters") or {}).get("purpose")
        ]
        ok = bool(with_results) and len(semantic) >= max(1, len(with_results) // 2)
        return _binary(ok, f"research nodes with numeric results={len(with_results)}; purposeful FINAL figures={len(semantic)}")
    if aspect == "模型/流程示意图":
        process_figures = [
            item for item in figures
            if str((item.get("parameters") or {}).get("semantic_kind", "")).lower()
            in {"workflow", "research_workflow", "model_flow", "process_diagram"}
        ]
        return _binary(bool(process_figures), f"registered process/workflow figures={len(process_figures)}")
    if aspect == "模型优缺点自评":
        ok = "robustness and limitations" in lowered and "limitation" in lowered
        return _binary(ok, "explicit limitations are discussed" if ok else "no explicit model limitation discussion detected")
    if aspect == "结果量化、给出具体数字":
        quantified = [node for node in research_nodes if getattr(node, "key_results", [])]
        ok = len(quantified) == len(research_nodes) and bool(research_nodes)
        return _binary(ok, f"quantified research nodes={len(quantified)}/{len(research_nodes)}")
    if aspect == "敏感性分析验证稳健性":
        robust_nodes = [
            node for node in research_nodes
            if any(
                token in str(getattr(node, "validation_protocol_id", "")).lower()
                for token in ("bootstrap", "robust", "calibr", "simplex", "stability", "stress")
            )
            or any(token in str(getattr(node, "answer", "")).lower() for token in ("bootstrap", "uncertainty", "interval", "probab"))
            or any(
                any(token in str(getattr(result, "metric", "")).lower() for token in ("stability", "sensitivity", "winner_retention", "mean_spearman"))
                for result in getattr(node, "key_results", [])
            )
            or bool(getattr(getattr(node, "alternative_comparison", None), "stress_runs", None))
        ]
        ok = bool(robust_nodes) and "robustness" in lowered
        return _binary(ok, f"nodes with structured uncertainty/stability evidence={len(robust_nodes)}")
    if aspect == "分情形/多方案对比呈现":
        # Candidate discussion is not enough: this standard is marked met only
        # when the accepted Research State contains evidence of an actual
        # alternative comparison. This prevents corpus pressure from fabricating
        # head-to-head metrics for methods that were never executed.
        empirical_families = {
            "forecasting",
            "distribution_forecasting",
            "classification",
            "optimization",
            "ranking",
        }
        eligible = [
            str(getattr(node, "subproblem_id", ""))
            for node in research_nodes
            if getattr(node, "task_family", "") in empirical_families
            and any(
                not getattr(item, "selected", False)
                and str(getattr(item, "feasibility", "")).upper() == "PASS"
                and bool(getattr(item, "comparison_compatible", False))
                for item in getattr(node, "candidate_considerations", [])
            )
        ]
        compared = sorted(set(eligible) & comparison_subproblem_ids)
        if not eligible:
            return (
                "MET",
                "No distinct alternative is both solver-available and semantically comparable; comparison is not fabricated from alias availability or PLANNED candidate labels.",
                [],
            )
        return (
            ("MET" if compared else "GAP"),
            f"explicitly executable comparison subproblems={eligible}; accepted head-to-head comparison evidence={compared or 'none'}",
            eligible if not compared else [],
        )
    if aspect == "现实背景铺垫、交代动机":
        ok = "related domain work" in lowered or "background" in lowered or "motivation" in lowered
        return _binary(ok, "domain/background motivation section detected" if ok else "background motivation not explicit")
    if aspect == "结论落到业务/策略建议":
        ok = "practical interpretation and recommendations" in lowered and "recommendation" in lowered
        return _binary(ok, "question-level practical recommendations present")
    if aspect == "公式推导完整清晰":
        equation_count = text.count("$$") // 2
        ok = equation_count >= len(research_nodes)
        return _binary(ok, f"display equations={equation_count}; research nodes={len(research_nodes)}")
    if aspect == "变量符号统一规范":
        equation_count = text.count("$$") // 2
        pollution = any(token in text for token in ("A_t", "B_t", "kWh", "CNY"))
        ok = equation_count > 0 and not pollution
        return _binary(ok, f"equations={equation_count}; known cross-problem notation/unit pollution={pollution}")
    if aspect == "统计量/误差指标明确":
        metric_nodes = [node for node in research_nodes if getattr(node, "key_results", []) and getattr(node, "validation_protocol_id", None)]
        ok = len(metric_nodes) == len(research_nodes) and bool(research_nodes)
        return _binary(ok, f"nodes with result metrics + validation protocol={len(metric_nodes)}/{len(research_nodes)}")

    if not full_text:
        return (
            "UNVERIFIED",
            "No structured detector is justified from extracted summaries alone.",
            [],
        )
    return "UNVERIFIED", "Full-text detector not yet registered for this aspect.", []


def _binary(ok: bool, evidence: str) -> tuple[GapStatus, str, list[str]]:
    return ("MET" if ok else "GAP", evidence, [])


def _repair_type(aspect: str) -> RepairType:
    if aspect in {"分情形/多方案对比呈现", "敏感性分析验证稳健性"}:
        return "RESEARCH"
    return "DOCUMENT"


def _gap_message(standard: CorpusStandard, status: GapStatus) -> str:
    if status == "UNVERIFIED":
        return "The extracted-summary corpus is insufficient to judge this aspect; full-text evidence is required."
    if standard.repair_type == "RESEARCH":
        return "Recurring excellent-paper pattern is missing from accepted Research State; repair upstream evidence rather than inventing prose or metrics."
    return "Recurring excellent-paper structure/narrative pattern is missing from the current draft and can be addressed in the Paper Engine if evidence permits."


def _standard_id(focus: str, aspect: str) -> str:
    import hashlib

    digest = hashlib.sha256(f"{focus}|{aspect}".encode("utf-8")).hexdigest()[:10]
    return f"excellent-standard-{digest}"

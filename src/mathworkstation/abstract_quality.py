from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .io_utils import atomic_write_json, now_iso


AbstractStatus = Literal["PASS", "REVIEW"]


class AbstractQualityDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str
    status: AbstractStatus
    score: float = Field(ge=0.0, le=100.0)
    evidence: str
    gap: str = ""


class AbstractQualityAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str | None = None
    profile_id: str
    gate: AbstractStatus
    score: float = Field(ge=0.0, le=100.0)
    dimensions: list[AbstractQualityDimension]
    checked_at: str


_FAMILY_TERMS = {
    "forecasting": ("预测", "forecast", "trend", "趋势"),
    "distribution_forecasting": ("分布", "distribution", "probability", "概率"),
    "classification": ("分类", "classification", "class", "类别"),
    "explanatory_inference": ("影响", "关联", "effect", "association", "relation", "关系"),
    "exploratory_analysis": ("特征", "画像", "聚类", "分析", "profile", "cluster", "pattern"),
    "optimization": ("优化", "最优", "minimum", "maximum", "optimiz"),
    "simulation": ("模拟", "仿真", "simulation", "monte carlo"),
    "ranking": ("评价", "排序", "ranking", "score", "评分"),
}

_INTERNAL_TERMS = (
    "accepted research state",
    "accepted question-level evidence",
    "solverregistry",
    "modelingbrain",
    "narrativegraph",
    "evidencegraph",
    "pass / needs_solver",
    "needs_solver",
    "已接受研究状态",
    "求解器注册表",
    "研究状态",
    "检验协议id",
)

_TEMPLATE_PATTERNS = (
    r"针对问题\s*\d+\s*[，,]\s*采用",
    r"for question\s+\d+\s*,\s*we use",
)


def extract_abstract(paper_text: str) -> str:
    """Extract the first competition abstract/summary section from Markdown."""

    match = re.search(r"(?im)^\s*#\s*(?:摘要|summary|abstract)\s*$", paper_text)
    if not match:
        return ""
    rest = paper_text[match.end():]
    stop = re.search(r"(?im)^\s*#\s+[^#].*$", rest)
    return (rest[: stop.start()] if stop else rest).strip()


class AbstractQualityService:
    """Deterministic excellent-paper-oriented abstract gate.

    This gate judges document communication only.  It never upgrades an absent
    research result, and it deliberately avoids calling an LLM.  The dimensions
    mirror recurring C-problem excellent-paper behaviour: cover the actual task
    chain, report quantitative answers when they exist, state methods with task
    meaning, communicate validation/uncertainty where relevant, and avoid a
    repetitive question-by-question template.
    """

    def assess(
        self,
        abstract_text: str,
        graph: Any,
        *,
        profile_id: str,
        case_id: str | None = None,
    ) -> AbstractQualityAssessment:
        text = " ".join(str(abstract_text or "").split())
        lowered = text.lower()
        research_nodes = [node for node in graph.nodes if getattr(node, "role", "") == "RESEARCH"]
        dimensions: list[AbstractQualityDimension] = []

        dimensions.append(self._coverage(text, lowered, research_nodes))
        dimensions.append(self._quantitative(text, research_nodes))
        dimensions.append(self._method_specificity(text, lowered, research_nodes))
        dimensions.append(self._validation_signal(text, lowered, research_nodes))
        dimensions.append(self._conclusion_signal(text, lowered, graph))
        dimensions.append(self._style_and_leakage(text, lowered, profile_id))
        dimensions.append(self._density(text, profile_id))

        weights = {
            "task_chain_coverage": 0.20,
            "quantitative_answer_coverage": 0.20,
            "method_task_specificity": 0.14,
            "validation_uncertainty_signal": 0.12,
            "conclusion_decision_signal": 0.12,
            "competition_style_and_leakage": 0.14,
            "information_density": 0.08,
        }
        score = sum(item.score * weights[item.dimension] for item in dimensions)
        gate: AbstractStatus = "PASS" if score >= 80 and all(item.status == "PASS" for item in dimensions[:2]) else "REVIEW"
        return AbstractQualityAssessment(
            case_id=case_id,
            profile_id=profile_id,
            gate=gate,
            score=round(float(score), 2),
            dimensions=dimensions,
            checked_at=now_iso(),
        )

    def persist(
        self,
        cases: Any,
        artifacts: Any,
        case_id: str,
        assessment: AbstractQualityAssessment,
        *,
        source_artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        root = cases.case_root(case_id)
        path = root / "review" / "abstract_quality" / "assessment.json"
        atomic_write_json(path, assessment.model_dump(mode="json"))
        artifact = artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "abstract_quality_assessment",
            "abstract_quality",
            upstream=list(source_artifact_ids or []),
            paper_eligible=False,
        )
        return {"assessment": assessment, "artifact": artifact}

    def _coverage(self, text: str, lowered: str, nodes: list[Any]) -> AbstractQualityDimension:
        if not nodes:
            return AbstractQualityDimension(
                dimension="task_chain_coverage", status="REVIEW", score=0, evidence="no research nodes", gap="Abstract cannot be calibrated without research questions."
            )
        represented = 0
        evidence: list[str] = []
        for node in nodes:
            family = str(getattr(node, "task_family", ""))
            terms = _FAMILY_TERMS.get(family, ())
            title_tokens = _semantic_tokens(str(getattr(node, "title", "")) + " " + str(getattr(node, "objective", "")))
            family_hit = any(term in lowered for term in terms)
            token_hit = any(token.lower() in lowered for token in title_tokens[:8])
            hit = family_hit or token_hit
            represented += int(hit)
            evidence.append(f"{getattr(node, 'subproblem_id', '?')}={'yes' if hit else 'no'}")
        ratio = represented / len(nodes)
        return AbstractQualityDimension(
            dimension="task_chain_coverage",
            status="PASS" if ratio >= 0.8 else "REVIEW",
            score=100.0 * ratio,
            evidence=f"represented research questions = {represented}/{len(nodes)} ({', '.join(evidence)})",
            gap="" if ratio >= 0.8 else "Abstract does not yet communicate enough of the actual linked question chain.",
        )

    def _quantitative(self, text: str, nodes: list[Any]) -> AbstractQualityDimension:
        evidence_nodes = [node for node in nodes if getattr(node, "key_results", [])]
        numeric_tokens = re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?%?", text)
        if not evidence_nodes:
            score = 100.0 if text else 0.0
            return AbstractQualityDimension(
                dimension="quantitative_answer_coverage",
                status="PASS" if text else "REVIEW",
                score=score,
                evidence="no question-level numeric evidence is registered, so the abstract is not forced to invent numbers",
                gap="" if text else "Abstract is empty.",
            )
        target = min(len(evidence_nodes), 4)
        ratio = min(1.0, len(numeric_tokens) / max(1, target))
        return AbstractQualityDimension(
            dimension="quantitative_answer_coverage",
            status="PASS" if ratio >= 0.75 else "REVIEW",
            score=100.0 * ratio,
            evidence=f"numeric tokens in abstract = {len(numeric_tokens)}; research questions with numeric evidence = {len(evidence_nodes)}",
            gap="" if ratio >= 0.75 else "High-visibility abstract should report more of the actual quantitative answers already present in evidence.",
        )

    def _method_specificity(self, text: str, lowered: str, nodes: list[Any]) -> AbstractQualityDimension:
        methods = []
        for node in nodes:
            method = _human_method_tokens(str(getattr(node, "method", "")))
            if method and any(token in lowered for token in method):
                methods.append(str(getattr(node, "subproblem_id", "?")))
        family_hits = sum(
            any(term in lowered for term in _FAMILY_TERMS.get(str(getattr(node, "task_family", "")), ()))
            for node in nodes
        )
        ratio = min(1.0, max(len(methods), family_hits) / max(1, len(nodes)))
        return AbstractQualityDimension(
            dimension="method_task_specificity",
            status="PASS" if ratio >= 0.6 else "REVIEW",
            score=100.0 * ratio,
            evidence=f"method/family-specific clauses cover about {max(len(methods), family_hits)}/{max(1, len(nodes))} research questions",
            gap="" if ratio >= 0.6 else "Abstract is too generic about how the questions were modeled.",
        )

    def _validation_signal(self, text: str, lowered: str, nodes: list[Any]) -> AbstractQualityDimension:
        needs_signal = any(
            str(getattr(node, "task_family", ""))
            in {"forecasting", "classification", "explanatory_inference", "optimization", "ranking", "simulation"}
            for node in nodes
        )
        terms = ("稳健", "敏感", "误差", "区间", "不确定", "检验", "validation", "robust", "sensitivity", "interval", "uncertainty", "error")
        hit = any(term in lowered for term in terms)
        score = 100.0 if hit or not needs_signal else 45.0
        return AbstractQualityDimension(
            dimension="validation_uncertainty_signal",
            status="PASS" if score >= 80 else "REVIEW",
            score=score,
            evidence=f"validation/uncertainty language present = {hit}; claim families require it = {needs_signal}",
            gap="" if score >= 80 else "At least one concise robustness, sensitivity, error, or uncertainty result should qualify the headline claims.",
        )

    def _conclusion_signal(self, text: str, lowered: str, graph: Any) -> AbstractQualityDimension:
        terms = ("表明", "结果显示", "说明", "建议", "方案", "决策", "因此", "最终", "we find", "results show", "recommend", "therefore", "decision")
        hit = any(term in lowered for term in terms)
        synthesis = any(getattr(node, "role", "") == "SYNTHESIS" for node in graph.nodes)
        score = 100.0 if hit else (60.0 if not synthesis else 40.0)
        return AbstractQualityDimension(
            dimension="conclusion_decision_signal",
            status="PASS" if score >= 80 else "REVIEW",
            score=score,
            evidence=f"conclusion/decision language present = {hit}; explicit synthesis node = {synthesis}",
            gap="" if score >= 80 else "Abstract ends as a method list rather than a result/decision-oriented competition summary.",
        )

    def _style_and_leakage(self, text: str, lowered: str, profile_id: str) -> AbstractQualityDimension:
        internal_hits = [term for term in _INTERNAL_TERMS if term in lowered]
        repeats = sum(len(re.findall(pattern, lowered, flags=re.IGNORECASE)) for pattern in _TEMPLATE_PATTERNS)
        penalty = min(80.0, len(internal_hits) * 30.0 + max(0, repeats - 1) * 18.0)
        score = max(0.0, 100.0 - penalty)
        evidence = f"internal-language hits = {internal_hits or 'none'}; repeated question-template hits = {repeats}; profile={profile_id}"
        return AbstractQualityDimension(
            dimension="competition_style_and_leakage",
            status="PASS" if score >= 80 else "REVIEW",
            score=score,
            evidence=evidence,
            gap="" if score >= 80 else "Rewrite repetitive engineering-log phrasing into a compact competition-paper narrative; internal framework vocabulary must stay out of the abstract.",
        )

    def _density(self, text: str, profile_id: str) -> AbstractQualityDimension:
        chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
        english = len(re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", text))
        units = chinese + english
        if not text:
            score = 0.0
        elif profile_id == "CUMCM_C":
            score = _band_score(units, 220, 850)
        else:
            score = _band_score(units, 180, 650)
        return AbstractQualityDimension(
            dimension="information_density",
            status="PASS" if score >= 75 else "REVIEW",
            score=score,
            evidence=f"rough information units = {units} for profile {profile_id}",
            gap="" if score >= 75 else "Abstract is unusually sparse or bloated for a high-information competition summary; adjust compression without inventing content.",
        )


def _band_score(value: int, low: int, high: int) -> float:
    if low <= value <= high:
        return 100.0
    if value < low:
        return max(20.0, 100.0 * value / max(1, low))
    return max(20.0, 100.0 * high / max(1, value))


def _semantic_tokens(text: str) -> list[str]:
    chinese = re.findall(r"[\u4e00-\u9fff]{2,6}", text)
    english = re.findall(r"\b[A-Za-z][A-Za-z-]{3,}\b", text.lower())
    stop = {"建立", "模型", "分析", "问题", "结果", "进行", "使用", "based", "model", "using", "problem", "analysis"}
    values = [value for value in [*chinese, *english] if value.lower() not in stop]
    return list(dict.fromkeys(values))


def _human_method_tokens(method: str) -> list[str]:
    normalized = method.lower().replace("_", " ").replace("-", " ")
    tokens = [token for token in re.findall(r"[a-z]{3,}|[\u4e00-\u9fff]{2,}", normalized) if token not in {"gold", "solver", "model", "method"}]
    return list(dict.fromkeys(tokens))[:6]

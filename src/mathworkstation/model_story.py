from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .io_utils import now_iso
from .model_spine import ModelSpine, ModelSpineNode


StoryMoveKind = Literal[
    "PROBLEM_INSIGHT",
    "INHERITED_RESULT",
    "SIMPLE_RELATION",
    "INSUFFICIENCY_EVIDENCE",
    "NECESSARY_CORRECTION",
    "CORE_MODEL",
    "EXTENSION",
    "VALIDATION",
    "DECISION",
]


class SolverStoryEvidence(BaseModel):
    """Small evidence-only projection of a solver run for paper-story planning.

    The planner never reads arbitrary solver internals as prose.  It accepts an
    explicit ``story_trace`` when a solver provides one, otherwise it extracts a
    conservative simple-to-richer model-selection trace from protocol metadata.
    Missing fields stay missing: no narrative gap/correction may be fabricated.
    """

    model_config = ConfigDict(extra="forbid")

    source_artifact_ids: list[str] = Field(default_factory=list)
    protocol_method: str = ""
    simple_candidate: str | None = None
    richer_candidates: list[str] = Field(default_factory=list)
    selected_variants: dict[str, str] = Field(default_factory=dict)
    upgrade_threshold: float | None = None
    explicit_insufficiency: str = ""
    explicit_correction: str = ""

    @property
    def richer_selected(self) -> bool:
        if not self.simple_candidate or not self.selected_variants:
            return False
        return any(value != self.simple_candidate for value in self.selected_variants.values())

    @property
    def selected_counts(self) -> dict[str, int]:
        return dict(Counter(self.selected_variants.values()))


class StoryMove(BaseModel):
    model_config = ConfigDict(extra="forbid")

    move_id: str
    subproblem_id: str
    kind: StoryMoveKind
    headline_zh: str
    headline_en: str
    directive_zh: str
    directive_en: str
    evidence_refs: list[str] = Field(default_factory=list)
    inherited_from: list[str] = Field(default_factory=list)
    burden_of_proof_required: bool = False
    burden_of_proof_satisfied: bool | None = None
    formula_allowed: bool = False
    emphasis: float = 1.0


class SectionStory(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subproblem_id: str
    role: str
    heading_hint: str
    heading_basis: Literal["METHOD", "MECHANISM", "PROBLEM"]
    question_locator: str
    inherits_from: list[str] = Field(default_factory=list)
    repeat_full_derivation: bool = True
    moves: list[StoryMove]


class ModelStoryPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str
    principles: list[str] = Field(default_factory=list)
    sections: list[SectionStory]
    whole_story_zh: list[str]
    whole_story_en: list[str]
    generated_at: str

    def section(self, subproblem_id: str) -> SectionStory:
        for item in self.sections:
            if item.subproblem_id == subproblem_id:
                return item
        raise KeyError(f"model story section not found: {subproblem_id}")


class ModelStoryPlanner:
    """Turn accepted research state into an evidence-locked progressive model story.

    Reference papers act only as soft structural priors: start from insight or a
    simple relation, expose a gap only when evidence proves one, add only the
    necessary correction, inherit accepted upstream work, validate adjacent to
    the model, then convert evidence into a decision.  The planner never selects
    a new algorithm and never changes solver results.
    """

    def __init__(self, policy_path: str | Path | None = None) -> None:
        if policy_path is None:
            policy_path = Path(__file__).resolve().parents[2] / "config" / "ref_models" / "model_story_policy_v1.json"
        self.policy_path = Path(policy_path)
        self.policy = json.loads(self.policy_path.read_text(encoding="utf-8"))
        if int(self.policy.get("schema_version", 0)) != 1:
            raise ValueError("MODEL_STORY_POLICY_V1_REQUIRED")
        self.emphasis = dict(self.policy.get("stage_emphasis") or {})

    def plan(
        self,
        graph: Any,
        spine: ModelSpine,
        *,
        solver_evidence: dict[str, SolverStoryEvidence] | None = None,
    ) -> ModelStoryPlan:
        solver_evidence = dict(solver_evidence or {})
        sections: list[SectionStory] = []
        whole_zh: list[str] = []
        whole_en: list[str] = []

        for node in graph.nodes:
            sid = str(node.subproblem_id)
            spine_node = spine.node(sid)
            evidence = solver_evidence.get(sid)
            section = self._section(node, spine_node, evidence)
            sections.append(section)
            whole_zh.append(_whole_story_sentence_zh(node, spine_node, evidence))
            whole_en.append(_whole_story_sentence_en(node, spine_node, evidence))

        return ModelStoryPlan(
            case_id=str(getattr(graph, "case_id", "")),
            principles=[str(value) for value in self.policy.get("principles") or []],
            sections=sections,
            whole_story_zh=whole_zh,
            whole_story_en=whole_en,
            generated_at=now_iso(),
        )

    def _section(self, node: Any, spine_node: ModelSpineNode, evidence: SolverStoryEvidence | None) -> SectionStory:
        sid = str(node.subproblem_id)
        source_refs = list(dict.fromkeys(getattr(node, "source_artifact_ids", []) or []))
        moves: list[StoryMove] = []

        def add(
            kind: StoryMoveKind,
            headline_zh: str,
            headline_en: str,
            directive_zh: str,
            directive_en: str,
            *,
            evidence_refs: list[str] | None = None,
            inherited_from: list[str] | None = None,
            burden_required: bool = False,
            burden_satisfied: bool | None = None,
            formula_allowed: bool = False,
        ) -> None:
            moves.append(
                StoryMove(
                    move_id=f"{sid}:{len(moves) + 1}:{kind.lower()}",
                    subproblem_id=sid,
                    kind=kind,
                    headline_zh=headline_zh,
                    headline_en=headline_en,
                    directive_zh=directive_zh,
                    directive_en=directive_en,
                    evidence_refs=list(dict.fromkeys(evidence_refs or source_refs)),
                    inherited_from=list(inherited_from or []),
                    burden_of_proof_required=burden_required,
                    burden_of_proof_satisfied=burden_satisfied,
                    formula_allowed=formula_allowed,
                    emphasis=float(self.emphasis.get(kind, 1.0)),
                )
            )

        add(
            "PROBLEM_INSIGHT",
            "先回答：真正需要刻画什么",
            "Start from the modeling tension",
            f"从“{getattr(node, 'objective', '')}”中提炼本问的对象、约束与可验证输出；先讲为什么需要这一步，再出现方法名。",
            f"Extract the object, constraints, and verifiable output from: {getattr(node, 'objective', '')}. Motivate the step before naming a method.",
            formula_allowed=False,
        )

        if spine_node.inherits_from:
            parents_zh = "、".join(_question_label_zh(value) for value in spine_node.inherits_from)
            parents_en = ", ".join(spine_node.inherits_from)
            add(
                "INHERITED_RESULT",
                "承接已经验证的上游结果",
                "Inherit accepted upstream work",
                f"先明确从{parents_zh}继承的是{_inheritance_label_zh(spine_node)}，只把它作为本问起点，不重复上游完整推导。",
                f"State that {parents_en} contributes {_inheritance_label_en(spine_node)}. Reuse it as the starting point instead of repeating the full upstream derivation.",
                inherited_from=list(spine_node.inherits_from),
                formula_allowed=False,
            )

        if getattr(node, "role", "") == "SYNTHESIS" or spine_node.role == "SYNTHESIS":
            add(
                "DECISION",
                "把已验证结果合成为交付结论",
                "Synthesize accepted evidence into the deliverable",
                "只组合依赖小问中已经通过检验的结果与局限，不建立新模型、不创造新数值。",
                "Combine only validated upstream results and limitations; introduce neither a new model nor new numeric claims.",
                inherited_from=list(spine_node.inherits_from),
            )
            return SectionStory(
                subproblem_id=sid,
                role=spine_node.role,
                heading_hint=str(getattr(node, "title", "") or sid),
                heading_basis="PROBLEM",
                question_locator=sid,
                inherits_from=list(spine_node.inherits_from),
                repeat_full_derivation=False,
                moves=moves,
            )

        if spine_node.role == "FOUNDATION":
            add(
                "SIMPLE_RELATION",
                "先识别可复用的数据关系",
                "Establish the reusable empirical relation",
                "以描述性结构、关联、异常或变化证据建立后续模型的最小事实基础；不把探索性关系夸大为因果机制。",
                "Use descriptive structure, association, anomaly, or change evidence as the minimum factual basis for downstream modeling; do not turn exploratory relations into causal claims.",
                formula_allowed=False,
            )
        elif spine_node.role == "EXTENSION":
            add(
                "EXTENSION",
                "只增加本问真正新增的机制或约束",
                "Add only the new mechanism or constraint",
                f"以上游{_inheritance_label_zh(spine_node)}为基础，只展开本问新增变量、可行域、情景或决策层，不重复上一问已经完成的模型推导。",
                f"Starting from the inherited {_inheritance_label_en(spine_node)}, expand only the new variables, feasible region, scenario, or decision layer without repeating the completed upstream derivation.",
                inherited_from=list(spine_node.inherits_from),
                formula_allowed=True,
            )
        else:
            if evidence is not None and evidence.simple_candidate:
                add(
                    "SIMPLE_RELATION",
                    "从最简单可检验关系开始",
                    "Start with the simplest testable relation",
                    "候选关系从最简形式开始比较；先检验只保留核心解释关系是否已经足够，只有样本外验证证明有必要时才增加时间项或非线性项。",
                    "Candidate relations are compared from the simplest form upward; richer temporal or nonlinear terms are added only when out-of-sample validation demonstrates a need.",
                    evidence_refs=evidence.source_artifact_ids or source_refs,
                    formula_allowed=True,
                )
                if evidence.richer_selected or evidence.explicit_insufficiency:
                    threshold_zh = _threshold_zh(evidence.upgrade_threshold)
                    threshold_en = _threshold_en(evidence.upgrade_threshold)
                    insufficiency_zh = evidence.explicit_insufficiency or (
                        f"只有当时间/留出验证显示更丰富候选相对简单关系达到{threshold_zh}的实际改进时，才认定简单关系在相应对象上不足。"
                    )
                    insufficiency_en = (
                        f"Only when holdout validation shows an actual improvement of {threshold_en} over the simple relation is the simple relation treated as insufficient for that entity."
                    )
                    add(
                        "INSUFFICIENCY_EVIDENCE",
                        "先证明简单关系哪里不够",
                        "Prove where the simple relation is insufficient",
                        insufficiency_zh,
                        insufficiency_en,
                        evidence_refs=evidence.source_artifact_ids or source_refs,
                        burden_required=True,
                        burden_satisfied=True,
                    )
                    selected_summary_zh = _selected_summary_zh(evidence)
                    selected_summary_en = _selected_summary_en(evidence)
                    add(
                        "NECESSARY_CORRECTION",
                        "只加入被证据支持的必要修正",
                        "Add only the correction supported by evidence",
                        evidence.explicit_correction or selected_summary_zh,
                        selected_summary_en,
                        evidence_refs=evidence.source_artifact_ids or source_refs,
                        burden_required=True,
                        burden_satisfied=True,
                        formula_allowed=True,
                    )
            add(
                "CORE_MODEL",
                "形成可求解的核心模型",
                "Assemble the solvable core model",
                "把前述关系收束为可求解的核心模型，只呈现决定模型行为的核心关系、目标函数与关键约束。",
                "Assemble the preceding relations into a solvable core model, presenting only the governing relation, objective, and essential constraints.",
                formula_allowed=True,
            )

        protocol = str(getattr(node, "validation_protocol_id", "") or "family-specific validation")
        add(
            "VALIDATION",
            "模型建立后立即用独立检验证据约束它",
            "Validate immediately after model construction",
            "使用与模型目标相匹配的独立检验约束结论；只有检验通过的关系、参数或策略才进入下一问和最终建议。",
            "Use independent validation matched to the modeling objective; only validated relations, parameters, or strategies may flow to downstream questions and final recommendations.",
            formula_allowed=False,
        )
        add(
            "DECISION",
            "把模型输出翻译成题目需要的结论",
            "Translate model output into the required decision",
            "用已接受数值、图表和局限回答本问；结论强度不得超过验证证据。",
            "Answer the subproblem with accepted numbers, figures, and limitations; the conclusion must not be stronger than the validation evidence.",
            formula_allowed=False,
        )

        heading_hint, heading_basis = _heading_hint(node, spine_node)
        return SectionStory(
            subproblem_id=sid,
            role=spine_node.role,
            heading_hint=heading_hint,
            heading_basis=heading_basis,
            question_locator=sid,
            inherits_from=list(spine_node.inherits_from),
            repeat_full_derivation=spine_node.role not in {"EXTENSION", "SYNTHESIS"},
            moves=moves,
        )


def extract_solver_story_evidence(payload: dict[str, Any], *, artifact_id: str = "") -> SolverStoryEvidence | None:
    """Extract only story-relevant, non-numeric-claim solver protocol evidence."""

    result = payload.get("result") if isinstance(payload.get("result"), dict) else {}
    explicit = result.get("story_trace") if isinstance(result.get("story_trace"), dict) else None
    if explicit is None and isinstance(payload.get("story_trace"), dict):
        explicit = payload.get("story_trace")

    protocol = result.get("protocol") if isinstance(result.get("protocol"), dict) else {}
    if not protocol and not explicit:
        return None

    explicit = dict(explicit or {})
    candidate_order = explicit.get("candidate_order") or protocol.get("candidate_feature_order") or protocol.get("candidate_order") or []
    if not isinstance(candidate_order, list):
        candidate_order = []
    candidate_order = [str(value) for value in candidate_order if str(value).strip()]

    selected = explicit.get("selected_variants") or protocol.get("feature_variants_selected") or protocol.get("selected_variants") or {}
    if not isinstance(selected, dict):
        selected = {}
    selected = {str(key): str(value) for key, value in selected.items() if str(value).strip()}

    threshold = explicit.get("upgrade_threshold")
    if threshold is None:
        threshold = protocol.get("complexity_upgrade_min_relative_improvement")
    try:
        threshold_value = float(threshold) if threshold is not None else None
    except (TypeError, ValueError):
        threshold_value = None

    simple = str(explicit.get("simple_candidate") or (candidate_order[0] if candidate_order else "")).strip() or None
    richer = [value for value in candidate_order[1:] if value != simple]
    evidence = SolverStoryEvidence(
        source_artifact_ids=[artifact_id] if artifact_id else [],
        protocol_method=str(explicit.get("protocol_method") or protocol.get("method") or ""),
        simple_candidate=simple,
        richer_candidates=richer,
        selected_variants=selected,
        upgrade_threshold=threshold_value,
        explicit_insufficiency=str(explicit.get("insufficiency_evidence") or ""),
        explicit_correction=str(explicit.get("necessary_correction") or ""),
    )
    if not any(
        [
            evidence.simple_candidate,
            evidence.selected_variants,
            evidence.explicit_insufficiency,
            evidence.explicit_correction,
        ]
    ):
        return None
    return evidence


def _heading_hint(node: Any, spine_node: ModelSpineNode) -> tuple[str, Literal["METHOD", "MECHANISM", "PROBLEM"]]:
    method = str(getattr(node, "method", "") or "").strip()
    title = str(getattr(node, "title", "") or "").strip()
    if spine_node.role in {"CORE_MODEL", "EXTENSION", "INDEPENDENT_MODEL"} and method:
        return method, "METHOD"
    if title:
        return title, "PROBLEM"
    return str(getattr(node, "subproblem_id", "Model")), "PROBLEM"


def _inheritance_label_zh(node: ModelSpineNode) -> str:
    return {
        "MODEL": "模型结构",
        "CONSTRAINT": "模型结构与经检验的参数，再加入新的约束",
        "SCENARIO": "模型结构，并改变情景或参数",
        "EVIDENCE": "已验证结果",
        "SYNTHESIS": "已验证结果",
    }.get(node.inheritance_kind, "经检验的上游结果")


def _inheritance_label_en(node: ModelSpineNode) -> str:
    return {
        "MODEL": "model structure",
        "CONSTRAINT": "model structure and accepted parameters, with new constraints",
        "SCENARIO": "model structure under a new scenario or parameter setting",
        "EVIDENCE": "validated evidence",
        "SYNTHESIS": "validated evidence",
    }.get(node.inheritance_kind, "accepted upstream results")


def _threshold_zh(value: float | None) -> str:
    if value is None:
        return "预设阈值"
    return f"{value:.1%}"


def _threshold_en(value: float | None) -> str:
    if value is None:
        return "the preregistered threshold"
    return f"at least {value:.1%}"


def _selected_summary_zh(evidence: SolverStoryEvidence) -> str:
    counts = evidence.selected_counts
    if not counts:
        return "仅对通过复杂度升级门槛的对象采用更丰富候选，其余保持最简单关系。"
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    detail = "、".join(f"{_candidate_label_zh(name)}：{count}个对象" for name, count in ordered)
    return f"按同一验证门槛逐对象选择后，{detail}；因此修正是局部、证据驱动的，而不是全局强制升级。"


def _candidate_label_zh(value: str) -> str:
    """Turn protocol-level candidate identifiers into competition-paper labels.

    This is semantic token humanization rather than one-problem naming: unknown
    variants degrade to readable words instead of leaking snake_case internals.
    """

    normalized = str(value or "").strip().lower().replace("-", "_")
    tokens = [token for token in normalized.split("_") if token]
    token_labels = {
        "simple": "简约",
        "linear": "线性",
        "quadratic": "二次",
        "markup": "加价响应",
        "temporal": "时间校正",
        "time": "时间校正",
        "trend": "趋势",
        "ridge": "岭回归",
        "baseline": "基准",
    }
    rendered = "".join(token_labels.get(token, token) for token in tokens)
    return rendered or "候选关系"


def _selected_summary_en(evidence: SolverStoryEvidence) -> str:
    counts = evidence.selected_counts
    if not counts:
        return "Use a richer candidate only for entities that clear the complexity-upgrade gate; keep the simplest relation elsewhere."
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    detail = ", ".join(f"{name}: {count} entities" for name, count in ordered)
    return f"Entity-wise selection under one validation gate yields {detail}; the correction is local and evidence-driven rather than a global complexity upgrade."


def _question_label_zh(value: str) -> str:
    text = str(value or "").strip()
    if text.upper().startswith("SP") and text[2:].isdigit():
        return f"问题{text[2:]}"
    return text


def _whole_story_sentence_zh(node: Any, spine_node: ModelSpineNode, evidence: SolverStoryEvidence | None) -> str:
    sid = _question_label_zh(str(getattr(node, "subproblem_id", "")))
    if spine_node.role == "FOUNDATION":
        return f"{sid}先识别可复用的数据结构与规律，为后续模型提供事实基础。"
    if spine_node.role == "CORE_MODEL":
        if evidence is not None and evidence.richer_selected:
            return f"{sid}从最简单关系出发，仅在独立验证证明不足时增加必要修正，再形成核心决策模型。"
        return f"{sid}把上游证据收束为核心模型，并以独立检验决定哪些输出可继续向下游传递。"
    if spine_node.role == "EXTENSION":
        parents = "、".join(_question_label_zh(value) for value in spine_node.inherits_from)
        return f"{sid}承接{parents}，只增加本问新约束或决策层，不重复重建上游模型。"
    if spine_node.role == "SYNTHESIS":
        return f"{sid}综合已验证的上游结果形成最终交付，不新增独立模型。"
    return f"{sid}独立完成必要模型、检验与决策输出。"


def _whole_story_sentence_en(node: Any, spine_node: ModelSpineNode, evidence: SolverStoryEvidence | None) -> str:
    sid = str(getattr(node, "subproblem_id", ""))
    if spine_node.role == "FOUNDATION":
        return f"{sid} establishes reusable empirical structure as the factual foundation for downstream modeling."
    if spine_node.role == "CORE_MODEL":
        if evidence is not None and evidence.richer_selected:
            return f"{sid} starts from the simplest relation, adds a correction only where independent validation proves it necessary, and then forms the core decision model."
        return f"{sid} consolidates upstream evidence into the core model and uses independent validation to control downstream reuse."
    if spine_node.role == "EXTENSION":
        parents = ", ".join(spine_node.inherits_from)
        return f"{sid} builds on {parents}, adding only the new constraint or decision layer instead of rebuilding the upstream model."
    if spine_node.role == "SYNTHESIS":
        return f"{sid} synthesizes validated upstream results into the final deliverable without introducing a new model."
    return f"{sid} completes the necessary model, validation, and decision output as an independent node."

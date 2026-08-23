from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .io_utils import now_iso


ModelingRole = Literal["FOUNDATION", "CORE_MODEL", "EXTENSION", "INDEPENDENT_MODEL", "SYNTHESIS"]
InheritanceKind = Literal["NONE", "EVIDENCE", "MODEL", "CONSTRAINT", "SCENARIO", "SYNTHESIS"]


class ModelSpineNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subproblem_id: str
    role: ModelingRole
    method: str
    task_family: str
    dependencies: list[str] = Field(default_factory=list)
    inherits_from: list[str] = Field(default_factory=list)
    inheritance_kind: InheritanceKind = "NONE"
    downstream_reach: int = 0
    core_score: float = 0.0
    equation_budget: int = 0
    paper_emphasis: float = 1.0
    narrative_directive: str


class ModelSpine(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str
    core_subproblem_ids: list[str] = Field(default_factory=list)
    nodes: list[ModelSpineNode]
    storyline: list[str]
    generated_at: str

    def node(self, subproblem_id: str) -> ModelSpineNode:
        for item in self.nodes:
            if item.subproblem_id == subproblem_id:
                return item
        raise KeyError(f"model spine node not found: {subproblem_id}")


class ModelSpinePlanner:
    """Infer a compact paper-facing modeling spine from an accepted NarrativeGraph.

    The planner deliberately avoids hard-coding "Q2 is the core model" or any
    fixed question count.  It derives roles from research dependencies, task
    family, model execution semantics, and downstream reuse.  The configuration
    contains only soft structural priors such as equation budgets and score
    weights; the current problem graph decides which nodes become foundation,
    core model, extension, or synthesis.
    """

    def __init__(self, policy_path: str | Path | None = None) -> None:
        if policy_path is None:
            policy_path = Path(__file__).resolve().parents[2] / "config" / "ref_models" / "modeling_narrative_policy_v1.json"
        self.policy_path = Path(policy_path)
        self.policy = json.loads(self.policy_path.read_text(encoding="utf-8"))

    def plan(self, graph: Any) -> ModelSpine:
        research = [node for node in graph.nodes if getattr(node, "role", "") == "RESEARCH"]
        synthesis = [node for node in graph.nodes if getattr(node, "role", "") == "SYNTHESIS"]
        ids = {str(node.subproblem_id) for node in research}
        descendants = _descendant_map(research)
        direct_dependents = _direct_dependents(research)
        selection = self.policy.get("core_selection", {})
        model_bonus = float(selection.get("model_family_bonus", 2.0))
        reach_weight = float(selection.get("downstream_reach_weight", 1.0))
        dependent_weight = float(selection.get("direct_dependency_weight", 0.5))
        foundation_penalty = float(selection.get("foundation_family_penalty", 1.5))
        scores: dict[str, float] = {}
        for node in research:
            sid = str(node.subproblem_id)
            family = str(getattr(node, "task_family", "") or "")
            is_substantive_model = family not in {"exploratory_analysis", "synthesis"}
            score = (model_bonus if is_substantive_model else -foundation_penalty)
            score += reach_weight * len(descendants.get(sid, set()))
            score += dependent_weight * len(direct_dependents.get(sid, set()))
            scores[sid] = score

        model_candidates = [
            str(node.subproblem_id)
            for node in research
            if str(getattr(node, "task_family", "") or "") not in {"exploratory_analysis", "synthesis"}
        ]
        core_ids: list[str] = []
        if model_candidates:
            best = max(scores[sid] for sid in model_candidates)
            band = float(selection.get("core_score_band", 0.75))
            maximum = int(selection.get("maximum_core_models", 2))
            ranked = sorted(model_candidates, key=lambda sid: (-scores[sid], _node_order(research, sid)))
            for sid in ranked:
                if len(core_ids) >= maximum:
                    break
                if scores[sid] + band < best:
                    continue
                # A node that is already downstream of a selected core is usually
                # an extension, not another headline model.
                if any(core in _ancestor_set(research, sid) for core in core_ids):
                    continue
                core_ids.append(sid)

        budgets = self.policy.get("role_equation_budget", {})
        emphasis = self.policy.get("paper_emphasis", {})
        spine_nodes: list[ModelSpineNode] = []
        resolved_roles: dict[str, ModelingRole] = {}

        for node in research:
            sid = str(node.subproblem_id)
            family = str(getattr(node, "task_family", "") or "")
            deps = [str(value) for value in (getattr(node, "dependencies", []) or []) if str(value) in ids]
            upstream_core = [dep for dep in _ancestor_list(research, sid) if dep in core_ids]
            if sid in core_ids:
                role: ModelingRole = "CORE_MODEL"
                inheritance_kind: InheritanceKind = "EVIDENCE" if deps else "NONE"
                inherits_from = deps
            elif family == "exploratory_analysis" and descendants.get(sid):
                role = "FOUNDATION"
                inheritance_kind = "NONE"
                inherits_from = []
            elif upstream_core:
                role = "EXTENSION"
                inherits_from = _nearest_upstream(upstream_core, deps)
                inheritance_kind = _infer_inheritance_kind(node, research, inherits_from)
            else:
                role = "INDEPENDENT_MODEL"
                inherits_from = deps
                inheritance_kind = "EVIDENCE" if deps else "NONE"
            resolved_roles[sid] = role
            spine_nodes.append(
                ModelSpineNode(
                    subproblem_id=sid,
                    role=role,
                    method=str(getattr(node, "method", "") or ""),
                    task_family=family,
                    dependencies=deps,
                    inherits_from=inherits_from,
                    inheritance_kind=inheritance_kind,
                    downstream_reach=len(descendants.get(sid, set())),
                    core_score=round(scores.get(sid, 0.0), 3),
                    equation_budget=int(budgets.get(role, 2)),
                    paper_emphasis=float(emphasis.get(role, 1.0)),
                    narrative_directive=_directive(role, inheritance_kind, inherits_from),
                )
            )

        for node in synthesis:
            sid = str(node.subproblem_id)
            deps = [str(value) for value in (getattr(node, "dependencies", []) or [])]
            spine_nodes.append(
                ModelSpineNode(
                    subproblem_id=sid,
                    role="SYNTHESIS",
                    method=str(getattr(node, "method", "") or ""),
                    task_family=str(getattr(node, "task_family", "") or "synthesis"),
                    dependencies=deps,
                    inherits_from=deps,
                    inheritance_kind="SYNTHESIS",
                    downstream_reach=0,
                    core_score=0.0,
                    equation_budget=int(budgets.get("SYNTHESIS", 0)),
                    paper_emphasis=float(emphasis.get("SYNTHESIS", 0.7)),
                    narrative_directive="综合前序已验证结果，不新建独立模型。",
                )
            )

        storyline = [_storyline_sentence(item) for item in spine_nodes]
        return ModelSpine(
            case_id=str(getattr(graph, "case_id", "")),
            core_subproblem_ids=core_ids,
            nodes=spine_nodes,
            storyline=storyline,
            generated_at=now_iso(),
        )


def _descendant_map(nodes: list[Any]) -> dict[str, set[str]]:
    direct = _direct_dependents(nodes)
    result: dict[str, set[str]] = {}
    for node in nodes:
        sid = str(node.subproblem_id)
        seen: set[str] = set()
        stack = list(direct.get(sid, set()))
        while stack:
            current = stack.pop()
            if current in seen:
                continue
            seen.add(current)
            stack.extend(direct.get(current, set()) - seen)
        result[sid] = seen
    return result


def _direct_dependents(nodes: list[Any]) -> dict[str, set[str]]:
    ids = {str(node.subproblem_id) for node in nodes}
    result = {sid: set() for sid in ids}
    for node in nodes:
        target = str(node.subproblem_id)
        for dep in getattr(node, "dependencies", []) or []:
            dep = str(dep)
            if dep in ids:
                result.setdefault(dep, set()).add(target)
    return result


def _ancestor_list(nodes: list[Any], subproblem_id: str) -> list[str]:
    by_id = {str(node.subproblem_id): node for node in nodes}
    result: list[str] = []
    seen: set[str] = set()
    stack = list(getattr(by_id[subproblem_id], "dependencies", []) or []) if subproblem_id in by_id else []
    while stack:
        current = str(stack.pop(0))
        if current in seen or current not in by_id:
            continue
        seen.add(current)
        result.append(current)
        stack.extend(getattr(by_id[current], "dependencies", []) or [])
    return result


def _ancestor_set(nodes: list[Any], subproblem_id: str) -> set[str]:
    return set(_ancestor_list(nodes, subproblem_id))


def _nearest_upstream(upstream_core: list[str], direct_dependencies: list[str]) -> list[str]:
    direct = [value for value in direct_dependencies if value in upstream_core]
    return direct or upstream_core[:1]


def _infer_inheritance_kind(node: Any, nodes: list[Any], inherits_from: list[str]) -> InheritanceKind:
    if not inherits_from:
        return "NONE"
    by_id = {str(item.subproblem_id): item for item in nodes}
    own_family = str(getattr(node, "task_family", "") or "")
    own_text = " ".join(
        [str(getattr(node, "title", "") or ""), str(getattr(node, "objective", "") or ""), str(getattr(node, "method", "") or "")]
    ).lower()
    if any(token in own_text for token in ("constraint", "约束", "限额", "数量", "可售", "组合")):
        return "CONSTRAINT"
    if any(token in own_text for token in ("scenario", "情景", "场景", "sensitivity", "敏感性")):
        return "SCENARIO"
    for dep in inherits_from:
        parent = by_id.get(dep)
        if parent is None:
            continue
        parent_family = str(getattr(parent, "task_family", "") or "")
        if parent_family == own_family and own_family not in {"exploratory_analysis", ""}:
            return "MODEL"
        if _method_overlap(str(getattr(parent, "method", "") or ""), str(getattr(node, "method", "") or "")) >= 0.2:
            return "MODEL"
    return "EVIDENCE"


def _method_overlap(left: str, right: str) -> float:
    stop = {"model", "method", "with", "and", "the", "for", "模型", "方法", "优化"}
    tokenize = lambda value: {
        token for token in re.split(r"[^a-z0-9\u4e00-\u9fff]+", value.lower()) if len(token) >= 2 and token not in stop
    }
    a, b = tokenize(left), tokenize(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _node_order(nodes: list[Any], sid: str) -> int:
    for index, node in enumerate(nodes):
        if str(node.subproblem_id) == sid:
            return index
    return len(nodes)


def _directive(role: ModelingRole, kind: InheritanceKind, inherits_from: list[str]) -> str:
    parent = "、".join(inherits_from)
    if role == "FOUNDATION":
        return "本问负责识别数据结构、关键关系或边界，为下游核心模型提供依据；避免堆叠额外模型。"
    if role == "CORE_MODEL":
        return "本问是论文核心模型，应优先呈现决策变量、核心关系/目标函数、关键约束和求解方法。"
    if role == "EXTENSION":
        relation = {
            "MODEL": "继承上游模型结构",
            "CONSTRAINT": "继承上游模型并增加本问约束",
            "SCENARIO": "继承上游模型并改变情景/参数",
            "EVIDENCE": "继承上游已验证结果作为输入",
        }.get(kind, "承接上游结果")
        return f"{relation}（{parent}），突出新增变量、约束或决策层，不重复完整推导。"
    if role == "SYNTHESIS":
        return "综合前序已验证结果，不新建独立模型。"
    return "独立研究节点；仅保留解决本问所必需的模型与验证。"


def _storyline_sentence(node: ModelSpineNode) -> str:
    labels = {
        "FOUNDATION": "作为数据与规律基础",
        "CORE_MODEL": "作为核心建模节点",
        "EXTENSION": "作为上游模型的扩展",
        "INDEPENDENT_MODEL": "作为独立建模节点",
        "SYNTHESIS": "作为综合输出",
    }
    parent = f"，承接{'、'.join(node.inherits_from)}" if node.inherits_from else ""
    return f"{node.subproblem_id}{labels[node.role]}{parent}。"

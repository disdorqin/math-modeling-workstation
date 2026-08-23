from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .c_problem_modeling_priors import CProblemModelingPriorService
from .evidence_expression import EvidenceExpressionPlan, EvidenceExpressionPlanner, WholePaperExpressionPlan
from .hmml import MethodRetriever
from .io_utils import atomic_write_json, now_iso
from .knowledge_cards import KnowledgeCardRetriever
from .modeling_skills import ModelingSkillAdvice, ModelingSkillRetriever
from .model_structure import ModelStructurePlan, ModelStructurePlanner, UnifiedModelFrameworkPlan
from .problem_graph import ProblemGraphService, SubproblemNode
from .research_preferences import ResearchPreferenceProfile, ResearchPreferenceService
from .solver_engine import SolverRegistry


FeasibilityStatus = Literal["PASS", "NEEDS_SOLVER", "REJECT"]
CandidateSource = Literal["native", "hmml", "knowledge_card", "skill"]


class CandidateStrategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    method: str
    source: CandidateSource
    retrieval_score: float = 0.0
    feasibility: FeasibilityStatus
    rationale: str
    model_id: str | None = None
    task_types: list[str] = Field(default_factory=list)


class ModelingBrainDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str
    subproblem_id: str
    task_family: str
    gate: Literal["PASS", "BLOCKED", "SKIP"]
    query: str
    candidates: list[CandidateStrategy] = Field(default_factory=list)
    selected_candidate_ids: list[str] = Field(default_factory=list)
    selected_methods: list[str] = Field(default_factory=list)
    skill_advice: list[ModelingSkillAdvice] = Field(default_factory=list)
    quality_checks: list[str] = Field(default_factory=list)
    avoidance_rules: list[str] = Field(default_factory=list)
    feasibility_summary: dict[str, int] = Field(default_factory=dict)
    c_problem_prior_names: list[str] = Field(default_factory=list)
    research_obligations: list[str] = Field(default_factory=list)
    benchmark_validation_obligations: list[str] = Field(default_factory=list)
    benchmark_forbidden_shortcuts: list[str] = Field(default_factory=list)
    benchmark_prior_source: str | None = None
    model_structure: ModelStructurePlan | None = None
    unified_framework: UnifiedModelFrameworkPlan | None = None
    preference_profile: ResearchPreferenceProfile | None = None
    expression_plan: EvidenceExpressionPlan | None = None
    whole_paper_expression_plan: WholePaperExpressionPlan | None = None
    generated_at: str


class ModelingBrainService:
    """Node-level method retrieval and feasibility criticism.

    Existing HMML and knowledge cards previously influenced only the single
    whole-problem ModelPlan prompt. This service makes them operate on one
    ProblemGraph node at a time. Retrieval can expand the research search space,
    while feasibility status prevents a retrieved method from being treated as
    executable before a solver actually exists.
    """

    def __init__(
        self,
        cases: Any,
        artifacts: Any,
        problem_graphs: ProblemGraphService,
        *,
        hmml: MethodRetriever | None = None,
        cards: KnowledgeCardRetriever | None = None,
        skills: ModelingSkillRetriever | None = None,
        solver_registry: SolverRegistry | None = None,
        c_problem_priors: CProblemModelingPriorService | None = None,
        top_k: int = 4,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.problem_graphs = problem_graphs
        self.hmml = hmml or MethodRetriever(top_k=top_k)
        self.cards = cards or KnowledgeCardRetriever(top_k=top_k)
        self.skills = skills or ModelingSkillRetriever()
        self.solver_registry = solver_registry or SolverRegistry()
        self.c_problem_priors = c_problem_priors
        if self.c_problem_priors is None:
            try:
                self.c_problem_priors = CProblemModelingPriorService.from_default_registry()
            except FileNotFoundError:
                self.c_problem_priors = None
        self.top_k = top_k
        self.structure_planner = ModelStructurePlanner()
        self.expression_planner = EvidenceExpressionPlanner()
        self.preference_service = ResearchPreferenceService(cases, artifacts)

    def deliberate(
        self,
        case_id: str,
        subproblem_id: str,
        *,
        source_artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        graph = self.problem_graphs.load(case_id)
        node = graph.node(subproblem_id)
        decision = self._decide(case_id, node, graph)
        root = self.cases.case_root(case_id)
        path = root / "analysis" / "modeling_brain" / f"{subproblem_id}.json"
        atomic_write_json(path, decision.model_dump(mode="json"))
        artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "modeling_brain_decision",
            "modeling_brain",
            upstream=list(source_artifact_ids or []),
            paper_eligible=False,
        )
        node.plan.modeling_brain_artifact_id = artifact["artifact_id"]
        node.plan.selected_candidate_ids = list(decision.selected_candidate_ids)
        if decision.selected_methods:
            node.plan.candidate_methods = list(
                dict.fromkeys([*decision.selected_methods, *node.plan.candidate_methods])
            )
        _, graph_artifact = self.problem_graphs.save(
            case_id,
            graph,
            [artifact["artifact_id"], *(source_artifact_ids or [])],
            created_by="modeling_brain",
        )
        return {
            "decision": decision,
            "artifact": artifact,
            "graph_artifact": graph_artifact,
        }

    def _decide(self, case_id: str, node: SubproblemNode, graph: Any) -> ModelingBrainDecision:
        query = " ".join(
            [
                node.title,
                node.objective,
                *node.inputs,
                *node.outputs,
                *node.constraints,
                node.task_family,
            ]
        ).strip()
        benchmark = self.c_problem_priors.assess(node, graph) if self.c_problem_priors else None
        preferences = self.preference_service.load(case_id)
        model_structure = self.structure_planner.plan_node(node, graph, preferences)
        unified_framework = self.structure_planner.plan_graph(graph, preferences)
        structures = {
            item.subproblem_id: self.structure_planner.plan_node(item, graph, preferences)
            for item in graph.nodes
        }
        expression_plan = self.expression_planner.plan_node(model_structure, preferences)
        whole_paper_expression_plan = self.expression_planner.plan_paper(structures, unified_framework, preferences)
        if node.execution_kind == "DELIVERABLE":
            return ModelingBrainDecision(
                case_id=case_id,
                subproblem_id=node.subproblem_id,
                task_family=node.task_family,
                gate="SKIP",
                query=query,
                c_problem_prior_names=list(benchmark.prior_names) if benchmark else [],
                research_obligations=list(benchmark.research_obligations) if benchmark else [],
                benchmark_validation_obligations=list(benchmark.validation_obligations) if benchmark else [],
                benchmark_forbidden_shortcuts=list(benchmark.forbidden_shortcuts) if benchmark else [],
                benchmark_prior_source=benchmark.source_registry if benchmark else None,
                model_structure=model_structure,
                unified_framework=unified_framework,
                preference_profile=preferences,
                expression_plan=expression_plan,
                whole_paper_expression_plan=whole_paper_expression_plan,
                generated_at=now_iso(),
            )

        skill_advice = self.skills.retrieve(node.task_family, query)
        candidates = self._native_candidates(node)
        candidates.extend(self._card_candidates(node, query))
        candidates.extend(self._hmml_candidates(node, query))
        candidates.extend(self._skill_candidates(node, skill_advice))
        candidates = _deduplicate_candidates(candidates)
        selected = _select_candidate_set(candidates)
        pass_count = sum(item.feasibility == "PASS" for item in candidates)
        summary = {
            "PASS": pass_count,
            "NEEDS_SOLVER": sum(item.feasibility == "NEEDS_SOLVER" for item in candidates),
            "REJECT": sum(item.feasibility == "REJECT" for item in candidates),
        }
        return ModelingBrainDecision(
            case_id=case_id,
            subproblem_id=node.subproblem_id,
            task_family=node.task_family,
            gate="PASS" if pass_count else "BLOCKED",
            query=query,
            candidates=candidates,
            selected_candidate_ids=[item.candidate_id for item in selected],
            selected_methods=[item.method for item in selected],
            skill_advice=skill_advice,
            quality_checks=list(dict.fromkeys(check for skill in skill_advice for check in skill.quality_checks)),
            avoidance_rules=list(dict.fromkeys(rule for skill in skill_advice for rule in skill.when_not_to_use)),
            feasibility_summary=summary,
            c_problem_prior_names=list(benchmark.prior_names) if benchmark else [],
            research_obligations=list(benchmark.research_obligations) if benchmark else [],
            benchmark_validation_obligations=list(benchmark.validation_obligations) if benchmark else [],
            benchmark_forbidden_shortcuts=list(benchmark.forbidden_shortcuts) if benchmark else [],
            benchmark_prior_source=benchmark.source_registry if benchmark else None,
            model_structure=model_structure,
            unified_framework=unified_framework,
            preference_profile=preferences,
            expression_plan=expression_plan,
            whole_paper_expression_plan=whole_paper_expression_plan,
            generated_at=now_iso(),
        )

    def _native_candidates(self, node: SubproblemNode) -> list[CandidateStrategy]:
        values: list[CandidateStrategy] = []
        for index, method in enumerate(node.plan.candidate_methods, start=1):
            executable = self.solver_registry.supports_method(method, node.task_family)
            status: FeasibilityStatus = "PASS" if executable else "NEEDS_SOLVER"
            rationale = (
                f"SolverRegistry 已有与该方法匹配的 {node.task_family} 插件。"
                if executable
                else "研究路线合理，但当前 SolverRegistry 没有与该具体方法匹配的插件。"
            )
            values.append(
                CandidateStrategy(
                    candidate_id=f"native:{node.subproblem_id}:{index}",
                    method=method,
                    source="native",
                    retrieval_score=max(0.0, 1.0 - index * 0.05),
                    feasibility=status,
                    rationale=rationale,
                )
            )
        return values

    def _card_candidates(self, node: SubproblemNode, query: str) -> list[CandidateStrategy]:
        task_types = _knowledge_task_types(node.task_family)
        cards = self.cards.retrieve(query, task_types=task_types, top_k=self.top_k)
        values: list[CandidateStrategy] = []
        for card in cards:
            model_id = str(card.get("model_id") or "")
            feasibility, reason = _card_feasibility(node.task_family, model_id, self.solver_registry)
            values.append(
                CandidateStrategy(
                    candidate_id=f"card:{model_id or _slug(str(card.get('title') or 'method'))}",
                    method=str(card.get("title") or model_id),
                    source="knowledge_card",
                    retrieval_score=float(card.get("score", 0.0)),
                    feasibility=feasibility,
                    rationale=reason,
                    model_id=model_id or None,
                    task_types=[str(value) for value in card.get("task_types", [])],
                )
            )
        return values

    def _skill_candidates(
        self, node: SubproblemNode, advice: list[ModelingSkillAdvice]
    ) -> list[CandidateStrategy]:
        values: list[CandidateStrategy] = []
        for skill in advice:
            for index, method in enumerate(skill.method_hints):
                feasibility, reason = _skill_feasibility(node.task_family, method, self.solver_registry)
                values.append(
                    CandidateStrategy(
                        candidate_id=f"skill:{skill.name}:{index + 1}:{_slug(method)}",
                        method=method,
                        source="skill",
                        retrieval_score=max(0.0, skill.relevance - index * 0.02),
                        feasibility=feasibility,
                        rationale=f"{skill.name}: {reason}",
                    )
                )
        return values

    def _hmml_candidates(self, node: SubproblemNode, query: str) -> list[CandidateStrategy]:
        values: list[CandidateStrategy] = []
        for item in self.hmml.retrieve(query, top_k=self.top_k):
            method = str(item.get("method") or "")
            feasibility, reason = _hmml_feasibility(node.task_family, method, self.solver_registry)
            values.append(
                CandidateStrategy(
                    candidate_id=f"hmml:{_slug(method)}",
                    method=method,
                    source="hmml",
                    retrieval_score=float(item.get("score", 0.0)),
                    feasibility=feasibility,
                    rationale=reason,
                )
            )
        return values


def _knowledge_task_types(task_family: str) -> list[str]:
    mapping = {
        "forecasting": ["prediction", "regression"],
        "explanatory_inference": ["correlation_analysis", "regression"],
        "distribution_forecasting": ["prediction", "regression"],
        "classification": ["classification"],
        "exploratory_analysis": ["correlation_analysis", "clustering", "dimension_reduction"],
        "optimization": ["optimization"],
        "simulation": ["simulation"],
        "ranking": ["evaluation"],
        "generic_modeling": ["regression", "classification"],
    }
    return mapping.get(task_family, [])


def _card_feasibility(
    task_family: str, model_id: str, registry: SolverRegistry
) -> tuple[FeasibilityStatus, str]:
    if registry.supports_method(model_id, task_family):
        return "PASS", f"SolverRegistry 已有与知识卡 {model_id} 兼容的 {task_family} 插件。"
    return "NEEDS_SOLVER", f"知识卡与 {task_family} 相关，但当前 SolverRegistry 尚未注册 {model_id} 插件。"


def _skill_feasibility(
    task_family: str, method: str, registry: SolverRegistry
) -> tuple[FeasibilityStatus, str]:
    normalized = method.lower()
    if registry.supports_method(method, task_family):
        return "PASS", "Skill 方法提示与当前 SolverRegistry 的同族插件能力匹配。"
    hinted = _method_family_hint(normalized)
    if hinted and hinted != task_family and not _compatible_family_hint(task_family, hinted):
        return "REJECT", f"Skill 方法提示更接近 {hinted}，不应为 {task_family} 节点强行选用。"
    return "NEEDS_SOLVER", "Skill 建议该方法，但当前 Solver Engine 尚无对应插件；保留为后续扩展候选。"


def _hmml_feasibility(
    task_family: str, method: str, registry: SolverRegistry
) -> tuple[FeasibilityStatus, str]:
    lowered = method.lower()
    if registry.supports_method(method, task_family):
        return "PASS", "HMML 方法与当前 SolverRegistry 的同族插件能力匹配。"
    hinted = _method_family_hint(lowered)
    if hinted and hinted != task_family and not _compatible_family_hint(task_family, hinted):
        return "REJECT", f"HMML 方法更接近 {hinted}，与当前节点 {task_family} 研究语义不匹配。"
    return "NEEDS_SOLVER", "HMML 方法与题意相关，但需要 Solver Engine 插件后才能执行，当前只作为候选研究路线。"


def _method_family_hint(text: str) -> str | None:
    rules = (
        ("optimization", ("linear programming", "integer programming", "optimization", "milp")),
        ("classification", ("classification", "logistic", "svm", "support vector")),
        ("simulation", ("monte carlo", "simulation")),
        ("forecasting", ("arima", "forecast", "time series", "exponential smoothing", "holt")),
        ("exploratory_analysis", ("cluster", "pca", "principal component", "dbscan", "k-means")),
    )
    for family, tokens in rules:
        if any(token in text for token in tokens):
            return family
    return None


def _compatible_family_hint(task_family: str, hinted: str) -> bool:
    return (task_family, hinted) in {
        ("distribution_forecasting", "forecasting"),
        ("explanatory_inference", "forecasting"),
        ("exploratory_analysis", "classification"),
    }


def _select_candidate_set(candidates: list[CandidateStrategy], limit: int = 4) -> list[CandidateStrategy]:
    if not candidates:
        return []
    native_pass = [item for item in candidates if item.source == "native" and item.feasibility == "PASS"]
    retrieved_pass = [item for item in candidates if item.source != "native" and item.feasibility == "PASS"]
    retrieved_build = [item for item in candidates if item.source != "native" and item.feasibility == "NEEDS_SOLVER"]
    native_other = [item for item in candidates if item.source == "native" and item.feasibility != "REJECT"]
    for group in (native_pass, retrieved_pass, retrieved_build, native_other):
        group.sort(key=lambda item: item.retrieval_score, reverse=True)
    selected: list[CandidateStrategy] = []
    for group in (native_pass[:1], retrieved_pass[:1], retrieved_build[:2], native_pass[1:], native_other):
        for item in group:
            if item.candidate_id not in {value.candidate_id for value in selected}:
                selected.append(item)
            if len(selected) >= limit:
                return selected
    return selected


def _deduplicate_candidates(candidates: list[CandidateStrategy]) -> list[CandidateStrategy]:
    seen: set[tuple[str, str]] = set()
    result: list[CandidateStrategy] = []
    for item in candidates:
        key = (item.source, item.method.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def _slug(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return normalized[:80] or "method"

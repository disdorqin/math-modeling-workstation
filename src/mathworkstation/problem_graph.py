from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .io_utils import atomic_write_json, now_iso
from .paper_contracts import SubproblemContract


TaskFamily = Literal[
    "forecasting",
    "explanatory_inference",
    "distribution_forecasting",
    "classification",
    "exploratory_analysis",
    "optimization",
    "simulation",
    "ranking",
    "synthesis",
    "generic_modeling",
]

ExecutionKind = Literal["MODEL", "ANALYSIS", "DELIVERABLE"]
ResearchStatus = Literal["PLANNED", "READY", "RUNNING", "COMPLETED", "BLOCKED"]


class DependencyEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_subproblem_id: str
    target_subproblem_id: str
    relation: Literal["DEPENDS_ON", "SYNTHESIZES", "INFORMS"] = "DEPENDS_ON"
    rationale: str = Field(min_length=3)


class SubproblemState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: ResearchStatus = "PLANNED"
    active_plan_id: str | None = None
    experiment_ids: list[str] = Field(default_factory=list)
    evidence_artifact_ids: list[str] = Field(default_factory=list)
    answer_id: str | None = None
    blockers: list[str] = Field(default_factory=list)


class SubproblemPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    plan_id: str
    task_family: TaskFamily
    execution_kind: ExecutionKind
    candidate_methods: list[str] = Field(min_length=1)
    selected_method: str | None = None
    validation_protocol: list[str] = Field(min_length=1)
    requires_model_execution: bool = True
    executor_family: str | None = None
    executor_available: bool = False
    executor_blocker: str | None = None
    modeling_brain_artifact_id: str | None = None
    selected_candidate_ids: list[str] = Field(default_factory=list)


class SubproblemExperiment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    experiment_id: str
    subproblem_id: str
    method: str
    status: ResearchStatus = "PLANNED"
    validation_protocol: list[str] = Field(default_factory=list)
    validation_artifact_ids: list[str] = Field(default_factory=list)
    evidence_artifact_ids: list[str] = Field(default_factory=list)


class SubproblemAnswer(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_id: str
    subproblem_id: str
    method: str
    answer: str
    limitation: str
    evidence_artifact_ids: list[str] = Field(default_factory=list)


class SubproblemNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subproblem_id: str
    title: str
    objective: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    task_family: TaskFamily
    execution_kind: ExecutionKind
    dependencies: list[str] = Field(default_factory=list)
    plan: SubproblemPlan
    state: SubproblemState = Field(default_factory=SubproblemState)
    experiments: list[SubproblemExperiment] = Field(default_factory=list)
    answer: SubproblemAnswer | None = None

    @model_validator(mode="after")
    def validate_execution_semantics(self) -> "SubproblemNode":
        if self.execution_kind == "DELIVERABLE" and self.plan.requires_model_execution:
            raise ValueError("deliverable nodes cannot require model execution")
        if self.task_family == "synthesis" and self.execution_kind != "DELIVERABLE":
            raise ValueError("synthesis nodes must be deliverables")
        return self


class ProblemGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    nodes: list[SubproblemNode] = Field(min_length=1)
    edges: list[DependencyEdge] = Field(default_factory=list)
    generated_at: str

    @model_validator(mode="after")
    def validate_graph(self) -> "ProblemGraph":
        node_ids = [node.subproblem_id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("problem graph requires unique subproblem ids")
        known = set(node_ids)
        for edge in self.edges:
            if edge.source_subproblem_id not in known or edge.target_subproblem_id not in known:
                raise ValueError("problem graph edge references unknown subproblem")
            if edge.source_subproblem_id == edge.target_subproblem_id:
                raise ValueError("problem graph cannot contain self dependency")
        return self

    def node(self, subproblem_id: str) -> SubproblemNode:
        for item in self.nodes:
            if item.subproblem_id == subproblem_id:
                return item
        raise KeyError(f"subproblem not found: {subproblem_id}")


class ProblemGraphAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    structure_gate: Literal["PASS", "FAIL"]
    research_gate: Literal["PASS", "INCOMPLETE", "FAIL"]
    findings: list[dict[str, str]] = Field(default_factory=list)
    checked_at: str


class ProblemGraphBuilder:
    """Deterministically lift flat SubproblemContract records into research nodes.

    The builder does not solve a subproblem. Its job is to stop the pipeline from
    silently treating every question as the same supervised-learning task. It
    classifies the research family, assigns an execution semantic, proposes a
    family-specific method/validation envelope, and makes synthesis deliverables
    depend on the research questions they summarize.
    """

    def build(self, subproblems: list[SubproblemContract]) -> ProblemGraph:
        if not subproblems:
            raise ValueError("problem graph requires at least one subproblem")
        nodes = [self._node(contract) for contract in subproblems]
        edges: list[DependencyEdge] = _infer_contract_dependencies(nodes, subproblems)
        research_ids = [node.subproblem_id for node in nodes if node.execution_kind != "DELIVERABLE"]
        for node in nodes:
            if node.task_family != "synthesis":
                continue
            node.dependencies = list(research_ids)
            for source_id in research_ids:
                edges.append(
                    DependencyEdge(
                        source_subproblem_id=source_id,
                        target_subproblem_id=node.subproblem_id,
                        relation="SYNTHESIZES",
                        rationale="交付物只能综合已完成研究子问题的已接受结论与证据。",
                    )
                )
        return ProblemGraph(nodes=nodes, edges=edges, generated_at=now_iso())

    def _node(self, contract: SubproblemContract) -> SubproblemNode:
        family = _infer_task_family(contract)
        execution_kind = _execution_kind(family)
        methods, validation = _research_envelope(family)
        plan_id = f"plan-{contract.subproblem_id}"
        experiments = []
        if execution_kind != "DELIVERABLE":
            experiments.append(
                SubproblemExperiment(
                    experiment_id=f"experiment-{contract.subproblem_id}-planned",
                    subproblem_id=contract.subproblem_id,
                    method=methods[0],
                    status="PLANNED",
                    validation_protocol=list(validation),
                )
            )
        return SubproblemNode(
            subproblem_id=contract.subproblem_id,
            title=contract.title,
            objective=contract.objective,
            inputs=list(contract.inputs),
            outputs=list(contract.outputs),
            constraints=list(contract.constraints),
            task_family=family,
            execution_kind=execution_kind,
            plan=SubproblemPlan(
                plan_id=plan_id,
                task_family=family,
                execution_kind=execution_kind,
                candidate_methods=methods,
                validation_protocol=validation,
                requires_model_execution=execution_kind == "MODEL",
                executor_family=_executor_family(family),
                executor_available=_executor_family(family) is not None,
                executor_blocker=(
                    None
                    if execution_kind == "DELIVERABLE" or _executor_family(family) is not None
                    else f"no dedicated executor registered for {family}"
                ),
            ),
            state=SubproblemState(
                status="PLANNED",
                active_plan_id=plan_id,
                evidence_artifact_ids=[],
            ),
            experiments=experiments,
        )


def _infer_contract_dependencies(
    nodes: list[SubproblemNode],
    contracts: list[SubproblemContract],
) -> list[DependencyEdge]:
    """Infer only high-confidence research dependencies from the prompt contracts.

    This replaces the old assumption that cross-question links must be written by
    a problem-specific gate.  It intentionally uses strong textual evidence only:
    explicit subproblem/question references or phrases such as "基于上一问".  A
    shared task family by itself is never enough to create an edge.
    """

    by_id = {node.subproblem_id: node for node in nodes}
    order = {node.subproblem_id: index for index, node in enumerate(nodes)}
    research_ids = [node.subproblem_id for node in nodes if node.execution_kind != "DELIVERABLE"]
    edges: list[DependencyEdge] = []
    for contract, node in zip(contracts, nodes):
        if node.execution_kind == "DELIVERABLE":
            continue
        current_index = order[node.subproblem_id]
        previous_research = [sid for sid in research_ids if order[sid] < current_index]
        if not previous_research:
            continue
        text = " ".join(
            [
                contract.title,
                contract.objective,
                *contract.inputs,
                *contract.constraints,
            ]
        )
        normalized = text.lower()
        dependencies: list[str] = []

        # Explicit IDs such as SP1, II-A, or exact subproblem identifiers are the
        # strongest signal because they originate in the parsed task contract.
        for sid in previous_research:
            if re.search(rf"(?<![A-Za-z0-9]){re.escape(sid.lower())}(?![A-Za-z0-9])", normalized):
                dependencies.append(sid)
                continue
            number = _question_number_from_id(sid)
            if number is not None and _mentions_question_number(normalized, number):
                dependencies.append(sid)

        # Natural-language inheritance without an explicit number is resolved to
        # the nearest previous research node, which mirrors how competition prompts
        # phrase "在上一问基础上" or "using the previous result".
        if not dependencies and _mentions_previous_question(normalized):
            dependencies.append(previous_research[-1])

        for dep in dict.fromkeys(dependencies):
            if dep == node.subproblem_id or dep not in by_id:
                continue
            node.dependencies.append(dep)
            edges.append(
                DependencyEdge(
                    source_subproblem_id=dep,
                    target_subproblem_id=node.subproblem_id,
                    relation="DEPENDS_ON",
                    rationale="题目/子问题契约明确引用前序问题或其结果，后续建模应承接该已验证输出。",
                )
            )
        node.dependencies = list(dict.fromkeys(node.dependencies))
    return edges


def _question_number_from_id(value: str) -> int | None:
    match = re.search(r"(\d+)$", str(value))
    return int(match.group(1)) if match else None


def _mentions_question_number(text: str, number: int) -> bool:
    patterns = (
        rf"问题\s*{number}(?!\d)",
        rf"第\s*{number}\s*问",
        rf"question\s*{number}(?!\d)",
        rf"q\s*{number}(?!\d)",
    )
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _mentions_previous_question(text: str) -> bool:
    tokens = (
        "上一问",
        "前一问",
        "前问",
        "在此基础上",
        "基于上述",
        "根据上述",
        "基于前述",
        "previous question",
        "previous result",
        "based on the above",
        "building on the above",
    )
    return any(token in text for token in tokens)


def assess_problem_graph(graph: ProblemGraph) -> ProblemGraphAssessment:
    findings: list[dict[str, str]] = []
    structure_failed = False
    research_incomplete = False
    research_failed = False
    research_nodes = [node for node in graph.nodes if node.execution_kind != "DELIVERABLE"]
    if len(research_nodes) > 1 and len({node.task_family for node in research_nodes}) == 1:
        # A shared task family is not itself evidence of flattening.  CUMCM C
        # problems often form a legitimate multi-stage chain inside one family
        # (for example: general optimization -> constrained scenario -> refined
        # cost optimization).  Only near-identical semantic nodes are blocked.
        semantic_signatures = {
            " ".join((node.title + " " + node.objective).lower().split())
            for node in research_nodes
        }
        if len(semantic_signatures) == 1:
            structure_failed = True
            findings.append(
                {
                    "code": "SUBPROBLEMS_FLATTENED_TO_ONE_FAMILY",
                    "detail": "多个研究子问题不仅 task family 相同，而且标题/目标也没有形成可区分的研究任务。",
                }
            )
    known = {node.subproblem_id: node for node in graph.nodes}
    for node in graph.nodes:
        if node.execution_kind == "DELIVERABLE":
            if node.plan.requires_model_execution:
                structure_failed = True
                findings.append(
                    {
                        "code": "DELIVERABLE_REQUIRES_MODEL_EXECUTION",
                        "detail": f"{node.subproblem_id} 是交付物却被配置为训练节点。",
                    }
                )
            if not node.dependencies:
                structure_failed = True
                findings.append(
                    {
                        "code": "DELIVERABLE_DEPENDENCY_MISSING",
                        "detail": f"{node.subproblem_id} 缺少前序研究依赖。",
                    }
                )
            if node.state.status == "COMPLETED":
                incomplete_dependencies = [
                    dependency
                    for dependency in node.dependencies
                    if known[dependency].state.status != "COMPLETED"
                ]
                if incomplete_dependencies:
                    research_failed = True
                    findings.append(
                        {
                            "code": "DELIVERABLE_COMPLETED_BEFORE_DEPENDENCIES",
                            "detail": f"{node.subproblem_id} 在依赖 {','.join(incomplete_dependencies)} 完成前被标记完成。",
                        }
                    )
        if node.state.status == "COMPLETED":
            if node.answer is None or not node.state.evidence_artifact_ids:
                research_failed = True
                findings.append(
                    {
                        "code": "COMPLETED_WITHOUT_ANSWER_OR_EVIDENCE",
                        "detail": f"{node.subproblem_id} 完成状态缺少独立 answer/evidence。",
                    }
                )
        else:
            research_incomplete = True
            findings.append(
                {
                    "code": "SUBPROBLEM_RESEARCH_INCOMPLETE",
                    "detail": f"{node.subproblem_id} 当前研究状态为 {node.state.status}。",
                }
            )
    return ProblemGraphAssessment(
        structure_gate="FAIL" if structure_failed else "PASS",
        research_gate="FAIL" if research_failed else ("INCOMPLETE" if research_incomplete else "PASS"),
        findings=findings,
        checked_at=now_iso(),
    )


class ProblemGraphService:
    def __init__(self, cases: CaseManager, artifacts: ArtifactRegistry) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.builder = ProblemGraphBuilder()

    def assess(self, graph: ProblemGraph) -> ProblemGraphAssessment:
        return assess_problem_graph(graph)

    def load(self, case_id: str) -> ProblemGraph:
        path = self.cases.case_root(case_id) / "analysis" / "problem_graph.json"
        if not path.is_file():
            raise FileNotFoundError(f"problem graph not found: {case_id}")
        import json

        return ProblemGraph.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def persist(
        self,
        case_id: str,
        subproblems: list[SubproblemContract],
        source_artifact_ids: list[str],
    ) -> tuple[ProblemGraph, dict]:
        graph = self.builder.build(subproblems)
        return self.save(case_id, graph, source_artifact_ids)

    def save(
        self,
        case_id: str,
        graph: ProblemGraph,
        source_artifact_ids: list[str] | None = None,
        *,
        created_by: str = "python",
    ) -> tuple[ProblemGraph, dict]:
        """Persist the latest research state plus an explicit gate assessment."""
        root = self.cases.case_root(case_id)
        path = root / "analysis" / "problem_graph.json"
        atomic_write_json(path, graph.model_dump(mode="json"))
        artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "problem_graph",
            created_by,
            upstream=list(source_artifact_ids or []),
            paper_eligible=False,
        )
        assessment = self.assess(graph)
        assessment_path = root / "review" / "problem_graph" / "assessment.json"
        atomic_write_json(assessment_path, assessment.model_dump(mode="json"))
        assessment_artifact = self.artifacts.register_existing(
            case_id,
            assessment_path.relative_to(root).as_posix(),
            "problem_graph_assessment",
            created_by,
            upstream=[artifact["artifact_id"]],
            paper_eligible=False,
        )
        artifact["assessment_artifact_id"] = assessment_artifact["artifact_id"]
        artifact["structure_gate"] = assessment.structure_gate
        artifact["research_gate"] = assessment.research_gate
        return graph, artifact


def _contract_text(contract: SubproblemContract) -> str:
    return " ".join(
        [
            contract.title,
            contract.objective,
            *contract.inputs,
            *contract.outputs,
            *contract.constraints,
        ]
    ).lower()


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    return any(term in text for term in terms)


def _infer_task_family(contract: SubproblemContract) -> TaskFamily:
    text = _contract_text(contract)

    # Deliverables are checked first so "summarize prediction results in a letter"
    # cannot accidentally become another forecasting model.
    if _contains_any(
        text,
        (
            "letter",
            "editor",
            "memo",
            "brief",
            "write summary",
            "summary letter",
            "recommendation report",
            "actions the",
            "actions might",
            "policy actions",
            "致编辑",
            "信函",
            "总结信",
            "报告撰写",
        ),
    ):
        return "synthesis"
    if _contains_any(
        text,
        (
            "optimize", "optimization", "maximiz", "minimiz",
            "最优", "优化", "最大化", "最小化",
            "总费用最小", "总费用最省", "费用最小", "费用最省", "最小费用", "最低费用", "最少总费用",
            "成本最小", "成本最低", "收益最大", "利润最大", "最优布局", "布局优化", "最经济", "损耗最少",
        ),
    ):
        return "optimization"
    if _contains_any(text, ("rank", "ranking", "best profile", "which state", "评价排序", "排序", "最佳", "最优画像")):
        return "ranking"
    if _contains_any(text, ("simulate", "simulation", "monte carlo", "仿真", "模拟")):
        return "simulation"
    if _contains_any(text, ("distribution", "1 try", "2 tries", "6 tries", "future word", "结果分布", "概率分布")) and _contains_any(
        text, ("predict", "forecast", "future", "预测", "未来")
    ):
        return "distribution_forecasting"
    if _contains_any(text, ("classify", "classification", "difficulty", "category", "难度", "分类")):
        return "classification"
    if _contains_any(text, ("effect", "influence", "impact", "attribute", "association", "影响", "效应", "属性", "相关")):
        return "explanatory_inference"
    if _contains_any(text, ("determine", "set", "establish")) and _contains_any(
        text, ("target", "targets", "goal", "goals", "usage target", "政策目标", "目标值")
    ):
        return "optimization"
    if _contains_any(text, ("explore", "interesting", "discover", "pattern", "other feature", "create an energy profile", "create a profile", "探索", "有趣", "发现", "其它特征", "其他特征", "画像")):
         return "exploratory_analysis"
    if _contains_any(text, ("evolved", "evolution", "historical evolution", "演化", "演变")):
        return "forecasting"
        return "exploratory_analysis"
    if _contains_any(text, ("predict", "forecast", "future", "daily", "date", "time", "预测", "未来", "每日", "日期", "时序", "时间")):
        return "forecasting"
    return "generic_modeling"


def _executor_family(family: TaskFamily) -> str | None:
    if family in {
        "forecasting",
        "classification",
        "optimization",
        "simulation",
        "ranking",
        "explanatory_inference",
        "distribution_forecasting",
        "exploratory_analysis",
    }:
        return family
    return None


def _execution_kind(family: TaskFamily) -> ExecutionKind:
    if family == "synthesis":
        return "DELIVERABLE"
    if family in {"explanatory_inference", "exploratory_analysis"}:
        return "ANALYSIS"
    return "MODEL"


def _research_envelope(family: TaskFamily) -> tuple[list[str], list[str]]:
    envelopes: dict[str, tuple[list[str], list[str]]] = {
        "forecasting": (
            [
                "ridge time trend with residual bootstrap interval",
                "change-point-aware time-series model",
                "ARIMA/ETS or other dedicated forecasting plugin",
            ],
            ["temporal split / rolling-origin validation", "forecast error + interval coverage", "change-point and residual diagnostics"],
        ),
        "explanatory_inference": (
            [
                "standardized ridge effect estimation with bootstrap intervals",
                "partial effects or permutation-importance model",
                "causal/semiparametric effect model when assumptions are justified",
            ],
            ["effect direction and magnitude", "uncertainty/significance or bootstrap interval", "robustness to feature specification"],
        ),
        "distribution_forecasting": (
            [
                "multi-output ridge with simplex projection",
                "compositional/log-ratio or Dirichlet-style model",
                "probabilistic ensemble with calibrated simplex output",
            ],
            ["temporal/out-of-sample validation", "distribution error + simplex constraint", "prediction uncertainty / calibration"],
        ),
        "classification": (
            [
                "logistic regression classification baseline with future prediction",
                "ordinal classifier when category order is intrinsic",
                "tree/ensemble classifier with calibrated probabilities",
            ],
            ["stratified or temporal cross-validation as appropriate", "macro-F1/balanced accuracy", "calibration and per-class error analysis"],
        ),
        "exploratory_analysis": (
            [
                "Spearman association + IQR outlier + mean-shift scan",
                "clustering/change-point pattern discovery",
                "hypothesis generation followed by resampling confirmation",
            ],
            ["novelty relative to earlier subproblems", "effect size/pattern strength", "resampling or holdout confirmation"],
        ),
        "optimization": (
            ["bounded-grid optimization for small constrained models", "LP/MILP/NLP formulation with dedicated solver plugin", "multiobjective or scenario optimization"],
            ["feasibility and constraint audit", "objective comparison", "sensitivity/scenario robustness"],
        ),
        "simulation": (
            ["Monte Carlo additive-normal scenario simulation", "discrete-event/difference-equation simulation", "scenario stress testing"],
            ["replication stability", "uncertainty interval", "scenario sensitivity"],
        ),
        "ranking": (
            ["pairwise/listwise ranking evaluation", "multi-criteria evaluation", "learning-to-rank or robust aggregation"],
            ["rank stability", "sensitivity to weights", "held-out or expert consistency"],
        ),
        "synthesis": (
            ["evidence synthesis from accepted subproblem answers", "audience-targeted deliverable drafting", "claim/evidence consistency check"],
            ["all dependencies completed", "every quantitative claim traceable", "deliverable-specific format/compliance review"],
        ),
        "generic_modeling": (
            ["baseline model family", "task-specific alternative", "complexity-controlled comparison"],
            ["task-appropriate holdout/cross-validation", "robustness analysis", "failure-case diagnostics"],
        ),
    }
    return envelopes[family]

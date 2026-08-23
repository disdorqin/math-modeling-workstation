from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .evidence_expression import EvidenceExpressionPlan, EvidenceExpressionPlanner
from .io_utils import atomic_write_json, atomic_write_text, now_iso, read_json
from .model_structure import ModelStructurePlan, ModelStructurePlanner
from .problem_graph import ProblemGraphService, assess_problem_graph
from .research_preferences import ResearchPreferenceService
from .research_state_graphs import EvidenceGraphService, ModelGraphService
from .semantic_alternative_compatibility import SemanticAlternativeCompatibility


NarrativeRole = Literal["RESEARCH", "SYNTHESIS"]
NarrativeGate = Literal["PASS", "BLOCKED"]


class NarrativeResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    value: float
    direction: str
    model_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class NarrativeCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    method: str
    source: str
    feasibility: str
    rationale: str
    selected: bool = False
    comparison_compatible: bool = False
    comparison_compatibility: dict[str, bool] = Field(default_factory=dict)
    comparison_rationale: str = ""


class NarrativeAlternativeComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary_metric: str
    decision: str
    accepted_method: str
    alternative_methods: list[str] = Field(default_factory=list)
    best_method: str
    robust_best_method: str | None = None
    rationale: str
    stress_test_sizes: list[float] = Field(default_factory=list)
    stress_runs: list[dict[str, Any]] = Field(default_factory=list)


class NarrativeNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subproblem_id: str
    title: str
    role: NarrativeRole
    task_family: str
    objective: str
    dependencies: list[str] = Field(default_factory=list)
    method: str
    answer: str
    limitation: str
    key_results: list[NarrativeResult] = Field(default_factory=list)
    validation_gate: str | None = None
    validation_protocol_id: str | None = None
    result_ids: list[str] = Field(default_factory=list)
    table_ids: list[str] = Field(default_factory=list)
    figure_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    candidate_considerations: list[NarrativeCandidate] = Field(default_factory=list)
    model_structure: ModelStructurePlan | None = None
    expression_plan: EvidenceExpressionPlan | None = None
    data_columns: list[str] = Field(default_factory=list)
    preprocessing_notes: list[str] = Field(default_factory=list)
    alternative_comparison: NarrativeAlternativeComparison | None = None
    source_artifact_ids: list[str] = Field(default_factory=list)
    gate: NarrativeGate
    blockers: list[str] = Field(default_factory=list)


class NarrativeGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str
    gate: NarrativeGate
    research_gate: str
    model_graph_gate: str
    evidence_graph_gate: str
    nodes: list[NarrativeNode]
    storyline: list[str]
    source_artifact_ids: list[str] = Field(default_factory=list)
    generated_at: str

    def node(self, subproblem_id: str) -> NarrativeNode:
        for item in self.nodes:
            if item.subproblem_id == subproblem_id:
                return item
        raise KeyError(f"narrative node not found: {subproblem_id}")


class NarrativeGraphService:
    """Build the paper-facing storyline from accepted Research State.

    This layer deliberately sits between evidence registries and prose. It keeps
    internal ids for provenance, but the rendered preview never exposes those
    ids. A node cannot become narrative-PASS merely because a section template
    exists: it needs the corresponding accepted subproblem answer and, for
    research nodes, active numeric evidence plus non-failing validation.
    """

    def __init__(
        self,
        cases: Any,
        artifacts: Any,
        contracts: Any,
        claims: Any,
        figures: Any,
        problem_graphs: ProblemGraphService | None = None,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.contracts = contracts
        self.claims = claims
        self.figures = figures
        self.problem_graphs = problem_graphs or ProblemGraphService(cases, artifacts)
        self.model_graphs = ModelGraphService(cases, artifacts, self.problem_graphs)
        self.alternative_compatibility = SemanticAlternativeCompatibility()
        self.model_structure_planner = ModelStructurePlanner()
        self.expression_planner = EvidenceExpressionPlanner()
        self.preference_service = ResearchPreferenceService(cases, artifacts)
        self.evidence_graphs = EvidenceGraphService(
            cases,
            artifacts,
            contracts,
            claims,
            figures,
            self.problem_graphs,
            self.model_graphs,
        )

    def build(self, case_id: str) -> NarrativeGraph:
        graph = self.problem_graphs.load(case_id)
        research_assessment = assess_problem_graph(graph)
        model_graph = self.model_graphs.build(case_id)
        evidence_graph = self.evidence_graphs.build(case_id, model_graph)
        results = self.contracts.list_results(case_id, active_only=True)
        tables = self.contracts.list_tables(case_id, active_only=True)
        answers = {item.subproblem_id: item for item in self.contracts.list_answers(case_id)}
        claims = self.claims.list_claims(case_id)
        figures = self.figures.list_figures(case_id)

        result_by_sp: dict[str, list[Any]] = {}
        for result in results:
            subproblem_id = str(result.metadata.get("subproblem_id") or "")
            if subproblem_id:
                result_by_sp.setdefault(subproblem_id, []).append(result)

        table_by_sp: dict[str, list[Any]] = {}
        result_owner = {
            item.result_id: str(item.metadata.get("subproblem_id") or "")
            for item in results
        }
        for table in tables:
            owners = {result_owner.get(result_id, "") for result_id in table.result_ids}
            owners.discard("")
            for owner in owners:
                table_by_sp.setdefault(owner, []).append(table)

        figure_by_sp: dict[str, list[dict[str, Any]]] = {}
        for figure in figures:
            subproblem_id = str((figure.get("parameters") or {}).get("subproblem_id") or "")
            if subproblem_id:
                figure_by_sp.setdefault(subproblem_id, []).append(figure)

        claim_by_sp: dict[str, list[dict[str, Any]]] = {}
        for claim in claims:
            for subproblem_id in claim.get("subproblem_ids", []):
                claim_by_sp.setdefault(str(subproblem_id), []).append(claim)

        nodes: list[NarrativeNode] = []
        all_sources: list[str] = []
        for problem_node in graph.nodes:
            subproblem_id = problem_node.subproblem_id
            answer = answers.get(subproblem_id)
            node_results = result_by_sp.get(subproblem_id, [])
            node_tables = table_by_sp.get(subproblem_id, [])
            node_figures = [
                item for item in figure_by_sp.get(subproblem_id, [])
                if item.get("status") == "FINAL"
            ]
            node_claims = claim_by_sp.get(subproblem_id, [])
            validation_gate, protocol_id, validation_sources = self._validation_state(case_id, problem_node)
            candidate_considerations = self._candidate_considerations(case_id, problem_node, method_hint=(answer.method if answer else None))
            model_structure, expression_plan, modeling_sources = self._modeling_plans(case_id, problem_node, graph)
            data_columns, preprocessing_notes = self._solver_data_context(case_id, problem_node)
            alternative_comparison, comparison_source = self._alternative_comparison(case_id, subproblem_id)
            source_artifact_ids = list(
                dict.fromkeys(
                    [
                        *(answer.source_artifact_ids if answer else []),
                        *[value for result in node_results for value in result.source_artifact_ids],
                        *[value for table in node_tables for value in table.source_artifact_ids],
                        *[value for figure in node_figures for value in figure.get("source_artifact_ids", [])],
                        *validation_sources,
                        *comparison_source,
                        *modeling_sources,
                    ]
                )
            )
            all_sources.extend(source_artifact_ids)

            blockers: list[str] = []
            model_state = model_graph.node(subproblem_id)
            evidence_state = evidence_graph.node(subproblem_id)
            if model_state.gate != "PASS":
                blockers.extend(f"MODEL_GRAPH:{value}" for value in model_state.blockers)
            if evidence_state.gate != "PASS":
                blockers.extend(f"EVIDENCE_GRAPH:{value}" for value in evidence_state.blockers)
            if answer is None:
                blockers.append("SUBPROBLEM_ANSWER_MISSING")
            if problem_node.execution_kind != "DELIVERABLE":
                if not node_results:
                    blockers.append("ACTIVE_RESULT_MISSING")
                if validation_gate in {None, "FAIL", "BLOCK"}:
                    blockers.append("VALIDATION_NOT_ACCEPTED")
            else:
                incomplete = [
                    dependency
                    for dependency in problem_node.dependencies
                    if not any(item.subproblem_id == dependency and item.gate == "PASS" for item in nodes)
                ]
                if incomplete:
                    blockers.append("SYNTHESIS_DEPENDENCY_NOT_READY:" + ",".join(incomplete))

            key_results = [
                NarrativeResult(
                    metric=result.metric,
                    value=float(result.value),
                    direction=result.direction,
                    model_name=result.model_name,
                    metadata=dict(result.metadata),
                )
                for result in node_results
            ]
            method = (
                answer.method
                if answer is not None
                else str(problem_node.plan.selected_method or problem_node.plan.candidate_methods[0])
            )
            nodes.append(
                NarrativeNode(
                    subproblem_id=subproblem_id,
                    title=problem_node.title,
                    role="SYNTHESIS" if problem_node.execution_kind == "DELIVERABLE" else "RESEARCH",
                    task_family=problem_node.task_family,
                    objective=problem_node.objective,
                    dependencies=list(problem_node.dependencies),
                    method=method,
                    answer=(answer.answer if answer is not None else ""),
                    limitation=(answer.limitation if answer is not None else ""),
                    key_results=key_results,
                    validation_gate=validation_gate,
                    validation_protocol_id=protocol_id,
                    result_ids=[item.result_id for item in node_results],
                    table_ids=[item.table_id for item in node_tables],
                    figure_ids=[item["figure_id"] for item in node_figures],
                    claim_ids=[item["claim_id"] for item in node_claims if item.get("status") == "VERIFIED"],
                    candidate_considerations=candidate_considerations,
                    model_structure=model_structure,
                    expression_plan=expression_plan,
                    data_columns=data_columns,
                    preprocessing_notes=preprocessing_notes,
                    alternative_comparison=alternative_comparison,
                    source_artifact_ids=source_artifact_ids,
                    gate="BLOCKED" if blockers else "PASS",
                    blockers=blockers,
                )
            )

        narrative_gate: NarrativeGate = (
            "PASS"
            if (
                research_assessment.research_gate == "PASS"
                and model_graph.gate == "PASS"
                and evidence_graph.gate == "PASS"
                and all(item.gate == "PASS" for item in nodes)
            )
            else "BLOCKED"
        )
        return NarrativeGraph(
            case_id=case_id,
            gate=narrative_gate,
            research_gate=research_assessment.research_gate,
            model_graph_gate=model_graph.gate,
            evidence_graph_gate=evidence_graph.gate,
            nodes=nodes,
            storyline=[item.subproblem_id for item in nodes],
            source_artifact_ids=list(dict.fromkeys(all_sources)),
            generated_at=now_iso(),
        )

    def build_and_persist(self, case_id: str) -> dict[str, Any]:
        model_result = self.model_graphs.build_and_persist(case_id)
        evidence_result = self.evidence_graphs.build_and_persist(case_id, model_result["graph"])
        graph = self.build(case_id)
        root = self.cases.case_root(case_id)
        json_path = root / "paper" / "narrative" / "narrative_graph.json"
        preview_path = root / "paper" / "narrative" / "narrative_preview.md"
        atomic_write_json(json_path, graph.model_dump(mode="json"))
        atomic_write_text(preview_path, render_narrative_preview(graph))
        artifact = self.artifacts.register_existing(
            case_id,
            json_path.relative_to(root).as_posix(),
            "narrative_graph",
            "narrative_graph",
            upstream=list(dict.fromkeys([
                *graph.source_artifact_ids,
                model_result["artifact"]["artifact_id"],
                evidence_result["artifact"]["artifact_id"],
            ])),
            paper_eligible=False,
        )
        preview = self.artifacts.register_existing(
            case_id,
            preview_path.relative_to(root).as_posix(),
            "narrative_preview",
            "narrative_graph",
            upstream=[artifact["artifact_id"]],
            paper_eligible=False,
        )
        return {
            "graph": graph,
            "model_graph": model_result,
            "evidence_graph": evidence_result,
            "artifact": artifact,
            "preview_artifact": preview,
        }

    def _modeling_plans(
        self,
        case_id: str,
        problem_node: Any,
        graph: Any,
    ) -> tuple[ModelStructurePlan | None, EvidenceExpressionPlan | None, list[str]]:
        """Load ModelingBrain structure plans, with a deterministic paper-safe fallback.

        The normal AutoPipeline path persists model_structure/expression_plan inside
        the ModelingBrain decision.  Some validated legacy/showcase paths build a
        ProblemGraph and accepted evidence directly.  Those paths must not silently
        lose mathematical structure at paper time, so we reconstruct the same
        deterministic plan from ProblemGraph + case preferences.  The fallback does
        not select a solver or invent evidence; it only restores document-facing
        structure that is derivable from already registered problem semantics.
        """
        artifact_id = problem_node.plan.modeling_brain_artifact_id
        if artifact_id:
            try:
                artifact = self.artifacts.get(case_id, artifact_id)
                payload = read_json(self.cases.case_root(case_id) / artifact["path"])
                structure_payload = payload.get("model_structure")
                expression_payload = payload.get("expression_plan")
                structure = ModelStructurePlan.model_validate(structure_payload) if structure_payload else None
                expression = EvidenceExpressionPlan.model_validate(expression_payload) if expression_payload else None
                if structure is not None:
                    if expression is None:
                        preferences = self.preference_service.load(case_id)
                        expression = self.expression_planner.plan_node(structure, preferences)
                    return structure, expression, [artifact_id]
            except (KeyError, OSError, ValueError):
                pass

        preferences = self.preference_service.load(case_id)
        structure = self.model_structure_planner.plan_node(problem_node, graph, preferences)
        expression = self.expression_planner.plan_node(structure, preferences)
        return structure, expression, []

    def _candidate_considerations(
        self,
        case_id: str,
        problem_node: Any,
        *,
        method_hint: str | None = None,
    ) -> list[NarrativeCandidate]:
        if problem_node.execution_kind == "DELIVERABLE":
            return []
        selected_method = str(method_hint or problem_node.plan.selected_method or "")
        artifact_id = problem_node.plan.modeling_brain_artifact_id
        values: list[NarrativeCandidate] = []
        if artifact_id:
            try:
                artifact = self.artifacts.get(case_id, artifact_id)
                payload = read_json(self.cases.case_root(case_id) / artifact["path"])
                selected_ids = {str(value) for value in payload.get("selected_candidate_ids", [])}
                for candidate in payload.get("candidates", []):
                    candidate_id = str(candidate.get("candidate_id") or "")
                    method = str(candidate.get("method") or "")
                    if not method:
                        continue
                    compatibility = self.alternative_compatibility.assess(
                        problem_node,
                        method,
                        accepted_method=selected_method,
                    )
                    values.append(
                        NarrativeCandidate(
                            method=method,
                            source=str(candidate.get("source") or "modeling_brain"),
                            feasibility=str(candidate.get("feasibility") or "UNKNOWN"),
                            rationale=str(candidate.get("rationale") or "Candidate considered by Modeling Brain."),
                            selected=(
                                candidate_id in selected_ids
                                or _method_equivalent(method, selected_method)
                            ),
                            comparison_compatible=compatibility.comparable,
                            comparison_compatibility={
                                "input": compatibility.input_compatible,
                                "representation": compatibility.representation_compatible,
                                "constraint": compatibility.constraint_compatible,
                                "protocol": compatibility.protocol_comparable,
                            },
                            comparison_rationale=compatibility.rationale,
                        )
                    )
            except (KeyError, OSError, ValueError):
                values = []
        if not values:
            for method in problem_node.plan.candidate_methods:
                compatibility = self.alternative_compatibility.assess(
                    problem_node,
                    str(method),
                    accepted_method=selected_method,
                )
                values.append(
                    NarrativeCandidate(
                        method=str(method),
                        source="problem_graph_plan",
                        feasibility="PLANNED",
                        rationale=(
                            "Candidate recorded in the ProblemGraph research envelope; no node-level "
                            "Modeling Brain decision artifact is available on this compatibility path."
                        ),
                        selected=_method_equivalent(str(method), selected_method),
                        comparison_compatible=compatibility.comparable,
                        comparison_compatibility={
                            "input": compatibility.input_compatible,
                            "representation": compatibility.representation_compatible,
                            "constraint": compatibility.constraint_compatible,
                            "protocol": compatibility.protocol_comparable,
                        },
                        comparison_rationale=compatibility.rationale,
                    )
                )
        if selected_method and not any(item.selected for item in values):
            compatibility = self.alternative_compatibility.assess(
                problem_node,
                selected_method,
                accepted_method=selected_method,
            )
            values.insert(
                0,
                NarrativeCandidate(
                    method=selected_method,
                    source="executed_solver",
                    feasibility="PASS",
                    rationale="This is the method actually executed and accepted for the subproblem.",
                    selected=True,
                    comparison_compatible=compatibility.comparable,
                    comparison_compatibility={
                        "input": compatibility.input_compatible,
                        "representation": compatibility.representation_compatible,
                        "constraint": compatibility.constraint_compatible,
                        "protocol": compatibility.protocol_comparable,
                    },
                    comparison_rationale=compatibility.rationale,
                ),
            )
        return values[:8]

    def _alternative_comparison(
        self,
        case_id: str,
        subproblem_id: str,
    ) -> tuple[NarrativeAlternativeComparison | None, list[str]]:
        root = self.cases.case_root(case_id)
        for artifact in reversed(self.artifacts.list_artifacts(case_id)):
            if artifact.get("status") != "ACTIVE" or artifact.get("artifact_type") != "subproblem_alternative_comparison":
                continue
            try:
                payload = read_json(root / artifact["path"])
            except (OSError, ValueError):
                continue
            if str(payload.get("subproblem_id") or "") != subproblem_id:
                continue
            accepted = payload.get("accepted") or {}
            alternatives = payload.get("alternatives") or []
            return (
                NarrativeAlternativeComparison(
                    primary_metric=str(payload.get("primary_metric") or ""),
                    decision=str(payload.get("decision") or ""),
                    accepted_method=str(accepted.get("method") or ""),
                    alternative_methods=[str(item.get("method") or "") for item in alternatives if item.get("method")],
                    best_method=str(payload.get("best_method") or accepted.get("method") or ""),
                    robust_best_method=(
                        str(payload["robust_best_method"])
                        if payload.get("robust_best_method")
                        else None
                    ),
                    rationale=str(payload.get("rationale") or ""),
                    stress_test_sizes=[float(value) for value in payload.get("stress_test_sizes", [])],
                    stress_runs=[dict(value) for value in payload.get("stress_runs", []) if isinstance(value, dict)],
                ),
                [str(artifact["artifact_id"])],
            )
        return None, []

    def _solver_data_context(self, case_id: str, problem_node: Any) -> tuple[list[str], list[str]]:
        """Expose only preprocessing/input facts already persisted by the solver.

        The Paper Engine needs enough data context to explain preprocessing, but
        it must not reconstruct a cleaning story from domain intuition. We read
        the accepted solver plan itself and summarize only declared columns and
        ordering/feature-construction requirements.
        """
        if problem_node.execution_kind == "DELIVERABLE":
            return [], []
        root = self.cases.case_root(case_id)
        payload = None
        for artifact_id in reversed(list(problem_node.state.evidence_artifact_ids or [])):
            try:
                artifact = self.artifacts.get(case_id, artifact_id)
            except KeyError:
                continue
            if artifact.get("artifact_type") != "solver_execution_result":
                continue
            try:
                payload = read_json(root / artifact["path"])
            except (OSError, ValueError):
                continue
            break
        if not isinstance(payload, dict):
            return [], []
        plan = payload.get("plan") or {}
        columns: list[str] = []
        for key in ("time_column", "target_column"):
            value = plan.get(key)
            if value:
                columns.append(str(value))
        for key in ("feature_columns", "output_columns", "numeric_columns"):
            values = plan.get(key) or []
            columns.extend(str(value) for value in values if str(value))
        columns = list(dict.fromkeys(columns))

        notes: list[str] = []
        if plan.get("time_column"):
            notes.append(
                f"Temporal ordering follows {plan['time_column']} before model fitting, validation, or forecasting."
            )
        if plan.get("feature_columns"):
            notes.append(
                "The model uses the following predictor/input columns: "
                + ", ".join(str(value) for value in plan["feature_columns"])
                + "."
            )
        if plan.get("output_columns"):
            notes.append(
                "The modeled response uses the following output columns: "
                + ", ".join(str(value) for value in plan["output_columns"])
                + "."
            )
        if plan.get("numeric_columns"):
            notes.append(
                "Exploratory calculations use the following numeric columns: "
                + ", ".join(str(value) for value in plan["numeric_columns"])
                + "."
            )
        for value in plan.get("preprocessing_notes") or []:
            text = " ".join(str(value).split())
            if text and text not in notes:
                notes.append(text)
        return columns, notes

    def _validation_state(self, case_id: str, problem_node: Any) -> tuple[str | None, str | None, list[str]]:
        if problem_node.execution_kind == "DELIVERABLE" or not problem_node.experiments:
            return None, None, []
        experiment = problem_node.experiments[0]
        artifact_ids = list(getattr(experiment, "validation_artifact_ids", []) or [])
        protocol_id = getattr(experiment, "validation_protocol_id", None)
        if not artifact_ids:
            return None, protocol_id, []
        artifact = self.artifacts.get(case_id, artifact_ids[-1])
        payload = read_json(self.cases.case_root(case_id) / artifact["path"])
        assessment = payload.get("assessment", payload)
        return str(assessment.get("gate") or ""), str(assessment.get("protocol_id") or protocol_id or ""), artifact_ids


def render_narrative_preview(graph: NarrativeGraph) -> str:
    """Human-readable internal preview with no registry ids exposed."""

    lines = ["# Research Narrative", "", f"Gate: {graph.gate}", ""]
    for index, node in enumerate(graph.nodes, start=1):
        lines.extend(
            [
                f"## {index}. {node.title}",
                "",
                f"**Task:** {node.objective}",
                "",
                f"**Method:** {node.method}",
                "",
            ]
        )
        alternatives = [item for item in node.candidate_considerations if not item.selected]
        if alternatives:
            lines.append("**Alternatives considered:**")
            for item in alternatives[:4]:
                lines.append(f"- {item.method} ({item.feasibility}): {item.rationale}")
            lines.append("")
        if node.key_results:
            lines.append("**Key results:**")
            for result in node.key_results[:8]:
                lines.append(f"- {result.metric}: {result.value:.6g}")
            lines.append("")
        if node.answer:
            lines.extend(["**Answer:** " + node.answer, ""])
        if node.limitation:
            lines.extend(["**Limitation:** " + node.limitation, ""])
        if node.dependencies:
            lines.extend(["**Depends on:** " + ", ".join(node.dependencies), ""])
        if node.blockers:
            lines.extend(["**Blocked by:** " + "; ".join(node.blockers), ""])
    return "\n".join(lines).rstrip() + "\n"


def _method_equivalent(left: str, right: str) -> bool:
    def normalize(value: str) -> str:
        return " ".join(
            value.lower().replace("_", " ").replace("-", " ").split()
        )

    left_value = normalize(left)
    right_value = normalize(right)
    if not left_value or not right_value:
        return False
    return left_value == right_value or left_value in right_value or right_value in left_value

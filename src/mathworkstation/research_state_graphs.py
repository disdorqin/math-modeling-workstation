from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .io_utils import atomic_write_json, now_iso, read_json
from .problem_graph import ProblemGraphService, assess_problem_graph


GraphGate = Literal["PASS", "BLOCKED"]


class ModelGraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subproblem_id: str
    task_family: str
    execution_kind: str
    dependencies: list[str] = Field(default_factory=list)
    selected_method: str | None = None
    candidate_methods: list[str] = Field(default_factory=list)
    experiment_id: str | None = None
    experiment_status: str | None = None
    solver_evidence_artifact_ids: list[str] = Field(default_factory=list)
    validation_protocol_id: str | None = None
    validation_gate: str | None = None
    validation_artifact_ids: list[str] = Field(default_factory=list)
    modeling_brain_artifact_id: str | None = None
    gate: GraphGate
    blockers: list[str] = Field(default_factory=list)


class ModelGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str
    gate: GraphGate
    problem_graph_gate: str
    nodes: list[ModelGraphNode]
    source_artifact_ids: list[str] = Field(default_factory=list)
    generated_at: str

    def node(self, subproblem_id: str) -> ModelGraphNode:
        for item in self.nodes:
            if item.subproblem_id == subproblem_id:
                return item
        raise KeyError(f"model graph node not found: {subproblem_id}")


class EvidenceGraphNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subproblem_id: str
    role: Literal["RESEARCH", "SYNTHESIS"]
    dependencies: list[str] = Field(default_factory=list)
    answer_id: str | None = None
    answer_text: str = ""
    result_ids: list[str] = Field(default_factory=list)
    table_ids: list[str] = Field(default_factory=list)
    figure_ids: list[str] = Field(default_factory=list)
    claim_ids: list[str] = Field(default_factory=list)
    source_artifact_ids: list[str] = Field(default_factory=list)
    gate: GraphGate
    blockers: list[str] = Field(default_factory=list)


class EvidenceGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str
    gate: GraphGate
    model_graph_gate: str
    nodes: list[EvidenceGraphNode]
    active_generation: int | None = None
    active_lineage_artifact_id: str | None = None
    source_artifact_ids: list[str] = Field(default_factory=list)
    generated_at: str

    def node(self, subproblem_id: str) -> EvidenceGraphNode:
        for item in self.nodes:
            if item.subproblem_id == subproblem_id:
                return item
        raise KeyError(f"evidence graph node not found: {subproblem_id}")


class ModelGraphService:
    """Project ProblemGraph research execution into a model/solver graph."""

    def __init__(self, cases: Any, artifacts: Any, problem_graphs: ProblemGraphService | None = None) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.problem_graphs = problem_graphs or ProblemGraphService(cases, artifacts)

    def build(self, case_id: str) -> ModelGraph:
        problem_graph = self.problem_graphs.load(case_id)
        assessment = assess_problem_graph(problem_graph)
        nodes: list[ModelGraphNode] = []
        sources: list[str] = []
        for node in problem_graph.nodes:
            blockers: list[str] = []
            selected_method = node.plan.selected_method or (node.answer.method if node.answer else None)
            experiment = node.experiments[0] if node.experiments else None
            validation_gate = None
            validation_protocol_id = None
            validation_artifacts: list[str] = []
            solver_evidence: list[str] = []
            if node.execution_kind != "DELIVERABLE":
                if not selected_method:
                    blockers.append("SELECTED_METHOD_MISSING")
                if experiment is None:
                    blockers.append("EXPERIMENT_MISSING")
                else:
                    solver_evidence = list(experiment.evidence_artifact_ids)
                    validation_artifacts = list(experiment.validation_artifact_ids)
                    validation_protocol_id = getattr(experiment, "validation_protocol_id", None)
                    if not solver_evidence:
                        blockers.append("SOLVER_EVIDENCE_MISSING")
                    if not validation_artifacts:
                        blockers.append("VALIDATION_ARTIFACT_MISSING")
                    else:
                        artifact = self.artifacts.get(case_id, validation_artifacts[-1])
                        payload = read_json(self.cases.case_root(case_id) / artifact["path"])
                        value = payload.get("assessment", payload)
                        validation_gate = str(value.get("gate") or "")
                        validation_protocol_id = str(
                            value.get("protocol_id") or validation_protocol_id or ""
                        ) or None
                        if validation_gate in {"FAIL", "BLOCK", ""}:
                            blockers.append("VALIDATION_NOT_ACCEPTED")
            else:
                # A synthesis node is model-free by design. Its dependencies are
                # represented, but lack of an experiment is not a defect.
                selected_method = node.answer.method if node.answer else selected_method

            node_sources = list(
                dict.fromkeys(
                    [
                        *solver_evidence,
                        *validation_artifacts,
                        *([node.plan.modeling_brain_artifact_id] if node.plan.modeling_brain_artifact_id else []),
                    ]
                )
            )
            sources.extend(node_sources)
            nodes.append(
                ModelGraphNode(
                    subproblem_id=node.subproblem_id,
                    task_family=node.task_family,
                    execution_kind=node.execution_kind,
                    dependencies=list(node.dependencies),
                    selected_method=selected_method,
                    candidate_methods=list(node.plan.candidate_methods),
                    experiment_id=(experiment.experiment_id if experiment else None),
                    experiment_status=(experiment.status if experiment else None),
                    solver_evidence_artifact_ids=solver_evidence,
                    validation_protocol_id=validation_protocol_id,
                    validation_gate=validation_gate,
                    validation_artifact_ids=validation_artifacts,
                    modeling_brain_artifact_id=node.plan.modeling_brain_artifact_id,
                    gate="BLOCKED" if blockers else "PASS",
                    blockers=blockers,
                )
            )
        gate: GraphGate = (
            "PASS"
            if assessment.research_gate == "PASS" and all(item.gate == "PASS" for item in nodes)
            else "BLOCKED"
        )
        return ModelGraph(
            case_id=case_id,
            gate=gate,
            problem_graph_gate=assessment.research_gate,
            nodes=nodes,
            source_artifact_ids=list(dict.fromkeys(sources)),
            generated_at=now_iso(),
        )

    def build_and_persist(self, case_id: str) -> dict[str, Any]:
        graph = self.build(case_id)
        root = self.cases.case_root(case_id)
        path = root / "analysis" / "research_state" / "model_graph.json"
        atomic_write_json(path, graph.model_dump(mode="json"))
        artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "model_graph",
            "model_graph",
            upstream=graph.source_artifact_ids,
            paper_eligible=False,
        )
        return {"graph": graph, "artifact": artifact}


class EvidenceGraphService:
    """Join active paper evidence to each ModelGraph/ProblemGraph subproblem."""

    def __init__(
        self,
        cases: Any,
        artifacts: Any,
        contracts: Any,
        claims: Any,
        figures: Any,
        problem_graphs: ProblemGraphService | None = None,
        model_graphs: ModelGraphService | None = None,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.contracts = contracts
        self.claims = claims
        self.figures = figures
        self.problem_graphs = problem_graphs or ProblemGraphService(cases, artifacts)
        self.model_graphs = model_graphs or ModelGraphService(cases, artifacts, self.problem_graphs)

    def build(self, case_id: str, model_graph: ModelGraph | None = None) -> EvidenceGraph:
        model_graph = model_graph or self.model_graphs.build(case_id)
        problem_graph = self.problem_graphs.load(case_id)
        results = self.contracts.list_results(case_id, active_only=True)
        tables = self.contracts.list_tables(case_id, active_only=True)
        answers = {item.subproblem_id: item for item in self.contracts.list_answers(case_id)}
        claims = self.claims.list_claims(case_id)
        figures = self.figures.list_figures(case_id)
        active_path = self.cases.case_root(case_id) / "results" / "contracts" / "active_evidence.json"
        active = read_json(active_path) if active_path.is_file() else {}

        result_owner = {
            result.result_id: str(result.metadata.get("subproblem_id") or "")
            for result in results
        }
        nodes: list[EvidenceGraphNode] = []
        all_sources: list[str] = []
        for problem_node in problem_graph.nodes:
            subproblem_id = problem_node.subproblem_id
            answer = answers.get(subproblem_id)
            node_results = [
                item for item in results
                if str(item.metadata.get("subproblem_id") or "") == subproblem_id
            ]
            result_ids = [item.result_id for item in node_results]
            node_tables = [
                table for table in tables
                if any(result_owner.get(result_id) == subproblem_id for result_id in table.result_ids)
            ]
            node_figures = [
                item for item in figures
                if item.get("status") == "FINAL"
                and str((item.get("parameters") or {}).get("subproblem_id") or "") == subproblem_id
            ]
            node_claims = [
                item for item in claims
                if item.get("status") == "VERIFIED" and subproblem_id in item.get("subproblem_ids", [])
            ]
            blockers: list[str] = []
            if answer is None:
                blockers.append("ANSWER_MISSING")
            if problem_node.execution_kind != "DELIVERABLE":
                if not node_results:
                    blockers.append("ACTIVE_RESULT_MISSING")
                if not node_tables:
                    blockers.append("ACTIVE_TABLE_MISSING")
                if not node_figures:
                    blockers.append("FINAL_FIGURE_MISSING")
            else:
                missing_deps = [
                    dep for dep in problem_node.dependencies
                    if not any(item.subproblem_id == dep and item.gate == "PASS" for item in nodes)
                ]
                if missing_deps:
                    blockers.append("SYNTHESIS_EVIDENCE_DEPENDENCY_MISSING:" + ",".join(missing_deps))

            sources = list(
                dict.fromkeys(
                    [
                        *(answer.source_artifact_ids if answer else []),
                        *[source for result in node_results for source in result.source_artifact_ids],
                        *[source for table in node_tables for source in table.source_artifact_ids],
                        *[source for figure in node_figures for source in figure.get("source_artifact_ids", [])],
                        *[source for claim in node_claims for source in claim.get("evidence_artifact_ids", [])],
                    ]
                )
            )
            for artifact_id in sources:
                self.artifacts.get(case_id, artifact_id)
            all_sources.extend(sources)
            nodes.append(
                EvidenceGraphNode(
                    subproblem_id=subproblem_id,
                    role="SYNTHESIS" if problem_node.execution_kind == "DELIVERABLE" else "RESEARCH",
                    dependencies=list(problem_node.dependencies),
                    answer_id=(answer.answer_id if answer else None),
                    answer_text=(answer.answer if answer else ""),
                    result_ids=result_ids,
                    table_ids=[item.table_id for item in node_tables],
                    figure_ids=[item["figure_id"] for item in node_figures],
                    claim_ids=[item["claim_id"] for item in node_claims],
                    source_artifact_ids=sources,
                    gate="BLOCKED" if blockers else "PASS",
                    blockers=blockers,
                )
            )
        gate: GraphGate = (
            "PASS" if model_graph.gate == "PASS" and all(item.gate == "PASS" for item in nodes) else "BLOCKED"
        )
        return EvidenceGraph(
            case_id=case_id,
            gate=gate,
            model_graph_gate=model_graph.gate,
            nodes=nodes,
            active_generation=active.get("generation"),
            active_lineage_artifact_id=None,
            source_artifact_ids=list(dict.fromkeys(all_sources)),
            generated_at=now_iso(),
        )

    def build_and_persist(self, case_id: str, model_graph: ModelGraph | None = None) -> dict[str, Any]:
        graph = self.build(case_id, model_graph)
        root = self.cases.case_root(case_id)
        path = root / "analysis" / "research_state" / "evidence_graph.json"
        atomic_write_json(path, graph.model_dump(mode="json"))
        artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "evidence_graph",
            "evidence_graph",
            upstream=graph.source_artifact_ids,
            paper_eligible=False,
        )
        return {"graph": graph, "artifact": artifact}

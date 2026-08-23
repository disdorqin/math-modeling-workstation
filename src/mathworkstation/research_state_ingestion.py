from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .io_utils import atomic_write_json
from .paper_contracts import SubproblemAnswerRecord
from .problem_graph import ProblemGraphService, SubproblemAnswer, SubproblemExperiment


class AcceptedResultSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    result_type: Literal[
        "MODEL_COMPARISON", "SENSITIVITY", "DATA_QUALITY", "FORECAST",
        "OPTIMUM", "SIMULATION", "RANKING", "EXPLANATORY",
        "DISTRIBUTION_FORECAST", "EXPLORATORY", "CLASSIFICATION",
    ]
    metric: str
    value: float
    direction: Literal["MINIMIZE", "MAXIMIZE", "DESCRIPTIVE"] = "DESCRIPTIVE"
    scope: str
    model_name: str | None = None
    std: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AcceptedTableSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    columns: list[str] = Field(min_length=1)
    rows: list[list[str | int | float]] = Field(min_length=1)
    table_role: str = "summary_metrics"
    section_ids: list[str] = Field(default_factory=lambda: ["results"])


class AcceptedSubproblemExecution(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subproblem_id: str
    method: str = Field(min_length=3)
    solver_evidence_artifact_ids: list[str] = Field(min_length=1)
    validation_protocol_id: str = Field(min_length=3)
    validation_summary: dict[str, Any] = Field(default_factory=dict)
    time_column: str | None = None
    target_column: str | None = None
    feature_columns: list[str] = Field(default_factory=list)
    numeric_columns: list[str] = Field(default_factory=list)
    output_columns: list[str] = Field(default_factory=list)
    preprocessing_notes: list[str] = Field(default_factory=list)
    results: list[AcceptedResultSpec] = Field(min_length=1)
    tables: list[AcceptedTableSpec] = Field(min_length=1)
    answer: str = Field(min_length=5)
    limitation: str = Field(min_length=5)


class ResearchStateIngestionService:
    """Import completed solver work into the canonical Research State contracts."""

    def __init__(self, cases: Any, artifacts: Any, contracts: Any, problem_graphs: ProblemGraphService | None = None) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.contracts = contracts
        self.problem_graphs = problem_graphs or ProblemGraphService(cases, artifacts)

    def ingest(
        self,
        case_id: str,
        executions: list[AcceptedSubproblemExecution],
        *,
        generation: int | None = None,
        created_by: str = "research_state_ingestion",
    ) -> dict[str, Any]:
        if not executions:
            raise ValueError("at least one execution is required")
        graph = self.problem_graphs.load(case_id)
        seen: set[str] = set()
        all_result_ids: list[str] = []
        all_table_ids: list[str] = []
        upstream: list[str] = []
        answer_records: list[SubproblemAnswerRecord] = []
        validation_ids: list[str] = []

        for packet in executions:
            if packet.subproblem_id in seen:
                raise ValueError(f"duplicate execution packet: {packet.subproblem_id}")
            seen.add(packet.subproblem_id)
            node = graph.node(packet.subproblem_id)
            if node.execution_kind == "DELIVERABLE":
                raise ValueError(f"deliverable cannot receive solver execution: {packet.subproblem_id}")
            for artifact_id in packet.solver_evidence_artifact_ids:
                self.artifacts.get(case_id, artifact_id)
            upstream.extend(packet.solver_evidence_artifact_ids)

            execution_path = self.cases.case_root(case_id) / "analysis" / "research_state" / "executions" / f"{packet.subproblem_id}.json"
            atomic_write_json(
                execution_path,
                {
                    "schema_version": 1,
                    "case_id": case_id,
                    "subproblem_id": packet.subproblem_id,
                    "plan": {
                        "method": packet.method,
                        "time_column": packet.time_column,
                        "target_column": packet.target_column,
                        "feature_columns": packet.feature_columns,
                        "numeric_columns": packet.numeric_columns,
                        "output_columns": packet.output_columns,
                        "preprocessing_notes": packet.preprocessing_notes,
                        "validation_protocol": packet.validation_protocol_id,
                    },
                    "result": {
                        "protocol": {"method": packet.method},
                        "metrics": [item.model_dump(mode="json") for item in packet.results],
                    },
                    "source_artifact_ids": packet.solver_evidence_artifact_ids,
                },
            )
            execution_artifact = self.artifacts.register_existing(
                case_id,
                execution_path.relative_to(self.cases.case_root(case_id)).as_posix(),
                "solver_execution_result",
                created_by,
                upstream=packet.solver_evidence_artifact_ids,
                paper_eligible=False,
            )
            upstream.append(execution_artifact["artifact_id"])

            validation_path = self.cases.case_root(case_id) / "analysis" / "research_state" / "validation" / f"{packet.subproblem_id}.json"
            atomic_write_json(
                validation_path,
                {
                    "schema_version": 1,
                    "case_id": case_id,
                    "subproblem_id": packet.subproblem_id,
                    "assessment": {
                        "gate": "PASS",
                        "protocol_id": packet.validation_protocol_id,
                        "summary": packet.validation_summary,
                    },
                },
            )
            validation_artifact = self.artifacts.register_existing(
                case_id,
                validation_path.relative_to(self.cases.case_root(case_id)).as_posix(),
                "validation_assessment",
                created_by,
                upstream=[execution_artifact["artifact_id"], *packet.solver_evidence_artifact_ids],
                paper_eligible=False,
            )
            validation_ids.append(validation_artifact["artifact_id"])
            upstream.append(validation_artifact["artifact_id"])
            result_sources = [execution_artifact["artifact_id"], *packet.solver_evidence_artifact_ids, validation_artifact["artifact_id"]]

            result_ids: list[str] = []
            for spec in packet.results:
                metadata = dict(spec.metadata)
                metadata["subproblem_id"] = packet.subproblem_id
                record = self.contracts.create_result(
                    case_id,
                    result_type=spec.result_type,
                    metric=spec.metric,
                    value=spec.value,
                    std=spec.std,
                    model_name=spec.model_name or packet.method,
                    direction=spec.direction,
                    scope=spec.scope,
                    source_artifact_ids=result_sources,
                    section_ids=["model_construction", "results", "conclusion"],
                    metadata=metadata,
                )
                result_ids.append(record.result_id)
                all_result_ids.append(record.result_id)

            for spec in packet.tables:
                table, _ = self.contracts.create_table(
                    case_id,
                    title=spec.title,
                    columns=spec.columns,
                    rows=spec.rows,
                    result_ids=result_ids,
                    source_artifact_ids=result_sources,
                    section_ids=spec.section_ids,
                    metadata={"subproblem_id": packet.subproblem_id, "table_role": spec.table_role},
                )
                all_table_ids.append(table.table_id)

            answer_id = f"answer-{packet.subproblem_id}-accepted"
            answer_records.append(
                SubproblemAnswerRecord(
                    answer_id=answer_id,
                    subproblem_id=packet.subproblem_id,
                    method=packet.method,
                    result_record_ids=result_ids,
                    answer=packet.answer,
                    limitation=packet.limitation,
                    source_artifact_ids=result_sources,
                )
            )
            experiment = SubproblemExperiment(
                experiment_id=f"experiment-{packet.subproblem_id}-accepted",
                subproblem_id=packet.subproblem_id,
                method=packet.method,
                status="COMPLETED",
                validation_protocol=[packet.validation_protocol_id],
                validation_artifact_ids=[validation_artifact["artifact_id"]],
                evidence_artifact_ids=[execution_artifact["artifact_id"], *packet.solver_evidence_artifact_ids],
            )
            node.plan.selected_method = packet.method
            if packet.method not in node.plan.candidate_methods:
                node.plan.candidate_methods = [packet.method, *node.plan.candidate_methods]
            node.plan.validation_protocol = [packet.validation_protocol_id]
            node.experiments = [experiment]
            node.state.status = "COMPLETED"
            node.state.experiment_ids = [experiment.experiment_id]
            node.state.evidence_artifact_ids = result_sources
            node.state.answer_id = answer_id
            node.state.blockers = []
            node.answer = SubproblemAnswer(
                answer_id=answer_id,
                subproblem_id=packet.subproblem_id,
                method=packet.method,
                answer=packet.answer,
                limitation=packet.limitation,
                evidence_artifact_ids=result_sources,
            )

        self.contracts.persist_analysis_records(case_id, answers=answer_records)
        lineage = self.contracts.activate_evidence_lineage(
            case_id,
            result_ids=all_result_ids,
            table_ids=all_table_ids,
            source_artifact_ids=list(dict.fromkeys(upstream)),
            generation=generation,
        )
        saved_graph, graph_artifact = self.problem_graphs.save(
            case_id,
            graph,
            source_artifact_ids=list(dict.fromkeys([*upstream, lineage["artifact_id"]])),
            created_by=created_by,
        )
        return {
            "graph": saved_graph,
            "problem_graph_artifact": graph_artifact,
            "lineage": lineage,
            "result_ids": all_result_ids,
            "table_ids": all_table_ids,
            "validation_artifact_ids": validation_ids,
            "answer_ids": [record.answer_id for record in answer_records],
        }

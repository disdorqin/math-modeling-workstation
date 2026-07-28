from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .io_utils import append_jsonl, atomic_write_json, atomic_write_text, now_iso
from .paper_outline import REQUIRED_SECTIONS


class SubproblemContract(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subproblem_id: str = Field(min_length=3)
    title: str = Field(min_length=2)
    objective: str = Field(min_length=3)
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    evaluation_metrics: list[str] = Field(default_factory=list)
    owner_section: str = "problem_restated"
    status: Literal["PLANNED", "COMPLETED", "BLOCKED"] = "PLANNED"
    evidence_artifact_ids: list[str] = Field(default_factory=list)


class ResultRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_id: str = Field(min_length=3)
    result_type: Literal[
        "MODEL_COMPARISON", "SENSITIVITY", "DATA_QUALITY", "FORECAST",
        "OPTIMUM", "SIMULATION", "RANKING",
    ]
    metric: str = Field(min_length=1)
    value: float
    std: float | None = None
    model_name: str | None = None
    dataset_id: str | None = None
    experiment_id: str | None = None
    direction: Literal["MINIMIZE", "MAXIMIZE", "DESCRIPTIVE"] = "DESCRIPTIVE"
    scope: str = Field(min_length=3)
    source_artifact_ids: list[str] = Field(min_length=1)
    section_ids: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    def formatted_value(self) -> str:
        return f"{self.value:.6f}"


class TableRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_id: str = Field(min_length=3)
    title: str = Field(min_length=2)
    columns: list[str] = Field(min_length=1)
    rows: list[list[str | int | float]] = Field(min_length=1)
    result_ids: list[str] = Field(min_length=1)
    source_artifact_ids: list[str] = Field(min_length=1)
    section_ids: list[str] = Field(default_factory=list)
    markdown_path: str | None = None

    @model_validator(mode="after")
    def validate_width(self) -> "TableRecord":
        if any(len(row) != len(self.columns) for row in self.rows):
            raise ValueError("table row width must match columns")
        return self


class SectionEvidencePack(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str
    subproblems: list[SubproblemContract] = Field(default_factory=list)
    results: list[ResultRecord] = Field(default_factory=list)
    tables: list[TableRecord] = Field(default_factory=list)
    assumptions: list["AssumptionRecord"] = Field(default_factory=list)
    data_semantics: list["DataSemanticRecord"] = Field(default_factory=list)
    diagnostics: list["DiagnosticRecord"] = Field(default_factory=list)
    answers: list["SubproblemAnswerRecord"] = Field(default_factory=list)


class AssumptionRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assumption_id: str
    statement: str = Field(min_length=3)
    source_artifact_ids: list[str] = Field(min_length=1)
    necessity: str = Field(min_length=3)
    risk: str = Field(min_length=3)
    validation: str = Field(min_length=3)
    affected_sections: list[str] = Field(min_length=1)
    status: Literal["SUPPORTED", "REVIEW", "BLOCKED"] = "SUPPORTED"


class DataSemanticRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    semantic_id: str
    dataset_id: str
    field: str
    role: Literal["FEATURE", "TARGET", "IDENTIFIER", "TIME", "EXCLUDED"]
    meaning: str = Field(min_length=2)
    unit: str | None = None
    missing_count: int = 0
    unique_count: int | None = None
    leakage_risk: Literal["LOW", "REVIEW", "BLOCKED"] = "LOW"
    decision: str = Field(min_length=2)
    source_artifact_ids: list[str] = Field(min_length=1)
    section_ids: list[str] = Field(default_factory=lambda: ["data_analysis", "model_construction"])


class DiagnosticRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    diagnostic_id: str
    diagnostic_type: Literal["RESIDUAL", "ERROR_SLICE", "CALIBRATION", "UNCERTAINTY", "FAILURE_CASE"]
    metric: str
    value: float | None = None
    interpretation: str = Field(min_length=3)
    limitation: str = Field(min_length=3)
    source_artifact_ids: list[str] = Field(min_length=1)
    section_ids: list[str] = Field(default_factory=lambda: ["results", "strengths_weaknesses", "conclusion"])


class SubproblemAnswerRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer_id: str
    subproblem_id: str
    method: str = Field(min_length=3)
    result_record_ids: list[str] = Field(default_factory=list)
    answer: str = Field(min_length=5)
    limitation: str = Field(min_length=5)
    source_artifact_ids: list[str] = Field(min_length=1)
    section_id: str = "conclusion"


class StorylineRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storyline_id: str
    title: str
    steps: list[dict[str, str]] = Field(min_length=1)
    subproblem_ids: list[str] = Field(min_length=1)
    source_record_ids: list[str] = Field(default_factory=list)


class CompletePaperAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gate: Literal["PASS", "FAIL"]
    issue_codes: list[str]
    details: list[dict[str, Any]]
    required_sections: list[str]
    checked_at: str


class PaperContractService:
    def __init__(self, cases: CaseManager, artifacts: ArtifactRegistry) -> None:
        self.cases = cases
        self.artifacts = artifacts

    def _registry_path(self, case_id: str, name: str) -> Path:
        return self.cases.case_root(case_id) / "results" / "contracts" / f"{name}.jsonl"

    def _list(self, case_id: str, name: str, key: str, model: type[BaseModel]) -> list[Any]:
        path = self._registry_path(case_id, name)
        if not path.exists():
            return []
        records: dict[str, Any] = {}
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    value = json.loads(line)
                    records[value[key]] = model.model_validate(value)
        return list(records.values())

    def list_subproblems(self, case_id: str) -> list[SubproblemContract]:
        return self._list(case_id, "subproblems", "subproblem_id", SubproblemContract)

    def list_results(self, case_id: str) -> list[ResultRecord]:
        return self._list(case_id, "results", "result_id", ResultRecord)

    def list_tables(self, case_id: str) -> list[TableRecord]:
        return self._list(case_id, "tables", "table_id", TableRecord)

    def _record_path(self, case_id: str, name: str) -> Path:
        return self._registry_path(case_id, name)

    def _append_record(self, case_id: str, name: str, value: BaseModel) -> None:
        append_jsonl(self._record_path(case_id, name), value.model_dump(mode="json"))

    def list_assumptions(self, case_id: str) -> list[AssumptionRecord]:
        return self._list(case_id, "assumptions", "assumption_id", AssumptionRecord)

    def list_data_semantics(self, case_id: str) -> list[DataSemanticRecord]:
        return self._list(case_id, "data_semantics", "semantic_id", DataSemanticRecord)

    def list_diagnostics(self, case_id: str) -> list[DiagnosticRecord]:
        return self._list(case_id, "diagnostics", "diagnostic_id", DiagnosticRecord)

    def list_answers(self, case_id: str) -> list[SubproblemAnswerRecord]:
        return self._list(case_id, "answers", "answer_id", SubproblemAnswerRecord)

    def list_storylines(self, case_id: str) -> list[StorylineRecord]:
        return self._list(case_id, "storylines", "storyline_id", StorylineRecord)

    def persist_analysis_records(
        self,
        case_id: str,
        assumptions: list[AssumptionRecord] | None = None,
        semantics: list[DataSemanticRecord] | None = None,
        diagnostics: list[DiagnosticRecord] | None = None,
        answers: list[SubproblemAnswerRecord] | None = None,
        storyline: StorylineRecord | None = None,
    ) -> None:
        groups = (("assumptions", assumptions or [], AssumptionRecord, "assumption_id"), ("data_semantics", semantics or [], DataSemanticRecord, "semantic_id"), ("diagnostics", diagnostics or [], DiagnosticRecord, "diagnostic_id"), ("answers", answers or [], SubproblemAnswerRecord, "answer_id"))
        for name, values, model, key in groups:
            existing = {item.model_dump(mode="json")[key] for item in self._list(case_id, name, key, model)}
            for value in values:
                if value.model_dump(mode="json")[key] not in existing:
                    self._append_record(case_id, name, value)
        if storyline is not None:
            self._append_record(case_id, "storylines", storyline)

    def persist_subproblems(self, case_id: str, values: list[SubproblemContract]) -> list[SubproblemContract]:
        known = {item.subproblem_id: item for item in self.list_subproblems(case_id)}
        for value in values:
            if value.subproblem_id in known and known[value.subproblem_id] == value:
                continue
            append_jsonl(self._registry_path(case_id, "subproblems"), value.model_dump(mode="json"))
        return self.list_subproblems(case_id)

    def create_result(self, case_id: str, **fields: Any) -> ResultRecord:
        value = ResultRecord(result_id=f"result-{uuid.uuid4().hex[:12]}", **fields)
        for artifact_id in value.source_artifact_ids:
            self.artifacts.get(case_id, artifact_id)
        append_jsonl(self._registry_path(case_id, "results"), value.model_dump(mode="json"))
        return value

    def create_table(self, case_id: str, **fields: Any) -> tuple[TableRecord, dict[str, Any]]:
        table_id = f"table-{uuid.uuid4().hex[:12]}"
        value = TableRecord(table_id=table_id, **fields)
        known_results = {item.result_id for item in self.list_results(case_id)}
        if not set(value.result_ids) <= known_results:
            raise ValueError("table references unknown result records")
        root = self.cases.case_root(case_id)
        path = root / "tables" / "final" / f"{table_id}.md"
        atomic_write_text(path, _render_table(value))
        artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "result_table",
            "python",
            upstream=value.source_artifact_ids,
            paper_eligible=True,
        )
        value = value.model_copy(update={"markdown_path": artifact["path"]})
        append_jsonl(self._registry_path(case_id, "tables"), value.model_dump(mode="json"))
        return value, artifact

    def build_section_pack(self, case_id: str, section_id: str) -> SectionEvidencePack:
        return SectionEvidencePack(
            section_id=section_id,
            subproblems=[item for item in self.list_subproblems(case_id) if item.owner_section == section_id],
            results=[item for item in self.list_results(case_id) if section_id in item.section_ids],
            tables=[item for item in self.list_tables(case_id) if section_id in item.section_ids],
            assumptions=[item for item in self.list_assumptions(case_id) if section_id in item.affected_sections],
            data_semantics=[item for item in self.list_data_semantics(case_id) if section_id in item.section_ids],
            diagnostics=[item for item in self.list_diagnostics(case_id) if section_id in item.section_ids],
            answers=[item for item in self.list_answers(case_id) if item.section_id == section_id],
        )

    def assess_complete_paper(self, case_id: str, paper_text: str) -> CompletePaperAssessment:
        details: list[dict[str, Any]] = []
        subproblems = self.list_subproblems(case_id)
        results = self.list_results(case_id)
        tables = self.list_tables(case_id)
        if not subproblems:
            details.append({"code": "SUBPROBLEM_CONTRACT_MISSING"})
        for item in subproblems:
            if not item.owner_section:
                details.append({"code": "SUBPROBLEM_OWNER_MISSING", "subproblem_id": item.subproblem_id})
            if item.status != "COMPLETED" or not item.evidence_artifact_ids:
                details.append({"code": "SUBPROBLEM_INCOMPLETE", "subproblem_id": item.subproblem_id})
        if not results:
            details.append({"code": "RESULT_RECORD_MISSING"})
        for item in results:
            if item.formatted_value() not in paper_text:
                details.append({"code": "RESULT_METRIC_NOT_IN_PAPER", "result_id": item.result_id})
        if not tables:
            details.append({"code": "RESULT_TABLE_MISSING"})
        for item in tables:
            if item.table_id not in paper_text:
                details.append({"code": "RESULT_TABLE_NOT_REFERENCED", "table_id": item.table_id})
        if not self.list_diagnostics(case_id):
            details.append({"code": "DIAGNOSTIC_RECORD_MISSING"})
        if not self.list_answers(case_id):
            details.append({"code": "SUBPROBLEM_ANSWER_MISSING"})
        for answer in self.list_answers(case_id):
            if answer.answer not in paper_text:
                details.append({"code": "SUBPROBLEM_ANSWER_NOT_IN_PAPER", "answer_id": answer.answer_id})
        for section_id in ("abstract", "results", "sensitivity", "conclusion"):
            pack = self.build_section_pack(case_id, section_id)
            if section_id != "conclusion" and not pack.results:
                details.append({"code": "SECTION_RESULT_EVIDENCE_MISSING", "section_id": section_id})
        issue_codes = list(dict.fromkeys(item["code"] for item in details))
        return CompletePaperAssessment(
            gate="FAIL" if details else "PASS",
            issue_codes=issue_codes,
            details=details,
            required_sections=sorted(REQUIRED_SECTIONS),
            checked_at=now_iso(),
        )

    def write_assessment(self, case_id: str, paper_text: str) -> tuple[CompletePaperAssessment, dict[str, Any]]:
        assessment = self.assess_complete_paper(case_id, paper_text)
        root = self.cases.case_root(case_id)
        path = root / "review" / "structural" / "complete-paper-assessment.json"
        atomic_write_json(path, assessment.model_dump(mode="json"))
        artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "complete_paper_assessment",
            "python",
            upstream=[],
        )
        return assessment, artifact


def _render_table(table: TableRecord) -> str:
    header = "| " + " | ".join(table.columns) + " |"
    divider = "|" + "|".join("---" for _ in table.columns) + "|"
    rows = ["| " + " | ".join(str(cell) for cell in row) + " |" for row in table.rows]
    return f"表：{table.title} [{table.table_id}]\n\n{header}\n{divider}\n" + "\n".join(rows) + "\n"

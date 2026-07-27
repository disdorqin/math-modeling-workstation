from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .io_utils import append_jsonl, atomic_write_json, now_iso


DOMAINS = (
    "PROBLEM_COVERAGE", "ASSUMPTION_SUPPORT", "DATA_SEMANTICS", "LEAKAGE_OR_SPLIT",
    "MODEL_RATIONALE", "EQUATION_COMPLETENESS", "EXPERIMENT_PROTOCOL",
    "RESULT_EVIDENCE", "DIAGNOSTIC_INTERPRETATION", "FIGURE_TABLE_ALIGNMENT",
    "CITATION_SUPPORT", "NARRATIVE_LOGIC", "LANGUAGE_STYLE", "SUBMISSION_FORMAT",
    "REPRODUCIBILITY",
)


class ReviewIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    issue_id: str
    domain: str
    code: str
    severity: Literal["INFO", "REVIEW", "BLOCK"]
    section_id: str | None = None
    subproblem_ids: list[str] = Field(default_factory=list)
    evidence_dependencies: list[str] = Field(default_factory=list)
    repair_class: Literal["DOCUMENT_PATCH", "UPSTREAM_REPAIR", "SUBMISSION_REPAIR"]
    verification: str
    message: str


class UpstreamRepairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    request_id: str
    issue_id: str
    repair_class: Literal["DATA_REPAIR", "MODEL_REPAIR", "EXPERIMENT_REPAIR", "CITATION_REPAIR"]
    reason: str
    required_inputs: list[str]
    status: Literal["OPEN", "BLOCKED", "RESOLVED"] = "OPEN"
    new_epoch_required: bool = True
    created_at: str


class ReviewEngine:
    def __init__(self, cases: CaseManager, artifacts: ArtifactRegistry) -> None:
        self.cases = cases
        self.artifacts = artifacts

    def review(self, case_id: str, paper_text: str, contract: Any) -> dict[str, Any]:
        issues: list[ReviewIssue] = []
        packs = {section: contract.build_section_pack(case_id, section) for section in ("abstract", "results", "sensitivity", "conclusion")}
        if not contract.list_subproblems(case_id):
            issues.append(self._issue("PROBLEM_COVERAGE", "SUBPROBLEM_CONTRACT_MISSING", "BLOCK", "未登记子问题合同。", "UPSTREAM_REPAIR", "补齐子问题合同"))
        if any(item.status != "COMPLETED" for item in contract.list_subproblems(case_id)):
            issues.append(self._issue("PROBLEM_COVERAGE", "SUBPROBLEM_INCOMPLETE", "BLOCK", "存在未完成子问题。", "UPSTREAM_REPAIR", "完成子问题证据闭环"))
        if not contract.list_diagnostics(case_id):
            issues.append(self._issue("DIAGNOSTIC_INTERPRETATION", "DIAGNOSTIC_RECORD_MISSING", "BLOCK", "缺少诊断记录。", "UPSTREAM_REPAIR", "登记诊断记录"))
        if not contract.list_answers(case_id):
            issues.append(self._issue("NARRATIVE_LOGIC", "SUBPROBLEM_ANSWER_MISSING", "BLOCK", "缺少子问题答案矩阵。", "DOCUMENT_PATCH", "生成答案矩阵"))
        if "The " in paper_text or "The validated" in paper_text:
            issues.append(self._issue("LANGUAGE_STYLE", "ENGLISH_CLAIM_IN_CHINESE_PAPER", "REVIEW", None, "DOCUMENT_PATCH", "替换为中文证据句"))
        if re.search(r"结果.{0,20}(显著|优秀|很好|稳健)", paper_text) and not contract.list_results(case_id):
            issues.append(self._issue("RESULT_EVIDENCE", "VAGUE_RESULT_WITHOUT_METRIC", "BLOCK", "结果表述缺乏量化证据。", "DOCUMENT_PATCH", "补充量化结果"))
        issues.extend(self._reward_hacking(case_id, paper_text, contract))
        result = {"schema_version": 1, "case_id": case_id, "domains": list(DOMAINS), "issues": [item.model_dump(mode="json") for item in issues], "gate": "BLOCK" if any(item.severity == "BLOCK" for item in issues) else "REVIEW" if issues else "PASS", "generated_at": now_iso()}
        root = self.cases.case_root(case_id)
        path = root / "review" / "domains" / "full-review.json"
        atomic_write_json(path, result)
        artifact = self.artifacts.register_existing(case_id, path.relative_to(root).as_posix(), "full_paper_review", "python")
        return {"report": result, "artifact": artifact}

    def create_repair_requests(self, case_id: str, issues: list[dict[str, Any]]) -> list[UpstreamRepairRequest]:
        requests: list[UpstreamRepairRequest] = []
        path = self.cases.case_root(case_id) / "refinement" / "repair_requests" / "requests.jsonl"
        for issue in issues:
            if issue["repair_class"] != "UPSTREAM_REPAIR":
                continue
            request = UpstreamRepairRequest(request_id=f"repair-{uuid.uuid4().hex[:12]}", issue_id=issue["issue_id"], repair_class=_repair_type(issue["domain"]), reason=issue["message"], required_inputs=issue["evidence_dependencies"])
            append_jsonl(path, request.model_dump(mode="json"))
            requests.append(request)
        return requests

    def _issue(self, domain: str, code: str, severity: str, message: str | None, repair_class: str, verification: str) -> ReviewIssue:
        return ReviewIssue(issue_id=f"issue-{uuid.uuid4().hex[:12]}", domain=domain, code=code, severity=severity, repair_class=repair_class, verification=verification, message=message or "")

    def _reward_hacking(self, case_id: str, paper_text: str, contract: Any) -> list[ReviewIssue]:
        if len(paper_text) > 12000 and len(contract.list_results(case_id)) < 2:
            return [self._issue("NARRATIVE_LOGIC", "LENGTH_WITHOUT_EVIDENCE", "REVIEW", "篇幅增长但证据记录不足。", "DOCUMENT_PATCH", "比较证据记录增量")]
        return []


def _repair_type(domain: str) -> str:
    if domain == "DATA_SEMANTICS":
        return "DATA_REPAIR"
    if domain == "MODEL_RATIONALE":
        return "MODEL_REPAIR"
    if domain in {"EXPERIMENT_PROTOCOL", "RESULT_EVIDENCE", "DIAGNOSTIC_INTERPRETATION"}:
        return "EXPERIMENT_REPAIR"
    return "CITATION_REPAIR"

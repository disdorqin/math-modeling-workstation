from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from .case_manager import CaseManager
from .io_utils import append_jsonl, atomic_write_json, now_iso, read_json
from .workflow import default_workflow_graph
from .workflow_service import WorkflowService

WORKSTATION_DOMAINS: tuple[str, ...] = (
    "problem",
    "data",
    "model",
    "experiment",
    "evidence",
    "paper",
    "presentation",
    "submission",
)

# A Round audits every domain, but only re-executes from the earliest affected
# node. These groups are deliberately aligned with the existing acyclic DAG.
DOMAIN_NODES: dict[str, tuple[str, ...]] = {
    "problem": ("input_validation", "problem_analysis"),
    "data": ("data_registration", "data_quality", "eda"),
    "model": ("model_plan", "baseline", "model_selection"),
    "experiment": ("experiments", "sensitivity"),
    "evidence": ("model_selection", "sensitivity", "paper_outline"),
    "paper": ("paper_outline", "paper_draft", "consistency_check", "refinement_loop"),
    "presentation": ("supplementary_figure", "paper_draft", "refinement_loop"),
    "submission": ("final_review", "export"),
}

DOMAIN_DEFAULT_PIVOT: dict[str, str] = {
    "problem": "problem_analysis",
    "data": "data_quality",
    "model": "model_plan",
    "experiment": "experiments",
    "evidence": "model_selection",
    "paper": "paper_outline",
    "presentation": "paper_draft",
    "submission": "final_review",
}

_STATUS_SCORE = {
    "SUCCEEDED": 1.0,
    "DEGRADED": 0.8,
    "NEEDS_REVIEW": 0.7,
    "RUNNING": 0.5,
    "STALE": 0.3,
    "RETRYING": 0.3,
    "PENDING": 0.0,
    "BLOCKED": 0.0,
    "FAILED": 0.0,
    "SKIPPED": 0.0,
}

_SEVERITY_RANK = {"P0": 0, "P1": 1, "P2": 2}
ROUND_FOCUS: dict[int, str] = {
    0: "coverage",
    1: "correctness",
    2: "modeling_depth",
    3: "robustness",
    4: "storyline",
    5: "competition_polish",
}
_FOCUS_DOMAINS: dict[str, tuple[str, ...]] = {
    "coverage": ("problem", "data", "model", "experiment", "evidence"),
    "correctness": ("problem", "data", "experiment", "evidence"),
    "modeling_depth": ("model", "experiment"),
    "robustness": ("experiment", "evidence", "data"),
    "storyline": ("evidence", "paper"),
    "competition_polish": ("paper", "presentation", "submission"),
}
_NODE_ORDER = tuple(default_workflow_graph().definitions)
_NODE_INDEX = {node_id: index for index, node_id in enumerate(_NODE_ORDER)}

# CompletePaperContract findings are more useful when they can route upstream
# instead of being flattened into a generic paper-writing defect.
_COMPLETE_PAPER_ROUTES: dict[str, tuple[str, str]] = {
    "SUBPROBLEM_CONTRACT_MISSING": ("problem", "problem_analysis"),
    "SUBPROBLEM_OWNER_MISSING": ("problem", "problem_analysis"),
    "SUBPROBLEM_INCOMPLETE": ("problem", "problem_analysis"),
    "RESULT_RECORD_MISSING": ("experiment", "experiments"),
    "DIAGNOSTIC_RECORD_MISSING": ("experiment", "experiments"),
    "RESULT_TABLE_MISSING": ("evidence", "model_selection"),
    "SECTION_RESULT_EVIDENCE_MISSING": ("evidence", "model_selection"),
    "SUBPROBLEM_ANSWER_MISSING": ("evidence", "model_selection"),
    "RESULT_METRIC_NOT_IN_PAPER": ("paper", "paper_draft"),
    "RESULT_TABLE_NOT_REFERENCED": ("paper", "paper_draft"),
    "SUBPROBLEM_ANSWER_NOT_IN_PAPER": ("paper", "paper_draft"),
}


@dataclass(frozen=True)
class RecurrentWorkstationConfig:
    """Outer-loop policy for the M-round workstation.

    This policy is intentionally independent from ``RefinementConfig``. The
    latter controls bounded edits *inside* the paper cell; this configuration
    controls whole-workstation rounds across modeling, experiments and paper.
    """

    max_rounds: int = 5
    min_rounds: int = 2
    target_total: float = 0.9
    min_delta: float = 0.01
    max_domain_regression: float = 0.08
    patience: int = 2
    max_findings_per_round: int = 8

    def __post_init__(self) -> None:
        if self.max_rounds < 1 or not 0 <= self.min_rounds <= self.max_rounds:
            raise ValueError("invalid recurrent workstation round bounds")
        if not 0 <= self.target_total <= 1:
            raise ValueError("target_total must be in [0, 1]")
        if self.min_delta < 0:
            raise ValueError("min_delta must be non-negative")
        if self.max_domain_regression < 0:
            raise ValueError("max_domain_regression must be non-negative")
        if self.patience < 1 or self.max_findings_per_round < 1:
            raise ValueError("patience and max_findings_per_round must be positive")


@dataclass(frozen=True)
class WorkstationFinding:
    issue_id: str
    domain: str
    severity: str
    code: str
    message: str
    repair_node: str
    source: str
    evidence_ids: tuple[str, ...] = ()
    subproblem_id: str | None = None
    repair_phase: str | None = None
    research_artifact_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["evidence_ids"] = list(self.evidence_ids)
        return value


@dataclass(frozen=True)
class WorkstationAudit:
    case_id: str
    quality: dict[str, float]
    findings: tuple[WorkstationFinding, ...]
    gate: str
    total: float
    checked_at: str
    workflow_status: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "case_id": self.case_id,
            "quality": self.quality,
            "findings": [item.to_dict() for item in self.findings],
            "gate": self.gate,
            "total": self.total,
            "checked_at": self.checked_at,
            "workflow_status": self.workflow_status,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "WorkstationAudit":
        return cls(
            case_id=str(payload["case_id"]),
            quality={key: float(value) for key, value in payload["quality"].items()},
            findings=tuple(
                WorkstationFinding(
                    issue_id=str(item["issue_id"]),
                    domain=str(item["domain"]),
                    severity=str(item["severity"]),
                    code=str(item["code"]),
                    message=str(item.get("message", "")),
                    repair_node=str(item["repair_node"]),
                    source=str(item.get("source", "unknown")),
                    evidence_ids=tuple(item.get("evidence_ids", [])),
                    subproblem_id=(str(item["subproblem_id"]) if item.get("subproblem_id") else None),
                    repair_phase=(str(item["repair_phase"]) if item.get("repair_phase") else None),
                    research_artifact_id=(
                        str(item["research_artifact_id"])
                        if item.get("research_artifact_id")
                        else None
                    ),
                )
                for item in payload.get("findings", [])
            ),
            gate=str(payload["gate"]),
            total=float(payload["total"]),
            checked_at=str(payload.get("checked_at", now_iso())),
            workflow_status={key: str(value) for key, value in payload.get("workflow_status", {}).items()},
        )


@dataclass(frozen=True)
class ResearchRepairTarget:
    subproblem_id: str
    phase: str
    code: str
    source: str
    evidence_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "subproblem_id": self.subproblem_id,
            "phase": self.phase,
            "code": self.code,
            "source": self.source,
            "evidence_ids": list(self.evidence_ids),
        }


@dataclass(frozen=True)
class WorkstationRoundPlan:
    round_number: int
    pivot: str | None
    selected_issue_ids: tuple[str, ...]
    affected_domains: tuple[str, ...]
    rationale: str
    full_audit_required: bool = True
    repair_targets: tuple[ResearchRepairTarget, ...] = ()
    focus: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "round": self.round_number,
            "pivot": self.pivot,
            "selected_issue_ids": list(self.selected_issue_ids),
            "affected_domains": list(self.affected_domains),
            "rationale": self.rationale,
            "full_audit_required": self.full_audit_required,
            "repair_targets": [item.to_dict() for item in self.repair_targets],
            "focus": self.focus,
        }


@dataclass(frozen=True)
class WorkstationRoundDecision:
    accepted: bool
    reasons: tuple[str, ...]
    total_delta: float
    domain_deltas: dict[str, float]
    decided_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "accepted": self.accepted,
            "reasons": list(self.reasons),
            "total_delta": self.total_delta,
            "domain_deltas": self.domain_deltas,
            "decided_at": self.decided_at,
        }


class WorkstationGlobalAuditor:
    """Deterministic outer-loop audit over the complete workstation state.

    The first implementation intentionally consumes existing, already-verified
    contracts instead of introducing another LLM judge. Later rounds can add a
    blinded LLM/human reviewer on top, but the repair routing must remain
    grounded in workflow and evidence state.
    """

    def __init__(self, cases: CaseManager) -> None:
        self.cases = cases

    def audit(self, case_id: str) -> WorkstationAudit:
        root = self.cases.case_root(case_id)
        workflow_status = self._workflow_status(root)
        quality = {
            domain: self._domain_score(workflow_status, nodes)
            for domain, nodes in DOMAIN_NODES.items()
        }
        findings: list[WorkstationFinding] = []
        findings.extend(self._workflow_findings(workflow_status))
        findings.extend(self._model_fanout_findings(root))
        findings.extend(self._research_data_coverage_findings(root))
        if self._research_state_enabled(root):
            findings.extend(self._problem_graph_findings(root))
            findings.extend(self._solver_gap_findings(root))
            findings.extend(self._validation_findings(root))
            findings.extend(self._c_problem_prior_findings(root))
            findings.extend(self._subproblem_evidence_findings(root))
        findings.extend(self._consistency_findings(root))
        findings.extend(self._complete_paper_findings(root))
        findings.extend(self._expression_fulfillment_findings(root))
        findings.extend(self._competition_paper_findings(root))
        findings.extend(self._excellent_readiness_findings(root))
        findings.extend(self._refinement_findings(root))
        findings.extend(self._artifact_presence_findings(root, workflow_status))
        findings = _dedupe_findings(findings)

        # A finding caps its domain score. This prevents a visually "mostly
        # succeeded" DAG from hiding a known hard contract failure.
        caps = {"P0": 0.25, "P1": 0.5, "P2": 0.8}
        for finding in findings:
            if finding.domain in quality:
                quality[finding.domain] = min(quality[finding.domain], caps[finding.severity])
        quality = {key: round(_clamp(value), 6) for key, value in quality.items()}
        total = round(sum(quality.values()) / len(WORKSTATION_DOMAINS), 6)
        if any(item.severity == "P0" for item in findings):
            gate = "BLOCK"
        elif findings:
            gate = "REVIEW"
        else:
            gate = "PASS"
        return WorkstationAudit(
            case_id=case_id,
            quality=quality,
            findings=tuple(findings),
            gate=gate,
            total=total,
            checked_at=now_iso(),
            workflow_status=workflow_status,
        )

    @staticmethod
    def _workflow_status(root: Path) -> dict[str, str]:
        path = root / ".internal" / "checkpoints" / "current.json"
        if not path.is_file():
            return {}
        snapshot = read_json(path)
        return {
            node_id: str(value.get("status", "PENDING"))
            for node_id, value in snapshot.get("nodes", {}).items()
        }

    @staticmethod
    def _domain_score(statuses: dict[str, str], nodes: Iterable[str]) -> float:
        values = [_STATUS_SCORE.get(statuses.get(node_id, "PENDING"), 0.0) for node_id in nodes]
        return 0.0 if not values else sum(values) / len(values)

    def _workflow_findings(self, statuses: dict[str, str]) -> list[WorkstationFinding]:
        findings: list[WorkstationFinding] = []
        node_to_domain: dict[str, str] = {}
        for domain, nodes in DOMAIN_NODES.items():
            for node_id in nodes:
                node_to_domain.setdefault(node_id, domain)
        for node_id, status in statuses.items():
            if status not in {"FAILED", "BLOCKED", "STALE", "NEEDS_REVIEW"}:
                continue
            severity = "P0" if status == "FAILED" else "P1" if status in {"BLOCKED", "STALE"} else "P2"
            domain = node_to_domain.get(node_id, "paper")
            findings.append(
                _finding(
                    domain=domain,
                    severity=severity,
                    code=f"WORKFLOW_{status}",
                    message=f"workflow node {node_id} is {status}",
                    repair_node=node_id if node_id in _NODE_INDEX else DOMAIN_DEFAULT_PIVOT[domain],
                    source="workflow",
                )
            )
        return findings

    def _research_data_coverage_findings(self, root: Path) -> list[WorkstationFinding]:
        path = root / "review" / "research" / "data_coverage.json"
        if not path.is_file():
            return []
        report = read_json(path)
        findings: list[WorkstationFinding] = []
        for item in report.get("findings", []):
            severity = "P1" if str(item.get("severity")) == "BLOCK" else "P2"
            findings.append(
                _finding(
                    domain="data",
                    severity=severity,
                    code="RESEARCH_DATA_" + str(item.get("code") or "COVERAGE_FINDING"),
                    message=str(item.get("message") or "research data coverage finding"),
                    repair_node="data_registration",
                    source="research_data_coverage",
                    repair_phase=str(item.get("repair_phase") or "data_registration"),
                )
            )
        return findings

    def _model_fanout_findings(self, root: Path) -> list[WorkstationFinding]:
        path = root / "analysis" / "model_fanout_summary.json"
        if not path.is_file():
            return []
        summary = read_json(path)
        outcome = str(summary.get("outcome") or "")
        if outcome == "NO_ACCEPTABLE_WINNER":
            return [
                _finding(
                    domain="model",
                    severity="P1",
                    code="MODEL_FANOUT_NO_ACCEPTABLE_WINNER",
                    message="bounded model fan-out found no protocol-valid acceptable winner",
                    repair_node="model_plan",
                    source="model_fanout",
                    evidence_ids=[str(summary.get("comparison_artifact_id", ""))],
                )
            ]
        if outcome == "TIE":
            return [
                _finding(
                    domain="model",
                    severity="P2",
                    code="MODEL_FANOUT_UNRESOLVED_TIE",
                    message=f"bounded model fan-out has unresolved tie: {summary.get('tie_candidate_ids', [])}",
                    repair_node="model_plan",
                    source="model_fanout",
                    evidence_ids=[str(summary.get("comparison_artifact_id", ""))],
                )
            ]
        return []

    @staticmethod
    def _research_state_enabled(root: Path) -> bool:
        """Only activate node-level research auditing after the new path is in use.

        This compatibility gate prevents migrated/legacy cases that merely have
        a ProblemGraph snapshot from being forced into Section-5 semantics before
        they have produced any node-level brain/solver/validation/evidence state.
        """
        return any(
            path.exists()
            for path in (
                root / "analysis" / "modeling_brain",
                root / "analysis" / "solver_gaps",
                root / "results" / "validation",
                root / "results" / "contracts" / "subproblem_evidence_index.json",
            )
        )

    def _problem_graph_findings(self, root: Path) -> list[WorkstationFinding]:
        graph_path = root / "analysis" / "problem_graph.json"
        if not graph_path.is_file():
            return [
                _finding(
                    domain="problem",
                    severity="P1",
                    code="PROBLEM_GRAPH_MISSING",
                    message="node-level research artifacts exist but analysis/problem_graph.json is missing",
                    repair_node="problem_analysis",
                    source="problem_graph",
                    repair_phase="problem_graph",
                )
            ]
        graph = read_json(graph_path)
        nodes = {
            str(item.get("subproblem_id")): item
            for item in graph.get("nodes", [])
            if item.get("subproblem_id")
        }
        findings: list[WorkstationFinding] = []
        assessment_path = root / "review" / "problem_graph" / "assessment.json"
        assessment = read_json(assessment_path) if assessment_path.is_file() else {}
        if str(assessment.get("structure_gate", "PASS")) == "FAIL":
            findings.append(
                _finding(
                    domain="problem",
                    severity="P0",
                    code="PROBLEM_GRAPH_STRUCTURE_FAILED",
                    message="ProblemGraph structure gate failed; repair decomposition/dependencies before solving",
                    repair_node="problem_analysis",
                    source="problem_graph_assessment",
                    repair_phase="problem_graph",
                )
            )
        for subproblem_id, node in nodes.items():
            state = node.get("state") or {}
            status = str(state.get("status", "PLANNED"))
            execution_kind = str(node.get("execution_kind", "MODEL"))
            evidence = [str(value) for value in state.get("evidence_artifact_ids", []) if str(value)]
            answer = node.get("answer")
            if status == "COMPLETED":
                if not answer or not evidence:
                    findings.append(
                        _finding(
                            domain="evidence",
                            severity="P0",
                            code="SUBPROBLEM_COMPLETED_WITHOUT_EVIDENCE",
                            message=f"{subproblem_id} is COMPLETED but lacks answer/evidence lineage",
                            repair_node="model_selection",
                            source="problem_graph",
                            evidence_ids=evidence,
                            subproblem_id=subproblem_id,
                            repair_phase="evidence",
                        )
                    )
                if execution_kind == "DELIVERABLE":
                    incomplete = [
                        dep
                        for dep in node.get("dependencies", [])
                        if str((nodes.get(str(dep), {}).get("state") or {}).get("status", "PLANNED"))
                        != "COMPLETED"
                    ]
                    if incomplete:
                        findings.append(
                            _finding(
                                domain="evidence",
                                severity="P1",
                                code="SYNTHESIS_DEPENDENCY_INCOMPLETE",
                                message=f"{subproblem_id} synthesis depends on incomplete nodes {incomplete}",
                                repair_node="model_selection",
                                source="problem_graph",
                                subproblem_id=subproblem_id,
                                repair_phase="synthesis",
                            )
                        )
                continue
            if status == "BLOCKED":
                findings.append(
                    _finding(
                        domain="experiment",
                        severity="P1",
                        code="SUBPROBLEM_RESEARCH_BLOCKED",
                        message=f"{subproblem_id} research state is BLOCKED",
                        repair_node="experiments",
                        source="problem_graph",
                        evidence_ids=evidence,
                        subproblem_id=subproblem_id,
                        repair_phase="solver",
                    )
                )
            elif status in {"PLANNED", "READY", "RUNNING"}:
                phase = "synthesis" if execution_kind == "DELIVERABLE" else "solver"
                repair_node = "model_selection" if execution_kind == "DELIVERABLE" else "experiments"
                domain = "evidence" if execution_kind == "DELIVERABLE" else "experiment"
                findings.append(
                    _finding(
                        domain=domain,
                        severity="P1",
                        code="SUBPROBLEM_RESEARCH_INCOMPLETE",
                        message=f"{subproblem_id} research state is {status}; node-specific research is incomplete",
                        repair_node=repair_node,
                        source="problem_graph",
                        evidence_ids=evidence,
                        subproblem_id=subproblem_id,
                        repair_phase=phase,
                    )
                )
        return findings

    def _solver_gap_findings(self, root: Path) -> list[WorkstationFinding]:
        gap_root = root / "analysis" / "solver_gaps"
        if not gap_root.is_dir():
            return []
        findings: list[WorkstationFinding] = []
        for path in sorted(gap_root.glob("*.json")):
            payload = read_json(path)
            if not bool(payload.get("blocking", False)):
                continue
            missing = payload.get("missing_solver_methods", [])
            if not missing:
                continue
            subproblem_id = str(payload.get("subproblem_id") or path.stem)
            methods = [str(item.get("method", "")) for item in missing]
            findings.append(
                _finding(
                    domain="model",
                    severity="P1",
                    code="SOLVER_CAPABILITY_BLOCKING",
                    message=f"{subproblem_id} has no executable selected solver; missing methods={methods}",
                    repair_node="model_plan",
                    source="solver_capability_gap",
                    subproblem_id=subproblem_id,
                    repair_phase="solver",
                    research_artifact_id=self._artifact_id_for_path(root, path),
                )
            )
        return findings

    def _validation_findings(self, root: Path) -> list[WorkstationFinding]:
        validation_root = root / "results" / "validation"
        if not validation_root.is_dir():
            return []
        findings: list[WorkstationFinding] = []
        for path in sorted(validation_root.glob("*/assessment.json")):
            payload = read_json(path)
            gate = str(payload.get("gate", "PASS"))
            if gate == "PASS":
                continue
            subproblem_id = str(payload.get("subproblem_id") or path.parent.name)
            artifact_id = self._artifact_id_for_path(root, path)
            raw_findings = payload.get("findings", []) or [
                {"severity": "REVIEW", "code": f"VALIDATION_{gate}", "detail": f"gate={gate}"}
            ]
            for item in raw_findings:
                severity = "P1" if str(item.get("severity")) == "BLOCK" or gate == "FAIL" else "P2"
                code = str(item.get("code", f"VALIDATION_{gate}"))
                findings.append(
                    _finding(
                        domain="experiment",
                        severity=severity,
                        code=f"VALIDATION_{code}",
                        message=str(item.get("detail") or f"{subproblem_id} validation gate={gate}"),
                        repair_node="experiments",
                        source="validation_protocol",
                        evidence_ids=([artifact_id] if artifact_id else []),
                        subproblem_id=subproblem_id,
                        repair_phase="validation",
                        research_artifact_id=artifact_id,
                    )
                )
        return findings

    def _c_problem_prior_findings(self, root: Path) -> list[WorkstationFinding]:
        """Route C-problem benchmark obligations to real research validation.

        The excellent-paper corpus never supplies a solver result itself.  This
        audit only activates for ModelingBrain decisions that explicitly record
        a C-problem benchmark source, and only after the node is COMPLETED.  It
        catches two cases that prose-level readiness checks cannot safely fix:
        missing validation evidence, and validation from the wrong task family.
        """

        brain_root = root / "analysis" / "modeling_brain"
        graph_path = root / "analysis" / "problem_graph.json"
        if not brain_root.is_dir() or not graph_path.is_file():
            return []
        graph = read_json(graph_path)
        nodes = {
            str(item.get("subproblem_id")): item
            for item in graph.get("nodes", [])
            if item.get("subproblem_id")
        }
        findings: list[WorkstationFinding] = []
        for path in sorted(brain_root.glob("*.json")):
            payload = read_json(path)
            if not payload.get("benchmark_prior_source"):
                continue
            if str(payload.get("gate", "")) == "SKIP":
                continue
            obligations = [str(value) for value in payload.get("benchmark_validation_obligations", []) if str(value)]
            if not obligations:
                continue
            subproblem_id = str(payload.get("subproblem_id") or path.stem)
            node = nodes.get(subproblem_id) or {}
            state = node.get("state") or {}
            if str(state.get("status", "PLANNED")) != "COMPLETED":
                continue
            validation_path = root / "results" / "validation" / subproblem_id / "assessment.json"
            if not validation_path.is_file():
                findings.append(
                    _finding(
                        domain="experiment",
                        severity="P1",
                        code="C_PROBLEM_VALIDATION_MISSING",
                        message=(
                            f"{subproblem_id} is COMPLETED and carries C-problem validation obligations "
                            "but has no validation assessment artifact"
                        ),
                        repair_node="experiments",
                        source="c_problem_benchmark",
                        subproblem_id=subproblem_id,
                        repair_phase="validation",
                        research_artifact_id=self._artifact_id_for_path(root, path),
                    )
                )
                continue
            assessment = read_json(validation_path)
            expected_family = str(node.get("task_family") or payload.get("task_family") or "")
            actual_family = str(assessment.get("family") or "")
            if expected_family and actual_family and expected_family != actual_family:
                findings.append(
                    _finding(
                        domain="experiment",
                        severity="P1",
                        code="C_PROBLEM_VALIDATION_FAMILY_MISMATCH",
                        message=(
                            f"{subproblem_id} benchmark obligation expects family={expected_family} "
                            f"but validation artifact reports family={actual_family}"
                        ),
                        repair_node="experiments",
                        source="c_problem_benchmark",
                        evidence_ids=([self._artifact_id_for_path(root, validation_path)] if self._artifact_id_for_path(root, validation_path) else []),
                        subproblem_id=subproblem_id,
                        repair_phase="validation",
                        research_artifact_id=self._artifact_id_for_path(root, path),
                    )
                )
        return findings

    def _subproblem_evidence_findings(self, root: Path) -> list[WorkstationFinding]:
        graph_path = root / "analysis" / "problem_graph.json"
        index_path = root / "results" / "contracts" / "subproblem_evidence_index.json"
        if not graph_path.is_file():
            return []
        graph = read_json(graph_path)
        index = read_json(index_path) if index_path.is_file() else {"subproblems": {}}
        indexed = index.get("subproblems", {})
        findings: list[WorkstationFinding] = []
        for node in graph.get("nodes", []):
            subproblem_id = str(node.get("subproblem_id") or "")
            if not subproblem_id:
                continue
            state = node.get("state") or {}
            if str(state.get("status", "PLANNED")) != "COMPLETED":
                continue
            entry = indexed.get(subproblem_id) or {}
            if str(node.get("execution_kind", "MODEL")) == "DELIVERABLE":
                if not entry.get("source_artifact_ids"):
                    findings.append(
                        _finding(
                            domain="evidence",
                            severity="P1",
                            code="SYNTHESIS_PAPER_EVIDENCE_MISSING",
                            message=f"{subproblem_id} is complete but has no synthesis evidence index entry",
                            repair_node="model_selection",
                            source="subproblem_evidence_index",
                            subproblem_id=subproblem_id,
                            repair_phase="evidence",
                        )
                    )
                continue
            if not entry.get("result_ids") or not entry.get("table_ids"):
                findings.append(
                    _finding(
                        domain="evidence",
                        severity="P1",
                        code="SUBPROBLEM_PAPER_EVIDENCE_MISSING",
                        message=f"{subproblem_id} is complete but node-specific Result/Table evidence is missing",
                        repair_node="model_selection",
                        source="subproblem_evidence_index",
                        evidence_ids=tuple(state.get("evidence_artifact_ids", [])),
                        subproblem_id=subproblem_id,
                        repair_phase="evidence",
                    )
                )
        return findings

    @staticmethod
    def _artifact_id_for_path(root: Path, path: Path) -> str | None:
        registry = root / "artifact_registry.jsonl"
        if not registry.is_file():
            return None
        try:
            relative = path.relative_to(root).as_posix()
        except ValueError:
            return None
        match: str | None = None
        with registry.open("r", encoding="utf-8") as handle:
            for line in handle:
                if not line.strip():
                    continue
                item = json.loads(line)
                if str(item.get("path")) == relative:
                    match = str(item.get("artifact_id"))
        return match

    def _consistency_findings(self, root: Path) -> list[WorkstationFinding]:
        path = root / "review" / "consistency" / "paper_consistency.json"
        if not path.is_file():
            return []
        report = read_json(path)
        gate = str(report.get("gate", "PASS"))
        if gate == "PASS":
            return []
        # ``paper_consistency.json`` is intentionally produced *before* the
        # bounded refinement loop. A REVIEW there is therefore historical once
        # the downstream complete-paper contract has passed on ``paper/final``;
        # carrying it into the next outer Round would create a phantom issue
        # and force an unnecessary refinement-only Round forever.
        complete_path = root / "review" / "structural" / "complete-paper-assessment.json"
        if gate == "REVIEW" and complete_path.is_file():
            complete = read_json(complete_path)
            if str(complete.get("gate", "")) == "PASS":
                return []
        severity = "P0" if gate == "BLOCK" else "P2"
        repair_node = "paper_draft" if gate == "BLOCK" else "refinement_loop"
        findings = [
            _finding(
                domain="paper",
                severity=severity,
                code=f"PAPER_CONSISTENCY_{gate}",
                message=f"paper consistency gate is {gate}",
                repair_node=repair_node,
                source="paper_consistency",
            )
        ]
        for item in report.get("findings", []):
            code = str(item.get("code", "CONSISTENCY_FINDING"))
            findings.append(
                _finding(
                    domain="paper",
                    severity=severity,
                    code=code,
                    message=str(item.get("detail") or item.get("message") or code),
                    repair_node=repair_node,
                    source="paper_consistency",
                )
            )
        return findings

    def _complete_paper_findings(self, root: Path) -> list[WorkstationFinding]:
        path = root / "review" / "structural" / "complete-paper-assessment.json"
        if not path.is_file():
            return []
        report = read_json(path)
        if str(report.get("gate", "PASS")) == "PASS":
            return []
        details = report.get("details") or [{"code": code} for code in report.get("issue_codes", [])]
        findings: list[WorkstationFinding] = []
        for item in details:
            code = str(item.get("code", "COMPLETE_PAPER_FAIL"))
            domain, repair_node = _COMPLETE_PAPER_ROUTES.get(code, ("paper", "paper_draft"))
            findings.append(
                _finding(
                    domain=domain,
                    severity="P1",
                    code=code,
                    message=json.dumps(item, ensure_ascii=False, sort_keys=True),
                    repair_node=repair_node,
                    source="complete_paper_contract",
                )
            )
        return findings

    def _expression_fulfillment_findings(self, root: Path) -> list[WorkstationFinding]:
        path = root / "review" / "expression_fulfillment" / "assessment.json"
        if not path.is_file():
            return []
        report = read_json(path)
        findings: list[WorkstationFinding] = []
        for item in report.get("items", []):
            status = str(item.get("status") or "")
            if status in {"SATISFIED", "OPTIONAL_SKIPPED"}:
                continue
            priority = str(item.get("priority") or "RECOMMENDED")
            medium = str(item.get("medium") or "")
            phase = str(item.get("repair_phase") or "paper_visual")
            subproblem_id = str(item.get("subproblem_id") or "") or None
            missing_evidence = status == "MISSING_EVIDENCE"
            severity = "P1" if priority == "REQUIRED" or missing_evidence else "P2"
            if missing_evidence:
                if phase in {"validation", "experiment"}:
                    domain, repair_node = "experiment", "experiments"
                elif phase == "model_structure":
                    domain, repair_node = "model", "model_plan"
                else:
                    domain, repair_node = "evidence", "model_selection"
            else:
                domain = "presentation" if medium in {"FIGURE", "TABLE"} else "paper"
                repair_node = "supplementary_figure" if medium == "FIGURE" else "paper_draft"
            findings.append(
                _finding(
                    domain=domain,
                    severity=severity,
                    code="EXPRESSION_" + str(item.get("semantic_kind") or medium or "MISSING").upper(),
                    message=str(item.get("detail") or f"planned {medium} expression is not fulfilled"),
                    repair_node=repair_node,
                    source="evidence_expression_fulfillment",
                    subproblem_id=subproblem_id,
                    repair_phase=phase,
                )
            )
        return findings

    def _competition_paper_findings(self, root: Path) -> list[WorkstationFinding]:
        path = root / "review" / "competition" / "paper_assessment.json"
        if not path.is_file():
            return []
        report = read_json(path)
        findings: list[WorkstationFinding] = []
        research_routes = {
            "problem_graph": ("problem", "problem_analysis"),
            "research": ("problem", "problem_analysis"),
            "modeling": ("model", "model_plan"),
            "solver": ("model", "model_plan"),
            "experiment": ("experiment", "experiments"),
            "validation": ("experiment", "experiments"),
            "evidence": ("evidence", "model_selection"),
            "synthesis": ("evidence", "model_selection"),
        }
        for item in report.get("findings", []):
            defect_type = str(item.get("defect_type") or "DOCUMENT")
            severity = "P1" if str(item.get("severity")) == "BLOCK" else "P2"
            repair_phase = str(item.get("repair_phase") or "") or None
            subproblem_id = str(item.get("subproblem_id") or "") or None
            if defect_type == "RESEARCH":
                domain, repair_node = research_routes.get(
                    repair_phase or "research",
                    ("model", "model_plan"),
                )
            else:
                domain = "paper"
                repair_node = "paper_draft" if severity == "P1" else "refinement_loop"
            findings.append(
                _finding(
                    domain=domain,
                    severity=severity,
                    code="COMPETITION_" + str(item.get("code") or "PAPER_FINDING"),
                    message=str(item.get("message") or item.get("code") or "competition paper finding"),
                    repair_node=repair_node,
                    source="competition_paper_auditor",
                    subproblem_id=subproblem_id,
                    repair_phase=repair_phase,
                )
            )
        return findings

    def _excellent_readiness_findings(self, root: Path) -> list[WorkstationFinding]:
        path = root / "review" / "competition" / "excellent_readiness.json"
        if not path.is_file():
            return []
        report = read_json(path)
        findings: list[WorkstationFinding] = []
        for item in report.get("dimensions", []):
            if str(item.get("repair_type") or "") != "RESEARCH":
                continue
            if str(item.get("status") or "") not in {"REVIEW", "BLOCKED"}:
                continue
            dimension = str(item.get("dimension") or "")
            # Cross-problem generalization is a benchmark requirement, not a
            # defect that can be repaired by rerunning this case. Keep it in the
            # readiness report but do not feed it into the recurrent executor.
            if dimension == "cross_problem_generalization":
                continue
            if dimension != "empirical_alternative_comparison":
                continue
            subproblem_ids = [str(value) for value in item.get("subproblem_ids", []) if str(value)]
            for subproblem_id in subproblem_ids:
                findings.append(
                    _finding(
                        domain="experiment",
                        severity="P2",
                        code="READINESS_EMPIRICAL_ALTERNATIVE_COMPARISON",
                        message=(
                            f"{subproblem_id} has viable alternative strategies but only one accepted execution; "
                            "run a head-to-head experiment only if the expected modeling insight justifies it."
                        ),
                        repair_node="experiments",
                        source="excellent_readiness",
                        subproblem_id=subproblem_id,
                        repair_phase="experiment",
                    )
                )
        return findings

    def _refinement_findings(self, root: Path) -> list[WorkstationFinding]:
        path = root / "memory" / "refinement_state.json"
        if not path.is_file():
            return []
        state = read_json(path)
        stop_reason = str(state.get("stop_reason", ""))
        if stop_reason not in {"REJECTION_LIMIT", "PLATEAU", "TOO_MANY_STAGE_FAILURES"}:
            return []
        severity = "P1" if stop_reason == "TOO_MANY_STAGE_FAILURES" else "P2"
        return [
            _finding(
                domain="paper",
                severity=severity,
                code=f"REFINEMENT_{stop_reason}",
                message=f"paper refinement stopped with {stop_reason}",
                repair_node="refinement_loop",
                source="refinement_state",
            )
        ]

    def _artifact_presence_findings(
        self,
        root: Path,
        statuses: dict[str, str],
    ) -> list[WorkstationFinding]:
        findings: list[WorkstationFinding] = []
        if statuses.get("paper_draft") in {"SUCCEEDED", "NEEDS_REVIEW", "DEGRADED"} and not (
            root / "paper" / "final.md"
        ).is_file():
            findings.append(
                _finding(
                    domain="paper",
                    severity="P1",
                    code="FINAL_PAPER_MISSING",
                    message="paper_draft completed but paper/final.md is missing",
                    repair_node="paper_draft",
                    source="artifact_presence",
                )
            )
        if statuses.get("export") == "SUCCEEDED":
            exports = root / "export"
            if not exports.is_dir() or not any(exports.glob("*.zip")):
                findings.append(
                    _finding(
                        domain="submission",
                        severity="P1",
                        code="EXPORT_ARTIFACT_MISSING",
                        message="export workflow succeeded but exports/ is empty",
                        repair_node="export",
                        source="artifact_presence",
                    )
                )
        return findings


class WorkstationRepairRouter:
    """Choose the earliest workflow pivot that can repair the selected issues."""

    def __init__(self, config: RecurrentWorkstationConfig | None = None) -> None:
        self.config = config or RecurrentWorkstationConfig()

    def plan(self, audit: WorkstationAudit, round_number: int) -> WorkstationRoundPlan:
        focus = ROUND_FOCUS.get(round_number, "competition_polish")
        focus_domains = _FOCUS_DOMAINS.get(focus, WORKSTATION_DOMAINS)

        def focus_rank(item: WorkstationFinding) -> int:
            if item.severity in {"P0", "P1"}:
                return 0
            try:
                return focus_domains.index(item.domain)
            except ValueError:
                return len(focus_domains) + WORKSTATION_DOMAINS.index(item.domain)

        hard = [item for item in audit.findings if item.severity in {"P0", "P1"}]
        soft = [item for item in audit.findings if item.severity == "P2"]
        focus_soft = [item for item in soft if item.domain in focus_domains]
        soft_pool = focus_soft if focus_soft else soft
        ordered = sorted(
            [*hard, *soft_pool],
            key=lambda item: (
                _SEVERITY_RANK.get(item.severity, 9),
                focus_rank(item),
                _NODE_INDEX.get(item.repair_node, len(_NODE_INDEX)),
                item.issue_id,
            ),
        )
        selected = ordered[: self.config.max_findings_per_round]
        if selected:
            pivot = min(
                (item.repair_node for item in selected),
                key=lambda node_id: _NODE_INDEX.get(node_id, len(_NODE_INDEX)),
            )
            domains = tuple(dict.fromkeys(item.domain for item in selected))
            repair_targets = tuple(
                ResearchRepairTarget(
                    subproblem_id=str(item.subproblem_id),
                    phase=str(item.repair_phase),
                    code=item.code,
                    source=item.source,
                    evidence_ids=item.evidence_ids,
                )
                for item in selected
                if item.subproblem_id and item.repair_phase
            )
            severity_text = "/".join(sorted({item.severity for item in selected}))
            target_text = (
                "; research targets="
                + ", ".join(f"{item.subproblem_id}/{item.phase}" for item in repair_targets)
                if repair_targets
                else ""
            )
            rationale = (
                f"selected {len(selected)} findings ({severity_text}); restart from earliest affected node {pivot}"
                + target_text
            )
            return WorkstationRoundPlan(
                round_number=round_number,
                pivot=pivot,
                selected_issue_ids=tuple(item.issue_id for item in selected),
                affected_domains=domains,
                rationale=rationale,
                repair_targets=repair_targets,
                focus=focus,
            )

        if audit.total + 1e-9 < self.config.target_total:
            candidate_domains = focus_domains or WORKSTATION_DOMAINS
            lowest_domain = min(
                candidate_domains,
                key=lambda item: (audit.quality[item], WORKSTATION_DOMAINS.index(item)),
            )
            pivot = DOMAIN_DEFAULT_PIVOT[lowest_domain]
            return WorkstationRoundPlan(
                round_number=round_number,
                pivot=pivot,
                selected_issue_ids=(),
                affected_domains=(lowest_domain,),
                rationale=(
                    f"round focus={focus}; no explicit finding but total={audit.total:.3f} is below "
                    f"target={self.config.target_total:.3f}; repair lowest-scoring focus domain "
                    f"{lowest_domain} from {pivot}"
                ),
                focus=focus,
            )

        return WorkstationRoundPlan(
            round_number=round_number,
            pivot=None,
            selected_issue_ids=(),
            affected_domains=(),
            rationale="all audited domains meet the current convergence target",
            focus=focus,
        )


class WorkstationRoundStore:
    """Crash-recoverable, append-audited hidden state for workstation rounds."""

    def __init__(self, cases: CaseManager) -> None:
        self.cases = cases

    def hidden_path(self, case_id: str) -> Path:
        return self.cases.case_root(case_id) / "workstation" / "hidden_state.json"

    def round_root(self, case_id: str, round_number: int) -> Path:
        return self.cases.case_root(case_id) / "workstation" / "rounds" / f"round-{round_number:03d}"

    def load(self, case_id: str) -> dict[str, Any] | None:
        path = self.hidden_path(case_id)
        return read_json(path) if path.is_file() else None

    def initialize(
        self,
        case_id: str,
        audit: WorkstationAudit,
        active_lineage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        existing = self.load(case_id)
        if existing is not None:
            return existing
        state = {
            "schema_version": 1,
            "case_id": case_id,
            "round": 0,
            "status": "IDLE",
            "active_round": None,
            "current_focus": ROUND_FOCUS[0],
            "quality": dict(audit.quality),
            "quality_total": audit.total,
            "gate": audit.gate,
            "open_issues": [item.issue_id for item in audit.findings],
            "resolved_issues": [],
            "next_pivot": None,
            "lessons": [],
            "active_lineage": dict(active_lineage or {}),
            "round_history": [],
            "no_progress_streak": 0,
            "updated_at": now_iso(),
        }
        atomic_write_json(self.hidden_path(case_id), state)
        return state

    def begin_round(
        self,
        case_id: str,
        plan: WorkstationRoundPlan,
        audit_before: WorkstationAudit,
        lineage_before: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        state = self.initialize(case_id, audit_before, lineage_before)
        if state.get("status") == "RUNNING":
            raise RuntimeError(f"workstation round {state.get('active_round')} is already running")
        expected_round = int(state.get("round", 0)) + 1
        if plan.round_number != expected_round:
            raise ValueError(f"round plan mismatch: expected {expected_round}, got {plan.round_number}")
        round_root = self.round_root(case_id, plan.round_number)
        atomic_write_json(round_root / "audit.before.json", audit_before.to_dict())
        atomic_write_json(round_root / "plan.json", plan.to_dict())
        atomic_write_json(round_root / "lineage.before.json", dict(lineage_before or state.get("active_lineage", {})))
        state = {
            **state,
            "status": "RUNNING",
            "active_round": plan.round_number,
            "current_focus": plan.focus or ROUND_FOCUS.get(plan.round_number, "competition_polish"),
            "next_pivot": plan.pivot,
            "open_issues": [item.issue_id for item in audit_before.findings],
            "updated_at": now_iso(),
        }
        atomic_write_json(self.hidden_path(case_id), state)
        append_jsonl(
            self.cases.case_root(case_id) / "decisions.jsonl",
            {
                "timestamp": now_iso(),
                "event": "workstation_round_started",
                "round": plan.round_number,
                "pivot": plan.pivot,
                "issue_ids": list(plan.selected_issue_ids),
            },
        )
        return state

    def record_execution(self, case_id: str, event: dict[str, Any]) -> None:
        state = self._require_running(case_id)
        round_root = self.round_root(case_id, int(state["active_round"]))
        append_jsonl(round_root / "execution.jsonl", {"timestamp": now_iso(), **event})

    def finalize_round(
        self,
        case_id: str,
        audit_after: WorkstationAudit,
        decision: WorkstationRoundDecision,
        lineage_after: dict[str, Any] | None = None,
        lessons: Iterable[str] = (),
    ) -> dict[str, Any]:
        state = self._require_running(case_id)
        round_number = int(state["active_round"])
        round_root = self.round_root(case_id, round_number)
        audit_before = WorkstationAudit.from_dict(read_json(round_root / "audit.before.json"))
        lineage_before = read_json(round_root / "lineage.before.json")
        candidate_lineage = dict(lineage_after or state.get("active_lineage", {}))
        atomic_write_json(round_root / "audit.after.json", audit_after.to_dict())
        atomic_write_json(round_root / "lineage.after.json", candidate_lineage)
        atomic_write_json(round_root / "decision.json", decision.to_dict())

        active_quality = audit_after if decision.accepted else audit_before
        old_open = set(state.get("open_issues", []))
        new_open = {item.issue_id for item in active_quality.findings}
        resolved = sorted(set(state.get("resolved_issues", [])) | (old_open - new_open))
        no_progress = 0 if decision.accepted and decision.total_delta > 0 else int(state.get("no_progress_streak", 0)) + 1
        plan_payload = read_json(round_root / "plan.json")
        history_item = {
            "round": round_number,
            "accepted": decision.accepted,
            "pivot": plan_payload.get("pivot"),
            "focus": plan_payload.get("focus") or ROUND_FOCUS.get(round_number, "competition_polish"),
            "total_before": audit_before.total,
            "total_after": audit_after.total,
            "total_delta": decision.total_delta,
            "gate_before": audit_before.gate,
            "gate_after": audit_after.gate,
            "reasons": list(decision.reasons),
        }
        merged_lessons = list(dict.fromkeys([*state.get("lessons", []), *[str(item) for item in lessons if str(item).strip()]]))
        state = {
            **state,
            "round": round_number,
            "status": "IDLE",
            "active_round": None,
            "quality": dict(active_quality.quality),
            "quality_total": active_quality.total,
            "gate": active_quality.gate,
            "open_issues": sorted(new_open),
            "resolved_issues": resolved,
            "next_pivot": None,
            "lessons": merged_lessons,
            "active_lineage": candidate_lineage if decision.accepted else lineage_before,
            "round_history": [*state.get("round_history", []), history_item],
            "no_progress_streak": no_progress,
            "updated_at": now_iso(),
        }
        atomic_write_json(self.hidden_path(case_id), state)
        append_jsonl(
            self.cases.case_root(case_id) / "decisions.jsonl",
            {
                "timestamp": now_iso(),
                "event": "workstation_round_finalized",
                "round": round_number,
                "accepted": decision.accepted,
                "total_delta": decision.total_delta,
                "reasons": list(decision.reasons),
            },
        )
        return state

    def recovery_status(self, case_id: str) -> dict[str, Any]:
        state = self.load(case_id)
        if state is None:
            return {"status": "UNINITIALIZED", "round": 0, "resumable": False}
        if state.get("status") != "RUNNING":
            return {"status": str(state.get("status")), "round": int(state.get("round", 0)), "resumable": False}
        active_round = int(state["active_round"])
        root = self.round_root(case_id, active_round)
        return {
            "status": "RUNNING",
            "round": active_round,
            "resumable": (root / "plan.json").is_file() and (root / "audit.before.json").is_file(),
            "decision_written": (root / "decision.json").is_file(),
            "execution_log_present": (root / "execution.jsonl").is_file(),
        }

    def _require_running(self, case_id: str) -> dict[str, Any]:
        state = self.load(case_id)
        if state is None or state.get("status") != "RUNNING" or state.get("active_round") is None:
            raise RuntimeError("no active workstation round")
        return state


class RecurrentWorkstationService:
    """Control plane for the outer recurrent workstation loop.

    The service owns audit/router/transaction semantics and accepts a callback
    executor for domain-specific rebuilding. Keeping execution injected avoids
    a circular dependency on ``AutoPipelineService`` while still making
    ``run_round`` / ``resume_round`` real, crash-recoverable APIs.
    """

    def __init__(
        self,
        cases: CaseManager,
        workflow: WorkflowService | None = None,
        config: RecurrentWorkstationConfig | None = None,
    ) -> None:
        self.cases = cases
        self.workflow = workflow
        self.config = config or RecurrentWorkstationConfig()
        self.auditor = WorkstationGlobalAuditor(cases)
        self.router = WorkstationRepairRouter(self.config)
        self.store = WorkstationRoundStore(cases)

    def register_bootstrap(
        self,
        case_id: str,
        active_lineage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Register a completed one-shot pipeline as Round-0 baseline.

        The outer recurrent loop starts at Round 1. Keeping the historical
        bootstrap outside the round counter lets existing cases adopt the new
        controller without pretending their original monolithic build was an
        already-reviewed recurrent repair round.
        """
        audit = self.auditor.audit(case_id)
        state = self.store.initialize(case_id, audit, active_lineage)
        return {"audit": audit, "state": state}

    def audit_and_plan(self, case_id: str) -> dict[str, Any]:
        audit = self.auditor.audit(case_id)
        state = self.store.load(case_id)
        round_number = 1 if state is None else int(state.get("round", 0)) + 1
        plan = self.router.plan(audit, round_number)
        return {"audit": audit, "plan": plan, "state": state}

    def begin_round(
        self,
        case_id: str,
        active_lineage: dict[str, Any] | None = None,
        invalidate: bool = False,
    ) -> dict[str, Any]:
        prepared = self.audit_and_plan(case_id)
        audit: WorkstationAudit = prepared["audit"]
        plan: WorkstationRoundPlan = prepared["plan"]
        if plan.pivot is None:
            state = self.store.initialize(case_id, audit, active_lineage)
            return {"started": False, "converged": True, "audit": audit, "plan": plan, "state": state}
        state = self.store.begin_round(case_id, plan, audit, active_lineage)
        invalidated = None
        if invalidate:
            if plan.repair_targets:
                # Node-level research repairs own their invalidation through
                # ProblemGraph/evidence lineage. Marking the legacy workflow
                # pivot STALE here would force a whole-branch rerun and defeat
                # the purpose of subproblem-aware M-Rounds.
                self.store.record_execution(
                    case_id,
                    {
                        "event": "research_targets_selected",
                        "pivot": plan.pivot,
                        "repair_targets": [item.to_dict() for item in plan.repair_targets],
                        "reason": plan.rationale,
                    },
                )
            else:
                if self.workflow is None:
                    raise RuntimeError("invalidate=True requires WorkflowService")
                invalidated = self.workflow.mark_stale(
                    case_id,
                    plan.pivot,
                    f"workstation round {plan.round_number}: {plan.rationale}",
                )
                self.store.record_execution(
                    case_id,
                    {"event": "workflow_invalidated", "pivot": plan.pivot, "reason": plan.rationale},
                )
        return {
            "started": True,
            "converged": False,
            "audit": audit,
            "plan": plan,
            "state": state,
            "workflow": invalidated,
        }

    def run_round(
        self,
        case_id: str,
        executor: Callable[[WorkstationRoundPlan], dict[str, Any]],
        *,
        active_lineage: dict[str, Any] | None = None,
        invalidate: bool = True,
    ) -> dict[str, Any]:
        """Audit, route, execute, evaluate and commit/reject one full Round.

        If ``executor`` raises, the Round intentionally remains ``RUNNING`` and
        its plan/before-audit stay on disk. ``resume_round`` can then continue
        from the same transaction instead of silently starting a new Round.
        """
        started = self.begin_round(case_id, active_lineage, invalidate=invalidate)
        if not started["started"]:
            return {
                **started,
                "execution": None,
                "decision": None,
                "audit_after": started["audit"],
            }
        plan: WorkstationRoundPlan = started["plan"]
        try:
            self.store.record_execution(
                case_id,
                {"event": "round_executor_started", "pivot": plan.pivot},
            )
            execution = executor(plan)
            self.store.record_execution(
                case_id,
                {
                    "event": "round_executor_succeeded",
                    "pivot": plan.pivot,
                    "executed_nodes": list(execution.get("executed_nodes", [])),
                },
            )
            audit_after = self.auditor.audit(case_id)
            decision = self.decide(
                started["audit"],
                audit_after,
                selected_issue_ids=plan.selected_issue_ids,
            )
            state = self.store.finalize_round(
                case_id,
                audit_after,
                decision,
                execution.get("lineage_after"),
                lessons=execution.get("lessons", ()),
            )
            return {
                **started,
                "execution": execution,
                "audit_after": audit_after,
                "decision": decision,
                "state": state,
                "converged": not self.should_continue(state),
            }
        except Exception as error:
            self.store.record_execution(
                case_id,
                {
                    "event": "round_executor_failed",
                    "pivot": plan.pivot,
                    "error": f"{type(error).__name__}: {error}",
                },
            )
            raise

    def resume_round(
        self,
        case_id: str,
        executor: Callable[[WorkstationRoundPlan], dict[str, Any]],
    ) -> dict[str, Any]:
        """Resume the transaction currently marked RUNNING after a crash."""
        recovery = self.store.recovery_status(case_id)
        if not recovery.get("resumable"):
            raise RuntimeError("no resumable workstation round")
        round_number = int(recovery["round"])
        root = self.store.round_root(case_id, round_number)
        plan_payload = read_json(root / "plan.json")
        plan = WorkstationRoundPlan(
            round_number=round_number,
            pivot=plan_payload.get("pivot"),
            selected_issue_ids=tuple(plan_payload.get("selected_issue_ids", [])),
            affected_domains=tuple(plan_payload.get("affected_domains", [])),
            rationale=str(plan_payload.get("rationale", "resume recurrent round")),
            full_audit_required=bool(plan_payload.get("full_audit_required", True)),
            repair_targets=tuple(
                ResearchRepairTarget(
                    subproblem_id=str(item["subproblem_id"]),
                    phase=str(item["phase"]),
                    code=str(item["code"]),
                    source=str(item.get("source", "unknown")),
                    evidence_ids=tuple(item.get("evidence_ids", [])),
                )
                for item in plan_payload.get("repair_targets", [])
            ),
            focus=str(plan_payload.get("focus") or ROUND_FOCUS.get(round_number, "competition_polish")),
        )
        audit_before = WorkstationAudit.from_dict(read_json(root / "audit.before.json"))
        try:
            self.store.record_execution(
                case_id,
                {"event": "round_executor_resumed", "pivot": plan.pivot},
            )
            execution = executor(plan)
            audit_after = self.auditor.audit(case_id)
            decision = self.decide(
                audit_before,
                audit_after,
                selected_issue_ids=plan.selected_issue_ids,
            )
            state = self.store.finalize_round(
                case_id,
                audit_after,
                decision,
                execution.get("lineage_after"),
                lessons=execution.get("lessons", ()),
            )
            return {
                "started": True,
                "resumed": True,
                "plan": plan,
                "audit": audit_before,
                "execution": execution,
                "audit_after": audit_after,
                "decision": decision,
                "state": state,
                "converged": not self.should_continue(state),
            }
        except Exception as error:
            self.store.record_execution(
                case_id,
                {
                    "event": "round_executor_resume_failed",
                    "pivot": plan.pivot,
                    "error": f"{type(error).__name__}: {error}",
                },
            )
            raise

    def run_until_converged(
        self,
        case_id: str,
        executor: Callable[[WorkstationRoundPlan], dict[str, Any]],
        *,
        invalidate: bool = True,
    ) -> dict[str, Any]:
        """Execute bounded recurrent Rounds until convergence/budget/patience."""
        rounds: list[dict[str, Any]] = []
        while True:
            current = self.store.load(case_id)
            if current is not None and int(current.get("round", 0)) > 0 and not self.should_continue(current):
                return {"case_id": case_id, "rounds": rounds, "state": current, "converged": True}
            result = self.run_round(case_id, executor, invalidate=invalidate)
            rounds.append(result)
            if not result["started"] or result["converged"]:
                return {
                    "case_id": case_id,
                    "rounds": rounds,
                    "state": result["state"],
                    "converged": result["converged"],
                }

    def decide(
        self,
        before: WorkstationAudit,
        after: WorkstationAudit,
        *,
        selected_issue_ids: Iterable[str] = (),
    ) -> WorkstationRoundDecision:
        return decide_round(
            before,
            after,
            self.config,
            selected_issue_ids=selected_issue_ids,
        )

    def should_continue(self, state: dict[str, Any]) -> bool:
        rounds = int(state.get("round", 0))
        if rounds >= self.config.max_rounds:
            return False
        if rounds < self.config.min_rounds:
            return True
        if state.get("gate") == "PASS" and float(state.get("quality_total", 0.0)) >= self.config.target_total:
            return False
        if int(state.get("no_progress_streak", 0)) >= self.config.patience:
            return False
        return True


def decide_round(
    before: WorkstationAudit,
    after: WorkstationAudit,
    config: RecurrentWorkstationConfig | None = None,
    *,
    selected_issue_ids: Iterable[str] = (),
) -> WorkstationRoundDecision:
    config = config or RecurrentWorkstationConfig()
    domain_deltas = {
        domain: round(after.quality[domain] - before.quality[domain], 6)
        for domain in WORKSTATION_DOMAINS
    }
    total_delta = round(after.total - before.total, 6)
    reasons: list[str] = []
    new_p0 = {item.issue_id for item in after.findings if item.severity == "P0"} - {
        item.issue_id for item in before.findings if item.severity == "P0"
    }
    regressions = {
        domain: delta
        for domain, delta in domain_deltas.items()
        if delta < -config.max_domain_regression
    }
    before_hard = sum(item.severity in {"P0", "P1"} for item in before.findings)
    after_hard = sum(item.severity in {"P0", "P1"} for item in after.findings)
    severity_weight = {"P0": 4, "P1": 2, "P2": 1}
    before_burden = sum(severity_weight.get(item.severity, 0) for item in before.findings)
    after_burden = sum(severity_weight.get(item.severity, 0) for item in after.findings)
    gate_improved = _gate_rank(after.gate) > _gate_rank(before.gate)
    hard_improved = after_hard < before_hard
    finding_burden_improved = after_burden < before_burden
    selected = {str(value) for value in selected_issue_ids if str(value)}
    after_issue_ids = {item.issue_id for item in after.findings}
    resolved_selected = sorted(selected - after_issue_ids)

    if new_p0:
        reasons.append(f"new P0 findings: {sorted(new_p0)}")
    if regressions:
        reasons.append(f"domain regression beyond tolerance: {regressions}")

    positive = (
        total_delta + 1e-9 >= config.min_delta
        or gate_improved
        or hard_improved
        or finding_burden_improved
        or bool(resolved_selected)
    )
    if not positive:
        reasons.append(
            f"no material improvement: total_delta={total_delta:.6f}, min_delta={config.min_delta:.6f}"
        )
    accepted = not new_p0 and not regressions and positive
    if accepted:
        if gate_improved:
            reasons.append(f"gate improved {before.gate}->{after.gate}")
        if hard_improved:
            reasons.append(f"hard findings reduced {before_hard}->{after_hard}")
        if finding_burden_improved:
            reasons.append(f"finding severity burden reduced {before_burden}->{after_burden}")
        if resolved_selected:
            reasons.append(f"selected findings resolved: {resolved_selected}")
        if total_delta > 0:
            reasons.append(f"quality total improved by {total_delta:.6f}")
    return WorkstationRoundDecision(
        accepted=accepted,
        reasons=tuple(reasons),
        total_delta=total_delta,
        domain_deltas=domain_deltas,
        decided_at=now_iso(),
    )


def _finding(
    *,
    domain: str,
    severity: str,
    code: str,
    message: str,
    repair_node: str,
    source: str,
    evidence_ids: Iterable[str] = (),
    subproblem_id: str | None = None,
    repair_phase: str | None = None,
    research_artifact_id: str | None = None,
) -> WorkstationFinding:
    payload = f"{domain}|{severity}|{code}|{repair_node}|{message}"
    issue_id = f"ws-issue-{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:12]}"
    return WorkstationFinding(
        issue_id=issue_id,
        domain=domain,
        severity=severity,
        code=code,
        message=message,
        repair_node=repair_node,
        source=source,
        evidence_ids=tuple(evidence_ids),
        subproblem_id=subproblem_id,
        repair_phase=repair_phase,
        research_artifact_id=research_artifact_id,
    )


def _dedupe_findings(findings: Iterable[WorkstationFinding]) -> list[WorkstationFinding]:
    by_id: dict[str, WorkstationFinding] = {}
    for item in findings:
        by_id.setdefault(item.issue_id, item)
    return sorted(
        by_id.values(),
        key=lambda item: (
            _SEVERITY_RANK.get(item.severity, 9),
            _NODE_INDEX.get(item.repair_node, len(_NODE_INDEX)),
            item.code,
            item.issue_id,
        ),
    )


def _gate_rank(gate: str) -> int:
    return {"BLOCK": 0, "REVIEW": 1, "PASS": 2}.get(gate, -1)


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))

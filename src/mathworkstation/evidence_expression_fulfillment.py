from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .io_utils import atomic_write_json, now_iso
from .paper_model_equations import equations_for_method
from .research_preferences import ResearchPreferenceService


FulfillmentStatus = Literal["SATISFIED", "MISSING_PRESENTATION", "MISSING_EVIDENCE", "OPTIONAL_SKIPPED"]
FulfillmentGate = Literal["PASS", "REVIEW"]


class ExpressionFulfillmentItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    need_id: str
    subproblem_id: str | None = None
    medium: str
    semantic_kind: str
    priority: str
    status: FulfillmentStatus
    matched_ids: list[str] = Field(default_factory=list)
    repair_phase: str
    detail: str


class ExpressionFulfillmentAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str
    gate: FulfillmentGate
    items: list[ExpressionFulfillmentItem]
    required_missing_count: int
    recommended_missing_count: int
    checked_at: str


class EvidenceExpressionFulfillmentService:
    """Audit whether planned equations/figures/tables are actually fulfilled.

    The service never fabricates a missing visual or formula.  It distinguishes a
    presentation gap (the research evidence exists but the paper medium is absent)
    from an evidence gap (the requested medium would require results that were
    never computed).  This distinction lets the recurrent workstation route a
    defect either back to experiments or forward to paper/figure composition.
    """

    def __init__(self, cases: Any, artifacts: Any) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.preferences = ResearchPreferenceService(cases, artifacts)

    def assess(
        self,
        case_id: str,
        graph: Any,
        figures: list[dict[str, Any]],
        tables: list[Any],
    ) -> ExpressionFulfillmentAssessment:
        items: list[ExpressionFulfillmentItem] = []
        research_nodes = [node for node in graph.nodes if getattr(node, "role", "") == "RESEARCH"]
        figure_kinds = [
            (str((item.get("parameters") or {}).get("subproblem_id") or ""),
             str((item.get("parameters") or {}).get("semantic_kind") or ""),
             str(item.get("figure_id") or ""))
            for item in figures
            if item.get("status") == "FINAL"
        ]
        table_roles = [
            (
                str((getattr(table, "metadata", {}) or {}).get("subproblem_id") or ""),
                str((getattr(table, "metadata", {}) or {}).get("table_role") or "summary_metrics"),
                str(getattr(table, "table_id", "")),
            )
            for table in tables
        ]

        # Whole-paper orientation needs are structural and can be checked without
        # touching numeric evidence.
        if len(research_nodes) > 1:
            items.append(
                self._figure_item(
                    need_id="paper:research-workflow",
                    subproblem_id=None,
                    semantic_kind="research_workflow",
                    priority="REQUIRED",
                    figure_kinds=figure_kinds,
                    evidence_exists=True,
                    repair_phase="paper_visual",
                )
            )
        preferences = self.preferences.load(case_id)
        if preferences.unified_framework_preferred and any(getattr(node, "model_structure", None) for node in research_nodes):
            items.append(
                self._figure_item(
                    need_id="paper:unified-model-framework",
                    subproblem_id=None,
                    semantic_kind="model_framework",
                    priority="RECOMMENDED",
                    figure_kinds=figure_kinds,
                    evidence_exists=True,
                    repair_phase="paper_visual",
                )
            )

        for node in research_nodes:
            plan = getattr(node, "expression_plan", None)
            if plan is None:
                continue
            equation_pool = equations_for_method(str(node.method or ""))
            equation_slots_used = 0
            for need in plan.needs:
                medium = str(need.medium)
                if medium == "FIGURE":
                    evidence_exists = bool(getattr(node, "key_results", []) or getattr(node, "model_structure", None))
                    items.append(
                        self._figure_item(
                            need_id=need.need_id,
                            subproblem_id=node.subproblem_id,
                            semantic_kind=need.semantic_kind,
                            priority=need.priority,
                            figure_kinds=figure_kinds,
                            evidence_exists=evidence_exists,
                            repair_phase=("validation" if need.semantic_kind in {"sensitivity", "probability_validation"} else "paper_visual"),
                        )
                    )
                elif medium == "TABLE":
                    matched = _matching_tables(node.subproblem_id, need.semantic_kind, table_roles)
                    evidence_exists = bool(getattr(node, "key_results", []))
                    status = _status_for_match(bool(matched), evidence_exists, need.priority)
                    items.append(
                        ExpressionFulfillmentItem(
                            need_id=need.need_id,
                            subproblem_id=node.subproblem_id,
                            medium="TABLE",
                            semantic_kind=need.semantic_kind,
                            priority=need.priority,
                            status=status,
                            matched_ids=matched,
                            repair_phase=("paper_table" if evidence_exists else "evidence"),
                            detail=_detail("table", need.semantic_kind, status),
                        )
                    )
                elif medium == "EQUATION":
                    equation_slots_used += 1
                    matched = [f"method-equation-{equation_slots_used}"] if len(equation_pool) >= equation_slots_used else []
                    structure = getattr(node, "model_structure", None)
                    evidence_exists = bool(structure and getattr(structure, "core_relations", []))
                    status = _status_for_match(bool(matched), evidence_exists, need.priority)
                    items.append(
                        ExpressionFulfillmentItem(
                            need_id=need.need_id,
                            subproblem_id=node.subproblem_id,
                            medium="EQUATION",
                            semantic_kind=need.semantic_kind,
                            priority=need.priority,
                            status=status,
                            matched_ids=matched,
                            repair_phase=("paper_equation" if evidence_exists else "model_structure"),
                            detail=_detail("equation", need.semantic_kind, status),
                        )
                    )
                elif medium == "DEFINITION":
                    structure = getattr(node, "model_structure", None)
                    satisfied = bool(structure and (structure.state_variables or structure.decision_variables or structure.objective_or_estimand))
                    status = "SATISFIED" if satisfied else ("MISSING_EVIDENCE" if need.priority == "REQUIRED" else "OPTIONAL_SKIPPED")
                    items.append(
                        ExpressionFulfillmentItem(
                            need_id=need.need_id,
                            subproblem_id=node.subproblem_id,
                            medium="DEFINITION",
                            semantic_kind=need.semantic_kind,
                            priority=need.priority,
                            status=status,
                            repair_phase="model_structure",
                            detail=_detail("definition", need.semantic_kind, status),
                        )
                    )

        required_missing = sum(
            item.priority == "REQUIRED" and item.status not in {"SATISFIED", "OPTIONAL_SKIPPED"}
            for item in items
        )
        recommended_missing = sum(
            item.priority == "RECOMMENDED" and item.status not in {"SATISFIED", "OPTIONAL_SKIPPED"}
            for item in items
        )
        return ExpressionFulfillmentAssessment(
            case_id=case_id,
            # Recommended media remain an optimization queue, not a hidden count
            # quota. Only a missing REQUIRED expression blocks paper readiness.
            gate="REVIEW" if required_missing else "PASS",
            items=items,
            required_missing_count=required_missing,
            recommended_missing_count=recommended_missing,
            checked_at=now_iso(),
        )

    def persist(
        self,
        case_id: str,
        assessment: ExpressionFulfillmentAssessment,
        *,
        source_artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        root = self.cases.case_root(case_id)
        path = root / "review" / "expression_fulfillment" / "assessment.json"
        atomic_write_json(path, assessment.model_dump(mode="json"))
        artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "evidence_expression_fulfillment",
            "evidence_expression_fulfillment",
            upstream=list(source_artifact_ids or []),
            paper_eligible=False,
        )
        return {"assessment": assessment, "artifact": artifact}

    @staticmethod
    def _figure_item(
        *,
        need_id: str,
        subproblem_id: str | None,
        semantic_kind: str,
        priority: str,
        figure_kinds: list[tuple[str, str, str]],
        evidence_exists: bool,
        repair_phase: str,
    ) -> ExpressionFulfillmentItem:
        matched = _matching_figures(subproblem_id, semantic_kind, figure_kinds)
        status = _status_for_match(bool(matched), evidence_exists, priority)
        return ExpressionFulfillmentItem(
            need_id=need_id,
            subproblem_id=subproblem_id,
            medium="FIGURE",
            semantic_kind=semantic_kind,
            priority=priority,
            status=status,
            matched_ids=matched,
            repair_phase=repair_phase if status == "MISSING_EVIDENCE" else "paper_visual",
            detail=_detail("figure", semantic_kind, status),
        )


def _status_for_match(matched: bool, evidence_exists: bool, priority: str) -> FulfillmentStatus:
    if matched:
        return "SATISFIED"
    if priority == "OPTIONAL":
        return "OPTIONAL_SKIPPED"
    return "MISSING_PRESENTATION" if evidence_exists else "MISSING_EVIDENCE"


def _matching_figures(
    subproblem_id: str | None,
    semantic_kind: str,
    figures: list[tuple[str, str, str]],
) -> list[str]:
    matches: list[str] = []
    for owner, kind, figure_id in figures:
        if subproblem_id is not None and owner not in {subproblem_id, ""}:
            continue
        if _figure_kind_matches(semantic_kind, kind):
            matches.append(figure_id)
    return matches


def _figure_kind_matches(required: str, actual: str) -> bool:
    if required == actual:
        return True
    if required == "model_framework":
        return actual == "model_framework"
    if required == "state_structure":
        return actual in {"state_structure", "model_framework", "state_transition", "probabilistic_graphical_model"}
    if required == "sensitivity":
        return "sensitivity" in actual or "robust" in actual
    if required == "probability_validation":
        return any(token in actual for token in ("probability", "calibration", "null", "permutation", "reliability"))
    if required == "state_trajectory":
        return any(token in actual for token in ("trajectory", "flow", "momentum", "time_series", "timeseries"))
    if required == "forecast_interval":
        return "forecast" in actual and ("interval" in actual or "uncertainty" in actual)
    if required == "ranking_structure":
        return "ranking" in actual or "criteria" in actual
    if required == "evidence_figure":
        return bool(actual)
    return False


def _matching_tables(
    subproblem_id: str,
    semantic_kind: str,
    tables: list[tuple[str, str, str]],
) -> list[str]:
    target_roles = {
        "decision_table": {"decision_schedule", "decision_table"},
        "ranking_table": {"ranking", "ranking_table", "summary_metrics"},
    }.get(semantic_kind, {semantic_kind})
    return [table_id for owner, role, table_id in tables if owner == subproblem_id and role in target_roles]


def _detail(medium: str, semantic_kind: str, status: FulfillmentStatus) -> str:
    if status == "SATISFIED":
        return f"{medium} requirement {semantic_kind} is represented by an existing accepted paper asset."
    if status == "OPTIONAL_SKIPPED":
        return f"optional {medium} requirement {semantic_kind} is intentionally not forced by a quota."
    if status == "MISSING_PRESENTATION":
        return f"research structure/evidence exists, but the planned {medium} representation {semantic_kind} is absent."
    return f"planned {medium} representation {semantic_kind} cannot be produced safely because supporting research evidence is missing."

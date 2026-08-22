from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .model_structure import ModelStructurePlan, UnifiedModelFrameworkPlan
from .research_preferences import ResearchPreferenceProfile


ExpressionMedium = Literal["TEXT", "DEFINITION", "EQUATION", "FIGURE", "TABLE", "PANEL", "ALGORITHM"]
ExpressionPriority = Literal["REQUIRED", "RECOMMENDED", "OPTIONAL"]


class EvidenceExpressionNeed(BaseModel):
    """One rhetorical/evidence job and the medium best suited to perform it."""

    model_config = ConfigDict(extra="forbid")

    need_id: str
    medium: ExpressionMedium
    priority: ExpressionPriority
    purpose: str
    semantic_kind: str
    evidence_requirement: str
    rationale: str
    pairable: bool = False
    avoid_if: list[str] = Field(default_factory=list)


class EvidenceExpressionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    subproblem_id: str
    needs: list[EvidenceExpressionNeed]
    selection_rules: list[str]
    anti_quota_rules: list[str]


class WholePaperExpressionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    global_needs: list[EvidenceExpressionNeed]
    subproblem_plans: dict[str, EvidenceExpressionPlan]
    composition_rules: list[str]


class EvidenceExpressionPlanner:
    """Choose equation/figure/table/text roles from argument semantics, never quotas."""

    def plan_node(
        self,
        structure: ModelStructurePlan,
        preferences: ResearchPreferenceProfile | None = None,
    ) -> EvidenceExpressionPlan:
        preferences = preferences or ResearchPreferenceProfile()
        needs: list[EvidenceExpressionNeed] = []

        if structure.framework_role in {"FOUNDATION", "CORE_MODEL"}:
            needs.append(
                EvidenceExpressionNeed(
                    need_id=f"{structure.subproblem_id}:principal-definition",
                    medium="DEFINITION",
                    priority="REQUIRED",
                    purpose="Define the principal modeled quantity/state before reporting its values.",
                    semantic_kind="model_definition",
                    evidence_requirement="Definition must be consistent with the executed solver/data transformation.",
                    rationale="Readers must know what a scalar/state means before seeing numerical values such as 0.6731.",
                )
            )

        for index, role in enumerate(structure.equation_roles, start=1):
            lowered_role = role.lower()
            if "objective" in lowered_role or "constraint" in lowered_role:
                priority: ExpressionPriority = "REQUIRED"
            elif "validation" in lowered_role or "statistical criterion" in lowered_role:
                priority = "RECOMMENDED"
            elif structure.framework_role in {"FOUNDATION", "CORE_MODEL", "INDEPENDENT_MODEL"} and index == 1:
                priority = "REQUIRED"
            elif structure.framework_role in {"CORE_MODEL", "INDEPENDENT_MODEL"} and index == 2 and "generic_structure" not in structure.archetypes:
                priority = "REQUIRED"
            else:
                priority = "RECOMMENDED"
            needs.append(
                EvidenceExpressionNeed(
                    need_id=f"{structure.subproblem_id}:equation:{index}",
                    medium="EQUATION",
                    priority=priority,
                    purpose=role,
                    semantic_kind=_equation_semantic_kind(role),
                    evidence_requirement="Equation symbols and numerical parameters must trace to accepted research state.",
                    rationale="Use an equation when the mathematical relation itself carries the argument; do not add formulas merely for visual complexity.",
                    pairable=False,
                )
            )

        for index, role in enumerate(structure.visual_roles, start=1):
            priority = "REQUIRED" if _visual_is_structural(role) else "RECOMMENDED"
            needs.append(
                EvidenceExpressionNeed(
                    need_id=f"{structure.subproblem_id}:visual:{index}",
                    medium="FIGURE",
                    priority=priority,
                    purpose=role,
                    semantic_kind=_visual_semantic_kind(role),
                    evidence_requirement="Numeric plots must use immutable solver/evidence data; explanatory diagrams may not invent numeric claims.",
                    rationale="A figure is selected because spatial/temporal/structural comparison is easier to understand visually than as prose or a table.",
                    pairable=not _visual_is_structural(role),
                    avoid_if=["The figure would repeat the same comparison already readable in a compact table.", "No evidence exists for the plotted quantities."],
                )
            )

        if structure.decision_variables:
            needs.append(
                EvidenceExpressionNeed(
                    need_id=f"{structure.subproblem_id}:decision-table",
                    medium="TABLE",
                    priority="REQUIRED",
                    purpose="Report the final decision variables, units, constraints and objective contribution in an auditable form.",
                    semantic_kind="decision_table",
                    evidence_requirement="Every row/cell must trace to accepted optimization output.",
                    rationale="Tables are superior to charts when exact multi-entity decision values must be recoverable by the judge.",
                )
            )

        if "ranking_evaluation" in structure.archetypes:
            needs.append(
                EvidenceExpressionNeed(
                    need_id=f"{structure.subproblem_id}:ranking-table",
                    medium="TABLE",
                    priority="REQUIRED",
                    purpose="Show exact alternative scores/ranks and the criteria contributing to them.",
                    semantic_kind="ranking_table",
                    evidence_requirement="Scores and ranks must come from accepted evaluation evidence.",
                    rationale="Exact rank and score lookup is a table task; ranking stability or criterion trade-offs may use a companion figure.",
                    pairable=True,
                )
            )

        if any("sensitivity" in item.lower() or "robust" in item.lower() for item in structure.validation_requirements):
            needs.append(
                EvidenceExpressionNeed(
                    need_id=f"{structure.subproblem_id}:robustness-evidence",
                    medium="FIGURE",
                    priority="RECOMMENDED",
                    purpose="Show how the main conclusion/decision changes under the key uncertain parameter or assumption.",
                    semantic_kind="sensitivity",
                    evidence_requirement="Only perturb parameters/scenarios actually evaluated by the solver or validation protocol.",
                    rationale="A response curve or compact panel reveals stability regimes faster than a list of isolated numbers.",
                    pairable=True,
                )
            )

        if any("calibration" in item.lower() or "probability" in item.lower() or "null" in item.lower() for item in structure.validation_requirements):
            needs.append(
                EvidenceExpressionNeed(
                    need_id=f"{structure.subproblem_id}:probability-validation",
                    medium="FIGURE",
                    priority="RECOMMENDED",
                    purpose="Visualize probability/null-model validation rather than relying on one scalar score.",
                    semantic_kind="probability_validation",
                    evidence_requirement="Plot must come from held-out, resampled, or simulated validation evidence.",
                    rationale="Probability models need distributional/calibration evidence; a single accuracy value is structurally incomplete.",
                    pairable=True,
                )
            )

        needs.append(
            EvidenceExpressionNeed(
                need_id=f"{structure.subproblem_id}:scope-text",
                medium="TEXT",
                priority="REQUIRED",
                purpose="Explain assumptions, limits, inheritance from upstream questions, and the interpretation of validation results.",
                semantic_kind="argument_transition",
                evidence_requirement="No new numerical result may be introduced in prose.",
                rationale="Some argumentative work is semantic rather than visual; forcing every statement into a chart weakens the paper.",
            )
        )

        return EvidenceExpressionPlan(
            subproblem_id=structure.subproblem_id,
            needs=_deduplicate_needs(needs),
            selection_rules=[
                "Use EQUATION for definitions/relations whose mathematical form is itself part of the model.",
                "Use FIGURE for trends, distributions, geometry, mechanisms, uncertainty, sensitivity and many-to-many visual comparison.",
                "Use TABLE for exact values, decision schedules, parameter summaries, ranks and compact lookup.",
                "Use PANEL only when multiple small plots answer one shared question; do not create panels only to increase figure count.",
                "A model parameter should be defined by an equation or compact parameter table at first introduction; avoid isolated naked scalars.",
                "Use TEXT for assumptions, causal caution, limitations and logical transitions that are not improved by a visual encoding.",
            ],
            anti_quota_rules=[
                "There is no target number of figures, tables or equations.",
                "Do not create a figure/table/equation whose only purpose is to satisfy a count threshold.",
                "When one strong panel performs one argument better than four separate figures, prefer the panel.",
                "When an exact table and a chart would duplicate the same information, keep only the medium required by the argument unless each has a distinct role.",
            ],
        )

    def plan_paper(
        self,
        structures: dict[str, ModelStructurePlan],
        framework: UnifiedModelFrameworkPlan,
        preferences: ResearchPreferenceProfile | None = None,
    ) -> WholePaperExpressionPlan:
        preferences = preferences or ResearchPreferenceProfile()
        global_needs: list[EvidenceExpressionNeed] = []
        if len([plan for plan in structures.values() if plan.framework_role != "SYNTHESIS"]) > 1:
            global_needs.append(
                EvidenceExpressionNeed(
                    need_id="paper:research-workflow",
                    medium="FIGURE",
                    priority="REQUIRED",
                    purpose="Show the dependency-aware research workflow from data/problem analysis through the model spine to validation and deliverables.",
                    semantic_kind="research_workflow",
                    evidence_requirement="Arrows and labels must be derived from the accepted ProblemGraph/ModelSpine.",
                    rationale="Award papers often establish orientation visually; this diagram prevents later questions from appearing as unrelated model demos.",
                )
            )
        if preferences.unified_framework_preferred:
            global_needs.append(
                EvidenceExpressionNeed(
                    need_id="paper:unified-model-framework",
                    medium="FIGURE",
                    priority="RECOMMENDED",
                    purpose="Explain the shared state/mechanism/decision framework and identify what each question inherits or extends.",
                    semantic_kind="model_framework",
                    evidence_requirement="Only mathematical objects and dependencies present in ModelStructurePlan may appear.",
                    rationale="This is different from the research workflow: it explains the model architecture rather than the project process.",
                )
            )
        if preferences.paper_style == "award_rich" or preferences.visual_density == "rich":
            global_needs.append(
                EvidenceExpressionNeed(
                    need_id="paper:context-orientation",
                    medium="FIGURE",
                    priority="OPTIONAL",
                    purpose="Provide one trustworthy context/orientation visual when it materially helps the reader enter the real problem setting.",
                    semantic_kind="context_reality",
                    evidence_requirement="Source, license and attribution must be verified; it cannot serve as numeric evidence.",
                    rationale="A context visual is useful only when the physical/business/sports setting benefits from visual orientation.",
                )
            )
        subplans = {sid: self.plan_node(plan, preferences) for sid, plan in structures.items()}
        return WholePaperExpressionPlan(
            global_needs=global_needs,
            subproblem_plans=subplans,
            composition_rules=[
                "Place each visual near the claim or model step it explains, not in a detached figure gallery.",
                "Alternate explanatory diagrams, equations, numeric evidence and exact tables according to argument needs to create page rhythm.",
                "A global workflow diagram and a model-framework diagram may coexist only when they answer different questions: process versus mathematical architecture.",
                "Use multi-panel composition for tightly related diagnostics; preserve large single figures for visually complex mechanisms or primary results.",
            ],
        )


def _equation_semantic_kind(role: str) -> str:
    lowered = role.lower()
    if "objective" in lowered:
        return "objective_function"
    if "constraint" in lowered:
        return "constraint_system"
    if "transition" in lowered or "update" in lowered or "evolution" in lowered:
        return "state_transition"
    if "probability" in lowered or "link" in lowered:
        return "probability_relation"
    if "latent" in lowered:
        return "latent_observation_relation"
    if "definition" in lowered:
        return "model_definition"
    return "core_model_relation"


def _visual_is_structural(role: str) -> bool:
    lowered = role.lower()
    return any(token in lowered for token in ("framework", "mechanism", "graphical model", "state diagram", "constraint schematic"))


def _visual_semantic_kind(role: str) -> str:
    lowered = role.lower()
    if "framework" in lowered or "mechanism" in lowered:
        return "model_framework"
    if "graphical model" in lowered or "state diagram" in lowered or "transition" in lowered:
        return "state_structure"
    if "trajectory" in lowered or "flow" in lowered:
        return "state_trajectory"
    if "sensitivity" in lowered or "feasible" in lowered:
        return "sensitivity"
    if "calibration" in lowered or "null" in lowered:
        return "probability_validation"
    if "forecast" in lowered:
        return "forecast_interval"
    if "ranking" in lowered or "criteria" in lowered:
        return "ranking_structure"
    return "evidence_figure"


def _deduplicate_needs(needs: list[EvidenceExpressionNeed]) -> list[EvidenceExpressionNeed]:
    seen: set[tuple[str, str]] = set()
    result: list[EvidenceExpressionNeed] = []
    for need in needs:
        key = (need.medium, need.semantic_kind)
        # Preserve distinct required core equations; deduplicate repeated visual/table jobs.
        if key in seen and need.medium not in {"EQUATION"}:
            continue
        seen.add(key)
        result.append(need)
    return result

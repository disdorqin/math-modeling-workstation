from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .problem_graph import ProblemGraph, SubproblemNode
from .research_preferences import ResearchPreferenceProfile


ModelArchetype = Literal[
    "dynamic_state",
    "probabilistic_state",
    "forecasting",
    "explanatory_inference",
    "optimization",
    "simulation",
    "ranking_evaluation",
    "network_spatial",
    "discrete_process",
    "geometry",
    "generic_structure",
]
FrameworkRole = Literal["FOUNDATION", "CORE_MODEL", "EXTENSION", "INDEPENDENT_MODEL", "SYNTHESIS"]


class ModelStructurePlan(BaseModel):
    """Mathematical structure that must be decided before choosing algorithms.

    The plan is deliberately solver-agnostic.  It states what the model *is*:
    objects, states, relations, constraints, uncertainty and validation.  A
    Random Forest, optimizer, MCMC sampler, etc. is only a possible numerical
    engine for estimating or solving this structure.
    """

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    subproblem_id: str
    framework_role: FrameworkRole
    archetypes: list[ModelArchetype] = Field(min_length=1)
    mathematical_objects: list[str] = Field(min_length=1)
    observed_variables: list[str] = Field(default_factory=list)
    state_variables: list[str] = Field(default_factory=list)
    latent_variables: list[str] = Field(default_factory=list)
    decision_variables: list[str] = Field(default_factory=list)
    parameters: list[str] = Field(default_factory=list)
    core_relations: list[str] = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    objective_or_estimand: str
    uncertainty_sources: list[str] = Field(default_factory=list)
    identifiability_questions: list[str] = Field(default_factory=list)
    validation_requirements: list[str] = Field(min_length=1)
    equation_roles: list[str] = Field(default_factory=list)
    visual_roles: list[str] = Field(default_factory=list)
    inherited_structure: list[str] = Field(default_factory=list)
    new_structure: list[str] = Field(default_factory=list)
    solver_role: str
    depth_warnings: list[str] = Field(default_factory=list)


class UnifiedModelFrameworkPlan(BaseModel):
    """Whole-problem model spine shared by multiple questions."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    anchor_subproblem_id: str
    shared_objects: list[str] = Field(default_factory=list)
    shared_state_representation: list[str] = Field(default_factory=list)
    shared_relations: list[str] = Field(default_factory=list)
    node_roles: dict[str, FrameworkRole]
    inheritance_chain: list[str] = Field(default_factory=list)
    continuity_rules: list[str] = Field(default_factory=list)
    anti_model_zoo_rules: list[str] = Field(default_factory=list)


class ModelStructurePlanner:
    """Infer a contest-agnostic mathematical structure from ProblemGraph semantics."""

    def plan_node(
        self,
        node: SubproblemNode,
        graph: ProblemGraph,
        preferences: ResearchPreferenceProfile | None = None,
    ) -> ModelStructurePlan:
        role_map = self._roles(graph)
        role = role_map[node.subproblem_id]
        text = " ".join(
            [node.title, node.objective, *node.inputs, *node.outputs, *node.constraints, node.task_family]
        ).lower()
        preferences = preferences or ResearchPreferenceProfile()
        archetypes = self._archetypes(node.task_family, text, preferences)
        objects = self._objects(node, archetypes)
        observed = list(dict.fromkeys(node.inputs))
        inherited = self._inherited(node, graph)
        state = self._states(archetypes, text, inherited)
        latent = self._latent(archetypes, text)
        decisions = self._decisions(archetypes, node)
        parameters = self._parameters(archetypes)
        relations = self._relations(archetypes, node)
        constraints = list(dict.fromkeys([*node.constraints, *self._structural_constraints(archetypes)]))
        estimand = self._objective(node, archetypes)
        uncertainty = self._uncertainty(archetypes)
        identifiability = self._identifiability(archetypes, latent, parameters)
        validation = self._validation(archetypes, node.task_family)
        equation_roles = self._equation_roles(archetypes, decisions, latent, node.task_family)
        visual_roles = self._visual_roles(archetypes, role)
        new_structure = self._new_structure(role, archetypes)
        warnings = self._depth_warnings(node, archetypes, latent, constraints, relations)
        return ModelStructurePlan(
            subproblem_id=node.subproblem_id,
            framework_role=role,
            archetypes=archetypes,
            mathematical_objects=objects,
            observed_variables=observed,
            state_variables=state,
            latent_variables=latent,
            decision_variables=decisions,
            parameters=parameters,
            core_relations=relations,
            constraints=constraints,
            objective_or_estimand=estimand,
            uncertainty_sources=uncertainty,
            identifiability_questions=identifiability,
            validation_requirements=validation,
            equation_roles=equation_roles,
            visual_roles=visual_roles,
            inherited_structure=inherited,
            new_structure=new_structure,
            solver_role=(
                "Estimate parameters / latent states or solve the declared mathematical structure; "
                "solver performance must not redefine the model semantics."
            ),
            depth_warnings=warnings,
        )

    def plan_graph(
        self,
        graph: ProblemGraph,
        preferences: ResearchPreferenceProfile | None = None,
    ) -> UnifiedModelFrameworkPlan:
        preferences = preferences or ResearchPreferenceProfile()
        roles = self._roles(graph)
        plans = {node.subproblem_id: self.plan_node(node, graph, preferences) for node in graph.nodes}
        anchor = next(
            (sid for sid, role in roles.items() if role == "CORE_MODEL"),
            next(sid for sid, role in roles.items() if role != "SYNTHESIS"),
        )
        shared_objects = _shared_values([plan.mathematical_objects for plan in plans.values() if plan.framework_role != "SYNTHESIS"])
        shared_states = _shared_values([plan.state_variables for plan in plans.values() if plan.framework_role != "SYNTHESIS"])
        shared_relations = _shared_values([plan.core_relations for plan in plans.values() if plan.framework_role != "SYNTHESIS"])
        chain = [node.subproblem_id for node in graph.nodes if roles[node.subproblem_id] != "SYNTHESIS"]
        return UnifiedModelFrameworkPlan(
            anchor_subproblem_id=anchor,
            shared_objects=shared_objects,
            shared_state_representation=shared_states,
            shared_relations=shared_relations,
            node_roles=roles,
            inheritance_chain=chain,
            continuity_rules=[
                "Later questions must inherit accepted upstream variables, states, parameters or constraints when semantics allow.",
                "A new model family requires an explicit structural reason: new state, mechanism, constraint, objective or data regime.",
                "Validation belongs to the claim being made; a generic accuracy paragraph cannot validate every question.",
                "Deliverables synthesize accepted evidence and do not introduce new unsupported mathematics.",
            ],
            anti_model_zoo_rules=[
                "Do not assign an unrelated algorithm to each question merely to increase model diversity.",
                "Do not select a method because it is frequent in award papers; corpus frequency is only a retrieval prior.",
                "Do not use predictive accuracy as the sole reason to replace a more interpretable structural model.",
            ],
        )

    def _roles(self, graph: ProblemGraph) -> dict[str, FrameworkRole]:
        research = [node for node in graph.nodes if node.execution_kind != "DELIVERABLE"]
        if not research:
            return {node.subproblem_id: "SYNTHESIS" for node in graph.nodes}
        downstream = {node.subproblem_id: 0 for node in research}
        for node in research:
            for dep in node.dependencies:
                if dep in downstream:
                    downstream[dep] += 1
        # Prefer a node reused downstream; otherwise the first substantial research node.
        anchor_node = max(research, key=lambda n: (downstream[n.subproblem_id], len(n.dependencies), -research.index(n)))
        roles: dict[str, FrameworkRole] = {}
        for index, node in enumerate(graph.nodes):
            if node.execution_kind == "DELIVERABLE":
                roles[node.subproblem_id] = "SYNTHESIS"
            elif node.subproblem_id == anchor_node.subproblem_id:
                roles[node.subproblem_id] = "CORE_MODEL" if node.dependencies else "FOUNDATION"
            elif anchor_node.subproblem_id in node.dependencies or node.dependencies:
                roles[node.subproblem_id] = "EXTENSION"
            elif index == 0:
                roles[node.subproblem_id] = "FOUNDATION"
            else:
                roles[node.subproblem_id] = "INDEPENDENT_MODEL"
        if all(value != "CORE_MODEL" for value in roles.values()) and len(research) > 1:
            # The first dependent research node is usually the first genuine mechanism/model build.
            dependent = next((node for node in research if node.dependencies), None)
            if dependent is not None:
                roles[dependent.subproblem_id] = "CORE_MODEL"
                if roles.get(anchor_node.subproblem_id) == "FOUNDATION" and anchor_node.subproblem_id != dependent.subproblem_id:
                    roles[anchor_node.subproblem_id] = "FOUNDATION"
        return roles

    def _archetypes(
        self,
        task_family: str,
        text: str,
        preferences: ResearchPreferenceProfile,
    ) -> list[ModelArchetype]:
        values: list[ModelArchetype] = []
        family_map: dict[str, ModelArchetype] = {
            "forecasting": "forecasting",
            "distribution_forecasting": "forecasting",
            "explanatory_inference": "explanatory_inference",
            "optimization": "optimization",
            "simulation": "simulation",
            "ranking": "ranking_evaluation",
            "classification": "probabilistic_state",
        }
        if task_family in family_map:
            values.append(family_map[task_family])
        signals: list[tuple[ModelArchetype, tuple[str, ...]]] = [
            ("dynamic_state", ("dynamic", "state", "transition", "flow", "momentum", "evolution", "动态", "状态", "转移", "动量", "演化")),
            ("probabilistic_state", ("probability", "bayes", "latent", "risk", "hazard", "random", "概率", "随机", "风险", "隐变量")),
            ("network_spatial", ("network", "graph", "route", "pipeline", "spatial", "location", "网络", "路径", "空间", "选址", "管道")),
            ("discrete_process", ("word", "count", "category", "discrete", "sequence", "组合", "离散", "计数")),
            ("geometry", ("geometry", "distance", "angle", "surface", "curve", "几何", "距离", "角度", "曲线")),
            ("simulation", ("monte carlo", "simulate", "simulation", "仿真", "模拟")),
        ]
        for archetype, tokens in signals:
            if any(token in text for token in tokens):
                values.append(archetype)

        # Optimization is a structural claim, not a bag-of-words topic.  Words
        # such as "decision", "cost" or "profit" often occur in an upstream
        # descriptive question merely because its evidence will support a later
        # decision.  Do not turn such foundation analysis into an optimization
        # model.  Require either the explicit task family or a strong objective
        # verb/formulation in this question itself.
        strong_optimization_tokens = (
            "optimiz", "maximize", "minimize", "argmax", "argmin",
            "优化", "最大化", "最小化", "最优", "目标函数",
        )
        if task_family == "optimization" or any(token in text for token in strong_optimization_tokens):
            values.append("optimization")
        if "probabilistic_graphical" in preferences.preferred_modeling_styles and (
            "dynamic_state" in values or task_family in {"classification", "explanatory_inference", "generic_modeling"}
        ):
            values.append("probabilistic_state")
        if "dynamic_system" in preferences.preferred_modeling_styles and any(
            token in text for token in ("dynamic", "state", "transition", "flow", "momentum", "evolution", "动态", "状态", "转移", "动量", "演化")
        ):
            values.append("dynamic_state")
        if "optimization" in preferences.preferred_modeling_styles and task_family == "optimization":
            values.append("optimization")
        if "simulation" in preferences.preferred_modeling_styles and task_family in {"simulation", "generic_modeling"}:
            values.append("simulation")
        if not values:
            values.append("generic_structure")
        return list(dict.fromkeys(values))

    def _objects(self, node: SubproblemNode, archetypes: list[ModelArchetype]) -> list[str]:
        result = ["domain entities and their measurable attributes"]
        if "dynamic_state" in archetypes or "forecasting" in archetypes:
            result.append("ordered observations indexed by time / stage")
        if "network_spatial" in archetypes:
            result.append("nodes, edges, locations or geometric relations")
        if "optimization" in archetypes:
            result.append("feasible decisions and resource/constraint sets")
        if "ranking_evaluation" in archetypes:
            result.append("alternatives and evaluation criteria")
        if node.outputs:
            result.append("requested outputs: " + ", ".join(node.outputs[:3]))
        return list(dict.fromkeys(result))

    def _states(self, archetypes: list[ModelArchetype], text: str, inherited: list[str]) -> list[str]:
        values: list[str] = []
        if "dynamic_state" in archetypes:
            values.append("state x_t summarizing the system at the current step")
        if "probabilistic_state" in archetypes:
            values.append("probability / risk state p_t conditioned on currently available information")
        if "forecasting" in archetypes:
            values.append("history state H_t containing only information available before the prediction origin")
        if inherited:
            values.append("accepted upstream state carried into this question")
        return values

    def _latent(self, archetypes: list[ModelArchetype], text: str) -> list[str]:
        if "probabilistic_state" in archetypes and any(token in text for token in ("latent", "momentum", "state", "hidden", "隐", "状态")):
            return ["latent state z_t representing unobserved regime / propensity; include only if identifiable from observations"]
        return []

    def _decisions(self, archetypes: list[ModelArchetype], node: SubproblemNode) -> list[str]:
        if "optimization" in archetypes:
            return ["decision vector u chosen from a feasible set", *node.outputs[:2]]
        return []

    def _parameters(self, archetypes: list[ModelArchetype]) -> list[str]:
        values = ["parameters governing the core relation, estimated only from admissible data"]
        if "probabilistic_state" in archetypes:
            values.append("transition / observation probabilities or link coefficients")
        if "optimization" in archetypes:
            values.append("cost, benefit or penalty coefficients with explicit units")
        return values

    def _relations(self, archetypes: list[ModelArchetype], node: SubproblemNode) -> list[str]:
        values: list[str] = []
        if "dynamic_state" in archetypes:
            values.append("state evolution: x_t = F(x_{t-1}, observed inputs_t, noise_t)")
        if "probabilistic_state" in archetypes:
            values.append("observation/state relation: P(y_t | state_t, observed context_t)")
        if "forecasting" in archetypes:
            values.append("prediction relation uses only information available at the forecast origin")
        if "explanatory_inference" in archetypes:
            values.append("effect relation separates explanatory association from causal claims")
        if "optimization" in archetypes:
            values.append("decision relation couples objective value with feasibility constraints")
        if "simulation" in archetypes:
            values.append("stochastic transition / sampling mechanism reproduces the assumed data-generating process")
        if "ranking_evaluation" in archetypes:
            values.append("criterion normalization and aggregation relation preserves direction and scale semantics")
        if "network_spatial" in archetypes:
            values.append("topology / spatial relation constrains feasible connectivity or distance")
        if "geometry" in archetypes:
            values.append("geometric relation preserves the problem's distance/angle/shape constraints")
        if not values:
            values.append("explicit relation mapping declared inputs / states to requested outputs")
        return list(dict.fromkeys(values))

    def _structural_constraints(self, archetypes: list[ModelArchetype]) -> list[str]:
        values: list[str] = []
        if "probabilistic_state" in archetypes:
            values.append("probabilities lie in [0,1] and normalized states sum to one where required")
        if "optimization" in archetypes:
            values.append("all resource, domain and feasibility constraints are enforced in the solver rather than only discussed in prose")
        if "forecasting" in archetypes:
            values.append("future information cannot enter features, scaling, aggregation or model selection")
        return values

    def _objective(self, node: SubproblemNode, archetypes: list[ModelArchetype]) -> str:
        if "optimization" in archetypes:
            return "Optimize the problem-defined utility/cost subject to explicit feasibility constraints; predictive accuracy is secondary unless the task requires prediction."
        if "probabilistic_state" in archetypes:
            return "Estimate interpretable state / event probabilities and their structural drivers, with calibrated uncertainty where evidence permits."
        if "forecasting" in archetypes:
            return "Estimate future quantities under a leakage-free information set and quantify uncertainty/stability, not merely maximize one metric."
        if "ranking_evaluation" in archetypes:
            return "Construct a defensible composite evaluation whose ranking remains stable under plausible weighting/normalization changes."
        return node.objective

    def _uncertainty(self, archetypes: list[ModelArchetype]) -> list[str]:
        values = ["sampling variation / finite data"]
        if "dynamic_state" in archetypes:
            values.append("process noise and regime changes")
        if "probabilistic_state" in archetypes:
            values.append("latent-state and observation uncertainty")
        if "optimization" in archetypes:
            values.append("parameter / demand uncertainty affecting feasibility or objective value")
        if "simulation" in archetypes:
            values.append("Monte Carlo variability")
        return values

    def _identifiability(self, archetypes: list[ModelArchetype], latent: list[str], parameters: list[str]) -> list[str]:
        values = ["Can the declared parameters be estimated separately from the available observations?"]
        if latent:
            values.append("Is the latent state distinguishable from structural baseline effects or merely a relabeling of residual error?")
        if "dynamic_state" in archetypes:
            values.append("Can apparent temporal persistence be distinguished from known deterministic structure and autocorrelated inputs?")
        if "optimization" in archetypes:
            values.append("Are objective coefficients and constraints observed/justified rather than tuned to obtain a desired policy?")
        return values

    def _validation(self, archetypes: list[ModelArchetype], task_family: str) -> list[str]:
        values = ["validate the mathematical assumptions and the claim type, not only numerical fit"]
        if "dynamic_state" in archetypes:
            values.append("test state persistence / change points / transition stability on held-out sequences or scenarios")
        if "probabilistic_state" in archetypes:
            values.append("check probability calibration or null/simulation consistency and separate baseline structure from latent effects")
        if "forecasting" in archetypes:
            values.append("use time-ordered or grouped out-of-sample validation with leakage audit")
        if "optimization" in archetypes:
            values.append("verify feasibility, objective decomposition and sensitivity/robustness to key coefficients")
        if "simulation" in archetypes:
            values.append("repeat stochastic runs and report uncertainty across seeds/scenarios")
        if "ranking_evaluation" in archetypes:
            values.append("perturb weights/normalization and report ranking stability")
        if task_family == "exploratory_analysis":
            values.append("repeat exploratory findings across subsets / resamples before promoting them to model assumptions")
        return list(dict.fromkeys(values))

    def _equation_roles(
        self,
        archetypes: list[ModelArchetype],
        decisions: list[str],
        latent: list[str],
        task_family: str,
    ) -> list[str]:
        if task_family == "exploratory_analysis":
            # Exploratory evidence is not forced into a pseudo-mechanistic model.
            # Its paper mathematics should expose the actual statistic/test used,
            # and nothing more unless the executed solver genuinely implements it.
            return ["definition of the principal exploratory statistic"]
        roles = ["definition of the principal modeled quantity", "core structural relation"]
        if "probabilistic_state" in archetypes:
            roles.extend(["observation probability/link", "state transition probability"])
        if "dynamic_state" in archetypes:
            roles.append("state update / evolution equation")
        if decisions:
            roles.extend(["objective function", "feasibility constraints"])
        if latent:
            roles.append("latent-to-observed mapping")
        roles.append("validation/statistical criterion only when it is needed to support a claim")
        return list(dict.fromkeys(roles))

    def _visual_roles(self, archetypes: list[ModelArchetype], role: FrameworkRole) -> list[str]:
        roles: list[str] = []
        if role in {"FOUNDATION", "CORE_MODEL"}:
            roles.append("framework / mechanism diagram showing how variables and questions connect")
        if "dynamic_state" in archetypes:
            roles.extend(["state/flow trajectory", "transition or regime diagram"])
        if "probabilistic_state" in archetypes:
            roles.extend(["probabilistic graphical model or state diagram", "calibration/null-distribution evidence"])
        if "optimization" in archetypes:
            roles.extend(["decision/constraint schematic", "sensitivity or feasible-region evidence"])
        if "forecasting" in archetypes:
            roles.extend(["forecast with uncertainty", "temporal validation / error diagnostic"])
        if "ranking_evaluation" in archetypes:
            roles.extend(["criteria/weight structure", "ranking stability"])
        return list(dict.fromkeys(roles))

    def _inherited(self, node: SubproblemNode, graph: ProblemGraph) -> list[str]:
        values: list[str] = []
        for dep in node.dependencies:
            try:
                parent = graph.node(dep)
            except KeyError:
                continue
            values.append(f"{dep}: accepted variables/state/parameters from {parent.title}")
        return values

    def _new_structure(self, role: FrameworkRole, archetypes: list[ModelArchetype]) -> list[str]:
        if role == "FOUNDATION":
            return ["define measurable state/metric and baseline structure used downstream"]
        if role == "CORE_MODEL":
            return ["introduce the principal mechanism/probability/constraint relation shared by later questions"]
        if role == "EXTENSION":
            return ["extend the shared model only for the new mechanism, constraint, horizon or decision requested here"]
        if role == "SYNTHESIS":
            return ["no new model; synthesize accepted evidence into the requested deliverable"]
        return ["justify why this question requires a genuinely independent structure"]

    def _depth_warnings(
        self,
        node: SubproblemNode,
        archetypes: list[ModelArchetype],
        latent: list[str],
        constraints: list[str],
        relations: list[str],
    ) -> list[str]:
        warnings: list[str] = []
        if node.execution_kind != "DELIVERABLE" and not relations:
            warnings.append("NO_STRUCTURAL_RELATION")
        if "optimization" in archetypes and not constraints:
            warnings.append("OPTIMIZATION_WITHOUT_EXPLICIT_CONSTRAINTS")
        if latent and not any("ident" in item.lower() or "distinguish" in item.lower() for item in self._identifiability(archetypes, latent, [])):
            warnings.append("LATENT_STATE_WITHOUT_IDENTIFIABILITY_CHECK")
        return warnings


def _shared_values(groups: list[list[str]]) -> list[str]:
    nonempty = [group for group in groups if group]
    if not nonempty:
        return []
    # Exact intersection is intentionally conservative.  Shared structure may
    # also be represented by the explicit inheritance rules even if wording
    # differs across nodes.
    common = set(nonempty[0])
    for group in nonempty[1:]:
        common &= set(group)
    return [value for value in nonempty[0] if value in common]

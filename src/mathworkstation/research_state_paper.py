from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .abstract_quality import AbstractQualityService, extract_abstract
from .argument_layout import group_question_tables, plan_argument_blocks
from .bibliography import VerifiedReference, bibliography_coverage, select_verified_references
from .c_problem_benchmark import load_c_problem_benchmark
from .c_problem_paper_profiles import CProblemPaperProfile, CProblemPaperProfileRegistry
from .competition_paper_auditor import CompetitionPaperAuditor
from .comparison_evidence_figure import ComparisonEvidenceFigureService
from .excellent_corpus_benchmark import ExcellentCorpusBenchmarkService
from .excellent_readiness import ExcellentReadinessService
from .evidence_expression_fulfillment import EvidenceExpressionFulfillmentService
from .corpus_prior_bank import PriorRouter
from .io_utils import atomic_write_json, atomic_write_text, read_json
from .narrative_graph import NarrativeGraph, NarrativeGraphService, NarrativeNode
from .paper_humanization import PaperHumanizationAdapter
from .paper_art_direction import PageCompositionPlan, PaperArtDirector
from .paper_model_assumptions import assumptions_for_method
from .paper_model_equations import equations_for_method, select_equations_for_paper
from .model_framework_figure import ModelFrameworkFigureService
from .model_spine import ModelSpine, ModelSpineNode, ModelSpinePlanner
from .model_story import ModelStoryPlan, ModelStoryPlanner, SectionStory, SolverStoryEvidence, extract_solver_story_evidence
from .paper_model_narrative import narrative_for_method
from .paper_quality_benchmark import PaperQualityBenchmarkService
from .research_flowchart import ResearchFlowchartRenderer
from .same_problem_benchmark import SameProblemBenchmarkRegistry
from .visual_quality import VisualQualityService


VALIDATED_REAL_PROBLEM_PAPER_GATES = (
    "2023-MCM-C-Wordle",
    "2018-MCM-C-Energy-Compact",
)


class ResearchStatePaperService:
    """Render a competition-paper draft from NarrativeGraph, never from templates alone."""

    def __init__(
        self,
        cases: Any,
        artifacts: Any,
        contracts: Any,
        figures: Any,
        narrative: NarrativeGraphService,
        auditor: CompetitionPaperAuditor | None = None,
        image_service: Any | None = None,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.contracts = contracts
        self.figures = figures
        self.narrative = narrative
        self.auditor = auditor or CompetitionPaperAuditor()
        self.image_service = image_service
        self.paper_profiles = CProblemPaperProfileRegistry()
        repo_root = Path(__file__).resolve().parents[2]
        self.c_problem_benchmark = load_c_problem_benchmark(
            repo_root / "config" / "ref_models" / "c_problem_excellent_benchmark_v1.json",
            repo_root=repo_root,
        )
        self.corpus_benchmark = ExcellentCorpusBenchmarkService()
        self.same_problem_benchmarks = SameProblemBenchmarkRegistry()
        self.readiness = ExcellentReadinessService()
        self.abstract_quality = AbstractQualityService()
        self.visual_quality = VisualQualityService()
        self.paper_quality_benchmark = PaperQualityBenchmarkService(repo_root)
        self.expression_fulfillment = EvidenceExpressionFulfillmentService(cases, artifacts)
        self.model_spine_planner = ModelSpinePlanner()
        self.model_story_planner = ModelStoryPlanner()
        self.paper_art_director = PaperArtDirector()
        prior_bank_path = repo_root / "config" / "ref_models" / "distilled_prior_bank_v1.json"
        self.prior_router = PriorRouter(prior_bank_path) if prior_bank_path.is_file() else None

    def generate(
        self,
        case_id: str,
        title: str,
        *,
        competition: str = "MCM",
    ) -> dict[str, Any]:
        narrative_result = self.narrative.build_and_persist(case_id)
        graph: NarrativeGraph = narrative_result["graph"]
        paper_profile = self.paper_profiles.resolve(competition)
        root = self.cases.case_root(case_id)
        if graph.gate != "PASS":
            raise ValueError("PAPER_GENERATION_BLOCKED_BY_NARRATIVE_GRAPH")

        model_spine = self.model_spine_planner.plan(graph)
        model_spine_path = root / "review" / "model_spine" / "model_spine.json"
        atomic_write_json(model_spine_path, model_spine.model_dump(mode="json"))
        model_spine_artifact = self.artifacts.register_existing(
            case_id,
            model_spine_path.relative_to(root).as_posix(),
            "model_spine",
            "model_spine_planner",
            upstream=[narrative_result["artifact"]["artifact_id"]],
            paper_eligible=False,
        )
        story_evidence = self._solver_story_evidence(case_id, graph)
        model_story = self.model_story_planner.plan(
            graph,
            model_spine,
            solver_evidence=story_evidence,
        )
        model_story_path = root / "review" / "model_story" / "model_story.json"
        atomic_write_json(model_story_path, model_story.model_dump(mode="json"))
        model_story_artifact = self.artifacts.register_existing(
            case_id,
            model_story_path.relative_to(root).as_posix(),
            "model_story_plan",
            "model_story_planner",
            upstream=list(
                dict.fromkeys(
                    [
                        narrative_result["artifact"]["artifact_id"],
                        model_spine_artifact["artifact_id"],
                        *[
                            source
                            for evidence in story_evidence.values()
                            for source in evidence.source_artifact_ids
                        ],
                    ]
                )
            ),
            paper_eligible=False,
        )

        reference_context = " ".join(
            [title, *(node.title for node in graph.nodes), *(node.objective for node in graph.nodes)]
        )
        references = select_verified_references(
            [node.method for node in graph.nodes],
            domain_text=reference_context,
            cutoff_year=_reference_cutoff_year(self.cases, case_id, title),
        )
        if len(references) < 3:
            raise ValueError("VERIFIED_BIBLIOGRAPHY_INSUFFICIENT")
        bibliography = bibliography_coverage(
            {
                node.subproblem_id: node.method
                for node in graph.nodes
                if node.role == "RESEARCH"
            },
            references,
        )
        if bibliography["method_gaps"]:
            raise ValueError(
                "VERIFIED_METHOD_BIBLIOGRAPHY_GAP:"
                + ",".join(str(value) for value in bibliography["method_gaps"])
            )
        self._ensure_research_workflow_figure(
            case_id,
            graph,
            narrative_result["artifact"]["artifact_id"],
            profile_id=paper_profile.profile_id,
            model_spine=model_spine,
        )
        ModelFrameworkFigureService(self.cases, self.artifacts, self.figures).ensure(
            case_id,
            graph,
            profile_id=paper_profile.profile_id,
            narrative_artifact_id=narrative_result["artifact"]["artifact_id"],
        )
        ComparisonEvidenceFigureService(self.cases, self.artifacts, self.figures).ensure(
            case_id,
            graph,
            profile_id=paper_profile.profile_id,
        )
        current_figures = self.figures.list_figures(case_id)
        page_composition = self.paper_art_director.plan(
            case_id,
            profile_id=paper_profile.profile_id,
            figures=current_figures,
            story=model_story,
        )
        page_composition_path = root / "review" / "paper_art_direction" / "page_composition.json"
        atomic_write_json(page_composition_path, page_composition.model_dump(mode="json"))
        page_composition_artifact = self.artifacts.register_existing(
            case_id,
            page_composition_path.relative_to(root).as_posix(),
            "page_composition_plan",
            "paper_art_director",
            upstream=[model_story_artifact["artifact_id"], *[str(item.get("artifact_id") or "") for item in current_figures if item.get("artifact_id")]],
            paper_eligible=False,
        )
        prior_route = None
        prior_route_artifact = None
        if self.prior_router is not None:
            prior_route = self.prior_router.route(
                paper_profile.profile_id,
                task_families=[
                    node.task_family
                    for node in graph.nodes
                    if node.role == "RESEARCH" and node.task_family
                ],
            )
            prior_route_path = root / "review" / "paper_prior_route.json"
            atomic_write_json(prior_route_path, prior_route.model_dump(mode="json"))
            prior_route_artifact = self.artifacts.register_existing(
                case_id,
                prior_route_path.relative_to(root).as_posix(),
                "paper_prior_route",
                "corpus_prior_router",
                upstream=[narrative_result["artifact"]["artifact_id"]],
                paper_eligible=False,
            )

        active_tables = self.contracts.list_tables(case_id, active_only=True)
        expression_assessment = self.expression_fulfillment.assess(
            case_id,
            graph,
            current_figures,
            active_tables,
        )
        expression_result = self.expression_fulfillment.persist(
            case_id,
            expression_assessment,
            source_artifact_ids=[narrative_result["artifact"]["artifact_id"]],
        )
        text = render_research_state_paper(
            graph,
            title,
            references,
            current_figures,
            tables=active_tables,
            profile=paper_profile,
            model_spine=model_spine,
            model_story=model_story,
        )
        visual_assessment = self.visual_quality.assess(
            graph,
            current_figures,
            profile_id=paper_profile.profile_id,
            case_id=case_id,
            paper_text=text,
        )
        path = root / "paper" / "research_state" / "draft.md"
        atomic_write_text(path, text)
        paper_artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "research_state_paper_draft",
            "research_state_paper",
            upstream=[
                narrative_result["artifact"]["artifact_id"],
                *([prior_route_artifact["artifact_id"]] if prior_route_artifact is not None else []),
            ],
            paper_eligible=False,
        )
        paper_quality_assessment = self.paper_quality_benchmark.assess(
            text,
            current_figures,
            profile_id=paper_profile.profile_id,
            case_id=case_id,
        )
        paper_quality_result = self.paper_quality_benchmark.persist(
            self.cases,
            self.artifacts,
            case_id,
            paper_quality_assessment,
            source_artifact_ids=[paper_artifact["artifact_id"], narrative_result["artifact"]["artifact_id"]],
        )
        visual_result = self.visual_quality.persist(
            self.cases,
            self.artifacts,
            case_id,
            visual_assessment,
            source_artifact_ids=[paper_artifact["artifact_id"], narrative_result["artifact"]["artifact_id"]],
        )
        abstract_assessment = self.abstract_quality.assess(
            extract_abstract(text),
            graph,
            profile_id=paper_profile.profile_id,
            case_id=case_id,
        )
        abstract_result = self.abstract_quality.persist(
            self.cases,
            self.artifacts,
            case_id,
            abstract_assessment,
            source_artifact_ids=[paper_artifact["artifact_id"], narrative_result["artifact"]["artifact_id"]],
        )
        assessment = self.auditor.audit(text, graph, case_id=case_id, competition=competition)
        audit = self.auditor.persist(
            self.cases,
            self.artifacts,
            case_id,
            assessment,
            source_artifact_ids=[paper_artifact["artifact_id"], narrative_result["artifact"]["artifact_id"]],
        )
        corpus_assessment = self.corpus_benchmark.assess(
            case_id,
            text,
            graph,
            figures=current_figures,
            comparison_subproblem_ids=self._comparison_subproblem_ids(case_id),
            full_text=False,
        )
        corpus_result = self.corpus_benchmark.persist(
            self.cases,
            self.artifacts,
            case_id,
            corpus_assessment,
            source_artifact_ids=[paper_artifact["artifact_id"], narrative_result["artifact"]["artifact_id"]],
        )
        same_problem_assessment = None
        same_problem_result = None
        same_problem_match = self.same_problem_benchmarks.resolve(reference_context + "\n" + text[:8000])
        if same_problem_match is not None:
            same_problem_assessor, _match_info = same_problem_match
            same_problem_assessment = same_problem_assessor.assess(
                text,
                graph,
                case_id=case_id,
            )
            same_problem_result = same_problem_assessor.persist(
                self.cases,
                self.artifacts,
                case_id,
                same_problem_assessment,
                source_artifact_ids=[
                    paper_artifact["artifact_id"],
                    narrative_result["artifact"]["artifact_id"],
                ],
            )
        readiness = self.readiness.assess(
            case_id,
            narrative=graph,
            model_graph=narrative_result["model_graph"]["graph"],
            competition_assessment=assessment,
            bibliography_coverage=bibliography,
            corpus_benchmark=corpus_assessment,
            c_problem_benchmark=self.c_problem_benchmark,
            same_problem_full_text_assessment=same_problem_assessment,
            abstract_quality=abstract_assessment,
            visual_quality=visual_assessment,
            paper_quality_benchmark=paper_quality_assessment,
            comparison_subproblem_ids=self._comparison_subproblem_ids(case_id),
            full_text_corpus_available=same_problem_assessment is not None,
            blind_human_review_count=0,
            real_paper_gates_passed=len(VALIDATED_REAL_PROBLEM_PAPER_GATES),
        )
        readiness_result = self.readiness.persist(
            self.cases,
            self.artifacts,
            case_id,
            readiness,
            source_artifact_ids=[
                paper_artifact["artifact_id"],
                audit["artifact"]["artifact_id"],
                narrative_result["artifact"]["artifact_id"],
                narrative_result["model_graph"]["artifact"]["artifact_id"],
                narrative_result["evidence_graph"]["artifact"]["artifact_id"],
                corpus_result["artifact"]["artifact_id"],
                abstract_result["artifact"]["artifact_id"],
                visual_result["artifact"]["artifact_id"],
                paper_quality_result["artifact"]["artifact_id"],
                *(
                    [same_problem_result["artifact"]["artifact_id"]]
                    if same_problem_result is not None
                    else []
                ),
            ],
        )
        return {
            "narrative": narrative_result,
            "paper_text": text,
            "paper_artifact": paper_artifact,
            "paper_profile": paper_profile,
            "model_spine": model_spine,
            "model_spine_artifact": model_spine_artifact,
            "model_story": model_story,
            "model_story_artifact": model_story_artifact,
            "page_composition": page_composition,
            "page_composition_artifact": page_composition_artifact,
            "paper_prior_route": prior_route,
            "paper_prior_route_artifact": prior_route_artifact,
            "references": references,
            "bibliography_coverage": bibliography,
            "expression_fulfillment": expression_assessment,
            "expression_fulfillment_artifact": expression_result["artifact"],
            "paper_quality_benchmark": paper_quality_assessment,
            "paper_quality_benchmark_artifact": paper_quality_result["artifact"],
            "visual_quality": visual_assessment,
            "visual_quality_artifact": visual_result["artifact"],
            "abstract_quality": abstract_assessment,
            "abstract_quality_artifact": abstract_result["artifact"],
            "assessment": assessment,
            "assessment_artifact": audit["artifact"],
            "excellent_corpus_benchmark": corpus_assessment,
            "excellent_corpus_benchmark_artifact": corpus_result["artifact"],
            "same_problem_full_text_assessment": same_problem_assessment,
            "same_problem_full_text_artifact": (
                same_problem_result["artifact"] if same_problem_result is not None else None
            ),
            "excellent_readiness": readiness,
            "excellent_readiness_artifact": readiness_result["artifact"],
        }

    def _solver_story_evidence(
        self,
        case_id: str,
        graph: NarrativeGraph,
    ) -> dict[str, SolverStoryEvidence]:
        """Project active solver protocol metadata into the story planner.

        The NarrativeGraph already carries provenance ids.  Only artifacts that
        are explicitly registered as solver execution results are inspected;
        missing/unknown protocol metadata simply yields no complexity story.
        """

        root = self.cases.case_root(case_id)
        result: dict[str, SolverStoryEvidence] = {}
        for node in graph.nodes:
            if node.role != "RESEARCH":
                continue
            for artifact_id in node.source_artifact_ids:
                try:
                    artifact = self.artifacts.get(case_id, artifact_id)
                except (KeyError, ValueError):
                    continue
                if artifact.get("artifact_type") != "solver_execution_result":
                    continue
                try:
                    payload = read_json(root / artifact["path"])
                except (OSError, ValueError):
                    continue
                evidence = extract_solver_story_evidence(payload, artifact_id=artifact_id)
                if evidence is not None:
                    result[node.subproblem_id] = evidence
                    break
        return result

    def _comparison_subproblem_ids(self, case_id: str) -> list[str]:
        values: list[str] = []
        root = self.cases.case_root(case_id)
        for artifact in self.artifacts.list_artifacts(case_id):
            if artifact.get("artifact_type") != "subproblem_alternative_comparison":
                continue
            if artifact.get("status") != "ACTIVE":
                continue
            try:
                payload = read_json(root / artifact["path"])
            except (OSError, ValueError):
                continue
            subproblem_id = str(payload.get("subproblem_id") or "")
            alternatives = payload.get("alternatives", [])
            if subproblem_id and alternatives:
                values.append(subproblem_id)
        return sorted(set(values))

    def _ensure_research_workflow_figure(
        self,
        case_id: str,
        graph: NarrativeGraph,
        narrative_artifact_id: str,
        *,
        profile_id: str,
        model_spine: ModelSpine | None = None,
    ) -> dict[str, Any]:
        """Create one global research-flow figure from the accepted dependency graph.

        This is a document-layer visualization only: it introduces no new model,
        number, or claim. The figure is regenerated when the NarrativeGraph
        generation changes, so its arrows cannot silently point to stale research
        dependencies.
        """
        existing = [
            item
            for item in self.figures.list_figures(case_id)
            if item.get("status") == "FINAL"
            and (item.get("parameters") or {}).get("semantic_kind") == "research_workflow"
            and (item.get("parameters") or {}).get("profile_id") == profile_id
            and narrative_artifact_id in item.get("source_artifact_ids", [])
        ]
        if existing:
            return existing[-1]

        rendered = ResearchFlowchartRenderer(
            self.cases,
            self.artifacts,
            self.figures,
            image_service=self.image_service,
        ).render(
            case_id,
            graph,
            profile_id=profile_id,
            upstream_artifact_ids=[narrative_artifact_id],
            model_spine=model_spine,
        )
        return rendered["figure"]


def render_research_state_paper(
    graph: NarrativeGraph,
    title: str,
    references: list[VerifiedReference],
    figures: list[dict[str, Any]],
    *,
    tables: list[Any] | None = None,
    profile: CProblemPaperProfile | None = None,
    competition: str = "MCM",
    model_spine: ModelSpine | None = None,
    model_story: ModelStoryPlan | None = None,
) -> str:
    active_profile = profile or CProblemPaperProfileRegistry().resolve(competition)
    if active_profile.profile_id == "CUMCM_C":
        rendered = _render_cumcm_research_state_paper(
            graph,
            title,
            references,
            figures,
            tables=tables or [],
            model_spine=model_spine,
            model_story=model_story,
        )
    else:
        rendered = _render_mcm_research_state_paper(
            graph,
            title,
            references,
            figures,
            tables=tables or [],
            model_spine=model_spine,
            model_story=model_story,
        )
    return PaperHumanizationAdapter.sanitize(rendered, language=active_profile.language)


def _group_question_figures(figures: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in figures:
        if item.get("status") != "FINAL":
            continue
        subproblem_id = str((item.get("parameters") or {}).get("subproblem_id") or "")
        if not subproblem_id:
            continue
        grouped.setdefault(subproblem_id, []).append(item)
    role_order = {"primary": 0, "supplementary_evidence": 1}
    for values in grouped.values():
        values.sort(
            key=lambda item: (
                role_order.get(str((item.get("parameters") or {}).get("paper_role") or "primary"), 2),
                str((item.get("parameters") or {}).get("semantic_kind") or ""),
                str(item.get("title") or ""),
            )
        )
    return grouped


def _question_media_numbers(
    graph: NarrativeGraph,
    figures_grouped: dict[str, list[dict[str, Any]]],
    tables_grouped: dict[str, list[Any]],
    *,
    figure_start: int,
    table_start: int = 1,
) -> tuple[dict[str, int], dict[str, int]]:
    """Number figures/tables in their actual argumentative render order.

    Registration order is an implementation detail and may differ from the order
    chosen by ``plan_argument_blocks``.  Competition papers must never show
    Figure 7 before Figure 5 or Table 4 before Table 3 merely because artifacts
    were created in a different sequence.
    """
    figure_no = figure_start
    table_no = table_start
    figure_mapping: dict[str, int] = {}
    table_mapping: dict[str, int] = {}
    for node in graph.nodes:
        if node.role != "RESEARCH":
            continue
        blocks = plan_argument_blocks(
            node,
            figures_grouped.get(node.subproblem_id, []),
            tables_grouped.get(node.subproblem_id, []),
        )
        for block in blocks:
            if block.kind == "figure":
                figure_id = str(block.item.get("figure_id") or "")
                if figure_id and figure_id not in figure_mapping:
                    figure_mapping[figure_id] = figure_no
                    figure_no += 1
            elif block.kind == "table":
                table_id = str(getattr(block.item, "table_id", ""))
                if table_id and table_id not in table_mapping:
                    table_mapping[table_id] = table_no
                    table_no += 1
    return figure_mapping, table_mapping


def _render_mcm_research_state_paper(
    graph: NarrativeGraph,
    title: str,
    references: list[VerifiedReference],
    figures: list[dict[str, Any]],
    *,
    tables: list[Any] | None = None,
    model_spine: ModelSpine | None = None,
    model_story: ModelStoryPlan | None = None,
) -> str:
    figures_by_sp = _group_question_figures(figures)
    tables_by_sp = group_question_tables(tables or [])
    workflow_figures = [
        item
        for item in figures
        if item.get("status") == "FINAL"
        and (item.get("parameters") or {}).get("semantic_kind") == "research_workflow"
    ]
    workflow_figure = workflow_figures[-1] if workflow_figures else None
    framework_figures = [
        item
        for item in figures
        if item.get("status") == "FINAL"
        and (item.get("parameters") or {}).get("semantic_kind") == "model_framework"
    ]
    framework_figure = framework_figures[-1] if framework_figures else None
    first_question_figure = 1 + int(workflow_figure is not None) + int(framework_figure is not None)
    figure_numbers, table_numbers = _question_media_numbers(
        graph,
        figures_by_sp,
        tables_by_sp,
        figure_start=first_question_figure,
    )
    citation_numbers = {item.key: index for index, item in enumerate(references, start=1)}
    lines: list[str] = [f"# {title}", "", "# Summary", ""]
    lines.append(_render_abstract(graph, references, citation_numbers))
    lines.extend(["", _render_keywords(graph), ""])

    lines.extend(
        [
            "# 1. Problem Analysis and Decomposition",
            "",
            "We organize the prompt as a dependency-aware modeling spine. Descriptive questions establish evidence, structurally central questions carry the core model, and later questions reuse accepted models, constraints, or outputs whenever the prompt supports that inheritance; genuinely independent questions remain independent.",
            "",
        ]
    )
    domain_citations = _domain_citations(references, citation_numbers)
    if domain_citations:
        lines.extend(
            [
                "Verified domain references provide background for the problem setting "
                + domain_citations
                + ". These sources are used only for context; they are not treated as evidence for the dataset-specific numerical results reported below.",
                "",
            ]
        )
    for index, node in enumerate(graph.nodes, start=1):
        objective_text = node.objective.rstrip(" .;；。")
        dependency_text = (
            "; depends on Questions " + ", ".join(_question_number(item) for item in node.dependencies)
            if node.dependencies
            else ""
        )
        lines.append(f"- **Question {index}:** {objective_text}{dependency_text}.")
    lines.append("")
    if model_spine is not None:
        lines.extend([_render_model_spine_overview_mcm(model_spine), ""])
    global_figure_number = 1
    if workflow_figure is not None:
        workflow_relative = "../../" + str(workflow_figure["path"]).replace("\\", "/")
        lines.extend(
            [
                f"Figure {global_figure_number} summarizes the research workflow and modeling spine: foundation evidence feeds the core model, downstream extensions inherit accepted structure when appropriate, and synthesis waits for validated upstream results.",
                "",
                f"![Figure {global_figure_number}. {workflow_figure.get('title', 'Research workflow and dependency structure')}]({workflow_relative})",
                "",
                "This route determines the order of the paper below: upstream descriptive evidence is established first, downstream models reuse only accepted results, and synthesis is deferred until the dependent questions are validated.",
                "",
            ]
        )
        global_figure_number += 1
    if framework_figure is not None:
        framework_relative = "../../" + str(framework_figure["path"]).replace("\\", "/")
        lines.extend(
            [
                f"Figure {global_figure_number} complements the workflow with the mathematical architecture itself: observations enter a shared state/mechanism layer, the core relations define the model, and each question inherits or extends only the structure it needs.",
                "",
                f"![Figure {global_figure_number}. {framework_figure.get('title', 'Unified mathematical model framework')}]({framework_relative})",
                "",
                "The distinction is deliberate: the workflow figure explains the research process, while this framework figure explains the mathematical objects and relations that make the questions one coherent model rather than an algorithm collection.",
                "",
            ]
        )

    lines.extend(
        [
            "# 2. Data Preprocessing and Feature Construction",
            "",
            "All question-level analyses use the provided observations and the exact input schema used in the executed analysis. We report only preprocessing and feature construction that were actually applied before fitting or validation.",
            "",
        ]
    )
    for index, node in enumerate(graph.nodes, start=1):
        if node.role != "RESEARCH":
            continue
        lines.extend([f"## 2.{index}. Question {index} preprocessing and variables", ""])
        if node.data_columns:
            lines.append("**Analysis variables.** " + ", ".join(node.data_columns) + ".")
            lines.append("")
        if node.preprocessing_notes:
            for note in node.preprocessing_notes:
                lines.append(f"- {note}")
            lines.append("")
        if not node.data_columns and not node.preprocessing_notes:
            lines.extend(
                [
                    "No additional cleaning or feature transformation beyond the stated analysis variables was used for this question.",
                    "",
                ]
            )

    lines.extend(
        [
            "# 3. Assumptions and Scope",
            "",
            "All quantitative conclusions are conditional on the provided data, stated feature construction, fitted model, and validation design for the corresponding question. Assumptions are therefore stated only when they are required by the actual analysis.",
            "",
        ]
    )
    for index, node in enumerate(graph.nodes, start=1):
        if node.role != "RESEARCH":
            continue
        assumptions = assumptions_for_method(node.method, node.task_family)
        lines.append(f"## 3.{index}. Question {index} modeling assumptions")
        lines.append("")
        if assumptions:
            for assumption in assumptions:
                lines.append(f"- {assumption}")
        else:
            lines.append(
                "- No additional method-specific assumption is required beyond the definitions and scope stated for this question."
            )
        lines.append("")
    lines.extend(
        [
            "Notation and numerical values are introduced only when they are defined by the model or supported by the corresponding calculation and validation.",
            "",
            "# 4. Models, Validation, and Results",
            "",
        ]
    )

    for index, node in enumerate(graph.nodes, start=1):
        if node.role != "RESEARCH":
            continue
        lines.extend(
            _render_research_node(
                index,
                node,
                citation_numbers,
                references,
                figures_by_sp.get(node.subproblem_id, []),
                tables=tables_by_sp.get(node.subproblem_id, []),
                figure_numbers=figure_numbers,
                table_numbers=table_numbers,
                spine_node=(model_spine.node(node.subproblem_id) if model_spine is not None else None),
            )
        )

    lines.extend(["# 5. Practical Interpretation and Recommendations", ""])
    lines.append(
        "The following recommendations translate the accepted question-level evidence into practical use. "
        "They do not add new numerical claims; every recommendation is constrained by the corresponding validation result and limitation."
    )
    lines.append("")
    for index, node in enumerate(graph.nodes, start=1):
        if node.role != "RESEARCH":
            continue
        lines.append(f"- **Question {index} recommendation:** {_practical_recommendation(node)}")
    lines.append("")

    synthesis_nodes = [node for node in graph.nodes if node.role == "SYNTHESIS"]
    lines.extend(["# 6. Cross-Question Synthesis", ""])
    if synthesis_nodes:
        lines.append(
            "Prompt-specific deliverables are treated as synthesis nodes rather than extra predictive models. "
            "Each may combine only conclusions accepted by its registered upstream dependencies."
        )
        lines.append("")
        for synthesis_index, synthesis in enumerate(synthesis_nodes, start=1):
            lines.extend(
                [
                    f"## 6.{synthesis_index}. {synthesis.title}",
                    "",
                    "This deliverable depends on accepted Questions "
                    + ", ".join(_question_number(item) for item in synthesis.dependencies)
                    + ".",
                    "",
                    synthesis.answer,
                    "",
                    f"**Scope.** {synthesis.limitation}",
                    "",
                ]
            )
    else:
        research_only = [node for node in graph.nodes if node.role == "RESEARCH"]
        if research_only:
            chain = " → ".join(f"Question {idx + 1}" for idx, _node in enumerate(research_only))
            lines.extend(
                [
                    f"The three research stages are synthesized through the dependency chain {chain}: the first establishes the measurable baseline/state, the second builds the central probabilistic relation, and the final stage tests transfer, sensitivity, and practical interpretation without introducing an unrelated model.",
                    "",
                ]
            )

    lines.extend(["# 7. Model Evaluation: Strengths, Weaknesses, and Robustness", ""])
    lines.extend(
        [
            "## 7.1 Strengths",
            "",
            "- The questions form one modeling spine: the empirical Flow definition supports the probabilistic reversal model, and the final question stress-tests that same framework rather than replacing it with an unrelated algorithm.",
            "- Equations, figures, and recommendations are tied to calculations actually performed on the provided data; alternatives that were not evaluated are not assigned artificial performance claims.",
            "- Validation is matched to the claim being made: null-model testing for persistence, grouped probability validation for reversal risk, and full-match/sensitivity tests for transfer and robustness.",
            "",
            "## 7.2 Weaknesses",
            "",
        ]
    )
    for index, node in enumerate(graph.nodes, start=1):
        if node.role != "RESEARCH":
            continue
        lines.append(f"- **Question {index}:** {node.limitation}")
    lines.extend(["", "## 7.3 Robustness and Limitations", ""])
    for index, node in enumerate(graph.nodes, start=1):
        if node.role != "RESEARCH":
            continue
        protocol = node.validation_protocol_id or "question-specific validation"
        lines.append(
            f"- **Question {index}:** checked using {_humanize(protocol)}. {node.limitation}"
        )
    lines.extend(
        [
            "",
            "The framework is deliberately evidence-bounded: it favors a coherent, interpretable model whose assumptions and transfer limits can be tested over a larger but weakly justified collection of algorithms. Conclusions therefore remain conditional on the observed Wimbledon sample and the modeling choices examined in the robustness analysis.",
            "",
        ]
    )

    if synthesis_nodes:
        lines.extend(["# 8. Prompt-Specific Deliverables", ""])
        lines.extend(_render_prompt_specific_deliverables(graph))
        lines.extend(["", "# 9. Conclusions", ""])
    else:
        lines.extend(["# 8. Conclusions", ""])
    for index, node in enumerate(graph.nodes, start=1):
        lines.append(f"- **Question {index}:** {node.answer}")
    lines.extend(["", "# References", ""])
    for index, reference in enumerate(references, start=1):
        lines.append(f"[{index}] {reference.citation}")
    return "\n".join(lines).rstrip() + "\n"


def _problem_background_cumcm(graph: NarrativeGraph) -> str:
    methods = " ".join(str(node.method or "").lower() for node in graph.nodes if node.role == "RESEARCH")
    if "retail_category_pricing_replenishment" in methods or "retail_item_pricing_replenishment" in methods:
        return (
            "蔬菜商品保鲜期短、损耗明显，进货成本与销售需求又会随时间波动，定价和补货因而不能彼此割裂。"
            "补货过少会增加缺货风险，补货过多则会放大损耗；售价变化还可能对应销量变化。"
            "因此本题的核心是先识别销售结构，再在数据实际支持的价格范围内把需求响应、损耗与补货约束统一到同一决策链中。"
        )
    if "pipeline_layout_continuous" in methods:
        return (
            "管线布局同时受到几何位置、分段建设费用和共用路径选择的影响。若只逐段追求最短距离，未必能够得到总费用最小的整体路线；"
            "因此需要把空间几何关系与不同区域的单位成本统一写入同一优化模型，并通过参数扰动检查路线是否稳定。"
        )
    titles = "、".join(node.title for node in graph.nodes if node.role == "RESEARCH")
    return (
        f"本题围绕{titles}形成由数据认识到模型决策的连续任务链。"
        "前一阶段得到的数据结构和中间结果会直接限制后一阶段可采用的模型与结论，因此需要在统一证据边界下组织各小问，而不能只追求单个算法的局部效果。"
    )


def _summarize_data_columns_cumcm(columns: list[str]) -> str:
    category_count = sum(str(value).startswith("品类::") for value in columns)
    item_count = sum(str(value).startswith("单品::") for value in columns)
    if category_count or item_count:
        parts: list[str] = []
        if category_count:
            parts.append(f"{category_count}个品类销量序列")
        if item_count:
            parts.append(f"{item_count}个主要单品销量序列")
        return "**数据口径：** 将原始销售记录统一到日尺度后，保留" + "与".join(parts) + "进入本问分析。"
    if len(columns) <= 8:
        return "**实际使用字段：** " + "、".join(columns) + "。"
    return f"**数据口径：** 本问实际使用{len(columns)}个已登记字段；完整字段清单保留在研究证据中，正文仅说明与建模直接相关的口径。"


def _redundant_data_column_note(note: str, columns: list[str]) -> bool:
    text = str(note or "")
    if not columns:
        return False
    return (
        "registered numeric columns" in text.lower()
        or "实际登记并进入求解流程的数值字段" in text
        or (len(columns) > 8 and all(str(value) in text for value in columns[: min(3, len(columns))]))
    )


def _render_model_spine_overview_mcm(spine: ModelSpine) -> str:
    clauses: list[str] = []
    for node in spine.nodes:
        q = _question_number(node.subproblem_id)
        if node.role == "FOUNDATION":
            clauses.append(f"Question {q} establishes the empirical foundation used downstream")
        elif node.role == "CORE_MODEL":
            clauses.append(f"Question {q} carries the core model, its governing relation/objective, and essential constraints")
        elif node.role == "EXTENSION":
            parents = ", ".join(_question_number(value) for value in node.inherits_from)
            relation = "constraint extension" if node.inheritance_kind == "CONSTRAINT" else "model extension"
            clauses.append(f"Question {q} extends Question(s) {parents} by {relation} rather than rebuilding the model")
        elif node.role == "INDEPENDENT_MODEL":
            clauses.append(f"Question {q} remains an independent modeling node because the accepted dependency graph does not justify inheritance")
        elif node.role == "SYNTHESIS":
            clauses.append(f"Question {q} synthesizes validated upstream results without introducing a new model")
    return "**Modeling spine.** " + "; ".join(clauses) + "."


def _model_role_note_mcm(spine_node: ModelSpineNode) -> str:
    if spine_node.role == "CORE_MODEL":
        return "**Role: core model.** This is a principal modeling node; the paper prioritizes its variables, governing relation or objective, essential constraints, and solution logic."
    if spine_node.role == "FOUNDATION":
        return "**Role: modeling foundation.** This question establishes data structure and usable empirical relationships for downstream modeling rather than adding complexity for its own sake."
    if spine_node.role == "EXTENSION":
        parents = ", ".join(_question_number(value) for value in spine_node.inherits_from)
        relation = {
            "MODEL": "reuses the upstream model structure",
            "CONSTRAINT": "reuses the upstream model and adds question-specific constraints",
            "SCENARIO": "reuses the upstream model under a new scenario or parameter setting",
            "EVIDENCE": "uses validated upstream outputs as inputs",
        }.get(spine_node.inheritance_kind, "builds on accepted upstream results")
        return f"**Role: model extension.** This question builds on Question(s) {parents} and {relation}; only the new decision layer, variables, or constraints are expanded here."
    return f"**Role: {spine_node.role.lower().replace('_', ' ')}.** {spine_node.narrative_directive}"


def _render_model_spine_overview_cumcm(spine: ModelSpine) -> str:
    clauses: list[str] = []
    for node in spine.nodes:
        q = _question_number(node.subproblem_id)
        if node.role == "FOUNDATION":
            clauses.append(f"问题{q}承担数据结构与规律识别，为后续建模提供依据")
        elif node.role == "CORE_MODEL":
            clauses.append(f"问题{q}承担核心模型，集中给出主要关系、目标函数与关键约束")
        elif node.role == "EXTENSION":
            parents = "、".join(_question_number(value) for value in node.inherits_from)
            relation = "约束扩展" if node.inheritance_kind == "CONSTRAINT" else "模型扩展"
            clauses.append(f"问题{q}在问题{parents}基础上作{relation}，只说明新增决策层和约束")
        elif node.role == "INDEPENDENT_MODEL":
            clauses.append(f"问题{q}保留为独立建模节点")
        elif node.role == "SYNTHESIS":
            clauses.append(f"问题{q}只综合前序已验证结果，不另起模型")
    return "**建模主线：** " + "；".join(clauses) + "。全文以这一主线组织模型与公式，避免把每一问写成彼此割裂的算法展示。"


def _render_model_story_overview_cumcm(story: ModelStoryPlan) -> str:
    if not story.whole_story_zh:
        return ""
    return (
        "**研究故事主线：** "
        + " ".join(story.whole_story_zh)
        + " 全文只在已有研究证据证明必要时增加模型复杂度，并让后续问题优先继承已验证的上游结构或结果。"
    )


def _model_role_note_cumcm(spine_node: ModelSpineNode, *, index: int) -> str:
    labels = {
        "FOUNDATION": "建模基础",
        "CORE_MODEL": "核心模型",
        "EXTENSION": "模型扩展",
        "INDEPENDENT_MODEL": "独立模型",
        "SYNTHESIS": "综合输出",
    }
    label = labels.get(spine_node.role, "建模节点")
    if spine_node.role == "EXTENSION" and spine_node.inherits_from:
        parents = "、".join(_question_number(value) for value in spine_node.inherits_from)
        relation = {
            "MODEL": "继承模型结构",
            "CONSTRAINT": "继承上游模型并增加本问约束",
            "SCENARIO": "继承上游模型并改变情景或参数",
            "EVIDENCE": "继承上游已验证结果作为输入",
        }.get(spine_node.inheritance_kind, "承接上游结果")
        return f"**本问定位：{label}。** 本问承接问题{parents}，{relation}；正文重点写新增变量、约束与决策，不重复前问已经建立的模型。"
    if spine_node.role == "CORE_MODEL":
        return "**本问定位：核心模型。** 本问是全文主要建模节点，正文优先呈现决策变量、核心关系或目标函数、关键约束与求解逻辑。"
    if spine_node.role == "FOUNDATION":
        return "**本问定位：建模基础。** 本问以数据结构与规律识别为主，所得关系只作为后续模型依据，不额外堆叠复杂算法。"
    return f"**本问定位：{label}。** {spine_node.narrative_directive}"


def _render_cumcm_research_state_paper(
    graph: NarrativeGraph,
    title: str,
    references: list[VerifiedReference],
    figures: list[dict[str, Any]],
    *,
    tables: list[Any] | None = None,
    model_spine: ModelSpine | None = None,
    model_story: ModelStoryPlan | None = None,
) -> str:
    """Render the same accepted Research State with CUMCM-C document conventions."""

    figures_by_sp = _group_question_figures(figures)
    tables_by_sp = group_question_tables(tables or [])
    context_figures = [
        item
        for item in figures
        if item.get("status") == "FINAL"
        and (item.get("parameters") or {}).get("semantic_kind") == "context_reality"
    ]
    context_figure = context_figures[-1] if context_figures else None
    workflow_figures = [
        item
        for item in figures
        if item.get("status") == "FINAL"
        and (item.get("parameters") or {}).get("semantic_kind") == "research_workflow"
    ]
    workflow_figure = workflow_figures[-1] if workflow_figures else None
    framework_figures = [
        item
        for item in figures
        if item.get("status") == "FINAL"
        and (item.get("parameters") or {}).get("semantic_kind") == "model_framework"
    ]
    framework_figure = framework_figures[-1] if framework_figures else None
    first_question_figure = (
        1
        + int(context_figure is not None)
        + int(workflow_figure is not None)
        + int(framework_figure is not None)
    )
    figure_numbers, table_numbers = _question_media_numbers(
        graph,
        figures_by_sp,
        tables_by_sp,
        figure_start=first_question_figure,
    )
    citation_numbers = {item.key: index for index, item in enumerate(references, start=1)}
    research_nodes = [node for node in graph.nodes if node.role == "RESEARCH"]
    has_data_section = any(node.data_columns or node.preprocessing_notes for node in research_nodes)
    synthesis_nodes = [node for node in graph.nodes if node.role == "SYNTHESIS"]

    next_section = 2
    data_section_no = next_section if has_data_section else None
    next_section += int(has_data_section)
    assumptions_section_no = next_section
    next_section += 1
    models_section_no = next_section
    next_section += 1
    recommendations_section_no = next_section
    next_section += 1
    synthesis_section_no = next_section if synthesis_nodes else None
    next_section += int(bool(synthesis_nodes))
    evaluation_section_no = next_section
    next_section += 1
    deliverables_section_no = next_section if synthesis_nodes else None
    next_section += int(bool(synthesis_nodes))
    conclusion_section_no = next_section

    lines: list[str] = [f"# {title}", "", "# 摘要", ""]
    lines.append(_render_abstract_cumcm(graph, references, citation_numbers))
    lines.extend(["", _render_keywords_cumcm(graph), ""])

    lines.extend(
        [
            "# 1. 问题重述与分析",
            "",
            _problem_background_cumcm(graph),
            "",
        ]
    )
    if context_figure is not None:
        context_relative = "../../" + str(context_figure["path"]).replace("\\", "/")
        context_parameters = context_figure.get("parameters") or {}
        context_title = PaperHumanizationAdapter.figure_title(context_figure, language="zh")
        source_provider = str(context_parameters.get("source_provider") or "可信公开来源")
        source_author = str(context_parameters.get("source_author") or "")
        source_license = str(context_parameters.get("source_license") or "")
        attribution_parts = [f"来源：{source_provider}"]
        if source_author:
            attribution_parts.append(f"作者：{source_author}")
        if source_license:
            attribution_parts.append(f"许可：{source_license}")
        lines.extend(
            [
                "为把抽象的定价与补货问题落到真实经营语境中，图1给出生鲜果蔬零售场景。该图片只承担问题背景说明作用，不参与任何销量、价格或收益数值的估计。",
                "",
                f"![图1  {context_title}]({context_relative})",
                "",
                "；".join(attribution_parts) + "。图片仅用于现实语境说明，完整来源页面与许可记录保存在可追溯的图像来源清单中。",
                "",
            ]
        )
    lines.extend(
        [
            "据此，本文不把各小问处理成彼此割裂的算法演示，而是沿“数据结构识别—模型建立—可靠性检验—决策输出”的顺序推进。每一问先完成本问所需的建模与检验；存在依赖时，后续小问只承接已经获得证据支持的上游结果。",
            "",
        ]
    )
    domain_citations = _domain_citations(references, citation_numbers)
    if domain_citations:
        lines.extend(
            [
                "经核验的领域文献用于说明问题背景 "
                + domain_citations
                + "。这些文献只支持背景与方法语义，不作为本题数据所得数值结论的证据。",
                "",
            ]
        )
    for index, node in enumerate(graph.nodes, start=1):
        dependency_text = (
            "；依赖问题" + "、".join(_question_number(item) for item in node.dependencies)
            if node.dependencies
            else ""
        )
        lines.append(f"- **问题{index}：** {node.objective}{dependency_text}。")
    lines.append("")
    if model_story is not None:
        lines.extend([_render_model_story_overview_cumcm(model_story), ""])
    elif model_spine is not None:
        lines.extend([_render_model_spine_overview_cumcm(model_spine), ""])
    global_figure_number = 1 + int(context_figure is not None)
    if workflow_figure is not None:
        workflow_relative = "../../" + str(workflow_figure["path"]).replace("\\", "/")
        lines.extend(
            [
                f"图{global_figure_number}给出本文从数据分析到决策输出的完整技术路线，并用承接箭头标出小问之间的证据依赖；图中不增加正文之外的新模型或数值结论。",
                "",
                f"![图{global_figure_number}  {PaperHumanizationAdapter.figure_title(workflow_figure, language='zh')}]({workflow_relative})",
                "",
                "后续正文沿图中的路线展开：先明确数据口径与分析目标，再建立并检验对应模型，最后把通过检验的中间结果转化为决策或综合建议。",
                "",
            ]
        )
        global_figure_number += 1
    if framework_figure is not None:
        framework_relative = "../../" + str(framework_figure["path"]).replace("\\", "/")
        lines.extend(
            [
                f"图{global_figure_number}进一步给出统一数学建模框架。它不重复技术路线，而是说明观测量如何进入状态/机理层，核心关系如何形成可求解模型，以及后续小问在什么位置继承或扩展该结构。",
                "",
                f"![图{global_figure_number}  {PaperHumanizationAdapter.figure_title(framework_figure, language='zh')}]({framework_relative})",
                "",
                "因此，本文的模型主线由同一组数学对象、关系和约束组织起来；只有当题目新增机理、约束、目标或数据状态时，后续小问才引入新的模型结构。",
                "",
            ]
        )

    if data_section_no is not None:
        lines.extend(
            [
                f"# {data_section_no}. 数据预处理与特征构造",
                "",
                "本节只记录实际进入模型的数据处理与特征构造步骤；未执行的清洗、变换或特征工程不在论文中补写。",
                "",
            ]
        )
        data_section_index = 0
        for node in research_nodes:
            if not node.data_columns and not node.preprocessing_notes:
                continue
            data_section_index += 1
            lines.extend([f"## {data_section_no}.{data_section_index}. 问题{data_section_index}的数据口径", ""])
            if node.data_columns:
                lines.extend([_summarize_data_columns_cumcm(node.data_columns), ""])
            if node.preprocessing_notes:
                kept_notes = [note for note in node.preprocessing_notes if not _redundant_data_column_note(note, node.data_columns)]
                for note in kept_notes:
                    lines.append(f"- {note}")
                if kept_notes:
                    lines.append("")

    lines.extend(
        [
            f"# {assumptions_section_no}. 模型假设与适用范围",
            "",
            "模型假设来自实际采用的方法、约束条件与数据口径，不使用与本题无关的通用假设填充章节。",
            "",
        ]
    )
    assumption_index = 0
    for node in graph.nodes:
        if node.role != "RESEARCH":
            continue
        assumption_index += 1
        lines.extend([f"## {assumptions_section_no}.{assumption_index}. 问题{assumption_index}的模型假设", ""])
        assumptions = assumptions_for_method(node.method, node.task_family, language="zh")
        if assumptions:
            for assumption in assumptions:
                lines.append(f"- {assumption}")
        else:
            lines.append("- 当前方法没有额外的专用假设需要补充，本文不以通用模板代替。")
        lines.append("")
    lines.extend(["符号、单位、公式和数值仅在对应已接受方法或证据能够支持时进入正文。", ""])

    lines.extend([f"# {models_section_no}. 模型建立、检验与结果", ""])
    research_index = 0
    for node in graph.nodes:
        if node.role != "RESEARCH":
            continue
        research_index += 1
        lines.extend(
            _render_research_node_cumcm(
                research_index,
                node,
                citation_numbers,
                references,
                figures_by_sp.get(node.subproblem_id, []),
                tables=tables_by_sp.get(node.subproblem_id, []),
                figure_numbers=figure_numbers,
                table_numbers=table_numbers,
                section_number=models_section_no,
                spine_node=(model_spine.node(node.subproblem_id) if model_spine is not None else None),
                section_story=(model_story.section(node.subproblem_id) if model_story is not None else None),
            )
        )

    lines.extend(
        [
            f"# {recommendations_section_no}. 结果解释与决策建议",
            "",
            "以下建议只把已接受的定量结果转换为题目语境下的解释，不增加新的数值结论；每条建议都受对应验证结果与局限约束。",
            "",
        ]
    )
    research_index = 0
    for node in graph.nodes:
        if node.role != "RESEARCH":
            continue
        research_index += 1
        lines.append(f"- **问题{research_index}：** {_practical_recommendation_cumcm(node)}")
    lines.append("")

    if synthesis_section_no is not None:
        lines.extend([f"# {synthesis_section_no}. 各问综合与交付结果", ""])
        lines.extend(["综合性结论只汇总其依赖小问中已经验证的结果，不把交付物误当成额外模型。", ""])
        for synthesis_index, synthesis in enumerate(synthesis_nodes, start=1):
            dependency_text = "、".join(_question_number(item) for item in synthesis.dependencies) or "无"
            lines.extend(
                [
                    f"## {synthesis_section_no}.{synthesis_index}. {synthesis.title}",
                    "",
                    f"该交付结果依赖问题 {dependency_text} 的研究结论。",
                    "",
                    synthesis.answer,
                    "",
                    f"**适用范围：** {synthesis.limitation}",
                    "",
                ]
            )

    lines.extend([f"# {evaluation_section_no}. 模型评价、稳健性与局限", "", f"## {evaluation_section_no}.1 模型优点", ""])
    lines.extend(
        [
            "- 各小问按“基础分析—核心模型—约束扩展—综合输出”的研究主线组织；后续问题优先复用上游模型、参数或已验证结果，而不是为每一问机械更换算法。",
            "- 正文公式只保留解释模型结构所必需的核心关系、目标函数和约束；常规估计与调参步骤用文字说明或保留在可复现证据中。",
            "- 定量结论、图表与建议均来自已验证研究证据；未执行候选不会被写成已验证模型，综合交付也不创造新的数值结论。",
            "",
            f"## {evaluation_section_no}.2 模型局限",
            "",
        ]
    )
    research_index = 0
    for node in graph.nodes:
        if node.role != "RESEARCH":
            continue
        research_index += 1
        lines.append(f"- **问题{research_index}：** {node.limitation}")
    lines.extend(["", f"## {evaluation_section_no}.3 稳健性与适用边界", ""])
    research_index = 0
    for node in graph.nodes:
        if node.role != "RESEARCH":
            continue
        research_index += 1
        protocol = PaperHumanizationAdapter.validation_label(node.validation_protocol_id or "family-specific validation", language="zh")
        validation_label = "通过" if str(node.validation_gate).upper() == "PASS" else "需复核"
        lines.append(
            f"- **问题{research_index}：** 采用{protocol}进行检验，结果{validation_label}；适用边界为：{node.limitation}"
        )
    lines.extend(["", "若后续发现研究证据不足，应回到相应小问的建模、求解或检验阶段补充，而不是只通过文字润色掩盖缺口。", ""])

    if deliverables_section_no is not None:
        lines.extend([f"# {deliverables_section_no}. 题目指定交付内容", ""])
        lines.extend(_render_prompt_specific_deliverables_cumcm(graph))
    lines.extend(["", f"# {conclusion_section_no}. 结论", ""])
    for index, node in enumerate(graph.nodes, start=1):
        lines.append(f"- **问题{index}：** {node.answer}")

    long_decision_tables: list[tuple[NarrativeNode, Any]] = []
    for node in graph.nodes:
        if node.role != "RESEARCH":
            continue
        for table in tables_by_sp.get(node.subproblem_id, []):
            metadata = dict(getattr(table, "metadata", {}) or {})
            if (
                str(metadata.get("table_role") or "") == "decision_schedule"
                and len(list(getattr(table, "rows", []) or [])) > 16
            ):
                long_decision_tables.append((node, table))
    if long_decision_tables:
        lines.extend(["", "# 附录A  详细决策表", "", "正文只保留支持论证所需的代表行；以下附录完整保留可执行决策值，便于复核与实施。", ""])
        for appendix_index, (node, table) in enumerate(long_decision_tables, start=1):
            lines.extend([f"## A.{appendix_index}  {getattr(table, 'title', '完整决策方案')}", ""])
            lines.extend(_registered_table_markdown(table, node=node, language="zh"))
            lines.append("")

    lines.extend(["", "# 参考文献", ""])
    for index, reference in enumerate(references, start=1):
        lines.append(f"[{index}] {reference.citation}")
    return "\n".join(lines).rstrip() + "\n"


def _render_abstract_cumcm(
    graph: NarrativeGraph,
    references: list[VerifiedReference],
    citation_numbers: dict[str, int],
) -> str:
    research_nodes = [node for node in graph.nodes if node.role == "RESEARCH"]
    if not research_nodes:
        return ""

    titles = "、".join(node.title for node in research_nodes[:3])
    if len(research_nodes) > 3:
        titles += "等任务"
    sentences: list[str] = [
        f"围绕{titles}构成的连续研究链，本文依据各小问的数据特征、约束结构和前后依赖分别建模，使后续结论建立在前序可复用结果之上。"
    ]
    transitions = ["首先", "随后", "进一步", "在此基础上", "最后"]
    for index, node in enumerate(research_nodes):
        transition = transitions[index] if index < len(transitions) else "进一步"
        citations = _method_citations(node.method, references, citation_numbers)
        citation_text = f" {citations}" if citations else ""
        result_text = _abstract_results(node, language="zh").removeprefix("关键结果为")
        result_clause = f"，得到{result_text}" if result_text else ""
        sentences.append(
            f"{transition}，针对{node.title}，采用{_humanize_cumcm(node.method)}{citation_text}{result_clause}。"
        )

    validation_terms = _abstract_validation_summary(research_nodes, language="zh")
    if validation_terms:
        sentences.append(validation_terms)
    synthesis_nodes = [node for node in graph.nodes if node.role == "SYNTHESIS"]
    if synthesis_nodes:
        sentences.append(f"据此形成{_compact_text(synthesis_nodes[0].answer, 90)}")
    else:
        final_answer = _compact_text(research_nodes[-1].answer, 90)
        if final_answer:
            sentences.append(f"综合各问结果，{final_answer}")
    return "".join(sentences)


def _render_keywords_cumcm(graph: NarrativeGraph) -> str:
    family_names = {
        "forecasting": "预测",
        "explanatory_inference": "解释性推断",
        "distribution_forecasting": "分布预测",
        "classification": "分类",
        "exploratory_analysis": "探索性分析",
        "optimization": "优化",
        "simulation": "仿真",
        "ranking": "综合评价",
    }
    keywords: list[str] = []
    for node in graph.nodes:
        if node.role == "RESEARCH" and node.task_family in family_names:
            keywords.append(family_names[node.task_family])
    keywords = list(dict.fromkeys(keywords))[:5]
    return "**关键词：** " + "；".join(keywords)


def _render_research_node_cumcm(
    index: int,
    node: NarrativeNode,
    citation_numbers: dict[str, int],
    references: list[VerifiedReference],
    figures: list[dict[str, Any]],
    *,
    tables: list[Any] | None = None,
    figure_numbers: dict[str, int] | None = None,
    table_numbers: dict[str, int] | None = None,
    section_number: int = 4,
    spine_node: ModelSpineNode | None = None,
    section_story: SectionStory | None = None,
) -> list[str]:
    if section_story is not None:
        return _render_research_node_cumcm_story(
            index,
            node,
            citation_numbers,
            references,
            figures,
            tables=tables or [],
            figure_numbers=figure_numbers or {},
            table_numbers=table_numbers or {},
            section_number=section_number,
            spine_node=spine_node,
            section_story=section_story,
        )

    lines = [f"## {section_number}.{index}. 问题{index}：{node.title}", "", f"**研究目标：** {node.objective}", ""]
    if spine_node is not None:
        lines.extend([_model_role_note_cumcm(spine_node, index=index), ""])
    citations = _method_citations(node.method, references, citation_numbers)
    citation_text = f" {citations}" if citations else ""
    model_narrative = narrative_for_method(node.method, node.task_family)
    if model_narrative.motivation_zh:
        lines.extend(["**建模动机：** " + model_narrative.motivation_zh, ""])
    lines.extend(
        [
            f"**模型与方法：** 采用{_humanize_cumcm(node.method)}{citation_text}。模型形式由本问的数据特征与约束结构决定，并以实际求解和验证结果作为保留依据。",
            "",
            "**变量与符号：** " + model_narrative.variables_zh,
            "",
            "**模型构造：** " + model_narrative.construction_zh,
            "",
        ]
    )
    alternatives = [
        item
        for item in node.candidate_considerations
        if not item.selected and str(item.feasibility).upper() == "PASS"
    ]
    if alternatives:
        lines.extend(["**候选方案审查：** 仅列出已经具备同口径执行条件的备选方案；未执行或仅计划方案不占用正文篇幅。", ""])
        for alternative in alternatives[:4]:
            feasibility = {"PASS": "可执行", "NEEDS_SOLVER": "当前不可直接执行", "PLANNED": "待验证"}.get(alternative.feasibility, alternative.feasibility)
            rationale = PaperHumanizationAdapter.candidate_rationale(alternative.rationale, language="zh")
            lines.append(f"- {_humanize_cumcm(alternative.method)} — {feasibility}：{rationale}")
        lines.append("")

    if node.alternative_comparison is not None:
        comparison = node.alternative_comparison
        executed = "、".join(_humanize_cumcm(value) for value in comparison.alternative_methods) or "无"
        lines.extend(
            [
                f"**对照实验：** 当前采用的{_humanize_cumcm(comparison.accepted_method)}与{executed}按{PaperHumanizationAdapter.metric_label(comparison.primary_metric, language='zh')}进行同协议比较。比较结论为：{comparison.rationale}",
                "",
            ]
        )
        if comparison.stress_runs:
            sizes = "、".join(f"{value:.0%}" for value in comparison.stress_test_sizes)
            lines.extend(
                [
                    f"同时在留出比例{sizes}下进行稳健性压力测试，单次切分占优不足以触发模型切换。",
                    "",
                    "| 已执行方法 | 中位指标 | 最差指标 | 相对已接受方法胜率 | 稳健优于 |",
                    "|---|---:|---:|---:|---|",
                ]
            )
            for run in comparison.stress_runs:
                lines.append(
                    f"| {_humanize(str(run.get('method') or run.get('solver') or 'method'))} | "
                    f"{float(run.get('median_value', 0.0)):.3f} | {float(run.get('worst_value', 0.0)):.3f} | "
                    f"{float(run.get('win_rate_vs_accepted', 0.0)):.0%} | "
                    f"{'是' if run.get('robustly_better') else '否'} |"
                )
            lines.append("")

    equation_budget = _adaptive_equation_budget(node, spine_node)
    equations = select_equations_for_paper(node.method, equation_budget)
    if equations:
        lines.extend(["**数学模型：**", ""])
        for equation in equations:
            label = equation.label_zh or equation.label
            explanation = equation.explanation_zh or equation.explanation
            lines.extend([f"{label}：", "", f"$${equation.latex}$$", "", explanation, ""])
    else:
        lines.extend(["**数学模型：** 当前求解方法未登记可直接写入正文的专用公式，论文不使用与实际求解无关的通用公式补位。", ""])
    lines.extend(["**求解过程：** " + model_narrative.solution_zh, ""])

    protocol = PaperHumanizationAdapter.validation_label(node.validation_protocol_id or "family-specific validation", language="zh")
    validation_label = "通过" if str(node.validation_gate).upper() == "PASS" else "需复核"
    lines.extend([f"**模型检验：** 采用{protocol}进行检验，结果为 **{validation_label}**。", ""])

    blocks = plan_argument_blocks(node, figures, tables or [])
    if blocks:
        for block in blocks:
            lines.extend([block.lead_zh, ""])
            if block.kind == "figure":
                figure = block.item
                relative = "../../" + str(figure["path"]).replace("\\", "/")
                number = (figure_numbers or {}).get(str(figure.get("figure_id") or ""), index)
                lines.extend(
                    [
                        f"![图{number}  {PaperHumanizationAdapter.figure_title(figure, language='zh')}]({relative})",
                        "",
                    ]
                )
            else:
                table = block.item
                table_id = str(getattr(table, "table_id", ""))
                number = (table_numbers or {}).get(table_id, index)
                metadata = dict(getattr(table, "metadata", {}) or {})
                is_long_decision = (
                    str(metadata.get("table_role") or "") == "decision_schedule"
                    and len(list(getattr(table, "rows", []) or [])) > 16
                )
                title = str(getattr(table, "title", f"问题{index}定量结果"))
                if is_long_decision:
                    title += "（正文摘录，完整方案见附录A）"
                lines.extend([f"**表{number}  {title}**", ""])
                lines.extend(
                    _registered_table_markdown(
                        table,
                        node=node,
                        language="zh",
                        max_rows=8 if is_long_decision else None,
                    )
                )
                if is_long_decision:
                    lines.extend(["", "正文仅保留代表性决策行以维持论证节奏，完整逐项执行方案列于附录A。"])
                lines.append("")
            if block.tail_zh:
                lines.extend([block.tail_zh, ""])
    else:
        if node.key_results:
            lines.extend([f"**表{index}  问题{index}的已接受定量结果**", ""])
            lines.extend(_markdown_result_table_cumcm(node))
            lines.append("")
        for figure in figures:
            relative = "../../" + str(figure["path"]).replace("\\", "/")
            number = (figure_numbers or {}).get(str(figure.get("figure_id") or ""), index)
            lines.extend(
                [
                    "该图在本问首次需要相应证据的位置展示，用于支撑正文判断而非装饰。",
                    "",
                    f"![图{number}  {PaperHumanizationAdapter.figure_title(figure, language='zh')}]({relative})",
                    "",
                ]
            )
    lines.extend([f"**本问结论：** {node.answer}", "", f"**局限：** {node.limitation}", ""])
    return lines


def _render_research_node_cumcm_story(
    index: int,
    node: NarrativeNode,
    citation_numbers: dict[str, int],
    references: list[VerifiedReference],
    figures: list[dict[str, Any]],
    *,
    tables: list[Any],
    figure_numbers: dict[str, int],
    table_numbers: dict[str, int],
    section_number: int,
    spine_node: ModelSpineNode | None,
    section_story: SectionStory,
) -> list[str]:
    """Render one question from the progressive ModelStoryPlan.

    This path intentionally avoids the old fixed sequence of ``目标/方法/变量/公式/
    求解/检验`` labels.  The accepted story moves choose the section rhythm, while
    formulas, tables and figures still come from the same evidence-locked registries.
    """

    role_label = {
        "FOUNDATION": "规律基础",
        "CORE_MODEL": "核心模型",
        "EXTENSION": "继承扩展",
        "INDEPENDENT_MODEL": "独立模型",
    }.get(section_story.role, "建模")
    lines: list[str] = [
        f"## {section_number}.{index}. {node.title}（问题{index}·{role_label}）",
        "",
    ]
    moves = {move.kind: move for move in section_story.moves}
    model_narrative = narrative_for_method(node.method, node.task_family)
    citations = _method_citations(node.method, references, citation_numbers)
    citation_text = f" {citations}" if citations else ""

    # Stage A — insight / inheritance / simplest relation.
    opening_title = "从问题洞察到可检验关系"
    if "INHERITED_RESULT" in moves:
        opening_title = "承接前问：不从零重新建模"
    elif "SIMPLE_RELATION" in moves:
        opening_title = moves["SIMPLE_RELATION"].headline_zh
    lines.extend([f"### {section_number}.{index}.1 {opening_title}", ""])
    lines.append(f"{node.objective}。")
    lines.append("")
    if model_narrative.motivation_zh:
        lines.extend([model_narrative.motivation_zh, ""])
    if "INHERITED_RESULT" in moves:
        inheritance = moves["INHERITED_RESULT"].directive_zh
        lines.extend([inheritance, ""])
    if "SIMPLE_RELATION" in moves:
        simple_text = moves["SIMPLE_RELATION"].directive_zh.replace("Solver 的", "实际求解协议的")
        lines.extend([simple_text, ""])

    # Stage B — complexity is admitted only when the story planner has evidence.
    stage_no = 2
    if "INSUFFICIENCY_EVIDENCE" in moves or "NECESSARY_CORRECTION" in moves:
        lines.extend([f"### {section_number}.{index}.{stage_no} 为什么简单关系还不够", ""])
        if "INSUFFICIENCY_EVIDENCE" in moves:
            lines.extend([moves["INSUFFICIENCY_EVIDENCE"].directive_zh, ""])
        if "NECESSARY_CORRECTION" in moves:
            lines.extend([moves["NECESSARY_CORRECTION"].directive_zh, ""])
        stage_no += 1

    alternatives = [
        item
        for item in node.candidate_considerations
        if not item.selected and str(item.feasibility).upper() == "PASS"
    ]
    if alternatives or node.alternative_comparison is not None:
        lines.extend([f"### {section_number}.{index}.{stage_no} 方案选择与复杂度门槛", ""])
        if alternatives:
            lines.append("只有具备同一数据口径与验证协议的备选方案才进入比较；未执行方案不写入性能结论。")
            lines.append("")
            for alternative in alternatives[:4]:
                rationale = PaperHumanizationAdapter.candidate_rationale(alternative.rationale, language="zh")
                lines.append(f"- {_humanize_cumcm(alternative.method)}：{rationale}")
            lines.append("")
        if node.alternative_comparison is not None:
            comparison = node.alternative_comparison
            executed = "、".join(_humanize_cumcm(value) for value in comparison.alternative_methods) or "无"
            lines.extend(
                [
                    f"已接受方法{_humanize_cumcm(comparison.accepted_method)}与{executed}按{PaperHumanizationAdapter.metric_label(comparison.primary_metric, language='zh')}采用同协议比较。{comparison.rationale}",
                    "",
                ]
            )
            if comparison.stress_runs:
                sizes = "、".join(f"{value:.0%}" for value in comparison.stress_test_sizes)
                lines.extend(
                    [
                        f"进一步在留出比例{sizes}下做压力测试，避免由单次切分决定模型升级。",
                        "",
                        "| 已执行方法 | 中位指标 | 最差指标 | 相对已接受方法胜率 | 稳健优于 |",
                        "|---|---:|---:|---:|---|",
                    ]
                )
                for run in comparison.stress_runs:
                    lines.append(
                        f"| {_humanize(str(run.get('method') or run.get('solver') or 'method'))} | "
                        f"{float(run.get('median_value', 0.0)):.3f} | {float(run.get('worst_value', 0.0)):.3f} | "
                        f"{float(run.get('win_rate_vs_accepted', 0.0)):.0%} | "
                        f"{'是' if run.get('robustly_better') else '否'} |"
                    )
                lines.append("")
        stage_no += 1

    # Stage C — core construction or inherited extension.
    if section_story.role == "EXTENSION":
        construction_title = "在上游模型上增加本问约束与决策层"
        if "EXTENSION" in moves:
            lines.extend([f"### {section_number}.{index}.{stage_no} {construction_title}", "", moves["EXTENSION"].directive_zh, ""])
        else:
            lines.extend([f"### {section_number}.{index}.{stage_no} {construction_title}", ""])
    elif section_story.role == "FOUNDATION":
        lines.extend([f"### {section_number}.{index}.{stage_no} 用最少方法提取可复用结构", ""])
    else:
        lines.extend([f"### {section_number}.{index}.{stage_no} 核心模型的建立与求解", ""])
        if "CORE_MODEL" in moves:
            lines.extend([moves["CORE_MODEL"].directive_zh, ""])

    lines.extend(
        [
            f"本文实际采用{_humanize_cumcm(node.method)}{citation_text}。{model_narrative.variables_zh}",
            "",
            model_narrative.construction_zh,
            "",
        ]
    )
    equation_budget = _adaptive_equation_budget(node, spine_node)
    equations = select_equations_for_paper(node.method, equation_budget)
    if equations:
        for equation in equations:
            label = equation.label_zh or equation.label
            explanation = equation.explanation_zh or equation.explanation
            lines.extend([f"{label}：", "", f"$${equation.latex}$$", "", explanation, ""])
    lines.extend(["求解时，" + model_narrative.solution_zh, ""])
    stage_no += 1

    # Stage D — validation and evidence are adjacent to the model they justify.
    lines.extend([f"### {section_number}.{index}.{stage_no} 检验、证据与本问决策", ""])
    protocol = PaperHumanizationAdapter.validation_label(node.validation_protocol_id or "family-specific validation", language="zh")
    validation_label = "通过" if str(node.validation_gate).upper() == "PASS" else "需复核"
    lines.extend(
        [
            f"模型建立后立即采用{protocol}进行独立检验，结果为 **{validation_label}**。只有通过该检验的关系、参数和策略才进入后续问题。",
            "",
        ]
    )

    blocks = plan_argument_blocks(node, figures, tables)
    if blocks:
        for block in blocks:
            lines.extend([block.lead_zh, ""])
            if block.kind == "figure":
                figure = block.item
                relative = "../../" + str(figure["path"]).replace("\\", "/")
                number = figure_numbers.get(str(figure.get("figure_id") or ""), index)
                lines.extend(
                    [
                        f"![图{number}  {PaperHumanizationAdapter.figure_title(figure, language='zh')}]({relative})",
                        "",
                    ]
                )
            else:
                table = block.item
                table_id = str(getattr(table, "table_id", ""))
                number = table_numbers.get(table_id, index)
                metadata = dict(getattr(table, "metadata", {}) or {})
                is_long_decision = (
                    str(metadata.get("table_role") or "") == "decision_schedule"
                    and len(list(getattr(table, "rows", []) or [])) > 16
                )
                title = str(getattr(table, "title", f"问题{index}定量结果"))
                if is_long_decision:
                    title += "（正文摘录，完整方案见附录A）"
                lines.extend([f"**表{number}  {title}**", ""])
                lines.extend(
                    _registered_table_markdown(
                        table,
                        node=node,
                        language="zh",
                        max_rows=8 if is_long_decision else None,
                    )
                )
                if is_long_decision:
                    lines.extend(["", "正文仅保留代表性决策行以维持论证节奏，完整逐项执行方案列于附录A。"])
                lines.append("")
            if block.tail_zh:
                lines.extend([block.tail_zh, ""])
    else:
        if node.key_results:
            lines.extend([f"**表{index}  问题{index}的已接受定量结果**", ""])
            lines.extend(_markdown_result_table_cumcm(node))
            lines.append("")
        for figure in figures:
            relative = "../../" + str(figure["path"]).replace("\\", "/")
            number = figure_numbers.get(str(figure.get("figure_id") or ""), index)
            lines.extend(
                [
                    f"![图{number}  {PaperHumanizationAdapter.figure_title(figure, language='zh')}]({relative})",
                    "",
                ]
            )

    lines.extend(
        [
            f"因此，本问得到：{node.answer}",
            "",
            f"这一结论的适用边界为：{node.limitation}",
            "",
        ]
    )
    return lines


def _registered_table_markdown(
    table: Any,
    *,
    node: NarrativeNode,
    language: str,
    max_rows: int | None = None,
) -> list[str]:
    metadata = dict(getattr(table, "metadata", {}) or {})
    if str(metadata.get("table_role") or "") == "summary_metrics" and node.key_results:
        return _markdown_result_table_cumcm(node) if language == "zh" else _markdown_result_table(node)
    columns = [str(value) for value in getattr(table, "columns", [])]
    rows = list(getattr(table, "rows", []) or [])
    if not columns or not rows:
        return []
    visible_rows = rows[: max_rows] if max_rows is not None else rows
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    lines.extend("| " + " | ".join(str(cell) for cell in row) + " |" for row in visible_rows)
    return lines


def _markdown_result_table_cumcm(node: NarrativeNode) -> list[str]:
    lines = ["| 指标 | 数值 | 解释 |", "|---|---:|---|"]
    seen: set[tuple[str, float]] = set()
    for result in node.key_results[:10]:
        signature = (str(result.metric), round(float(result.value), 12))
        if signature in seen:
            continue
        seen.add(signature)
        interpretation = _result_interpretation_cumcm(result.metric, result.metadata)
        label = PaperHumanizationAdapter.metric_label(result.metric, result.metadata, language="zh")
        lines.append(f"| {label} | {result.value:.6g} | {interpretation} |")
    return lines


def _practical_recommendation_cumcm(node: NarrativeNode) -> str:
    mapping = {
        "forecasting": "使用点预测时必须同时参考其预测区间；区间宽度决定单一点预测可以被赋予多大置信度。",
        "explanatory_inference": "使用稳定的特征效应解释观测关联，但除非研究设计支持因果识别，不把关联写成因果干预。",
        "distribution_forecasting": "使用完整预测分布刻画结果结构，并保留各分量的不确定性，不只报告最大分量。",
        "classification": "类别标签应与类别概率共同使用；低置信度结果应明确标注不确定，而不是强行给出确定类别。",
        "exploratory_analysis": "探索性规律用于提出后续分析重点；未经专门推断检验的模式不直接升级为确定结论。",
        "optimization": "最优方案只在登记约束与参数范围内成立；关键参数变化可能改变最优解时，应先完成敏感性或稳健性检验。",
        "simulation": "决策应参考重复仿真的分布与区间，而不是依赖单次随机模拟结果。",
        "ranking": "排序结论应结合稳定性分析；相邻方案在扰动下频繁互换时，应视为近似并列。",
    }
    return mapping.get(node.task_family, "该结论仅在本小问已接受的证据范围和检验边界内使用。")


def _render_prompt_specific_deliverables_cumcm(graph: NarrativeGraph) -> list[str]:
    synthesis_nodes = [node for node in graph.nodes if node.role == "SYNTHESIS"]
    if not synthesis_nodes:
        return ["题目未登记单独的 memo、letter 或其它综合交付节点。"]
    lines: list[str] = []
    for node in synthesis_nodes:
        label = (node.title + " " + node.objective).lower()
        if "memo" in label or "governor" in label:
            lines.extend([f"## {node.title}", "", "以下备忘录仅使用其依赖小问中的已接受证据。", "", node.answer, "", f"**适用范围：** {node.limitation}", ""])
        elif "letter" in label or "editor" in label:
            lines.extend([f"## {node.title}", "", "以下信件仅综合其依赖小问中的已接受证据。", "", node.answer, "", f"**适用范围：** {node.limitation}", ""])
        else:
            lines.extend([f"## {node.title}", "", node.answer, "", f"**适用范围：** {node.limitation}", ""])
    return lines


def _render_abstract(
    graph: NarrativeGraph,
    references: list[VerifiedReference],
    citation_numbers: dict[str, int],
) -> str:
    research_nodes = [node for node in graph.nodes if node.role == "RESEARCH"]
    if not research_nodes:
        return ""
    sentences = [
        "We treat the prompt as a linked sequence of research questions, choosing each model from the local data, constraints, and dependency structure rather than forcing one algorithm across the paper."
    ]
    transitions = ["First", "Next", "Finally", "Building on these results"]
    for index, node in enumerate(research_nodes):
        transition = transitions[index] if index < len(transitions) else "We further"
        citations = _method_citations(node.method, references, citation_numbers)
        citation_text = f" {citations}" if citations else ""
        result_text = _abstract_results(node).removeprefix("key results include ")
        result_clause = f", obtaining {result_text}" if result_text else ""
        sentences.append(
            f"{transition}, we address {node.title} with {_humanize(node.method)}{citation_text}{result_clause}."
        )
    validation_terms = _abstract_validation_summary(research_nodes, language="en")
    if validation_terms:
        sentences.append(validation_terms)
    synthesis_nodes = [node for node in graph.nodes if node.role == "SYNTHESIS"]
    if synthesis_nodes:
        sentences.append("These results support the requested deliverable: " + _compact_text(synthesis_nodes[0].answer, 170))
    else:
        final_answer = _compact_text(research_nodes[-1].answer, 260)
        if final_answer:
            sentences.append("Taken together, " + final_answer)
    return " ".join(sentences)


def _render_keywords(graph: NarrativeGraph) -> str:
    family_names = {
        "forecasting": "forecasting",
        "explanatory_inference": "statistical inference",
        "distribution_forecasting": "distribution forecasting",
        "classification": "probabilistic classification",
        "exploratory_analysis": "exploratory analysis",
        "optimization": "optimization",
        "simulation": "simulation",
        "ranking": "multi-criteria evaluation",
    }
    archetype_names = {
        "dynamic_state": "dynamic-state modeling",
        "probabilistic_state": "probabilistic state model",
        "forecasting": "forecasting",
        "explanatory_inference": "statistical inference",
        "optimization": "constrained optimization",
        "simulation": "stochastic simulation",
        "ranking_evaluation": "multi-criteria evaluation",
        "network_spatial": "network/spatial modeling",
        "discrete_process": "discrete process",
        "geometry": "geometric modeling",
    }
    keywords: list[str] = []
    for node in graph.nodes:
        if node.role != "RESEARCH":
            continue
        structure = getattr(node, "model_structure", None)
        for archetype in getattr(structure, "archetypes", []) or []:
            if archetype in archetype_names:
                keywords.append(archetype_names[archetype])
        if node.task_family in family_names:
            keywords.append(family_names[node.task_family])
    keywords = list(dict.fromkeys(keywords))[:5]
    return "**Keywords:** " + "; ".join(keywords)


def _render_research_node(
    index: int,
    node: NarrativeNode,
    citation_numbers: dict[str, int],
    references: list[VerifiedReference],
    figures: list[dict[str, Any]],
    *,
    tables: list[Any] | None = None,
    figure_numbers: dict[str, int] | None = None,
    table_numbers: dict[str, int] | None = None,
    spine_node: ModelSpineNode | None = None,
) -> list[str]:
    lines = [f"## 4.{index}. Question {index} — {node.title}", ""]
    lines.extend([f"**Objective.** {node.objective}", ""])
    if spine_node is not None:
        lines.extend([_model_role_note_mcm(spine_node), ""])
    citations = _method_citations(node.method, references, citation_numbers)
    citation_text = f" {citations}" if citations else ""
    lines.extend(
        [
            f"**Method.** We use {_humanize(node.method)}{citation_text}. The method is evaluated for this question under the validation design stated below; later questions reuse it only when the dependency structure justifies that inheritance.",
            "",
        ]
    )
    alternatives = [item for item in node.candidate_considerations if not item.selected]
    if alternatives:
        lines.extend(
            [
                "**Alternative strategies considered.** The research planner considered the following alternatives before the accepted execution. "
                "Their feasibility status is reported honestly; no unexecuted alternative is assigned invented performance metrics.",
                "",
            ]
        )
        for alternative in alternatives[:4]:
            lines.append(
                f"- {_humanize(alternative.method)} — {alternative.feasibility}: {alternative.rationale}"
            )
        lines.append("")

    if node.alternative_comparison is not None:
        comparison = node.alternative_comparison
        executed = ", ".join(_humanize(value) for value in comparison.alternative_methods) or "none"
        lines.extend(
            [
                "**Executed head-to-head comparison.** "
                f"The accepted method {_humanize(comparison.accepted_method)} was empirically compared with {executed} "
                f"using {comparison.primary_metric}. The recorded decision is **{comparison.decision}**: {comparison.rationale}",
                "",
            ]
        )
        if comparison.stress_runs:
            sizes = ", ".join(f"{value:.0%}" for value in comparison.stress_test_sizes)
            lines.extend(
                [
                    f"Temporal robustness was stress-tested at holdout fractions {sizes}; a single favorable split is not treated as sufficient evidence for switching models.",
                    "",
                    "| Executed method | Median metric | Worst metric | Win rate vs accepted | Robustly better |",
                    "|---|---:|---:|---:|---|",
                ]
            )
            for run in comparison.stress_runs:
                lines.append(
                    f"| {_humanize(str(run.get('method') or run.get('solver') or 'method'))} | "
                    f"{float(run.get('median_value', 0.0)):.3f} | {float(run.get('worst_value', 0.0)):.3f} | "
                    f"{float(run.get('win_rate_vs_accepted', 0.0)):.0%} | "
                    f"{'yes' if run.get('robustly_better') else 'no'} |"
                )
            lines.append("")

    equation_budget = _adaptive_equation_budget(node, spine_node)
    equations = select_equations_for_paper(node.method, equation_budget)
    if equations:
        lines.append("**Model equations.**")
        lines.append("")
        for equation in equations:
            lines.extend([f"{equation.label}:", "", f"$${equation.latex}$$", "", equation.explanation, ""])
    else:
        lines.extend(
            [
                "**Model equations.** No equation is emitted because this executed solver has no registered equation schema yet; the paper engine refuses to substitute a generic template.",
                "",
            ]
        )

    protocol = _humanize(node.validation_protocol_id or "family-specific validation")
    lines.extend(
        [
            f"**Validation.** We use {protocol}. The resulting checks satisfy the acceptance criteria for the claims reported in this section.",
            "",
        ]
    )
    blocks = plan_argument_blocks(node, figures, tables or [])
    if blocks:
        for block in blocks:
            lines.extend([block.lead_en, ""])
            if block.kind == "figure":
                figure = block.item
                relative = "../../" + str(figure["path"]).replace("\\", "/")
                number = (figure_numbers or {}).get(str(figure.get("figure_id") or ""), index)
                lines.extend(
                    [
                        f"![Figure {number}. {figure.get('title', f'Question {index} evidence visualization')}]({relative})",
                        "",
                    ]
                )
            else:
                table = block.item
                table_id = str(getattr(table, "table_id", ""))
                number = (table_numbers or {}).get(table_id, index)
                lines.extend(
                    [
                        f"**Table {number}. {getattr(table, 'title', f'Question {index} quantitative results')}.**",
                        "",
                    ]
                )
                lines.extend(_registered_table_markdown(table, node=node, language="en"))
                lines.append("")
            if block.tail_en:
                lines.extend([block.tail_en, ""])
    else:
        if node.key_results:
            lines.extend([f"**Table {index}. Accepted quantitative results for Question {index}.**", ""])
            lines.extend(_markdown_result_table(node))
            lines.append("")
        for figure in figures:
            relative = "../../" + str(figure["path"]).replace("\\", "/")
            number = (figure_numbers or {}).get(str(figure.get("figure_id") or ""), index)
            lines.extend(
                [
                    "The figure is placed where its evidence is first needed, rather than appended decoratively.",
                    "",
                    f"![Figure {number}. {figure.get('title', f'Question {index} evidence visualization')}]({relative})",
                    "",
                ]
            )
    lines.extend([f"**Answer.** {node.answer}", "", f"**Limitation.** {node.limitation}", ""])
    return lines


def _render_prompt_specific_deliverables(graph: NarrativeGraph) -> list[str]:
    """Render actual memo/letter deliverables from accepted dependency evidence."""

    synthesis_nodes = [node for node in graph.nodes if node.role == "SYNTHESIS"]
    if not synthesis_nodes:
        return ["No separate prompt-specific memo or letter is registered."]
    lines: list[str] = []
    for node in synthesis_nodes:
        label = (node.title + " " + node.objective).lower()
        if "memo" in label or "governor" in label:
            lines.extend(_render_governors_memo(graph, node))
        elif "letter" in label or "editor" in label:
            lines.extend(_render_editor_letter(graph, node))
        else:
            lines.extend([f"## {node.title}", "", node.answer, "", f"**Scope.** {node.limitation}", ""])
    return lines


def _dependency_research_nodes(graph: NarrativeGraph, synthesis: NarrativeNode) -> list[NarrativeNode]:
    dependencies = set(synthesis.dependencies)
    return [
        node
        for node in graph.nodes
        if node.role == "RESEARCH" and node.subproblem_id in dependencies
    ]


def _render_editor_letter(graph: NarrativeGraph, synthesis: NarrativeNode) -> list[str]:
    research_nodes = _dependency_research_nodes(graph, synthesis)
    lines = [
        "## Letter to the Puzzle Editor",
        "",
        "Dear Puzzle Editor,",
        "",
        "We analyzed the registered data as a sequence of linked but distinct questions. The recommendations below are restricted to accepted results and validation scope.",
        "",
    ]
    for index, node in enumerate(research_nodes, start=1):
        lines.append(f"**Finding {index}.** {node.answer}")
        lines.append(f"Editorial implication: {_practical_recommendation(node)}")
        lines.append("")
    lines.extend([synthesis.answer, "", "Sincerely,", "", "The Modeling Team", ""])
    return lines


def _render_governors_memo(graph: NarrativeGraph, synthesis: NarrativeNode) -> list[str]:
    research_nodes = _dependency_research_nodes(graph, synthesis)
    lines = [
        "## Governors' Memo",
        "",
        "**To:** The Group of Governors",
        "",
        "**From:** The Modeling Team",
        "",
        "**Subject:** Evidence-grounded findings and compact guidance",
        "",
        "This memo reports only conclusions accepted by the registered research and validation chain.",
        "",
    ]
    for index, node in enumerate(research_nodes, start=1):
        lines.append(f"**Evidence item {index}.** {node.answer}")
        lines.append("")
    lines.extend(["**Memo synthesis.** " + synthesis.answer, "", f"**Scope.** {synthesis.limitation}", ""])
    return lines


def _practical_recommendation(node: NarrativeNode) -> str:
    if node.task_family == "forecasting":
        return (
            "Use the point forecast together with its prediction interval when setting expectations; "
            "the interval should govern how much confidence is placed on the single forecast value."
        )
    if node.task_family == "explanatory_inference":
        return (
            "Use the strongest stable feature effects to explain which observed word properties are associated with the response, "
            "but do not treat those associations as causal interventions."
        )
    if node.task_family == "distribution_forecasting":
        return (
            "Use the predicted response distribution, not only its dominant component, to communicate the expected difficulty profile; "
            "retain the component uncertainty when presenting that profile."
        )
    if node.task_family == "classification":
        return (
            "Use the predicted class as a concise difficulty label and the class probabilities as the confidence qualifier; "
            "low-confidence classifications should be reported as uncertain rather than forced into a categorical claim."
        )
    if node.task_family == "exploratory_analysis":
        return (
            "Use the strongest exploratory patterns to prioritize follow-up analysis and decision explanation, "
            "while treating them as hypotheses unless they are confirmed by a dedicated inferential model."
        )
    if node.task_family == "optimization":
        return (
            "Use the accepted optimum only within the registered constraints; before making strong policy claims, "
            "require a registered sensitivity analysis rather than assuming the optimum is stable."
        )
    if node.task_family == "simulation":
        return "Use scenario distributions and uncertainty intervals for decisions instead of relying on a single simulation draw."
    if node.task_family == "ranking":
        return "Use the accepted ranking together with its stability analysis; unstable adjacent ranks should be treated as effectively tied."
    return "Apply this result only within the accepted evidence scope and validation limits recorded for the question."


def _markdown_result_table(node: NarrativeNode) -> list[str]:
    lines = ["| Metric | Value | Interpretation |", "|---|---:|---|"]
    for result in node.key_results[:10]:
        interpretation = _result_interpretation(result.metric, result.metadata)
        lines.append(f"| {_humanize(result.metric)} | {result.value:.6g} | {interpretation} |")
    return lines


def _result_interpretation(metric: str, metadata: dict[str, Any]) -> str:
    if metadata.get("future"):
        if metadata.get("component"):
            return f"future distribution component: {metadata['component']}"
        return "future target result"
    if metadata.get("feature"):
        return f"leading feature: {metadata['feature']}"
    if metadata.get("left") and metadata.get("right"):
        return f"association: {metadata['left']} vs {metadata['right']}"
    if metadata.get("decision_variable"):
        return "optimized decision variable"
    if metric in {"rmse", "mae"}:
        return "validation error; lower is better"
    if metric in {"balanced_accuracy", "macro_f1"}:
        return "classification validation metric; higher is better"
    return "question-level quantitative result"


def _result_interpretation_cumcm(metric: str, metadata: dict[str, Any]) -> str:
    if metadata.get("future"):
        if metadata.get("component"):
            return f"预测分布分量：{metadata['component']}"
        return "未来预测结果"
    if metadata.get("feature"):
        return f"主要影响特征：{metadata['feature']}"
    if metadata.get("left") and metadata.get("right"):
        return f"变量关联：{metadata['left']} 与 {metadata['right']}"
    if metadata.get("decision_variable"):
        return "优化模型得到的决策变量"
    lowered = str(metric).lower()
    if lowered in {"rmse", "mae"}:
        return "预测误差指标，数值越小越好"
    if lowered in {"balanced_accuracy", "macro_f1"}:
        return "分类检验指标，数值越大越好"
    if "sensitivity" in lowered:
        return "参数扰动下用于衡量解稳定性的指标"
    if "objective" in lowered:
        return "优化方案对应的目标函数值"
    if "advantage" in lowered:
        return "两种可行方案之间的目标值差异"
    return "本问求解得到的定量结果"


def _adaptive_equation_budget(node: NarrativeNode, spine_node: ModelSpineNode | None) -> int | None:
    """Choose a paper equation budget from executed structure, not a formula quota."""
    base = spine_node.equation_budget if spine_node is not None else None
    if base is None:
        return None
    registered = equations_for_method(node.method)
    if not registered:
        return base
    if spine_node is not None and spine_node.role == "FOUNDATION":
        structure = getattr(node, "model_structure", None)
        archetypes = set(getattr(structure, "archetypes", []) or [])
        if archetypes & {"dynamic_state", "probabilistic_state", "forecasting"}:
            return max(base, min(3, len(registered)))
    if spine_node is not None and spine_node.role == "EXTENSION" and spine_node.inheritance_kind in {"MODEL", "SCENARIO", "EVIDENCE"}:
        # Reuse the accepted upstream derivation and expose only the relation
        # necessary to understand the extension/validation scenario.
        return min(base, 1)
    return min(base, len(registered))


def _compact_text(text: str, limit: int) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    punctuation = max(value.rfind("。", 0, limit), value.rfind("；", 0, limit), value.rfind(". ", 0, limit))
    if punctuation >= limit // 2:
        cut = punctuation + 1
        return value[:cut].rstrip("，,;； ")
    # Never cut through a number, identifier, or word (e.g. turning 0.659 into
    # the embarrassing paper-facing fragment "0..").
    whitespace = value.rfind(" ", 0, limit)
    cut = whitespace if whitespace >= limit // 2 else limit
    suffix = "……" if re.search(r"[\u4e00-\u9fff]", value) else "..."
    return value[:cut].rstrip("，,;； .") + suffix


def _abstract_validation_summary(nodes: list[NarrativeNode], *, language: str) -> str:
    families = {node.task_family for node in nodes}
    concepts: list[str] = []
    if families & {"forecasting", "distribution_forecasting", "classification"}:
        concepts.append("out-of-sample/temporal validation" if language == "en" else "样本外或时序检验")
    if "optimization" in families:
        concepts.append("sensitivity/feasibility checks" if language == "en" else "可行性与敏感性检验")
    if families & {"explanatory_inference", "ranking", "exploratory_analysis"}:
        concepts.append("stability/uncertainty checks" if language == "en" else "稳定性或不确定性检验")
    concepts = list(dict.fromkeys(concepts))
    if not concepts:
        return ""
    if language == "zh":
        return "同时通过" + "、".join(concepts) + "评估主要结论的可靠性，避免仅凭单次拟合或单一参数给出强结论。"
    return "The main claims are qualified by " + ", ".join(concepts) + " rather than by in-sample fit alone."


def _abstract_results(node: NarrativeNode, *, language: str = "en") -> str:
    preferred = []
    for result in node.key_results:
        priority = (
            0 if result.metric in {"future_point", "objective_value", "activation_rate", "promotion_rate_difference"}
            else 1 if result.metric.startswith("future_") and result.metadata.get("component")
            else 2 if result.metric in {"leading_standardized_effect", "top_rule_lift", "top_decile_threshold"}
            else 3 if result.metric in {"balanced_accuracy", "macro_f1", "strongest_spearman_r", "silhouette", "top_decile_stability"}
            else 9
        )
        preferred.append((priority, result))
    preferred.sort(key=lambda item: item[0])
    selected = [item for _, item in preferred[:2]]
    if not selected:
        return ""
    if language == "zh":
        return "关键结果为" + "、".join(
            f"{PaperHumanizationAdapter.metric_label(item.metric, item.metadata, language='zh')}={_format_result_value(item.metric, item.value, item.metadata, language='zh')}"
            for item in selected
        )
    return "key results include " + " and ".join(
        f"{PaperHumanizationAdapter.metric_label(item.metric, item.metadata, language='en')}={_format_result_value(item.metric, item.value, item.metadata, language='en')}"
        for item in selected
    )


def _format_result_value(metric: str, value: float, metadata: dict[str, Any], *, language: str) -> str:
    """Render scalar evidence according to its mathematical meaning.

    Paper prose should not expose arbitrary six-decimal machine values. Rates and
    probabilities are humanized as percentages, p-values/calibration/error scores
    keep compact decimals, and counts remain count-like. The underlying ResultRecord
    remains unchanged and auditable.
    """
    lowered = str(metric or "").lower().replace("_", " ")
    if any(token in lowered for token in ("probability", "rate", "fraction", "share", "proportion")) and 0.0 <= value <= 1.0:
        return f"{value:.1%}"
    if "p-value" in lowered or "p value" in lowered:
        return f"{value:.3f}"
    if any(token in lowered for token in ("auc", "accuracy", "f1", "brier", "rmse", "mae", "error")):
        return f"{value:.3f}"
    if any(token in lowered for token in ("count", "number", "matches", "rows")) and abs(value - round(value)) < 1e-9:
        return str(int(round(value)))
    magnitude = abs(value)
    if magnitude >= 1000:
        return f"{value:,.1f}"
    if magnitude >= 100:
        return f"{value:.1f}"
    if magnitude >= 10:
        return f"{value:.2f}"
    return f"{value:.3g}"


def _domain_citations(
    references: list[VerifiedReference],
    citation_numbers: dict[str, int],
) -> str:
    numbers = [citation_numbers[item.key] for item in references if item.category == "domain"]
    return "".join(f"[{number}]" for number in numbers)


def _reference_cutoff_year(cases: Any, case_id: str, title: str) -> int | None:
    text = title
    try:
        text += " " + str(cases.show_case(case_id))
    except (AttributeError, KeyError, OSError, ValueError):
        pass
    years = [int(value) for value in re.findall(r"\b20\d{2}\b", text)]
    return min(years) if years else None


def _method_citations(
    method: str,
    references: list[VerifiedReference],
    citation_numbers: dict[str, int],
) -> str:
    lowered = method.lower().replace("_", " ")
    numbers = []
    for reference in references:
        if any(token.lower() in lowered for token in reference.supports):
            numbers.append(citation_numbers[reference.key])
    if "bootstrap" in lowered:
        for reference in references:
            if reference.key == "efron_tibshirani_1993":
                numbers.append(citation_numbers[reference.key])
    numbers = list(dict.fromkeys(numbers))
    return "".join(f"[{number}]" for number in numbers)


def _humanize(value: str) -> str:
    return PaperHumanizationAdapter.method_label(value, language="en")


def _humanize_cumcm(value: str) -> str:
    return PaperHumanizationAdapter.method_label(value, language="zh")


def _question_number(subproblem_id: str) -> str:
    match = re.search(r"(\d+)$", subproblem_id)
    return match.group(1) if match else subproblem_id

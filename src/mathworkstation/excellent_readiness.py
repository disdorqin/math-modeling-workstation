from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .io_utils import atomic_write_json, now_iso
from .solver_engine import SolverRegistry


DimensionStatus = Literal["PASS", "REVIEW", "UNVERIFIED", "BLOCKED"]
ReadinessVerdict = Literal[
    "NOT_READY",
    "PROMISING_INTERNAL_PASS_EXTERNAL_VALIDATION_REQUIRED",
    "VERIFIED_EXCELLENT",
]


class ReadinessDimension(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dimension: str
    status: DimensionStatus
    evidence: str
    gap: str = ""
    repair_type: Literal["DOCUMENT", "RESEARCH", "EXTERNAL"]
    subproblem_ids: list[str] = Field(default_factory=list)


class ExcellentReadinessAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str
    verdict: ReadinessVerdict
    dimensions: list[ReadinessDimension]
    internal_pass: bool
    external_validation_complete: bool
    checked_at: str


class ExcellentReadinessService:
    """Prevent internal green gates from being mislabeled as award-level proof."""

    EMPIRICAL_COMPARISON_FAMILIES = {
        "forecasting",
        "distribution_forecasting",
        "classification",
        "optimization",
        "ranking",
    }

    def __init__(self, solvers: SolverRegistry | None = None) -> None:
        self.solvers = solvers or SolverRegistry()

    def assess(
        self,
        case_id: str,
        *,
        narrative: Any,
        model_graph: Any,
        competition_assessment: Any,
        bibliography_coverage: dict[str, Any],
        corpus_benchmark: Any | None = None,
        c_problem_benchmark: Any | None = None,
        same_problem_full_text_assessment: Any | None = None,
        abstract_quality: Any | None = None,
        visual_quality: Any | None = None,
        paper_quality_benchmark: Any | None = None,
        comparison_subproblem_ids: list[str] | None = None,
        full_text_corpus_available: bool = False,
        blind_human_review_count: int = 0,
        real_paper_gates_passed: int = 1,
    ) -> ExcellentReadinessAssessment:
        dimensions: list[ReadinessDimension] = []
        dimensions.append(
            ReadinessDimension(
                dimension="research_state_closure",
                status="PASS" if narrative.gate == "PASS" else "BLOCKED",
                evidence=(
                    f"Problem/Model/Evidence/Narrative gates = {narrative.research_gate}/"
                    f"{narrative.model_graph_gate}/{narrative.evidence_graph_gate}/{narrative.gate}"
                ),
                gap="" if narrative.gate == "PASS" else "Research State is not fully closed.",
                repair_type="RESEARCH",
            )
        )
        dimensions.append(
            ReadinessDimension(
                dimension="competition_hard_defects",
                status="PASS" if competition_assessment.block_count == 0 else "BLOCKED",
                evidence=f"CompetitionPaperAuditor BLOCK count = {competition_assessment.block_count}",
                gap="" if competition_assessment.block_count == 0 else "Hard paper/research defects remain.",
                repair_type="DOCUMENT",
            )
        )
        extracted_gaps = [
            item for item in competition_assessment.findings
            if item.source == "excellent_c7_extracted_summary_prior"
        ]
        dimensions.append(
            ReadinessDimension(
                dimension="extracted_excellent_summary_alignment",
                status="PASS" if not extracted_gaps else "REVIEW",
                evidence=(
                    f"excellent_c7 extracted-summary gaps = {len(extracted_gaps)}; "
                    f"reference summaries = {competition_assessment.reference_papers_count}"
                ),
                gap="" if not extracted_gaps else "Recurring extracted-summary structure/narrative priors remain unmatched.",
                repair_type="DOCUMENT",
            )
        )
        if corpus_benchmark is not None:
            document_gaps = [
                item for item in corpus_benchmark.gaps
                if item.status == "GAP" and item.repair_type == "DOCUMENT"
            ]
            research_gaps = [
                item for item in corpus_benchmark.gaps
                if item.status == "GAP" and item.repair_type == "RESEARCH"
            ]
            dimensions.append(
                ReadinessDimension(
                    dimension="structured_corpus_document_alignment",
                    status="PASS" if not document_gaps else "REVIEW",
                    evidence=(
                        f"structured extracted-corpus document gaps = {[item.aspect for item in document_gaps] or 'none'}"
                    ),
                    gap=(
                        ""
                        if not document_gaps
                        else "Paper Engine still misses recurring excellent-paper document/communication patterns."
                    ),
                    repair_type="DOCUMENT",
                )
            )
            dimensions.append(
                ReadinessDimension(
                    dimension="structured_corpus_research_alignment",
                    status="PASS" if not research_gaps else "REVIEW",
                    evidence=(
                        f"structured extracted-corpus research gaps = {[item.aspect for item in research_gaps] or 'none'}"
                    ),
                    gap=(
                        ""
                        if not research_gaps
                        else "Recurring excellent-paper pattern requires upstream research evidence; do not patch it with prose."
                    ),
                    repair_type="RESEARCH",
                    subproblem_ids=sorted(
                        {
                            subproblem_id
                            for item in research_gaps
                            for subproblem_id in item.subproblem_ids
                            if subproblem_id
                        }
                    ),
                )
            )

        if same_problem_full_text_assessment is not None:
            same_document_gaps = [
                item for item in same_problem_full_text_assessment.gaps
                if item.defect_type == "DOCUMENT"
            ]
            same_research_gaps = [
                item for item in same_problem_full_text_assessment.gaps
                if item.defect_type == "RESEARCH"
            ]
            dimensions.append(
                ReadinessDimension(
                    dimension="same_problem_fulltext_document_alignment",
                    status="PASS" if not same_document_gaps else "REVIEW",
                    evidence=(
                        "same-problem full-text document gaps = "
                        + str([item.dimension for item in same_document_gaps] or "none")
                    ),
                    gap=(
                        ""
                        if not same_document_gaps
                        else "Same-problem O-award papers expose recurring competition-document patterns that the current draft still misses."
                    ),
                    repair_type="DOCUMENT",
                )
            )
            dimensions.append(
                ReadinessDimension(
                    dimension="same_problem_fulltext_research_alignment",
                    status="PASS" if not same_research_gaps else "REVIEW",
                    evidence=(
                        "same-problem full-text research gaps = "
                        + str([item.dimension for item in same_research_gaps] or "none")
                    ),
                    gap=(
                        ""
                        if not same_research_gaps
                        else "Same-problem O-award calibration indicates upstream research-depth gaps; these must be repaired before prose polish can claim competition parity."
                    ),
                    repair_type="RESEARCH",
                    subproblem_ids=sorted(
                        {
                            subproblem_id
                            for item in same_research_gaps
                            for subproblem_id in item.subproblem_ids
                            if subproblem_id
                        }
                    ),
                )
            )

        compared_subproblems = {str(value) for value in (comparison_subproblem_ids or [])}
        executable_comparison: list[str] = []
        solver_depth_gap: list[str] = []
        for node in narrative.nodes:
            if node.role != "RESEARCH" or node.task_family not in self.EMPIRICAL_COMPARISON_FAMILIES:
                continue
            pass_methods = {
                item.method
                for item in node.candidate_considerations
                if item.feasibility == "PASS"
                and bool(getattr(item, "comparison_compatible", False))
                and not item.selected
                and not _method_equivalent(item.method, node.method)
            }
            unavailable_methods = {
                item.method
                for item in node.candidate_considerations
                if item.feasibility == "NEEDS_SOLVER"
                and bool(getattr(item, "comparison_compatible", False))
                and not _method_equivalent(item.method, node.method)
            }
            # Do not promote generic ProblemGraph candidate labels to executable
            # alternatives merely because an alias exists in SolverRegistry.
            # A head-to-head obligation requires an explicit ModelingBrain/solver
            # feasibility decision (PASS or NEEDS_SOLVER) with a compatible plan.
            pass_alternatives = sorted(pass_methods)
            unavailable_alternatives = sorted(unavailable_methods)
            if pass_alternatives and node.subproblem_id not in compared_subproblems:
                executable_comparison.append(node.subproblem_id)
            if unavailable_alternatives:
                solver_depth_gap.append(node.subproblem_id)

        dimensions.append(
            ReadinessDimension(
                dimension="empirical_alternative_comparison",
                status="REVIEW" if executable_comparison else "PASS",
                evidence=(
                    "At least one distinct PASS alternative is solver-available and semantically comparable, but no head-to-head accepted comparison is recorded "
                    f"for {executable_comparison}."
                    if executable_comparison
                    else "No distinct solver-available, semantically comparable alternative is currently waiting for a head-to-head experiment."
                ),
                gap=(
                    "Compare the already-executable alternatives under the same validation protocol; do not invent comparison metrics in the paper."
                    if executable_comparison
                    else ""
                ),
                repair_type="RESEARCH",
                subproblem_ids=executable_comparison,
            )
        )
        dimensions.append(
            ReadinessDimension(
                dimension="alternative_solver_depth",
                status="REVIEW" if solver_depth_gap else "PASS",
                evidence=(
                    f"Potentially relevant alternatives require missing SolverPlugins for {solver_depth_gap}."
                    if solver_depth_gap
                    else "No high-priority missing-solver alternative detected from the current ModelingBrain candidates."
                ),
                gap=(
                    "Add a dedicated alternative solver only where the expected modeling insight justifies the implementation cost; "
                    "this is not resolved by rerunning the current accepted solver."
                    if solver_depth_gap
                    else ""
                ),
                repair_type="RESEARCH",
                subproblem_ids=solver_depth_gap,
            )
        )

        method_gaps = [str(value) for value in bibliography_coverage.get("method_gaps", [])]
        dimensions.append(
            ReadinessDimension(
                dimension="method_bibliography_coverage",
                status="PASS" if not method_gaps else "REVIEW",
                evidence=f"method reference gaps = {method_gaps or 'none'}",
                gap="" if not method_gaps else "Executed methods need verified bibliographic support.",
                repair_type="DOCUMENT",
                subproblem_ids=method_gaps,
            )
        )
        domain_count = int(bibliography_coverage.get("domain_reference_count", 0))
        dimensions.append(
            ReadinessDimension(
                dimension="domain_bibliography_coverage",
                status="PASS" if domain_count >= 2 else "REVIEW",
                evidence=f"verified domain references = {domain_count}",
                gap="" if domain_count >= 2 else "Domain/background literature remains thin.",
                repair_type="DOCUMENT",
            )
        )

        if abstract_quality is not None:
            abstract_gaps = [
                item.dimension
                for item in getattr(abstract_quality, "dimensions", [])
                if getattr(item, "status", "") != "PASS"
            ]
            dimensions.append(
                ReadinessDimension(
                    dimension="abstract_competition_quality",
                    status="PASS" if getattr(abstract_quality, "gate", "REVIEW") == "PASS" else "REVIEW",
                    evidence=(
                        f"AbstractQuality gate={getattr(abstract_quality, 'gate', 'UNKNOWN')}; "
                        f"score={getattr(abstract_quality, 'score', 'UNKNOWN')}; gaps={abstract_gaps or 'none'}"
                    ),
                    gap=(
                        ""
                        if getattr(abstract_quality, "gate", "REVIEW") == "PASS"
                        else "Abstract still misses one or more competition-facing qualities; repair only with already-supported methods, results, and validation evidence."
                    ),
                    repair_type="DOCUMENT",
                )
            )

        if visual_quality is not None:
            visual_gaps = [
                item.dimension
                for item in getattr(visual_quality, "dimensions", [])
                if getattr(item, "status", "") != "PASS"
            ]
            dimensions.append(
                ReadinessDimension(
                    dimension="visual_argument_quality",
                    status="PASS" if getattr(visual_quality, "gate", "REVIEW") == "PASS" else "REVIEW",
                    evidence=(
                        f"VisualQuality gate={getattr(visual_quality, 'gate', 'UNKNOWN')}; "
                        f"score={getattr(visual_quality, 'score', 'UNKNOWN')}; gaps={visual_gaps or 'none'}"
                    ),
                    gap=(
                        ""
                        if getattr(visual_quality, "gate", "REVIEW") == "PASS"
                        else "The paper's visual argument is incomplete or repetitive; add or revise only evidence-bearing figures and editable diagram sources."
                    ),
                    repair_type="DOCUMENT",
                )
            )

        if paper_quality_benchmark is not None:
            benchmark_gaps = [
                item.dimension
                for item in getattr(paper_quality_benchmark, "dimensions", [])
                if getattr(item, "status", "") != "PASS"
            ]
            dimensions.append(
                ReadinessDimension(
                    dimension="excellent_c_document_density_calibration",
                    status="PASS" if getattr(paper_quality_benchmark, "gate", "REVIEW") == "PASS" else "REVIEW",
                    evidence=(
                        f"Excellent-C document benchmark gate={getattr(paper_quality_benchmark, 'gate', 'UNKNOWN')}; "
                        f"score={getattr(paper_quality_benchmark, 'score', 'UNKNOWN')}; gaps={benchmark_gaps or 'none'}; "
                        f"source corpora={getattr(paper_quality_benchmark, 'source_corpora', [])}"
                    ),
                    gap=(
                        ""
                        if getattr(paper_quality_benchmark, "gate", "REVIEW") == "PASS"
                        else "The draft remains materially thinner or denser than the excellent C-paper corpus on one or more communication dimensions; close only evidence-backed gaps, never pad counts."
                    ),
                    repair_type="DOCUMENT",
                )
            )
        c_only_fulltext_ready = False
        c_only_evidence = ""
        if c_problem_benchmark is not None:
            status_map = dict(getattr(c_problem_benchmark, "benchmark_status", {}) or {})
            c_only_fulltext_ready = str(status_map.get("fulltext_text_layer", "")).upper() == "PASS"
            corpora = list(getattr(c_problem_benchmark, "corpora", []) or [])
            paper_count = int(getattr(c_problem_benchmark, "total_reference_papers", 0) or 0)
            c_only_evidence = (
                f"C-only benchmark registry: {len(corpora)} C-problem corpora / {paper_count} excellent papers; "
                f"fulltext_text_layer={status_map.get('fulltext_text_layer', 'UNVERIFIED')}; "
                f"pdf_visual_layout={status_map.get('pdf_visual_layout', 'UNVERIFIED')}"
            )
        fulltext_truth = c_only_fulltext_ready or (c_problem_benchmark is None and full_text_corpus_available)
        dimensions.append(
            ReadinessDimension(
                dimension="full_text_excellent_paper_benchmark",
                status="PASS" if fulltext_truth else "UNVERIFIED",
                evidence=(
                    c_only_evidence
                    if c_problem_benchmark is not None
                    else (
                        "same-problem full-text corpus is available for text/structure calibration; visual page/layout verification remains separate"
                        if full_text_corpus_available
                        else "no validated C-only full-text benchmark registry was supplied"
                    )
                ),
                gap=(
                    ""
                    if fulltext_truth
                    else "Validate the C-only excellent-paper full-text text layer before using this dimension as readiness evidence."
                ),
                repair_type="EXTERNAL",
            )
        )
        dimensions.append(
            ReadinessDimension(
                dimension="blind_human_competition_review",
                status="PASS" if blind_human_review_count > 0 else "UNVERIFIED",
                evidence=f"blind/human competition reviews completed = {blind_human_review_count}",
                gap="" if blind_human_review_count > 0 else "No independent human/blind competition review has validated the current draft.",
                repair_type="EXTERNAL",
            )
        )
        dimensions.append(
            ReadinessDimension(
                dimension="cross_problem_generalization",
                status="PASS" if real_paper_gates_passed >= 2 else "REVIEW",
                evidence=f"historical real-problem Paper Engine gates passed = {real_paper_gates_passed}",
                gap="" if real_paper_gates_passed >= 2 else "Fewer than two different-family historical problems have passed the full Paper Engine Gate.",
                repair_type="RESEARCH",
            )
        )

        internal_block = any(
            item.status == "BLOCKED" and item.repair_type != "EXTERNAL"
            for item in dimensions
        )
        internal_pass = not internal_block
        external_complete = all(
            item.status == "PASS" for item in dimensions if item.repair_type == "EXTERNAL"
        )
        if internal_block:
            verdict: ReadinessVerdict = "NOT_READY"
        elif external_complete and all(item.status == "PASS" for item in dimensions):
            verdict = "VERIFIED_EXCELLENT"
        else:
            verdict = "PROMISING_INTERNAL_PASS_EXTERNAL_VALIDATION_REQUIRED"
        return ExcellentReadinessAssessment(
            case_id=case_id,
            verdict=verdict,
            dimensions=dimensions,
            internal_pass=internal_pass,
            external_validation_complete=external_complete,
            checked_at=now_iso(),
        )

    def persist(
        self,
        cases: Any,
        artifacts: Any,
        case_id: str,
        assessment: ExcellentReadinessAssessment,
        *,
        source_artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        root = cases.case_root(case_id)
        path = root / "review" / "competition" / "excellent_readiness.json"
        atomic_write_json(path, assessment.model_dump(mode="json"))
        artifact = artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "excellent_readiness_assessment",
            "excellent_readiness",
            upstream=list(source_artifact_ids or []),
            paper_eligible=False,
        )
        return {"assessment": assessment, "artifact": artifact}


def _method_equivalent(left: str, right: str) -> bool:
    def normalize(value: str) -> str:
        return " ".join(value.lower().replace("_", " ").replace("-", " ").split())

    left_value = normalize(left)
    right_value = normalize(right)
    if not left_value or not right_value:
        return False
    left_compact = left_value.replace(" ", "")
    right_compact = right_value.replace(" ", "")
    return (
        left_value == right_value
        or left_value in right_value
        or right_value in left_value
        or left_compact == right_compact
        or left_compact in right_compact
        or right_compact in left_compact
    )

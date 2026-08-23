from pathlib import Path

import pandas as pd

from mathworkstation.access_policy import DEFAULT_NODE_POLICIES
from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.auto_pipeline import AutoPipelineService
from mathworkstation.case_manager import CaseManager
from mathworkstation.claims import ClaimRegistry
from mathworkstation.competition_paper_auditor import CompetitionPaperAuditor
from mathworkstation.datasets import DatasetRegistry
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.io_utils import atomic_write_json
from mathworkstation.llm.prompts import PromptRegistry
from mathworkstation.evidence_locked_writer import EvidenceLockedWriterService
from mathworkstation.narrative_graph import NarrativeGraphService
from mathworkstation.paper_contracts import PaperContractService, SubproblemContract
from mathworkstation.problem_graph import ProblemGraphService
from mathworkstation.research_state_paper import ResearchStatePaperService
from mathworkstation.subproblem_engine import SubproblemEngineService
from mathworkstation.subproblem_paper_bridge import SubproblemPaperEvidenceBridge
from mathworkstation.wordle_2023_gate import prepare_wordle_2023_research


CASE_ROOT = Path("output/mcm-c-2023/v3/20260805-MCM-0001-EUP7")


def _contracts() -> list[SubproblemContract]:
    return [
        SubproblemContract.model_validate_json(line)
        for line in (CASE_ROOT / "results/contracts/subproblems.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _service(tmp_path: Path):
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "2023 Wordle research-state paper Gate")
    case_id = case["case_id"]
    artifacts = ArtifactRegistry(cases)
    source = artifacts.ingest_file(
        case_id,
        CASE_ROOT / "input/data/uploaded/_wordle_data_clean.csv",
        "input/data/uploaded",
        "observed_data",
    )
    contracts = PaperContractService(cases, artifacts)
    contracts.persist_subproblems(case_id, _contracts())
    graphs = ProblemGraphService(cases, artifacts)
    graphs.persist(case_id, contracts.list_subproblems(case_id), [source["artifact_id"]])
    claims = ClaimRegistry(cases, artifacts, DatasetRegistry(cases, artifacts))
    figures = FigureRegistry(cases, artifacts)
    engine = SubproblemEngineService(cases, artifacts, graphs)
    bridge = SubproblemPaperEvidenceBridge(cases, artifacts, contracts, claims, figures)
    data, plans = prepare_wordle_2023_research(
        pd.read_csv(CASE_ROOT / "input/data/uploaded/_wordle_data_clean.csv")
    )
    for subproblem_id in ("SP1", "SP2", "SP3", "SP4", "SP5"):
        execution = engine.execute_node(
            case_id,
            subproblem_id,
            plans[subproblem_id],
            frame=data,
            source_artifact_ids=[source["artifact_id"]],
        )
        bridge.project(case_id, subproblem_id, execution)
    synthesis = engine.complete_synthesis(
        case_id,
        "SP6",
        "The editor letter synthesizes only the accepted findings from Questions 1 through 5 and introduces no new numerical evidence.",
    )
    bridge.project_synthesis(case_id, "SP6", synthesis)
    assert bridge.activate_if_complete(case_id, generation=1)
    narrative = NarrativeGraphService(cases, artifacts, contracts, claims, figures, graphs)
    auditor = CompetitionPaperAuditor()
    service = ResearchStatePaperService(cases, artifacts, contracts, figures, narrative, auditor)
    return cases, artifacts, narrative, auditor, service, case_id


def test_new_wordle_paper_removes_old_blocking_pollution(tmp_path: Path) -> None:
    cases, artifacts, narrative_service, auditor, service, case_id = _service(tmp_path)
    result = service.generate(case_id, "A Research-State Analysis of Wordle", competition="MCM")
    text = result["paper_text"]
    assessment = result["assessment"]
    codes = {item.code for item in assessment.findings}

    blocking = [
        (item.code, item.message, item.source)
        for item in assessment.findings
        if item.severity == "BLOCK"
    ]
    assert assessment.gate in {"PASS", "REVIEW"}, blocking
    assert assessment.block_count == 0
    assert "INTERNAL_REGISTRY_ID_LEAK" not in codes
    assert "FOREIGN_ENERGY_UNIT_POLLUTION" not in codes
    assert "FOREIGN_CURRENCY_UNIT_POLLUTION" not in codes
    assert "REFERENCE_PLACEHOLDER_FORBIDDEN" not in codes
    assert "VERIFIED_REFERENCES_MISSING" not in codes
    assert len(result["references"]) >= 3
    assert all(f"Question {index}" in text for index in range(1, 7))
    assert "2023-03-01" in text
    assert "logistic regression" in text
    assert "multioutput ridge with simplex projection" in text
    assert "A_t" not in text and "B_t" not in text
    for prefix in ("artifact-", "result-", "table-", "claim-", "figure-"):
        assert prefix not in text
    assert artifacts.verify(case_id)["valid"]


def test_same_auditor_scores_new_wordle_draft_better_than_old_baseline(tmp_path: Path) -> None:
    _cases, _artifacts, narrative_service, auditor, service, case_id = _service(tmp_path)
    new_result = service.generate(case_id, "A Research-State Analysis of Wordle")
    narrative = new_result["narrative"]["graph"]
    old_text = (CASE_ROOT / "paper/final.md").read_text(encoding="utf-8")
    old_assessment = auditor.audit(old_text, narrative)
    new_assessment = new_result["assessment"]

    assert old_assessment.gate == "BLOCK"
    assert new_assessment.gate in {"PASS", "REVIEW"}
    assert new_assessment.block_count < old_assessment.block_count
    assert new_assessment.document_defects < old_assessment.document_defects


def test_auto_pipeline_exposes_research_state_paper_entrypoint(tmp_path: Path) -> None:
    cases, _artifacts, _narrative, _auditor, _service_obj, case_id = _service(tmp_path)
    auto = AutoPipelineService(cases, None, coherence=False)  # type: ignore[arg-type]

    result = auto.generate_research_state_paper(case_id, "A Research-State Analysis of Wordle")

    assert result["assessment"].block_count == 0
    assert result["paper_artifact"]["artifact_type"] == "research_state_paper_draft"
    assert result["assessment_artifact"]["artifact_type"] == "competition_paper_assessment"


def test_wordle_same_problem_fulltext_gap_closes_after_real_sp1_stress_comparison(tmp_path: Path) -> None:
    cases, artifacts, _narrative, _auditor, service_obj, case_id = _service(tmp_path)
    auto = AutoPipelineService(cases, None, coherence=False)  # type: ignore[arg-type]
    frame, plans = prepare_wordle_2023_research(
        pd.read_csv(CASE_ROOT / "input/data/uploaded/_wordle_data_clean.csv")
    )
    source_id = next(
        item["artifact_id"]
        for item in auto.artifacts.list_artifacts(case_id)
        if item["artifact_type"] == "observed_data" and item["status"] == "ACTIVE"
    )

    comparison = auto.compare_subproblem_alternatives(
        case_id,
        "SP1",
        [
            {**plans["SP1"], "solver_method": "ridge_time_trend"},
            {**plans["SP1"], "solver_method": "popularity_lifecycle"},
        ],
        frame=frame,
        source_artifact_ids=[source_id],
        stress_test_sizes=[0.15, 0.20, 0.25, 0.30],
    )
    assert comparison["comparison"].decision == "KEEP_ACCEPTED"
    assert comparison["comparison"].accepted.solver == "gold.holt_exponential_smoothing"

    result = auto.generate_research_state_paper(case_id, "A Research-State Analysis of Wordle")
    same_problem = result["same_problem_full_text_assessment"]
    dimensions = {item.dimension: item for item in result["excellent_readiness"].dimensions}

    assert same_problem.document_gaps == 0
    assert same_problem.research_gaps == 0
    assert same_problem.gate == "PASS"
    assert dimensions["same_problem_fulltext_document_alignment"].status == "PASS"
    assert dimensions["same_problem_fulltext_research_alignment"].status == "PASS"
    assert dimensions["empirical_alternative_comparison"].status == "PASS"
    assert "popularity lifecycle" in result["paper_text"].lower()
    assert "temporal robustness was stress-tested" in result["paper_text"].lower()
    comparison_figures = [
        item
        for item in service_obj.figures.list_figures(case_id)
        if item.get("status") == "FINAL"
        and (item.get("parameters") or {}).get("subproblem_id") == "SP1"
    ]
    semantic_kinds = {
        str((item.get("parameters") or {}).get("semantic_kind") or "")
        for item in comparison_figures
    }
    assert "alternative_model_metric_comparison" in semantic_kinds
    assert "alternative_model_stress_comparison" in semantic_kinds
    assert "Executed alternative-model comparison on rmse" in result["paper_text"]
    assert "Model robustness across validation test sizes (rmse)" in result["paper_text"]
    assert artifacts.verify(case_id)["valid"]


def test_new_wordle_draft_exposes_no_unexplained_excellent_summary_gap(tmp_path: Path) -> None:
    _cases, _artifacts, _narrative, _auditor, service, case_id = _service(tmp_path)
    assessment = service.generate(case_id, "A Research-State Analysis of Wordle")["assessment"]
    review_codes = {
        item.code
        for item in assessment.findings
        if item.severity == "REVIEW" and item.source == "excellent_c7_extracted_summary_prior"
    }

    review_details = [
        (item.code, item.message)
        for item in assessment.findings
        if item.severity == "REVIEW" and item.source == "excellent_c7_extracted_summary_prior"
    ]
    assert not review_codes, review_details
    remaining_reviews = [
        (item.code, item.message, item.source)
        for item in assessment.findings
        if item.severity == "REVIEW"
    ]
    assert assessment.review_count == 0, remaining_reviews


def test_real_wordle_figures_have_question_specific_semantic_purpose(tmp_path: Path) -> None:
    _cases, _artifacts, _narrative, _auditor, service, case_id = _service(tmp_path)
    service.generate(case_id, "A Research-State Analysis of Wordle")
    figures = service.figures.list_figures(case_id)
    by_sp = {
        str((item.get("parameters") or {}).get("subproblem_id")): item
        for item in figures
        if (item.get("parameters") or {}).get("subproblem_id")
    }

    assert (by_sp["SP1"]["parameters"]["semantic_kind"] == "forecast_interval")
    assert (by_sp["SP2"]["parameters"]["semantic_kind"] == "effect_intervals")
    assert (by_sp["SP3"]["parameters"]["semantic_kind"] == "distribution_uncertainty")
    assert (by_sp["SP4"]["parameters"]["semantic_kind"] == "class_probabilities")
    assert (by_sp["SP5"]["parameters"]["semantic_kind"] == "association_ranking")
    assert all(item["parameters"].get("purpose") for item in by_sp.values())
    assert not any(item["parameters"]["semantic_kind"] == "metric_summary_fallback" for item in by_sp.values())


def test_wordle_excellent_readiness_never_confuses_internal_green_with_award_proof(tmp_path: Path) -> None:
    _cases, _artifacts, _narrative, _auditor, service, case_id = _service(tmp_path)
    result = service.generate(case_id, "A Research-State Analysis of Wordle")
    readiness = result["excellent_readiness"]
    dimensions = {item.dimension: item for item in readiness.dimensions}

    assert readiness.internal_pass is True
    assert readiness.external_validation_complete is False
    assert readiness.verdict == "PROMISING_INTERNAL_PASS_EXTERNAL_VALIDATION_REQUIRED"
    assert dimensions["research_state_closure"].status == "PASS"
    assert dimensions["competition_hard_defects"].status == "PASS"
    assert dimensions["method_bibliography_coverage"].status == "PASS"
    assert dimensions["domain_bibliography_coverage"].status == "PASS"
    assert dimensions["full_text_excellent_paper_benchmark"].status == "PASS"
    assert dimensions["same_problem_fulltext_document_alignment"].status == "PASS"
    assert dimensions["same_problem_fulltext_research_alignment"].status == "REVIEW"
    assert dimensions["same_problem_fulltext_research_alignment"].subproblem_ids == ["SP1"]
    assert dimensions["blind_human_competition_review"].status == "UNVERIFIED"
    assert dimensions["cross_problem_generalization"].status == "PASS"
    assert dimensions["empirical_alternative_comparison"].status == "PASS"
    assert dimensions["empirical_alternative_comparison"].subproblem_ids == []
    assert dimensions["alternative_solver_depth"].status == "PASS"
    assert dimensions["alternative_solver_depth"].subproblem_ids == []
    assert result["excellent_readiness_artifact"]["artifact_type"] == "excellent_readiness_assessment"


def test_wordle_bibliography_has_precontest_domain_sources_and_method_sources(tmp_path: Path) -> None:
    _cases, _artifacts, _narrative, _auditor, service, case_id = _service(tmp_path)
    result = service.generate(case_id, "A Research-State Analysis of Wordle")
    references = result["references"]

    assert sum(item.category == "domain" for item in references) >= 3
    assert sum(item.category == "method" for item in references) >= 3
    assert all(item.available_year <= 2023 for item in references)
    assert result["bibliography_coverage"]["gate"] == "PASS"
    assert result["bibliography_coverage"]["method_gaps"] == []
    assert all(result["bibliography_coverage"]["method_reference_keys"][f"SP{i}"] for i in range(1, 6))
    assert "arXiv:2205.11225" in result["paper_text"]
    assert "used only for context" in result["paper_text"]


def test_evidence_locked_writer_accepts_prose_only_change(tmp_path: Path) -> None:
    cases, artifacts, _narrative, auditor, service, case_id = _service(tmp_path)
    canonical = service.generate(case_id, "A Research-State Analysis of Wordle")
    writer = EvidenceLockedWriterService(auditor)
    candidate = canonical["paper_text"].replace(
        "The following recommendations translate the accepted question-level evidence into practical use.",
        "The recommendations below translate the accepted question-level evidence into practical use.",
        1,
    )

    result = writer.accept_and_persist(
        cases,
        artifacts,
        case_id,
        canonical["paper_artifact"]["artifact_id"],
        candidate,
        canonical["narrative"]["graph"],
    )

    assert result["accepted"] is True
    assert result["assessment"].gate == "PASS"
    assert result["paper_artifact"]["artifact_type"] == "research_state_paper_polished"


def test_evidence_locked_writer_blocks_new_number_model_equation_and_reference(tmp_path: Path) -> None:
    _cases, _artifacts, _narrative, auditor, service, case_id = _service(tmp_path)
    canonical = service.generate(case_id, "A Research-State Analysis of Wordle")
    writer = EvidenceLockedWriterService(auditor)
    text = canonical["paper_text"]
    candidate = (
        text
        + "\nWe additionally obtain a score of 9999 using XGBoost.\n"
        + "$$z=9999x$$\n"
        + "[99] Invented Author. Invented source. 2099.\n"
    )

    assessment, _competition = writer.validate(
        text,
        candidate,
        canonical["narrative"]["graph"],
        case_id=case_id,
    )
    codes = {item.code for item in assessment.findings}

    assert assessment.gate == "BLOCK"
    assert "WRITER_ADDED_NUMERIC_FACT" in codes
    assert "WRITER_ADDED_MODEL_FAMILY" in codes
    assert "WRITER_ADDED_EQUATION" in codes
    assert "WRITER_CHANGED_BIBLIOGRAPHY" in codes


def test_evidence_locked_writer_blocks_internal_id_and_dropped_question(tmp_path: Path) -> None:
    _cases, _artifacts, _narrative, auditor, service, case_id = _service(tmp_path)
    canonical = service.generate(case_id, "A Research-State Analysis of Wordle")
    writer = EvidenceLockedWriterService(auditor)
    candidate = canonical["paper_text"].replace("Question 6", "Final deliverable")
    candidate += "\nInternal trace artifact-deadbeef.\n"

    assessment, _competition = writer.validate(
        canonical["paper_text"],
        candidate,
        canonical["narrative"]["graph"],
        case_id=case_id,
    )
    codes = {item.code for item in assessment.findings}

    assert assessment.gate == "BLOCK"
    assert "WRITER_INTERNAL_ID_LEAK" in codes
    assert "WRITER_DROPPED_SUBPROBLEM" in codes


def test_auto_pipeline_evidence_locked_polish_entrypoint_uses_readable_packet(tmp_path: Path) -> None:
    cases, _artifacts, _narrative, _auditor, _service_obj, case_id = _service(tmp_path)
    auto = AutoPipelineService(cases, None, coherence=False)  # type: ignore[arg-type]
    prompt = PromptRegistry("prompts").load("research_state_paper_writer")
    assert "paper_draft" in prompt.allowed_nodes

    class CanonicalProseFixture:
        def __init__(self, service: AutoPipelineService) -> None:
            self.service = service

        def markdown_call(
            self,
            call_case_id: str,
            session_id: str,
            node_id: str,
            prompt_id: str,
            variables: dict,
            input_artifact_ids: list[str],
            **_kwargs,
        ):
            assert call_case_id == case_id
            assert session_id == "writer-session"
            assert node_id == "paper_draft"
            assert prompt_id == "research_state_paper_writer"
            assert len(input_artifact_ids) == 1
            packet_artifact = self.service.artifacts.get(case_id, input_artifact_ids[0])
            assert packet_artifact["artifact_type"] == "evidence_locked_writer_packet"
            assert DEFAULT_NODE_POLICIES["paper_draft"].can_read(packet_artifact["path"])
            candidate = variables["canonical_paper"].replace(
                "The recommendations below translate",
                "The recommendations that follow translate",
                1,
            )
            root = self.service.cases.case_root(case_id)
            path = root / "sessions" / "writer-session" / "responses" / "fixture-writer.json"
            atomic_write_json(path, {"content": candidate, "fixture": True})
            artifact = self.service.artifacts.register_existing(
                case_id,
                path.relative_to(root).as_posix(),
                "llm_response_fixture",
                "test",
            )
            return candidate, {"artifact_id": artifact["artifact_id"]}

    auto.llm = CanonicalProseFixture(auto)  # type: ignore[assignment]
    result = auto.polish_research_state_paper(
        case_id,
        "writer-session",
        "A Research-State Analysis of Wordle",
    )

    assert result["writer"]["accepted"] is True
    assert result["writer"]["paper_artifact"]["artifact_type"] == "research_state_paper_polished"
    assert result["writer_packet"]["artifact"]["artifact_type"] == "evidence_locked_writer_packet"


def test_paper_equations_are_method_registered_not_generic_templates(tmp_path: Path) -> None:
    _cases, _artifacts, _narrative, _auditor, service, case_id = _service(tmp_path)
    text = service.generate(case_id, "A Research-State Analysis of Wordle")["paper_text"]

    assert "arg\\min" in text
    assert "Simplex projection" in text
    assert "Multiclass logistic probability" in text
    assert "Spearman association" in text
    assert "No equation is emitted" not in text

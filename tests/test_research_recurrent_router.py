from pathlib import Path

import pandas as pd

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.auto_pipeline import AutoPipelineService
from mathworkstation.case_manager import CaseManager
from mathworkstation.claims import ClaimRegistry
from mathworkstation.datasets import DatasetRegistry
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.io_utils import atomic_write_json
from mathworkstation.modeling_brain import CandidateStrategy, ModelingBrainDecision
from mathworkstation.paper_contracts import PaperContractService, SubproblemContract
from mathworkstation.problem_graph import ProblemGraphService
from mathworkstation.recurrent_workstation import (
    WORKSTATION_DOMAINS,
    WorkstationAudit,
    WorkstationFinding,
    WorkstationGlobalAuditor,
    WorkstationRepairRouter,
)
from mathworkstation.solver_engine import SolverEngineService
from mathworkstation.subproblem_engine import SubproblemEngineService
from mathworkstation.subproblem_paper_bridge import SubproblemPaperEvidenceBridge
from mathworkstation.validation_protocol import ValidationAssessment, ValidationFinding, ValidationRunner
from mathworkstation.wordle_2023_gate import prepare_wordle_2023_research


CASE_ROOT = Path("output/mcm-c-2023/v3/20260805-MCM-0001-EUP7")


def _wordle_contracts() -> list[SubproblemContract]:
    return [
        SubproblemContract.model_validate_json(line)
        for line in (CASE_ROOT / "results/contracts/subproblems.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _completed_wordle_research_case(tmp_path: Path):
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "Wordle research recurrent router")
    case_id = case["case_id"]
    artifacts = ArtifactRegistry(cases)
    source = artifacts.ingest_file(
        case_id,
        CASE_ROOT / "input/data/uploaded/_wordle_data_clean.csv",
        "input/data/uploaded",
        "observed_data",
    )
    contracts = PaperContractService(cases, artifacts)
    contracts.persist_subproblems(case_id, _wordle_contracts())
    graphs = ProblemGraphService(cases, artifacts)
    graphs.persist(case_id, contracts.list_subproblems(case_id), [source["artifact_id"]])
    engine = SubproblemEngineService(cases, artifacts, graphs)
    bridge = SubproblemPaperEvidenceBridge(
        cases,
        artifacts,
        contracts,
        ClaimRegistry(cases, artifacts, DatasetRegistry(cases, artifacts)),
        FigureRegistry(cases, artifacts),
    )
    frame, plans = prepare_wordle_2023_research(
        pd.read_csv(CASE_ROOT / "input/data/uploaded/_wordle_data_clean.csv")
    )
    for subproblem_id in ("SP1", "SP2", "SP3", "SP4", "SP5"):
        executed = engine.execute_node(
            case_id,
            subproblem_id,
            plans[subproblem_id],
            frame=frame,
            source_artifact_ids=[source["artifact_id"]],
            answer_text=f"{subproblem_id} accepted real Wordle research answer.",
        )
        bridge.project(case_id, subproblem_id, executed)
    synthesis = engine.complete_synthesis(
        case_id,
        "SP6",
        "Editor letter synthesizes only accepted SP1-SP5 evidence.",
    )
    bridge.project_synthesis(case_id, "SP6", synthesis)
    bridge.activate_if_complete(case_id, generation=0)
    return cases, case_id, artifacts, graphs, engine, bridge, frame, plans


def test_excellent_readiness_empirical_comparison_routes_only_actionable_subproblems(tmp_path: Path) -> None:
    cases, case_id, _artifacts, _graphs, _engine, _bridge, _frame, _plans = _completed_wordle_research_case(tmp_path)
    atomic_write_json(
        cases.case_root(case_id) / "review" / "competition" / "excellent_readiness.json",
        {
            "verdict": "PROMISING_INTERNAL_PASS_EXTERNAL_VALIDATION_REQUIRED",
            "dimensions": [
                {
                    "dimension": "empirical_alternative_comparison",
                    "status": "REVIEW",
                    "repair_type": "RESEARCH",
                    "subproblem_ids": ["SP1", "SP3", "SP4"],
                },
                {
                    "dimension": "cross_problem_generalization",
                    "status": "REVIEW",
                    "repair_type": "RESEARCH",
                    "subproblem_ids": [],
                },
                {
                    "dimension": "full_text_excellent_paper_benchmark",
                    "status": "UNVERIFIED",
                    "repair_type": "EXTERNAL",
                    "subproblem_ids": [],
                },
            ],
        },
    )

    audit = WorkstationGlobalAuditor(cases).audit(case_id)
    readiness = [item for item in audit.findings if item.source == "excellent_readiness"]
    plan = WorkstationRepairRouter().plan(audit, 1)

    assert {item.subproblem_id for item in readiness} == {"SP1", "SP3", "SP4"}
    assert all(item.repair_node == "experiments" and item.repair_phase == "experiment" for item in readiness)
    assert plan.pivot == "experiments"
    assert {target.subproblem_id for target in plan.repair_targets} == {"SP1", "SP3", "SP4"}
    assert not any("cross_problem" in item.code.lower() for item in readiness)


def test_research_data_coverage_block_routes_to_data_registration(tmp_path: Path) -> None:
    cases, case_id, _artifacts, _graphs, _engine, _bridge, _frame, _plans = _completed_wordle_research_case(tmp_path)
    atomic_write_json(
        cases.case_root(case_id) / "review" / "research" / "data_coverage.json",
        {
            "gate": "BLOCK",
            "findings": [
                {
                    "severity": "BLOCK",
                    "code": "MULTI_ENTITY_DATA_COVERAGE_MISSING",
                    "message": "four-state problem has only TX data",
                    "repair_phase": "data_registration",
                }
            ],
        },
    )

    audit = WorkstationGlobalAuditor(cases).audit(case_id)
    issue = next(item for item in audit.findings if item.code == "RESEARCH_DATA_MULTI_ENTITY_DATA_COVERAGE_MISSING")
    plan = WorkstationRepairRouter().plan(audit, 1)

    assert issue.domain == "data"
    assert issue.repair_node == "data_registration"
    assert issue.repair_phase == "data_registration"
    assert plan.pivot == "data_registration"


def test_competition_document_defect_stays_in_paper_cell(tmp_path: Path) -> None:
    cases, case_id, _artifacts, _graphs, _engine, _bridge, _frame, _plans = _completed_wordle_research_case(tmp_path)
    atomic_write_json(
        cases.case_root(case_id) / "review" / "competition" / "paper_assessment.json",
        {
            "gate": "BLOCK",
            "findings": [
                {
                    "defect_type": "DOCUMENT",
                    "severity": "BLOCK",
                    "code": "INTERNAL_REGISTRY_ID_LEAK",
                    "message": "user-visible paper leaked an internal id",
                    "section": "global",
                    "subproblem_id": None,
                    "repair_phase": None,
                }
            ],
        },
    )

    audit = WorkstationGlobalAuditor(cases).audit(case_id)
    issue = next(item for item in audit.findings if item.code == "COMPETITION_INTERNAL_REGISTRY_ID_LEAK")

    assert issue.domain == "paper"
    assert issue.repair_node == "paper_draft"
    assert issue.subproblem_id is None
    assert issue.repair_phase is None


def test_competition_research_defect_returns_to_exact_subproblem_validation(tmp_path: Path) -> None:
    cases, case_id, _artifacts, _graphs, _engine, _bridge, _frame, _plans = _completed_wordle_research_case(tmp_path)
    atomic_write_json(
        cases.case_root(case_id) / "review" / "competition" / "paper_assessment.json",
        {
            "gate": "BLOCK",
            "findings": [
                {
                    "defect_type": "RESEARCH",
                    "severity": "BLOCK",
                    "code": "NARRATIVE_NODE_BLOCKED",
                    "message": "SP3 validation is not accepted",
                    "section": "results",
                    "subproblem_id": "SP3",
                    "repair_phase": "validation",
                }
            ],
        },
    )

    audit = WorkstationGlobalAuditor(cases).audit(case_id)
    issue = next(item for item in audit.findings if item.code == "COMPETITION_NARRATIVE_NODE_BLOCKED")
    plan = WorkstationRepairRouter().plan(audit, 1)

    assert issue.domain == "experiment"
    assert issue.repair_node == "experiments"
    assert issue.subproblem_id == "SP3"
    assert issue.repair_phase == "validation"
    assert plan.pivot == "experiments"
    assert any(target.subproblem_id == "SP3" and target.phase == "validation" for target in plan.repair_targets)


def _write_c_problem_prior_decision(cases: CaseManager, case_id: str, subproblem_id: str, task_family: str) -> None:
    atomic_write_json(
        cases.case_root(case_id) / "analysis" / "modeling_brain" / f"{subproblem_id}.json",
        {
            "schema_version": 1,
            "case_id": case_id,
            "subproblem_id": subproblem_id,
            "task_family": task_family,
            "gate": "PASS",
            "query": "C-problem benchmark prior test",
            "candidates": [],
            "selected_candidate_ids": [],
            "selected_methods": [],
            "skill_advice": [],
            "quality_checks": [],
            "avoidance_rules": [],
            "feasibility_summary": {},
            "c_problem_prior_names": ["validation_matches_claim_type"],
            "research_obligations": ["use problem-specific representation"],
            "benchmark_validation_obligations": ["family-specific validation required"],
            "benchmark_forbidden_shortcuts": ["corpus frequency cannot force a solver"],
            "benchmark_prior_source": "config/ref_models/c_problem_excellent_benchmark_v1.json",
            "generated_at": "2026-08-20T14:00:00+08:00",
        },
    )


def test_c_problem_prior_routes_validation_family_mismatch_to_exact_subproblem(tmp_path: Path) -> None:
    cases, case_id, _artifacts, _graphs, _engine, _bridge, _frame, _plans = _completed_wordle_research_case(tmp_path)
    _write_c_problem_prior_decision(cases, case_id, "SP3", "distribution_forecasting")
    validation_path = cases.case_root(case_id) / "results" / "validation" / "SP3" / "assessment.json"
    payload = __import__("json").loads(validation_path.read_text(encoding="utf-8"))
    payload["family"] = "classification"
    payload["gate"] = "PASS"
    payload["findings"] = []
    atomic_write_json(validation_path, payload)

    audit = WorkstationGlobalAuditor(cases).audit(case_id)
    issue = next(item for item in audit.findings if item.code == "C_PROBLEM_VALIDATION_FAMILY_MISMATCH")
    plan = WorkstationRepairRouter().plan(audit, 1)

    assert issue.source == "c_problem_benchmark"
    assert issue.subproblem_id == "SP3"
    assert issue.repair_phase == "validation"
    assert issue.repair_node == "experiments"
    assert any(target.subproblem_id == "SP3" and target.phase == "validation" for target in plan.repair_targets)


def test_c_problem_prior_adds_no_finding_when_completed_validation_family_matches(tmp_path: Path) -> None:
    cases, case_id, _artifacts, _graphs, _engine, _bridge, _frame, _plans = _completed_wordle_research_case(tmp_path)
    _write_c_problem_prior_decision(cases, case_id, "SP3", "distribution_forecasting")

    audit = WorkstationGlobalAuditor(cases).audit(case_id)

    assert not any(item.source == "c_problem_benchmark" for item in audit.findings)


def test_real_wordle_validation_defect_routes_to_exact_subproblem_phase_and_resolves(tmp_path: Path) -> None:
    cases, case_id, artifacts, graphs, engine, bridge, frame, plans = _completed_wordle_research_case(tmp_path)
    sp3 = graphs.load(case_id).node("SP3")
    source_artifact_id = sp3.state.evidence_artifact_ids[0]
    injected = ValidationAssessment(
        case_id=case_id,
        subproblem_id="SP3",
        protocol_id="distribution.temporal-simplex.v1",
        family="distribution_forecasting",
        gate="REVIEW",
        findings=[
            ValidationFinding(
                severity="REVIEW",
                code="TEST_SP3_REPAIR_REQUIRED",
                detail="Injected historical-Gate defect: SP3 uncertainty needs another validation pass.",
            )
        ],
        metrics={"projected_simplex_error": 0.0},
        generated_at="2026-08-19T18:00:00+08:00",
    )
    ValidationRunner().persist(
        cases,
        artifacts,
        case_id,
        "SP3",
        injected,
        [source_artifact_id],
    )

    audit = WorkstationGlobalAuditor(cases).audit(case_id)
    issue = next(item for item in audit.findings if item.code == "VALIDATION_TEST_SP3_REPAIR_REQUIRED")
    assert issue.subproblem_id == "SP3"
    assert issue.repair_phase == "validation"
    assert issue.repair_node == "experiments"
    assert issue.domain == "experiment"
    plan = WorkstationRepairRouter().plan(audit, 1)
    assert plan.pivot == "experiments"
    assert any(
        target.subproblem_id == "SP3" and target.phase == "validation"
        for target in plan.repair_targets
    )
    assert not any(target.phase == "paper" for target in plan.repair_targets)

    repaired = engine.execute_node(
        case_id,
        "SP3",
        plans["SP3"],
        frame=frame,
        answer_text="SP3 repaired distribution forecast with refreshed validation.",
    )
    bridge.project(case_id, "SP3", repaired)
    audit_after = WorkstationGlobalAuditor(cases).audit(case_id)
    assert not any(item.code == "VALIDATION_TEST_SP3_REPAIR_REQUIRED" for item in audit_after.findings)
    assert graphs.load(case_id).node("SP3").experiments[0].validation_protocol == [
        "distribution.temporal-simplex.v1"
    ]
    assert artifacts.verify(case_id)["valid"]


def test_auto_pipeline_recurrent_round_replays_only_wordle_sp3_validation_target(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "Wordle AutoPipeline research Round")
    case_id = case["case_id"]
    service = AutoPipelineService(cases, None, coherence=False)  # type: ignore[arg-type]
    source = service.artifacts.ingest_file(
        case_id,
        CASE_ROOT / "input/data/uploaded/_wordle_data_clean.csv",
        "input/data/uploaded",
        "observed_data",
    )
    service.contracts.persist_subproblems(case_id, _wordle_contracts())
    service.problem_graphs.persist(
        case_id,
        service.contracts.list_subproblems(case_id),
        [source["artifact_id"]],
    )
    frame, plans = prepare_wordle_2023_research(
        pd.read_csv(CASE_ROOT / "input/data/uploaded/_wordle_data_clean.csv")
    )
    for subproblem_id in ("SP1", "SP2", "SP3", "SP4", "SP5"):
        service.execute_subproblem_node(
            case_id,
            subproblem_id,
            plans[subproblem_id],
            frame=frame,
            source_artifact_ids=[source["artifact_id"]],
            answer_text=f"{subproblem_id} accepted Wordle answer before recurrent repair.",
        )
    service.complete_subproblem_synthesis(
        case_id,
        "SP6",
        "Editor letter synthesizes only accepted SP1-SP5 evidence.",
    )
    service.recurrent.register_bootstrap(case_id, {"problem_graph": "bootstrap"})

    sp3_before = service.problem_graphs.load(case_id).node("SP3")
    solver_artifact_before = sp3_before.state.evidence_artifact_ids[0]
    input_snapshot_before = sp3_before.experiments[0].evidence_artifact_ids[0]
    injected = ValidationAssessment(
        case_id=case_id,
        subproblem_id="SP3",
        protocol_id="distribution.temporal-simplex.v1",
        family="distribution_forecasting",
        gate="REVIEW",
        findings=[
            ValidationFinding(
                severity="REVIEW",
                code="TEST_AUTOPIPE_SP3_REPAIR",
                detail="Injected SP3 validation defect for AutoPipeline recurrent replay.",
            )
        ],
        metrics={"projected_simplex_error": 0.0},
        generated_at="2026-08-19T18:00:00+08:00",
    )
    ValidationRunner().persist(
        cases,
        service.artifacts,
        case_id,
        "SP3",
        injected,
        [solver_artifact_before],
    )

    round_result = service.run_recurrent_round(
        case_id,
        "research-round-session",
        "human",
        "MCM",
        invalidate=True,
    )
    assert round_result["started"] is True
    assert round_result["plan"].pivot == "experiments"
    assert any(
        target.subproblem_id == "SP3" and target.phase == "validation"
        for target in round_result["plan"].repair_targets
    )
    assert round_result["decision"].accepted is True
    assert round_result["execution"]["executed_nodes"] == [
        "subproblem:SP3:validation",
        "subproblem:SP6:synthesis",
    ]
    assert "model_reentry" not in round_result["execution"]
    assert "paper_reentry" not in round_result["execution"]
    sp3_after = service.problem_graphs.load(case_id).node("SP3")
    assert sp3_after.state.evidence_artifact_ids[0] != solver_artifact_before
    latest_solver = service.artifacts.get(case_id, sp3_after.state.evidence_artifact_ids[0])
    assert latest_solver["artifact_type"] == "solver_execution_result"
    assert any(
        service.artifacts.get(case_id, artifact_id)["artifact_type"] == "solver_input_frame"
        for artifact_id in latest_solver["upstream"]
    )
    audit_after = service.recurrent.auditor.audit(case_id)
    assert not any(item.code == "VALIDATION_TEST_AUTOPIPE_SP3_REPAIR" for item in audit_after.findings)
    assert service.artifacts.verify(case_id)["valid"]


def test_round_curriculum_prioritizes_modeling_depth_then_storyline_for_soft_findings() -> None:
    quality = {domain: 0.8 for domain in WORKSTATION_DOMAINS}
    model_issue = WorkstationFinding(
        issue_id="model-soft",
        domain="model",
        severity="P2",
        code="MODEL_DEPTH_OPPORTUNITY",
        message="try a stronger candidate family",
        repair_node="model_plan",
        source="test",
        subproblem_id="SP1",
        repair_phase="modeling_brain",
    )
    paper_issue = WorkstationFinding(
        issue_id="paper-soft",
        domain="paper",
        severity="P2",
        code="STORYLINE_WEAK",
        message="improve research storyline",
        repair_node="paper_outline",
        source="test",
    )
    audit = WorkstationAudit(
        case_id="case-curriculum",
        quality=quality,
        findings=(model_issue, paper_issue),
        gate="REVIEW",
        total=0.8,
        checked_at="2026-08-19T18:00:00+08:00",
    )

    round2 = WorkstationRepairRouter().plan(audit, 2)
    assert round2.focus == "modeling_depth"
    assert round2.selected_issue_ids == ("model-soft",)
    assert round2.pivot == "model_plan"

    round4 = WorkstationRepairRouter().plan(audit, 4)
    assert round4.focus == "storyline"
    assert round4.selected_issue_ids == ("paper-soft",)
    assert round4.pivot == "paper_outline"


def test_blocking_solver_gap_routes_to_subproblem_solver_not_paper(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "Blocking solver gap")
    case_id = case["case_id"]
    artifacts = ArtifactRegistry(cases)
    graphs = ProblemGraphService(cases, artifacts)
    graphs.persist(
        case_id,
        [
            SubproblemContract(
                subproblem_id="SP1",
                title="Forecast a future series",
                objective="Forecast a future time series with uncertainty",
            )
        ],
        [],
    )
    decision = ModelingBrainDecision(
        case_id=case_id,
        subproblem_id="SP1",
        task_family="forecasting",
        gate="BLOCKED",
        query="forecast with ARIMA",
        candidates=[
            CandidateStrategy(
                candidate_id="card:arima",
                method="ARIMA",
                source="knowledge_card",
                retrieval_score=1.0,
                feasibility="NEEDS_SOLVER",
                rationale="No registered ARIMA solver.",
            )
        ],
        selected_candidate_ids=["card:arima"],
        selected_methods=["ARIMA"],
        generated_at="2026-08-19T18:00:00+08:00",
    )
    gap = SolverEngineService(cases, artifacts).persist_gap_report(case_id, "SP1", decision)
    assert gap["blocking"] is True

    audit = WorkstationGlobalAuditor(cases).audit(case_id)
    issue = next(item for item in audit.findings if item.code == "SOLVER_CAPABILITY_BLOCKING")
    assert issue.subproblem_id == "SP1"
    assert issue.repair_phase == "solver"
    assert issue.repair_node == "model_plan"
    plan = WorkstationRepairRouter().plan(audit, 1)
    assert plan.pivot == "model_plan"
    assert any(target.subproblem_id == "SP1" and target.phase == "solver" for target in plan.repair_targets)
    assert all(target.phase != "paper" for target in plan.repair_targets)

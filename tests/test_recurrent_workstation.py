from __future__ import annotations

from pathlib import Path

from mathworkstation.case_manager import CaseManager
from mathworkstation.io_utils import atomic_write_json, read_json
from mathworkstation.recurrent_workstation import (
    RecurrentWorkstationConfig,
    RecurrentWorkstationService,
    WorkstationAudit,
    WorkstationFinding,
    WorkstationGlobalAuditor,
    WorkstationRepairRouter,
    WorkstationRoundPlan,
    WorkstationRoundStore,
    decide_round,
)


def _case(tmp_path: Path) -> tuple[CaseManager, str, Path]:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "recurrent workstation test")
    case_id = case["case_id"]
    return cases, case_id, cases.case_root(case_id)


def _all_succeeded(root: Path) -> dict:
    path = root / ".internal" / "checkpoints" / "current.json"
    snapshot = read_json(path)
    for runtime in snapshot["nodes"].values():
        runtime["status"] = "SUCCEEDED"
        runtime["active_run_id"] = None
        runtime["last_error"] = None
    atomic_write_json(path, snapshot)
    return snapshot


def _audit(
    case_id: str,
    score: float,
    *,
    gate: str = "REVIEW",
    findings: tuple[WorkstationFinding, ...] = (),
) -> WorkstationAudit:
    quality = {
        "problem": score,
        "data": score,
        "model": score,
        "experiment": score,
        "evidence": score,
        "paper": score,
        "presentation": score,
        "submission": score,
    }
    return WorkstationAudit(
        case_id=case_id,
        quality=quality,
        findings=findings,
        gate=gate,
        total=score,
        checked_at="2026-08-19T00:00:00+08:00",
        workflow_status={},
    )


def test_global_audit_routes_stale_model_upstream(tmp_path: Path) -> None:
    cases, case_id, root = _case(tmp_path)
    snapshot = _all_succeeded(root)
    snapshot["nodes"]["model_plan"]["status"] = "STALE"
    atomic_write_json(root / ".internal" / "checkpoints" / "current.json", snapshot)

    audit = WorkstationGlobalAuditor(cases).audit(case_id)
    stale = [item for item in audit.findings if item.code == "WORKFLOW_STALE"]

    assert stale
    assert stale[0].domain == "model"
    assert stale[0].repair_node == "model_plan"
    assert audit.quality["model"] <= 0.5
    plan = WorkstationRepairRouter().plan(audit, 1)
    assert plan.pivot == "model_plan"
    assert "model" in plan.affected_domains


def test_complete_paper_diagnostic_gap_routes_to_experiments(tmp_path: Path) -> None:
    cases, case_id, root = _case(tmp_path)
    _all_succeeded(root)
    atomic_write_json(
        root / "review" / "structural" / "complete-paper-assessment.json",
        {
            "gate": "FAIL",
            "issue_codes": ["DIAGNOSTIC_RECORD_MISSING"],
            "details": [{"code": "DIAGNOSTIC_RECORD_MISSING"}],
            "required_sections": [],
            "checked_at": "2026-08-19T00:00:00+08:00",
        },
    )

    audit = WorkstationGlobalAuditor(cases).audit(case_id)
    issue = next(item for item in audit.findings if item.code == "DIAGNOSTIC_RECORD_MISSING")
    assert issue.domain == "experiment"
    assert issue.repair_node == "experiments"
    assert WorkstationRepairRouter().plan(audit, 1).pivot == "experiments"


def test_round_store_commits_improved_lineage_and_is_recoverable(tmp_path: Path) -> None:
    cases, case_id, root = _case(tmp_path)
    store = WorkstationRoundStore(cases)
    before = _audit(case_id, 0.55)
    plan = WorkstationRoundPlan(
        round_number=1,
        pivot="model_plan",
        selected_issue_ids=(),
        affected_domains=("model",),
        rationale="improve model route",
    )

    running = store.begin_round(case_id, plan, before, {"paper": "artifact-old"})
    assert running["status"] == "RUNNING"
    recovery = store.recovery_status(case_id)
    assert recovery["resumable"] is True
    assert recovery["round"] == 1

    store.record_execution(case_id, {"event": "cell_completed", "node": "model_plan"})
    after = _audit(case_id, 0.72, gate="PASS")
    decision = decide_round(before, after, RecurrentWorkstationConfig(min_delta=0.01))
    assert decision.accepted is True
    state = store.finalize_round(
        case_id,
        after,
        decision,
        {"paper": "artifact-new"},
        lessons=["model diagnostics improved after candidate expansion"],
    )

    assert state["round"] == 1
    assert state["status"] == "IDLE"
    assert state["active_lineage"]["paper"] == "artifact-new"
    assert state["quality_total"] == 0.72
    assert state["lessons"] == ["model diagnostics improved after candidate expansion"]
    round_root = root / "workstation" / "rounds" / "round-001"
    assert (round_root / "audit.before.json").is_file()
    assert (round_root / "audit.after.json").is_file()
    assert (round_root / "execution.jsonl").is_file()
    assert read_json(round_root / "decision.json")["accepted"] is True


def test_targeted_p2_repair_can_be_accepted_even_if_total_score_is_flat(tmp_path: Path) -> None:
    _cases, case_id, _root = _case(tmp_path)
    target = WorkstationFinding(
        issue_id="ws-issue-target",
        domain="experiment",
        severity="P2",
        code="TARGET_VALIDATION_REVIEW",
        message="targeted validation review",
        repair_node="experiments",
        source="test",
    )
    replacement = WorkstationFinding(
        issue_id="ws-issue-unrelated",
        domain="paper",
        severity="P2",
        code="UNRELATED_POLISH_REVIEW",
        message="unrelated competition polish review",
        repair_node="refinement_loop",
        source="test",
    )
    before = _audit(case_id, 0.80, findings=(target,))
    after = _audit(case_id, 0.80, findings=(replacement,))

    decision = decide_round(
        before,
        after,
        RecurrentWorkstationConfig(min_delta=0.01),
        selected_issue_ids=(target.issue_id,),
    )

    assert decision.accepted is True
    assert any("selected findings resolved" in reason for reason in decision.reasons)


def test_rejected_round_restores_previous_active_lineage(tmp_path: Path) -> None:
    cases, case_id, _root = _case(tmp_path)
    store = WorkstationRoundStore(cases)
    before = _audit(case_id, 0.65, gate="REVIEW")
    plan = WorkstationRoundPlan(
        round_number=1,
        pivot="experiments",
        selected_issue_ids=(),
        affected_domains=("experiment",),
        rationale="repair experiments",
    )
    store.begin_round(case_id, plan, before, {"paper": "artifact-good"})

    new_p0 = WorkstationFinding(
        issue_id="ws-issue-newp0",
        domain="evidence",
        severity="P0",
        code="BROKEN_EVIDENCE",
        message="new evidence break",
        repair_node="model_selection",
        source="test",
    )
    after = _audit(case_id, 0.75, gate="BLOCK", findings=(new_p0,))
    decision = decide_round(before, after)
    assert decision.accepted is False
    state = store.finalize_round(case_id, after, decision, {"paper": "artifact-bad"})

    assert state["active_lineage"]["paper"] == "artifact-good"
    assert state["quality_total"] == 0.65
    assert state["gate"] == "REVIEW"
    assert state["no_progress_streak"] == 1


def test_router_uses_lowest_domain_when_no_explicit_findings(tmp_path: Path) -> None:
    _cases, case_id, _root = _case(tmp_path)
    audit = _audit(case_id, 0.95, gate="PASS")
    quality = dict(audit.quality)
    quality["experiment"] = 0.4
    audit = WorkstationAudit(
        case_id=case_id,
        quality=quality,
        findings=(),
        gate="PASS",
        total=sum(quality.values()) / len(quality),
        checked_at=audit.checked_at,
        workflow_status={},
    )
    router = WorkstationRepairRouter(RecurrentWorkstationConfig(target_total=0.9))
    plan = router.plan(audit, 2)
    assert plan.pivot == "experiments"
    assert plan.affected_domains == ("experiment",)


def test_model_fanout_no_winner_routes_next_round_to_model_plan(tmp_path: Path) -> None:
    cases, case_id, root = _case(tmp_path)
    _all_succeeded(root)
    atomic_write_json(
        root / "analysis" / "model_fanout_summary.json",
        {
            "outcome": "NO_ACCEPTABLE_WINNER",
            "comparison_artifact_id": "artifact-fanout-comparison",
            "candidate_artifact_ids": ["artifact-a", "artifact-b", "artifact-c"],
        },
    )

    audit = WorkstationGlobalAuditor(cases).audit(case_id)
    issue = next(item for item in audit.findings if item.code == "MODEL_FANOUT_NO_ACCEPTABLE_WINNER")
    assert issue.domain == "model"
    assert issue.severity == "P1"
    assert issue.repair_node == "model_plan"
    assert WorkstationRepairRouter().plan(audit, 1).pivot == "model_plan"


def test_model_fanout_unresolved_tie_is_model_plan_review_finding(tmp_path: Path) -> None:
    cases, case_id, root = _case(tmp_path)
    _all_succeeded(root)
    atomic_write_json(
        root / "analysis" / "model_fanout_summary.json",
        {
            "outcome": "TIE",
            "comparison_artifact_id": "artifact-fanout-comparison",
            "tie_candidate_ids": ["candidate-linear", "candidate-tree"],
        },
    )

    audit = WorkstationGlobalAuditor(cases).audit(case_id)
    issue = next(item for item in audit.findings if item.code == "MODEL_FANOUT_UNRESOLVED_TIE")
    assert issue.domain == "model"
    assert issue.severity == "P2"
    assert issue.repair_node == "model_plan"
    assert WorkstationRepairRouter().plan(audit, 1).pivot == "model_plan"


def test_consistency_review_is_historical_after_complete_paper_pass(tmp_path: Path) -> None:
    cases, case_id, root = _case(tmp_path)
    _all_succeeded(root)
    atomic_write_json(
        root / "review" / "consistency" / "paper_consistency.json",
        {"gate": "REVIEW", "findings": [{"code": "MINOR_DRAFT_GAP", "detail": "pre-refinement"}]},
    )
    atomic_write_json(
        root / "review" / "structural" / "complete-paper-assessment.json",
        {"gate": "PASS", "issue_codes": [], "details": []},
    )

    audit = WorkstationGlobalAuditor(cases).audit(case_id)
    assert not any(item.code in {"PAPER_CONSISTENCY_REVIEW", "MINOR_DRAFT_GAP"} for item in audit.findings)


def test_run_round_commits_executor_result(tmp_path: Path) -> None:
    cases, case_id, root = _case(tmp_path)
    _all_succeeded(root)
    service = RecurrentWorkstationService(
        cases,
        config=RecurrentWorkstationConfig(min_rounds=1, target_total=0.9),
    )
    service.register_bootstrap(case_id, {"paper": "artifact-old"})
    snapshot = read_json(root / ".internal" / "checkpoints" / "current.json")
    snapshot["nodes"]["experiments"]["status"] = "STALE"
    for node_id in ("model_selection", "sensitivity", "paper_outline", "paper_draft", "consistency_check", "refinement_loop", "final_review", "export"):
        snapshot["nodes"][node_id]["status"] = "BLOCKED"
    atomic_write_json(root / ".internal" / "checkpoints" / "current.json", snapshot)

    def executor(plan: WorkstationRoundPlan) -> dict:
        assert plan.pivot == "experiments"
        _all_succeeded(root)
        return {
            "executed_nodes": ["experiments", "model_selection", "sensitivity"],
            "lineage_after": {"paper": "artifact-new"},
            "lessons": ["executor repaired experiment branch"],
        }

    result = service.run_round(case_id, executor, invalidate=False)
    assert result["decision"].accepted is True
    assert result["state"]["round"] == 1
    assert result["state"]["status"] == "IDLE"
    assert result["state"]["active_lineage"]["paper"] == "artifact-new"
    assert result["state"]["lessons"] == ["executor repaired experiment branch"]


def test_resume_round_after_executor_crash(tmp_path: Path) -> None:
    cases, case_id, root = _case(tmp_path)
    _all_succeeded(root)
    service = RecurrentWorkstationService(cases, config=RecurrentWorkstationConfig(min_rounds=1))
    service.register_bootstrap(case_id, {"paper": "artifact-old"})
    snapshot = read_json(root / ".internal" / "checkpoints" / "current.json")
    snapshot["nodes"]["model_plan"]["status"] = "STALE"
    for node_id in ("baseline", "experiments", "model_selection", "sensitivity", "paper_outline", "paper_draft", "consistency_check", "refinement_loop", "final_review", "export"):
        snapshot["nodes"][node_id]["status"] = "BLOCKED"
    atomic_write_json(root / ".internal" / "checkpoints" / "current.json", snapshot)

    def crash(_plan: WorkstationRoundPlan) -> dict:
        raise RuntimeError("simulated executor crash")

    try:
        service.run_round(case_id, crash, invalidate=False)
    except RuntimeError as error:
        assert "simulated executor crash" in str(error)
    else:  # pragma: no cover - defensive assertion
        raise AssertionError("round executor should have crashed")

    recovery = service.store.recovery_status(case_id)
    assert recovery["status"] == "RUNNING"
    assert recovery["resumable"] is True

    def resume(plan: WorkstationRoundPlan) -> dict:
        assert plan.pivot == "model_plan"
        _all_succeeded(root)
        return {"executed_nodes": ["model_plan"], "lineage_after": {"paper": "artifact-resumed"}}

    result = service.resume_round(case_id, resume)
    assert result["resumed"] is True
    assert result["decision"].accepted is True
    assert result["state"]["status"] == "IDLE"
    assert result["state"]["active_lineage"]["paper"] == "artifact-resumed"


def test_service_stops_after_convergence_or_round_budget(tmp_path: Path) -> None:
    cases, _case_id, _root = _case(tmp_path)
    service = RecurrentWorkstationService(
        cases,
        config=RecurrentWorkstationConfig(max_rounds=3, min_rounds=1, target_total=0.9, patience=2),
    )
    assert service.should_continue({"round": 0, "gate": "PASS", "quality_total": 1.0, "no_progress_streak": 0})
    assert not service.should_continue({"round": 1, "gate": "PASS", "quality_total": 0.95, "no_progress_streak": 0})
    assert not service.should_continue({"round": 3, "gate": "REVIEW", "quality_total": 0.5, "no_progress_streak": 0})
    assert not service.should_continue({"round": 2, "gate": "REVIEW", "quality_total": 0.5, "no_progress_streak": 2})

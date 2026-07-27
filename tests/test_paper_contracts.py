from pathlib import Path

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.paper_contracts import PaperContractService, SubproblemContract


def _service(tmp_path: Path) -> tuple[str, PaperContractService, ArtifactRegistry]:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "paper-contract")
    artifacts = ArtifactRegistry(cases)
    return case["case_id"], PaperContractService(cases, artifacts), artifacts


def test_generic_paper_fails_with_stable_issue_codes(tmp_path: Path) -> None:
    case_id, service, _ = _service(tmp_path)

    assessment = service.assess_complete_paper(case_id, "摘要、模型、结果和结论结构齐全。")

    assert assessment.gate == "FAIL"
    assert assessment.issue_codes == [
        "SUBPROBLEM_CONTRACT_MISSING",
        "RESULT_RECORD_MISSING",
        "RESULT_TABLE_MISSING",
        "DIAGNOSTIC_RECORD_MISSING",
        "SUBPROBLEM_ANSWER_MISSING",
        "SECTION_RESULT_EVIDENCE_MISSING",
    ]


def test_missing_metric_and_table_reference_are_detected(tmp_path: Path) -> None:
    case_id, service, artifacts = _service(tmp_path)
    root = service.cases.case_root(case_id)
    source = root / "results" / "metrics" / "source.json"
    source.write_text("{}\n", encoding="utf-8")
    artifact = artifacts.register_existing(
        case_id, source.relative_to(root).as_posix(), "metric_source", "test", paper_eligible=True
    )
    service.persist_subproblems(
        case_id,
        [
            SubproblemContract(
                subproblem_id="subproblem-01",
                title="模型比较",
                objective="比较候选模型",
                status="COMPLETED",
                evidence_artifact_ids=[artifact["artifact_id"]],
            )
        ],
    )
    result = service.create_result(
        case_id,
        result_type="MODEL_COMPARISON",
        metric="rmse",
        value=0.125,
        std=0.01,
        scope="3-fold cross-validation",
        source_artifact_ids=[artifact["artifact_id"]],
        section_ids=["abstract", "results", "sensitivity", "conclusion"],
    )
    table, _ = service.create_table(
        case_id,
        title="模型比较",
        columns=["模型", "RMSE"],
        rows=[["linear", "0.125000"]],
        result_ids=[result.result_id],
        source_artifact_ids=[artifact["artifact_id"]],
        section_ids=["results"],
    )

    assessment = service.assess_complete_paper(case_id, "完整论文但尚未写入数值和表引用。")

    assert "RESULT_METRIC_NOT_IN_PAPER" in assessment.issue_codes
    assert "RESULT_TABLE_NOT_REFERENCED" in assessment.issue_codes
    assert table.table_id not in "完整论文但尚未写入数值和表引用。"

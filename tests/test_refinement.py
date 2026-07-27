import hashlib
from pathlib import Path

import pytest

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.checkpoint_manager import CheckpointManager
from mathworkstation.io_utils import atomic_write_json, atomic_write_text, read_json
from mathworkstation.memory_manager import MemoryManager
from mathworkstation.refinement import PaperQualityEvaluator, RefinementConfig, RefinementService
from mathworkstation.run_manager import RunManager
from mathworkstation.workflow import NodeStatus
from mathworkstation.workflow_service import WorkflowService


def _frozen(content: str) -> dict:
    return {
        "section_order": ["abstract"],
        "sections": {
            "abstract": {
                "required_claim_ids": [],
                "required_figure_ids": [],
                "allowed_claim_ids": [],
                "allowed_figure_ids": [],
                "number_tokens": ["95"],
                "synthetic_disclosure_required": False,
            }
        },
    }


def test_quality_evaluator_blocks_verified_number_changes() -> None:
    targets = {key: 0.0 for key in RefinementConfig().targets}
    original = "# 摘要\n\n研究目的、研究方法、主要结果与稳健性边界。准确率为 95。"
    changed = original.replace("95", "96")
    result = PaperQualityEvaluator().evaluate({"abstract": changed}, _frozen(original), targets)
    assert result["hard_gate"] == "BLOCK"
    assert "VERIFIED_NUMBERS_CHANGED" in {item["code"] for item in result["findings"]}


def _service_fixture(tmp_path: Path):
    cases = CaseManager(tmp_path / "output")
    case_id = cases.create_case("SM", "Refinement")['case_id']
    artifacts = ArtifactRegistry(cases)
    checkpoints = CheckpointManager(cases)
    runs = RunManager(cases)
    workflow = WorkflowService(cases, runs, checkpoints, MemoryManager(cases, artifacts))
    root = cases.case_root(case_id)
    section_id = "abstract"
    section_root = root / "paper" / "sections" / section_id
    context = {
        "allowed_claims": [],
        "allowed_figures": [],
    }
    atomic_write_json(section_root / "context.json", context)
    context_artifact = artifacts.register_existing(case_id, "paper/sections/abstract/context.json", "paper_section_context", "python")
    draft = "# 摘要\n\n研究目的明确，研究方法受控，主要结果可验证，并说明稳健性边界。\n"
    atomic_write_text(section_root / "draft.md", draft)
    atomic_write_json(
        root / "paper" / "sections" / "manifest.json",
        {
            "schema_version": 1,
            "outline_artifact_id": "artifact-fixture",
            "sections": [{"section_id": section_id, "context_artifact_id": context_artifact["artifact_id"]}],
        },
    )
    controller = checkpoints.load(case_id)
    controller.runtimes["consistency_check"].status = NodeStatus.SUCCEEDED
    checkpoints.save(case_id, controller, "test_fixture_ready")
    service = RefinementService(cases, artifacts, workflow, runs)
    targets = {key: 0.0 for key in RefinementConfig().targets}
    targets["abstract_quality"] = 0.85
    config = RefinementConfig(max_stages=1, min_stages=0, max_changed_ratio=1.0, targets=targets)
    return cases, case_id, service, config


def _improving_proposer(context: dict) -> dict:
    section_id = next(iter(context["sections"]))
    source = context["sections"][section_id]["markdown"]
    replacement = source + ("本文围绕完整论文建立循环精修机制，方法遵循证据约束，结果经过质量门控，结论保留适用边界。" * 8)
    return {
        "schema_version": 1,
        "strategy": "expand abstract information density",
        "issue_ids": [context["issues"][0]["issue_id"]],
        "expected_gains": {"abstract_quality": 0.2},
        "patches": [
            {
                "section_id": section_id,
                "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
                "replacement_markdown": replacement,
                "rationale": "complete the abstract contract",
            }
        ],
    }


def test_refinement_accepts_bounded_patch_and_publishes_version(tmp_path: Path) -> None:
    cases, case_id, service, config = _service_fixture(tmp_path)
    result = service.run(case_id, None, _improving_proposer, config)
    root = cases.case_root(case_id)
    assert result["accepted_stages"] == [1]
    assert (root / "paper" / "versions" / "stage-001.md").is_file()
    assert (root / "paper" / "final.md").is_file()
    stage_root = root / "refinement" / "stages" / "stage-001"
    assert (stage_root / "transaction.json").is_file()
    assert (stage_root / "result.json").is_file()
    assert (stage_root / "COMMITTED.json").is_file()
    assert not list((stage_root / ".pending").glob("*"))
    state = read_json(root / "memory" / "refinement_state.json")
    assert state["stop_reason"] == "MAX_STAGES"
    assert state["active_stage"] is None
    assert state["accepted_patch_ids"]
    assert state["section_attention"]["abstract"] > 0


def test_refinement_multiple_stages_keep_append_only_history(tmp_path: Path) -> None:
    cases, case_id, service, _ = _service_fixture(tmp_path)
    targets = {key: 0.0 for key in RefinementConfig().targets}
    targets["abstract_quality"] = 0.99
    config = RefinementConfig(
        max_stages=3,
        min_stages=0,
        patience=3,
        max_no_progress_attempts=3,
        max_rejection_streak=3,
        max_changed_ratio=1.0,
        targets=targets,
    )
    calls = 0

    def proposer(context: dict) -> dict:
        nonlocal calls
        calls += 1
        section_id = next(iter(context["sections"]))
        source = context["sections"][section_id]["markdown"]
        replacement = source + "\n本轮完成证据约束、结果解释和适用边界补充。" * 12
        return {
            "schema_version": 1,
            "strategy": f"stage-{calls}",
            "issue_ids": [context["issues"][0]["issue_id"]],
            "expected_gains": {"abstract_quality": 0.2},
            "patches": [{
                "section_id": section_id,
                "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
                "replacement_markdown": replacement,
                "rationale": "bounded multi-stage evidence-grounded patch",
            }],
        }

    result = service.run(case_id, None, proposer, config)
    root = cases.case_root(case_id)
    assert result["stages_completed"] >= 2
    assert calls == result["stages_completed"]
    assert len(list((root / "refinement" / "history.jsonl").read_text(encoding="utf-8").splitlines())) == result["stages_completed"]
    assert (root / "paper" / "versions" / "stage-001.md").is_file()
    assert not (root / "paper" / "versions" / "stage-002.md").exists()
    assert read_json(root / "refinement" / "stages" / "stage-002" / "decision.json")["accepted"] is False
    assert (root / "refinement" / "stages" / "stage-002" / "COMMITTED.json").is_file()


def test_refinement_resumes_after_interrupted_proposer(tmp_path: Path) -> None:
    cases, case_id, service, config = _service_fixture(tmp_path)

    def interrupted(_: dict) -> dict:
        raise RuntimeError("simulated transport interruption")

    with pytest.raises(RuntimeError, match="transport interruption"):
        service.run(case_id, None, interrupted, config)
    state = read_json(cases.case_root(case_id) / "memory" / "refinement_state.json")
    assert state["iteration"] == 0
    assert state["active_stage"] == 1
    assert (cases.case_root(case_id) / "refinement" / "stages" / "stage-001" / ".pending" / "input.json").is_file()
    result = service.run(case_id, None, _improving_proposer, config)
    assert result["accepted_stages"] == [1]
    assert result["stages_completed"] == 1


def test_refinement_plateaus_after_one_strategy_reset(tmp_path: Path) -> None:
    cases, case_id, service, config = _service_fixture(tmp_path)
    targets = {key: 0.0 for key in config.targets}
    targets["abstract_quality"] = 0.95
    config = RefinementConfig(
        max_stages=5,
        min_stages=0,
        max_changed_ratio=1.0,
        patience=1,
        max_no_progress_attempts=2,
        max_rejection_streak=5,
        max_issue_attempts=5,
        targets=targets,
    )

    def no_op(context: dict) -> dict:
        section_id = next(iter(context["sections"]))
        source = context["sections"][section_id]["markdown"]
        return {
            "schema_version": 1,
            "strategy": "repeat the same ineffective patch",
            "issue_ids": [context["issues"][0]["issue_id"]],
            "expected_gains": {},
            "patches": [{
                "section_id": section_id,
                "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
                "replacement_markdown": source,
                "rationale": "intentionally no quality change",
            }],
        }

    result = service.run(case_id, None, no_op, config)
    assert result["stop_reason"] == "PLATEAU"
    state = read_json(cases.case_root(case_id) / "memory" / "refinement_state.json")
    assert state["strategy_reset_count"] == 1
    assert result["rejected_stages"] == [1, 2, 3]


def test_refinement_resumes_completed_stage_without_duplicate_proposal(tmp_path: Path) -> None:
    cases, case_id, service, config = _service_fixture(tmp_path)
    original_commit = service._commit_stage
    proposal_calls = 0

    def proposer(context: dict) -> dict:
        nonlocal proposal_calls
        proposal_calls += 1
        return _improving_proposer(context)

    def interrupt_commit(*_args, **_kwargs) -> None:
        raise RuntimeError("simulated projection interruption")

    service._commit_stage = interrupt_commit  # type: ignore[method-assign]
    with pytest.raises(RuntimeError, match="projection interruption"):
        service.run(case_id, None, proposer, config)

    root = cases.case_root(case_id)
    stage_root = root / "refinement" / "stages" / "stage-001"
    assert (stage_root / "result.json").is_file()
    assert not (stage_root / "COMMITTED.json").exists()
    assert read_json(root / "memory" / "refinement_state.json")["iteration"] == 0

    service._commit_stage = original_commit  # type: ignore[method-assign]

    def must_not_run(_: dict) -> dict:
        raise AssertionError("completed stage should be hydrated, not proposed again")

    result = service.run(case_id, None, must_not_run, config)
    assert result["accepted_stages"] == [1]
    assert proposal_calls == 1
    assert (stage_root / "COMMITTED.json").is_file()
    history = [line for line in (root / "refinement" / "history.jsonl").read_text(encoding="utf-8").splitlines() if line]
    assert len(history) == 1


def test_refinement_reports_blocked_when_issue_attempts_are_exhausted(tmp_path: Path) -> None:
    cases, case_id, service, config = _service_fixture(tmp_path)
    targets = {key: 0.0 for key in config.targets}
    targets["abstract_quality"] = 0.95
    config = RefinementConfig(
        max_stages=3,
        min_stages=0,
        max_changed_ratio=1.0,
        max_issue_attempts=1,
        max_rejection_streak=3,
        patience=3,
        targets=targets,
    )

    def no_op(context: dict) -> dict:
        section_id = next(iter(context["sections"]))
        source = context["sections"][section_id]["markdown"]
        return {
            "schema_version": 1,
            "strategy": "one exhausted attempt",
            "issue_ids": [context["issues"][0]["issue_id"]],
            "expected_gains": {},
            "patches": [{
                "section_id": section_id,
                "source_sha256": hashlib.sha256(source.encode("utf-8")).hexdigest(),
                "replacement_markdown": source,
                "rationale": "leave issue unresolved",
            }],
        }

    result = service.run(case_id, None, no_op, config)
    assert result["stop_reason"] == "BLOCKED"
    assert result["stages_completed"] == 1

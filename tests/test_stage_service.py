import json
import os
from pathlib import Path

import pytest

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.checkpoint_manager import CheckpointManager
from mathworkstation.memory_manager import MemoryManager
from mathworkstation.run_manager import RunManager
from mathworkstation.stage_service import StageService
from mathworkstation.workflow import NodeStatus
from mathworkstation.workflow_service import WorkflowService
from mathworkstation.stage_service import _render_final_manuscript


def _services(tmp_path: Path):
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Stage integration")
    artifacts = ArtifactRegistry(cases)
    workflow = WorkflowService(cases, RunManager(cases), CheckpointManager(cases), MemoryManager(cases, artifacts))
    return cases, case["case_id"], artifacts, workflow, StageService(cases, artifacts, workflow)


def test_validated_stage_advances_to_review(tmp_path: Path) -> None:
    cases, case_id, _, workflow, stages = _services(tmp_path)
    workflow.start_node(case_id, "input_validation")
    workflow.succeed_node(case_id, "input_validation")
    workflow.start_node(case_id, "problem_analysis")
    workflow.succeed_node(case_id, "problem_analysis")
    workflow.approve_node(case_id, "problem_analysis", "human")
    workflow.start_node(case_id, "data_registration")
    workflow.succeed_node(case_id, "data_registration")
    workflow.approve_node(case_id, "data_registration", "human")
    workflow.start_node(case_id, "data_quality")
    workflow.succeed_node(case_id, "data_quality")
    workflow.start_node(case_id, "eda")
    workflow.succeed_node(case_id, "eda")

    result = stages.run_validated_stage(case_id, "model_plan", lambda: {"artifact_id": "test"})
    assert result["workflow_node"]["status"] == NodeStatus.NEEDS_REVIEW.value


def test_complete_paper_draft_rejects_placeholders(tmp_path: Path) -> None:
    cases, case_id, _, _, stages = _services(tmp_path)
    root = cases.case_root(case_id)
    section_root = root / "paper" / "sections" / "abstract"
    section_root.mkdir(parents=True)
    (section_root / "draft.md").write_text("[SECTION_DRAFT_PENDING]\n", encoding="utf-8")
    (root / "paper" / "sections" / "manifest.json").write_text(
        json.dumps(
            {
                "outline_artifact_id": "artifact-outline",
                "sections": [{"section_id": "abstract", "draft_artifact_id": "artifact-draft"}],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="abstract"):
        stages.complete_paper_draft(case_id)


def test_final_manuscript_removes_internal_markers() -> None:
    final = _render_final_manuscript(
        "# 摘要\n\n结果见 [claim-0123456789ab] 和 [figure-abcdefabcdef]。"
    )
    assert "claim-0123456789ab" not in final
    assert "图 1" in final


def test_env_file_does_not_override_existing_value(tmp_path: Path, monkeypatch) -> None:
    from mathworkstation.cli import _load_env_file

    env_file = tmp_path / ".env.local"
    env_file.write_text("MMW_TEST_KEY=file-value\n", encoding="utf-8")
    monkeypatch.setenv("MMW_TEST_KEY", "process-value")
    _load_env_file(env_file)
    assert os.environ["MMW_TEST_KEY"] == "process-value"


def test_synthetic_model_plan_fixture_is_valid_json() -> None:
    payload = json.loads(Path("examples/fixtures/phase4_synthetic_plan.json").read_text(encoding="utf-8"))
    assert payload["candidate_models"][1]["name"] == "ridge"

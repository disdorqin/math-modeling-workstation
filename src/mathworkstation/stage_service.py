from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .io_utils import atomic_write_text, read_json
from .paper_consistency import PaperConsistencyChecker
from .workflow import FailureCategory
from .workflow_service import WorkflowService


class StageService:
    """Keeps validated artifact creation and DAG transitions in sync."""

    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        workflow: WorkflowService,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.workflow = workflow

    def run_validated_stage(
        self,
        case_id: str,
        node_id: str,
        operation: Callable[[], dict[str, Any]],
        session_id: str | None = None,
    ) -> dict[str, Any]:
        started = self.workflow.start_node(case_id, node_id, session_id)
        try:
            result = operation()
        except Exception as error:
            self.workflow.fail_node(
                case_id,
                node_id,
                FailureCategory.SCHEMA,
                f"{type(error).__name__}: {error}",
            )
            raise
        node = self.workflow.succeed_node(case_id, node_id)
        return {"succeeded": True, "started": started, "result": result, "workflow_node": node}

    def complete_paper_draft(
        self,
        case_id: str,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        root = self.cases.case_root(case_id)
        manifest_path = root / "paper" / "sections" / "manifest.json"
        if not manifest_path.is_file():
            raise FileNotFoundError("paper sections manifest not found")
        manifest = read_json(manifest_path)
        parts: list[str] = []
        upstream: list[str] = [manifest["outline_artifact_id"]]
        for section in manifest["sections"]:
            section_id = section["section_id"]
            draft_path = root / "paper" / "sections" / section_id / "draft.md"
            content = draft_path.read_text(encoding="utf-8").strip()
            if not content or any(marker in content for marker in ("[SECTION_DRAFT_PENDING]", "[NEEDS_EVIDENCE]", "[TODO]", "[TBD]")):
                raise ValueError(f"section draft is incomplete: {section_id}")
            parts.append(content)
            relative_path = draft_path.relative_to(root).as_posix()
            current_draft = next(
                item
                for item in self.artifacts.list_artifacts(case_id)
                if item["path"] == relative_path and item["status"] == "ACTIVE"
            )
            upstream.append(current_draft["artifact_id"])

        started = self.workflow.start_node(case_id, "paper_draft", session_id)
        output_path = root / "paper" / "paper.md"
        atomic_write_text(output_path, "\n\n".join(parts) + "\n")
        artifact = self.artifacts.register_existing(
            case_id,
            output_path.relative_to(root).as_posix(),
            "paper_draft_compiled",
            "python",
            run_id=started["run"]["run_id"],
            upstream=list(dict.fromkeys(upstream)),
        )
        node = self.workflow.succeed_node(case_id, "paper_draft")
        return {"succeeded": True, "artifact": artifact, "workflow_node": node}

    def check_consistency(
        self,
        case_id: str,
        checker: PaperConsistencyChecker,
        session_id: str | None = None,
    ) -> dict[str, Any]:
        started = self.workflow.start_node(case_id, "consistency_check", session_id)
        try:
            result = checker.check(case_id)
        except Exception as error:
            self.workflow.fail_node(
                case_id,
                "consistency_check",
                FailureCategory.CRITICAL,
                f"{type(error).__name__}: {error}",
            )
            raise
        if result["report"]["gate"] == "PASS":
            node = self.workflow.succeed_node(case_id, "consistency_check")
        else:
            failure = self.workflow.fail_node(
                case_id,
                "consistency_check",
                FailureCategory.DATA_QUALITY,
                f"paper consistency gate: {result['report']['gate']}",
            )
            node = failure["node"]
        return {"succeeded": result["report"]["gate"] == "PASS", "started": started, "result": result, "workflow_node": node}

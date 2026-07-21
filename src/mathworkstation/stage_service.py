from __future__ import annotations

from collections.abc import Callable
import re
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
        final_path = root / "paper" / "paper_final.md"
        final_content = _render_final_manuscript("\n\n".join(parts))
        atomic_write_text(final_path, final_content)
        final_artifact = self.artifacts.register_existing(
            case_id,
            final_path.relative_to(root).as_posix(),
            "paper_final",
            "python",
            run_id=started["run"]["run_id"],
            upstream=[artifact["artifact_id"]],
            paper_eligible=True,
        )
        return {"succeeded": True, "artifact": artifact, "final_artifact": final_artifact, "workflow_node": node}

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


def _render_final_manuscript(content: str) -> str:
    """Remove internal claim/figure markers while keeping numbered figure references."""
    figure_numbers: dict[str, int] = {}

    def replace_figure(match: re.Match[str]) -> str:
        figure_id = match.group(1)
        figure_numbers.setdefault(figure_id, len(figure_numbers) + 1)
        return f"（图 {figure_numbers[figure_id]}）"

    content = re.sub(r"\[figure-([a-f0-9]{12})\]", replace_figure, content)
    content = re.sub(r"\[claim-[a-f0-9]{12}\]", "", content)
    content = re.sub(r"图表证据：([^\[]+)（图 \d+）", r"图：\1", content)
    return re.sub(r"\n{3,}", "\n\n", content).strip() + "\n"

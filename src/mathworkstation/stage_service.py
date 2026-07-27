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
        figure_assets: dict[str, dict[str, str]] = {}
        for section in manifest["sections"]:
            section_id = section["section_id"]
            context_path = root / "paper" / "sections" / section_id / "context.json"
            if context_path.is_file():
                for figure in read_json(context_path).get("allowed_figures", []):
                    figure_assets[figure["figure_id"]] = {
                        "path": figure["path"],
                        "title": figure.get("title", ""),
                    }
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
        final_content = _render_final_manuscript("\n\n".join(parts), figure_assets)
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
        # `prepare-submission` and `export-case` both read `paper/final.md`, which
        # until now was only written by the LLM refinement loop. Mirroring the
        # manuscript here keeps the deterministic, no-API path able to reach a
        # submission package. The refinement loop overwrites both files with its
        # accepted version, so the LLM path is unchanged.
        current_path = root / "paper" / "final.md"
        atomic_write_text(current_path, final_content)
        current_artifact = self.artifacts.register_existing(
            case_id,
            current_path.relative_to(root).as_posix(),
            "paper_final_current",
            "python",
            run_id=started["run"]["run_id"],
            upstream=[final_artifact["artifact_id"]],
            paper_eligible=True,
        )
        return {
            "succeeded": True,
            "artifact": artifact,
            "final_artifact": final_artifact,
            "current_artifact": current_artifact,
            "workflow_node": node,
        }

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


def _render_final_manuscript(
    content: str,
    figure_assets: dict[str, dict[str, str]] | None = None,
) -> str:
    """Remove internal markers, number figure references, and embed the figures.

    Cited figures are real, promoted case artifacts. Turning the citation into a
    bare "（图 N）" and dropping the image left the manuscript without any of the
    plots the pipeline produced, so each first citation now also emits a numbered
    Markdown image at the end of its paragraph.
    """
    assets = figure_assets or {}
    figure_numbers: dict[str, int] = {}

    def replace_figure(match: re.Match[str]) -> str:
        # Key by the full registry id, not the bare hex group, so the numbering
        # map can be joined against the figure registry.
        figure_id = f"figure-{match.group(1)}"
        figure_numbers.setdefault(figure_id, len(figure_numbers) + 1)
        return f"（图 {figure_numbers[figure_id]}）"

    content = re.sub(r"\[figure-([a-f0-9]{12})\]", replace_figure, content)
    content = re.sub(r"\[claim-[a-f0-9]{12}\]", "", content)
    content = re.sub(r"图表证据：([^\[]+)（图 \d+）", r"图：\1", content)
    content = re.sub(r"[ \t]+(?=[，。；：、）】])", "", content)
    content = _embed_figures(content, figure_numbers, assets)
    return re.sub(r"\n{3,}", "\n\n", content).strip() + "\n"


def _embed_figures(
    content: str,
    figure_numbers: dict[str, int],
    assets: dict[str, dict[str, str]],
) -> str:
    """Insert each figure once, after the paragraph that first references it."""
    if not figure_numbers or not assets:
        return content
    pending = {
        number: figure_id
        for figure_id, number in figure_numbers.items()
        if figure_id in assets
    }
    if not pending:
        return content
    blocks = content.split("\n\n")
    rendered: list[str] = []
    emitted: set[int] = set()
    for block in blocks:
        rendered.append(block)
        for number in sorted(pending):
            if number in emitted or f"（图 {number}）" not in block:
                continue
            asset = assets[pending[number]]
            caption = asset["title"].strip() or f"图 {number}"
            rendered.append(f"![图 {number} {caption}]({asset['path']})\n\n*图 {number}　{caption}*")
            emitted.add(number)
    return "\n\n".join(rendered)

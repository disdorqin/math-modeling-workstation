from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .io_utils import atomic_write_json, atomic_write_text, now_iso, read_json


class MemoryManager:
    def __init__(self, cases: CaseManager, artifacts: ArtifactRegistry) -> None:
        self.cases = cases
        self.artifacts = artifacts

    def initialize(self, case_id: str) -> None:
        root = self.cases.case_root(case_id)
        manifest = read_json(root / "manifest.json")
        files = {
            "memory/project_facts.md": (
                "# Project Facts\n\n"
                f"- Case ID: `{case_id}`\n"
                f"- Title: {manifest.get('title') or 'Pending'}\n"
                f"- Competition: `{manifest.get('competition_type')}`\n"
                f"- Output language: `{manifest.get('language')}`\n"
            ),
            "memory/decisions.md": "# Approved Decisions\n\nNo approved decisions yet.\n",
            "memory/current_state.md": "# Current State\n\nLifecycle: `CREATED`\n",
        }
        for relative, content in files.items():
            path = root / relative
            if not path.exists():
                atomic_write_text(path, content)
        evidence_path = root / "memory/evidence_index.json"
        if not evidence_path.exists():
            atomic_write_json(
                evidence_path,
                {"schema_version": 1, "case_id": case_id, "claims": [], "updated_at": now_iso()},
            )

    def update_current_state(self, case_id: str, content: str) -> None:
        root = self.cases.case_root(case_id)
        atomic_write_text(root / "memory/current_state.md", content.rstrip() + "\n")

    def build_resume_brief(
        self,
        case_id: str,
        workflow_snapshot: dict[str, Any] | None = None,
    ) -> str:
        root = self.cases.case_root(case_id)
        manifest = read_json(root / "manifest.json")
        status = read_json(root / "status.json")
        artifacts = self.artifacts.list_artifacts(case_id)
        snapshot = workflow_snapshot or {}
        nodes = snapshot.get("nodes", {})

        succeeded = sorted(node for node, value in nodes.items() if value.get("status") == "SUCCEEDED")
        failed = sorted(node for node, value in nodes.items() if value.get("status") == "FAILED")
        blocked = sorted(node for node, value in nodes.items() if value.get("status") == "BLOCKED")
        review = sorted(node for node, value in nodes.items() if value.get("status") == "NEEDS_REVIEW")
        active_artifacts = [item for item in artifacts if item.get("status") == "ACTIVE"]

        def section(title: str, values: list[str]) -> str:
            body = "\n".join(f"- `{value}`" for value in values) if values else "- None"
            return f"## {title}\n\n{body}\n"

        brief = (
            "# Resume Brief\n\n"
            f"Generated: `{now_iso()}`\n\n"
            f"- Case ID: `{case_id}`\n"
            f"- Title: {manifest.get('title') or 'Pending'}\n"
            f"- Competition: `{manifest.get('competition_type')}`\n"
            f"- Lifecycle: `{status.get('lifecycle')}`\n"
            f"- Active Session: `{status.get('active_session_id') or 'None'}`\n"
            f"- Active Run: `{status.get('active_run_id') or 'None'}`\n"
            f"- Active Artifacts: `{len(active_artifacts)}`\n\n"
            + section("Succeeded Nodes", succeeded)
            + "\n"
            + section("Failed Nodes", failed)
            + "\n"
            + section("Blocked Nodes", blocked)
            + "\n"
            + section("Needs Review", review)
            + "\n## Control Rules\n\n"
            "- Operate only inside this Case ID.\n"
            "- Use declared artifact IDs instead of guessing paths.\n"
            "- Do not invent numerical results.\n"
            "- Do not bypass blocked dependencies.\n"
            "- Mark missing evidence as NEEDS_REVIEW.\n"
        )
        atomic_write_text(root / ".internal/resume_brief.md", brief)
        atomic_write_json(
            root / ".internal/resume_context.json",
            {
                "schema_version": 1,
                "case_id": case_id,
                "status": status,
                "workflow": snapshot,
                "active_artifact_ids": [item["artifact_id"] for item in active_artifacts],
                "generated_at": now_iso(),
            },
        )
        return brief


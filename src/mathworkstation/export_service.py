from __future__ import annotations

import zipfile
import re
from pathlib import Path
from typing import Any

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .io_utils import atomic_write_json, sha256_file
from .workflow_service import WorkflowService


class ExportService:
    def __init__(self, cases: CaseManager, artifacts: ArtifactRegistry, workflow: WorkflowService) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.workflow = workflow

    def export_case(self, case_id: str, session_id: str | None = None) -> dict[str, Any]:
        root = self.cases.case_root(case_id)
        started = self.workflow.start_node(case_id, "export", session_id)
        export_root = root / "export"
        export_root.mkdir(parents=True, exist_ok=True)
        archive_path = export_root / f"{case_id}.zip"
        files: list[dict[str, Any]] = []
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob("*")):
                if not path.is_file() or export_root in path.parents:
                    continue
                relative = path.relative_to(root).as_posix()
                archive.write(path, relative)
                files.append({"path": relative, "sha256": sha256_file(path), "bytes": path.stat().st_size})
        manifest = {
            "schema_version": 1,
            "case_id": case_id,
            "archive": archive_path.name,
            "files": files,
            "artifact_integrity": self.artifacts.verify(case_id),
        }
        manifest_path = export_root / "manifest.json"
        atomic_write_json(manifest_path, manifest)
        archive_artifact = self.artifacts.register_existing(
            case_id,
            archive_path.relative_to(root).as_posix(),
            "case_export_zip",
            "python",
            run_id=started["run"]["run_id"],
            paper_eligible=False,
        )
        manifest_artifact = self.artifacts.register_existing(
            case_id,
            manifest_path.relative_to(root).as_posix(),
            "case_export_manifest",
            "python",
            run_id=started["run"]["run_id"],
            upstream=[archive_artifact["artifact_id"]],
        )
        node = self.workflow.succeed_node(case_id, "export")
        return {
            "succeeded": True,
            "archive_artifact_id": archive_artifact["artifact_id"],
            "manifest_artifact_id": manifest_artifact["artifact_id"],
            "archive_path": archive_path.relative_to(root).as_posix(),
            "file_count": len(files),
            "workflow_node": node,
        }

    def export_submission(self, case_id: str) -> dict[str, Any]:
        """Create a clean user-facing package without internal provenance state."""
        root = self.cases.case_root(case_id)
        export_root = root / "export" / "submission_package"
        export_root.mkdir(parents=True, exist_ok=True)
        archive_path = export_root / f"{case_id}-submission.zip"
        allowed: list[Path] = []
        for relative in ("paper/markdown/submission.md", "paper/latex/main.pdf", "paper/references", "tables/final", "figures/draft", "figures/final"):
            candidate = root / relative
            if candidate.is_file():
                allowed.append(candidate)
            elif candidate.is_dir():
                allowed.extend(path for path in candidate.rglob("*") if path.is_file())
        if not root.joinpath("paper", "final.md").is_file():
            raise FileNotFoundError("paper/final.md is required for submission package")
        files: list[dict[str, Any]] = []
        with zipfile.ZipFile(archive_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(set(allowed)):
                relative = path.relative_to(root).as_posix()
                package_name = "paper/final.md" if relative == "paper/markdown/submission.md" else relative
                archive.write(path, package_name)
                files.append({"path": package_name, "sha256": sha256_file(path), "bytes": path.stat().st_size})
        manifest = {"schema_version": 1, "case_id": case_id, "kind": "submission_package", "files": files, "forbidden_prefixes": ["sessions/", "memory/", "refinement/", "evidence/raw_responses/", "artifact_registry.jsonl"]}
        manifest_path = export_root / "manifest.json"
        atomic_write_json(manifest_path, manifest)
        archive_artifact = self.artifacts.register_existing(case_id, archive_path.relative_to(root).as_posix(), "submission_package_zip", "python")
        manifest_artifact = self.artifacts.register_existing(case_id, manifest_path.relative_to(root).as_posix(), "submission_package_manifest", "python", upstream=[archive_artifact["artifact_id"]])
        return {"succeeded": True, "archive_artifact_id": archive_artifact["artifact_id"], "manifest_artifact_id": manifest_artifact["artifact_id"], "archive_path": archive_path.relative_to(root).as_posix(), "file_count": len(files)}

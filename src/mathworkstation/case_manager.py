from __future__ import annotations

import shutil
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .errors import CaseNotFoundError, InvalidCaseError
from .ids import next_case_id, normalize_competition
from .io_utils import append_jsonl, atomic_write_json, atomic_write_text, now_iso, read_json
from .paths import CASE_DIRECTORIES, create_case_tree, resolve_within


class CaseManager:
    REGISTRY_FILES = (
        "artifact_registry.jsonl",
        "dataset_registry.jsonl",
        "figure_registry.jsonl",
        "experiment_registry.jsonl",
        "claim_registry.jsonl",
    )

    def __init__(self, output_root: str | Path = "output") -> None:
        self.output_root = Path(output_root).resolve()
        self.output_root.mkdir(parents=True, exist_ok=True)

    def case_root(self, case_id: str) -> Path:
        # Try legacy path first: output/<case_id>/
        root = resolve_within(self.output_root, case_id)
        if root.is_dir():
            return root
        # Try structured path: output/<comp>-<type>-<year>/v<N>/<case_id>/
        for folder in self.output_root.iterdir():
            if folder.is_dir() and folder.name.startswith("_"):
                continue  # skip _archive, etc.
            if folder.is_dir():
                for version_folder in folder.iterdir():
                    if version_folder.is_dir() and version_folder.name.startswith("v"):
                        candidate = version_folder / case_id
                        if candidate.is_dir():
                            return candidate
        raise CaseNotFoundError(f"case not found: {case_id}")

    def create_case(
        self,
        competition: str,
        title: str,
        language: str = "zh",
        problem_type: str | None = None,
        year: int | None = None,
        version: int = 1,
    ) -> dict[str, Any]:
        """Create a new case.

        New structure: output/<comp>-<type>-<year>/v<N>/<case_id>/
        Legacy: output/<case_id>/ (when problem_type or year is None)
        """
        competition = normalize_competition(competition)
        use_new_structure = problem_type is not None and year is not None

        if use_new_structure:
            # New structured path: output/mcm-c-2024/v1/<case_id>/
            problem_type = problem_type.strip().lower()
            folder_name = f"{competition.lower()}-{problem_type}-{year}"
            version_folder = f"v{version}"
            for _ in range(20):
                case_id = next_case_id(self.output_root, competition)
                case_root = self.output_root / folder_name / version_folder / case_id
                try:
                    # New structured path has parent folders (mcm-c-2024/v1) that
                    # may not exist yet — create them, then the case dir itself.
                    case_root.parent.mkdir(parents=True, exist_ok=True)
                    case_root.mkdir(parents=False, exist_ok=False)
                    break
                except FileExistsError:
                    continue
            else:
                raise InvalidCaseError("could not allocate a unique case id")
        else:
            # Legacy path: output/<case_id>/
            for _ in range(20):
                case_id = next_case_id(self.output_root, competition)
                case_root = resolve_within(self.output_root, case_id)
                try:
                    case_root.mkdir(parents=False, exist_ok=False)
                    break
                except FileExistsError:
                    continue
            else:
                raise InvalidCaseError("could not allocate a unique case id")

        try:
            create_case_tree(case_root)
            created_at = now_iso()
            manifest = {
                "schema_version": 1,
                "case_id": case_id,
                "case_uuid": str(uuid.uuid4()),
                "title": title.strip(),
                "competition_type": competition,
                "language": language,
                "created_at": created_at,
                "updated_at": created_at,
                "archived": False,
            }
            if use_new_structure:
                manifest["problem_type"] = problem_type
                manifest["year"] = year
                manifest["version"] = version
                manifest["directory_structure"] = "structured"
            status = {
                "schema_version": 1,
                "case_id": case_id,
                "lifecycle": "CREATED",
                "active_session_id": None,
                "active_run_id": None,
                "updated_at": created_at,
            }
            atomic_write_json(case_root / "manifest.json", manifest)
            atomic_write_json(case_root / "status.json", status)
            (case_root / "artifact_registry.jsonl").touch(exist_ok=False)
            (case_root / "dataset_registry.jsonl").touch(exist_ok=False)
            (case_root / "figure_registry.jsonl").touch(exist_ok=False)
            (case_root / "experiment_registry.jsonl").touch(exist_ok=False)
            (case_root / "claim_registry.jsonl").touch(exist_ok=False)
            atomic_write_text(
                case_root / "README.md",
                f"# {title.strip() or case_id}\n\n- Case ID: `{case_id}`\n"
                f"- Competition: `{competition}`\n- Created: `{created_at}`\n",
            )
            append_jsonl(
                case_root / "run_history.jsonl",
                {"timestamp": created_at, "event": "case_created", "case_id": case_id},
            )
            append_jsonl(
                case_root / "decisions.jsonl",
                {
                    "timestamp": created_at,
                    "event": "case_configuration",
                    "decision": {"competition": competition, "language": language},
                    "decided_by": "human",
                },
            )
            from .artifact_registry import ArtifactRegistry
            from .checkpoint_manager import CheckpointManager
            from .memory_manager import MemoryManager

            registry = ArtifactRegistry(self)
            MemoryManager(self, registry).initialize(case_id)
            CheckpointManager(self).initialize(case_id)
            return manifest
        except Exception:
            shutil.rmtree(case_root, ignore_errors=True)
            raise

    def list_cases(self, include_archived: bool = False) -> list[dict[str, Any]]:
        cases: list[dict[str, Any]] = []
        # Scan legacy structure: output/<case_id>/
        for entry in sorted(self.output_root.iterdir()):
            if not entry.is_dir() or entry.name.startswith("_"):
                continue
            manifest_path = entry / "manifest.json"
            if manifest_path.is_file():
                manifest = read_json(manifest_path)
                if include_archived or not manifest.get("archived", False):
                    cases.append(manifest)
        # Scan structured paths: output/<comp>-<type>-<year>/v<N>/<case_id>/
        for folder in sorted(self.output_root.iterdir()):
            if not folder.is_dir() or folder.name.startswith("_"):
                continue
            if not any(c.isalpha() for c in folder.name):
                continue  # skip non-competition folders
            for version_folder in sorted(folder.iterdir()):
                if not version_folder.is_dir() or not version_folder.name.startswith("v"):
                    continue
                for case_folder in sorted(version_folder.iterdir()):
                    if not case_folder.is_dir():
                        continue
                    manifest_path = case_folder / "manifest.json"
                    if manifest_path.is_file():
                        manifest = read_json(manifest_path)
                        if include_archived or not manifest.get("archived", False):
                            cases.append(manifest)
        return cases

    def show_case(self, case_id: str) -> dict[str, Any]:
        root = self.case_root(case_id)
        return {
            "manifest": read_json(root / "manifest.json"),
            "status": read_json(root / "status.json"),
        }

    def validate_case(self, case_id: str) -> dict[str, Any]:
        root = self.case_root(case_id)
        missing = [item for item in CASE_DIRECTORIES if not (root / item).is_dir()]
        required_files = ["manifest.json", "status.json", "run_history.jsonl", *self.REGISTRY_FILES]
        missing.extend(item for item in required_files if not (root / item).is_file())
        manifest = read_json(root / "manifest.json")
        status = read_json(root / "status.json")
        errors: list[str] = []
        if manifest.get("case_id") != case_id:
            errors.append("manifest case_id mismatch")
        if status.get("case_id") != case_id:
            errors.append("status case_id mismatch")
        errors.extend(f"missing: {item}" for item in missing)
        return {"case_id": case_id, "valid": not errors, "errors": errors}

    def migrate_case(self, case_id: str) -> dict[str, Any]:
        root = self.case_root(case_id)
        before = self.validate_case(case_id)
        create_case_tree(root)
        created_files: list[str] = []
        for relative in self.REGISTRY_FILES:
            path = root / relative
            if not path.exists():
                path.touch(exist_ok=False)
                created_files.append(relative)
        manifest = read_json(root / "manifest.json")
        manifest["schema_version"] = max(int(manifest.get("schema_version", 1)), 2)
        manifest["updated_at"] = now_iso()
        atomic_write_json(root / "manifest.json", manifest)
        append_jsonl(
            root / "run_history.jsonl",
            {
                "timestamp": now_iso(),
                "event": "case_migrated",
                "created_files": created_files,
                "previously_valid": before["valid"],
            },
        )
        after = self.validate_case(case_id)
        return {
            "case_id": case_id,
            "created_files": created_files,
            "valid": after["valid"],
            "errors": after["errors"],
        }

    def archive_case(self, case_id: str) -> dict[str, Any]:
        root = self.case_root(case_id)
        manifest = read_json(root / "manifest.json")
        manifest["archived"] = True
        manifest["archived_at"] = now_iso()
        manifest["updated_at"] = manifest["archived_at"]
        atomic_write_json(root / "manifest.json", manifest)
        status = read_json(root / "status.json")
        status["lifecycle"] = "ARCHIVED"
        status["updated_at"] = now_iso()
        atomic_write_json(root / "status.json", status)
        append_jsonl(
            root / "run_history.jsonl",
            {"timestamp": now_iso(), "event": "case_archived", "case_id": case_id},
        )
        return manifest

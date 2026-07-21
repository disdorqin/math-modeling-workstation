from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from .case_manager import CaseManager
from .errors import InvalidCaseError
from .io_utils import append_jsonl, now_iso, sha256_file
from .paths import resolve_within


IMMUTABLE_PREFIXES = ("input/", "data/raw/", "evidence/raw_responses/")


class ArtifactRegistry:
    def __init__(self, cases: CaseManager) -> None:
        self.cases = cases

    def registry_path(self, case_id: str) -> Path:
        return self.cases.case_root(case_id) / "artifact_registry.jsonl"

    def list_artifacts(self, case_id: str) -> list[dict[str, Any]]:
        path = self.registry_path(case_id)
        if not path.exists():
            return []
        artifacts: dict[str, dict[str, Any]] = {}
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    artifact = json.loads(line)
                    artifacts[artifact["artifact_id"]] = artifact
        return list(artifacts.values())

    def get(self, case_id: str, artifact_id: str) -> dict[str, Any]:
        for artifact in reversed(self.list_artifacts(case_id)):
            if artifact["artifact_id"] == artifact_id:
                return artifact
        raise KeyError(f"artifact not found: {artifact_id}")

    def register_existing(
        self,
        case_id: str,
        relative_path: str,
        artifact_type: str,
        created_by: str,
        run_id: str | None = None,
        upstream: list[str] | None = None,
        paper_eligible: bool = False,
    ) -> dict[str, Any]:
        case_root = self.cases.case_root(case_id)
        target = resolve_within(case_root, relative_path)
        if not target.is_file():
            raise FileNotFoundError(target)

        normalized_path = target.relative_to(case_root).as_posix()
        artifacts = self.list_artifacts(case_id)
        active_same_path = [
            item for item in artifacts
            if item.get("path") == normalized_path and item.get("status") == "ACTIVE"
        ]
        digest = sha256_file(target)
        if active_same_path and active_same_path[-1].get("sha256") == digest:
            return active_same_path[-1]
        if active_same_path and normalized_path.startswith(IMMUTABLE_PREFIXES):
            raise InvalidCaseError(f"immutable artifact changed: {normalized_path}")
        for previous in active_same_path:
            append_jsonl(
                self.registry_path(case_id),
                {
                    **previous,
                    "status": "SUPERSEDED",
                    "superseded_at": now_iso(),
                },
            )

        artifact = {
            "schema_version": 1,
            "artifact_id": f"artifact-{uuid.uuid4().hex[:12]}",
            "case_id": case_id,
            "path": normalized_path,
            "artifact_type": artifact_type,
            "created_by": created_by,
            "created_at": now_iso(),
            "run_id": run_id,
            "upstream": upstream or [],
            "sha256": digest,
            "size_bytes": target.stat().st_size,
            "paper_eligible": paper_eligible,
            "status": "ACTIVE",
        }
        append_jsonl(self.registry_path(case_id), artifact)
        return artifact

    def ingest_file(
        self,
        case_id: str,
        source: str | Path,
        destination_directory: str,
        artifact_type: str,
        created_by: str = "human",
    ) -> dict[str, Any]:
        source_path = Path(source).resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        case_root = self.cases.case_root(case_id)
        destination_root = resolve_within(case_root, destination_directory)
        destination_root.mkdir(parents=True, exist_ok=True)
        destination = destination_root / source_path.name
        if destination.exists():
            if sha256_file(destination) == sha256_file(source_path):
                return self.register_existing(
                    case_id,
                    destination.relative_to(case_root).as_posix(),
                    artifact_type,
                    created_by,
                )
            raise FileExistsError(f"refusing to overwrite input artifact: {destination.name}")
        shutil.copy2(source_path, destination)
        return self.register_existing(
            case_id,
            destination.relative_to(case_root).as_posix(),
            artifact_type,
            created_by,
        )

    def verify(self, case_id: str) -> dict[str, Any]:
        case_root = self.cases.case_root(case_id)
        missing: list[str] = []
        changed: list[str] = []
        for artifact in self.list_artifacts(case_id):
            if artifact.get("status") != "ACTIVE":
                continue
            target = resolve_within(case_root, artifact["path"])
            if not target.is_file():
                missing.append(artifact["artifact_id"])
            elif sha256_file(target) != artifact["sha256"]:
                changed.append(artifact["artifact_id"])
        return {
            "case_id": case_id,
            "valid": not missing and not changed,
            "missing_artifact_ids": missing,
            "changed_artifact_ids": changed,
        }

    def promote_to_paper(self, case_id: str, artifact_id: str, approval_artifact_id: str) -> dict[str, Any]:
        """Promote an already verified artifact after a human evidence decision."""
        current = self.get(case_id, artifact_id)
        if current.get("status") != "ACTIVE":
            raise InvalidCaseError(f"cannot promote inactive artifact: {artifact_id}")
        if not self.verify(case_id)["valid"]:
            raise InvalidCaseError("cannot promote artifacts while integrity check fails")
        promoted = {
            **current,
            "paper_eligible": True,
            "paper_ready_approval_id": approval_artifact_id,
            "updated_at": now_iso(),
        }
        append_jsonl(self.registry_path(case_id), promoted)
        return promoted

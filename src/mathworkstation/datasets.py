from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from enum import StrEnum
from pathlib import Path
from typing import Any

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .io_utils import append_jsonl, atomic_write_text, now_iso


class DatasetKind(StrEnum):
    OBSERVED = "OBSERVED"
    DERIVED = "DERIVED"
    SYNTHETIC = "SYNTHETIC"


class DatasetStatus(StrEnum):
    REGISTERED = "REGISTERED"
    PROFILED = "PROFILED"
    VERIFIED = "VERIFIED"
    REJECTED = "REJECTED"
    STALE = "STALE"


@dataclass(frozen=True)
class DatasetRecord:
    schema_version: int
    dataset_id: str
    case_id: str
    name: str
    kind: str
    artifact_id: str
    source_type: str
    source_uri: str | None
    retrieved_at: str | None
    license: str | None
    derived_from: list[str]
    description: str
    status: str
    created_at: str
    created_by: str


class DatasetRegistry:
    def __init__(self, cases: CaseManager, artifacts: ArtifactRegistry) -> None:
        self.cases = cases
        self.artifacts = artifacts

    def registry_path(self, case_id: str) -> Path:
        return self.cases.case_root(case_id) / "dataset_registry.jsonl"

    def list_records(self, case_id: str) -> list[dict[str, Any]]:
        path = self.registry_path(case_id)
        if not path.exists():
            return []
        records: list[dict[str, Any]] = []
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    records.append(json.loads(line))
        return records

    def current_records(self, case_id: str) -> list[dict[str, Any]]:
        current: dict[str, dict[str, Any]] = {}
        for record in self.list_records(case_id):
            current[record["dataset_id"]] = record
        return sorted(current.values(), key=lambda item: item["created_at"])

    def get(self, case_id: str, dataset_id: str) -> dict[str, Any]:
        for record in reversed(self.list_records(case_id)):
            if record["dataset_id"] == dataset_id:
                return record
        raise KeyError(f"dataset not found: {dataset_id}")

    def register(
        self,
        case_id: str,
        name: str,
        artifact_id: str,
        kind: DatasetKind,
        source_type: str,
        created_by: str,
        source_uri: str | None = None,
        retrieved_at: str | None = None,
        license_name: str | None = None,
        derived_from: list[str] | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        artifact = self.artifacts.get(case_id, artifact_id)
        parents = derived_from or []
        known_ids = {item["dataset_id"] for item in self.current_records(case_id)}
        missing_parents = sorted(set(parents) - known_ids)
        if missing_parents:
            raise ValueError(f"unknown parent datasets: {missing_parents}")
        if kind == DatasetKind.DERIVED and not parents:
            raise ValueError("DERIVED dataset requires derived_from")
        if kind != DatasetKind.DERIVED and parents:
            raise ValueError(f"{kind.value} dataset cannot declare derived_from")
        if kind == DatasetKind.OBSERVED and source_type == "generated":
            raise ValueError("OBSERVED dataset cannot use generated source")
        if artifact["case_id"] != case_id:
            raise ValueError("artifact belongs to another case")
        created_at = now_iso()
        record = DatasetRecord(
            schema_version=1,
            dataset_id=f"dataset-{uuid.uuid4().hex[:12]}",
            case_id=case_id,
            name=name.strip(),
            kind=kind.value,
            artifact_id=artifact_id,
            source_type=source_type,
            source_uri=source_uri,
            retrieved_at=retrieved_at,
            license=license_name,
            derived_from=parents,
            description=description.strip(),
            status=DatasetStatus.REGISTERED.value,
            created_at=created_at,
            created_by=created_by,
        )
        payload = asdict(record)
        append_jsonl(self.registry_path(case_id), payload)
        self._write_catalog(case_id)
        return payload

    def update_status(
        self,
        case_id: str,
        dataset_id: str,
        status: DatasetStatus,
        reason: str,
    ) -> dict[str, Any]:
        current = self.get(case_id, dataset_id)
        updated = {
            **current,
            "status": status.value,
            "status_reason": reason,
            "updated_at": now_iso(),
        }
        append_jsonl(self.registry_path(case_id), updated)
        self._write_catalog(case_id)
        return updated

    def _write_catalog(self, case_id: str) -> None:
        rows = self.current_records(case_id)
        lines = [
            "# Data Catalog",
            "",
            "| Dataset ID | Name | Kind | Status | Source | Artifact ID |",
            "|---|---|---|---|---|---|",
        ]
        for record in rows:
            lines.append(
                f"| `{record['dataset_id']}` | {record['name']} | `{record['kind']}` | "
                f"`{record['status']}` | {record['source_type']} | `{record['artifact_id']}` |"
            )
        atomic_write_text(
            self.cases.case_root(case_id) / "memory" / "data_catalog.md",
            "\n".join(lines) + "\n",
        )

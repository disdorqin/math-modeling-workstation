from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .datasets import DatasetRegistry
from .io_utils import append_jsonl, atomic_write_json, now_iso


class ClaimInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=3)
    claim_type: str = Field(min_length=3)
    evidence_artifact_ids: list[str] = Field(min_length=1)
    dataset_ids: list[str] = Field(default_factory=list)
    section_hint: str | None = None


class ClaimRegistry:
    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        datasets: DatasetRegistry,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.datasets = datasets

    def registry_path(self, case_id: str) -> Path:
        return self.cases.case_root(case_id) / "claim_registry.jsonl"

    def list_claims(self, case_id: str) -> list[dict[str, Any]]:
        path = self.registry_path(case_id)
        if not path.exists():
            return []
        claims: dict[str, dict[str, Any]] = {}
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    claim = json.loads(line)
                    claims[claim["claim_id"]] = claim
        return list(claims.values())

    def get(self, case_id: str, claim_id: str) -> dict[str, Any]:
        for claim in self.list_claims(case_id):
            if claim["claim_id"] == claim_id:
                return claim
        raise KeyError(f"claim not found: {claim_id}")

    def create(self, case_id: str, value: ClaimInput, created_by: str) -> dict[str, Any]:
        evidence = [self.artifacts.get(case_id, artifact_id) for artifact_id in value.evidence_artifact_ids]
        missing_eligibility = [item["artifact_id"] for item in evidence if not item.get("paper_eligible", False)]
        unknown_datasets: list[str] = []
        dataset_kinds: dict[str, str] = {}
        for dataset_id in value.dataset_ids:
            try:
                dataset_kinds[dataset_id] = self.datasets.get(case_id, dataset_id)["kind"]
            except KeyError:
                unknown_datasets.append(dataset_id)
        if unknown_datasets:
            raise ValueError(f"unknown datasets: {unknown_datasets}")
        status = "VERIFIED" if not missing_eligibility else "DRAFT"
        restrictions: list[str] = []
        if missing_eligibility:
            restrictions.append("evidence_not_paper_ready")
        if "SYNTHETIC" in dataset_kinds.values():
            restrictions.append("synthetic_data_claim")
        claim = {
            "schema_version": 1,
            "claim_id": f"claim-{uuid.uuid4().hex[:12]}",
            "case_id": case_id,
            **value.model_dump(mode="json"),
            "dataset_kinds": dataset_kinds,
            "status": status,
            "restrictions": restrictions,
            "created_by": created_by,
            "created_at": now_iso(),
        }
        append_jsonl(self.registry_path(case_id), claim)
        self._write_index(case_id)
        return claim

    def reject(self, case_id: str, claim_id: str, rejected_by: str, reason: str) -> dict[str, Any]:
        if not reason.strip():
            raise ValueError("claim rejection requires a reason")
        current = self.get(case_id, claim_id)
        updated = {
            **current,
            "status": "REJECTED",
            "rejected_by": rejected_by,
            "rejection_reason": reason,
            "updated_at": now_iso(),
        }
        append_jsonl(self.registry_path(case_id), updated)
        self._write_index(case_id)
        return updated

    def _write_index(self, case_id: str) -> None:
        root = self.cases.case_root(case_id)
        payload = {
            "schema_version": 1,
            "case_id": case_id,
            "claims": self.list_claims(case_id),
            "updated_at": now_iso(),
        }
        atomic_write_json(root / "memory" / "evidence_index.json", payload)


from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .case_manager import CaseManager
from .io_utils import append_jsonl, atomic_write_json, now_iso


class ApprovalEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: str
    case_id: str
    node_id: str
    actor_id: str = Field(min_length=2)
    actor_type: Literal["HUMAN", "SYSTEM"]
    action: Literal["APPROVE", "REJECT"]
    reason: str = Field(min_length=3)
    input_digest: str
    created_at: str


class BudgetPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_experiments: int = 20
    max_tokens: int = 120000
    max_wall_seconds: int = 3600
    max_artifacts: int = 500


class BudgetState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    policy: BudgetPolicy
    experiments: int = 0
    tokens: int = 0
    wall_seconds: float = 0.0
    artifacts: int = 0
    status: Literal["RUNNING", "EXHAUSTED"] = "RUNNING"


class ProvenancePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    data_classification: Literal["PUBLIC", "INTERNAL", "CONFIDENTIAL"] = "INTERNAL"
    allowed_providers: list[str] = Field(default_factory=list)
    redact_fields: list[str] = Field(default_factory=list)
    network_allowed: bool = False
    retention_days: int = 30


class ControlPlane:
    def __init__(self, cases: CaseManager) -> None:
        self.cases = cases

    def _path(self, case_id: str, *parts: str) -> Path:
        return self.cases.case_root(case_id).joinpath(*parts)

    def approve(self, case_id: str, node_id: str, actor_id: str, reason: str, input_digest: str, actor_type: str = "HUMAN") -> ApprovalEvent:
        if actor_type != "HUMAN":
            raise ValueError("approval requires an explicit human actor")
        event = ApprovalEvent(approval_id=f"approval-{uuid.uuid4().hex[:12]}", case_id=case_id, node_id=node_id, actor_id=actor_id, actor_type="HUMAN", action="APPROVE", reason=reason, input_digest=input_digest, created_at=now_iso())
        append_jsonl(self._path(case_id, "control", "approvals", "events.jsonl"), event.model_dump(mode="json"))
        return event

    def initialize_budget(self, case_id: str, policy: BudgetPolicy | None = None) -> BudgetState:
        state = BudgetState(policy=policy or BudgetPolicy())
        atomic_write_json(self._path(case_id, "control", "budgets", "state.json"), state.model_dump(mode="json"))
        return state

    def consume(self, case_id: str, *, experiments: int = 0, tokens: int = 0, wall_seconds: float = 0.0, artifacts: int = 0) -> BudgetState:
        path = self._path(case_id, "control", "budgets", "state.json")
        if not path.exists():
            state = self.initialize_budget(case_id)
        else:
            state = BudgetState.model_validate_json(path.read_text(encoding="utf-8"))
        state = state.model_copy(update={"experiments": state.experiments + experiments, "tokens": state.tokens + tokens, "wall_seconds": state.wall_seconds + wall_seconds, "artifacts": state.artifacts + artifacts})
        policy = state.policy
        exhausted = state.experiments > policy.max_experiments or state.tokens > policy.max_tokens or state.wall_seconds > policy.max_wall_seconds or state.artifacts > policy.max_artifacts
        if exhausted:
            state = state.model_copy(update={"status": "EXHAUSTED"})
        atomic_write_json(path, state.model_dump(mode="json"))
        if exhausted:
            raise RuntimeError("CONTROL_BUDGET_EXHAUSTED")
        return state

    def set_provenance_policy(self, case_id: str, policy: ProvenancePolicy) -> ProvenancePolicy:
        atomic_write_json(self._path(case_id, "control", "provenance", "policy.json"), policy.model_dump(mode="json"))
        return policy


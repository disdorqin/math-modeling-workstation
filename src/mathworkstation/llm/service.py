from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

from ..access_policy import DEFAULT_NODE_POLICIES
from ..artifact_registry import ArtifactRegistry
from ..case_manager import CaseManager
from ..checkpoint_manager import CheckpointManager
from ..io_utils import atomic_write_json, read_json
from ..session_manager import SessionManager
from .audit import LLMAuditLogger
from .budget import LLMBudgetManager
from .router import ChatRequest, LLMRouter


class CaseLLMService:
    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        sessions: SessionManager,
        checkpoints: CheckpointManager,
        router: LLMRouter,
        max_calls_per_session: int = 50,
        max_tokens_per_session: int = 300000,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.sessions = sessions
        self.checkpoints = checkpoints
        self.router = router
        self.max_calls_per_session = max_calls_per_session
        self.max_tokens_per_session = max_tokens_per_session

    def invoke(
        self,
        case_id: str,
        session_id: str,
        node_id: str,
        messages: list[dict[str, str]],
        input_artifact_ids: list[str],
        model: str | None = None,
        max_tokens: int = 2000,
        temperature: float = 0.2,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        root = self.cases.case_root(case_id)
        session_root = root / "sessions" / session_id
        session = read_json(session_root / "session.json")
        if session["case_id"] != case_id or session["status"] != "ACTIVE":
            raise ValueError("session is not active for this case")
        workflow = self.checkpoints.snapshot(case_id)
        if node_id not in workflow["definitions"]:
            raise KeyError(f"unknown workflow node: {node_id}")
        inputs = [self.artifacts.get(case_id, artifact_id) for artifact_id in input_artifact_ids]
        policy = DEFAULT_NODE_POLICIES.get(node_id)
        if policy:
            for artifact in inputs:
                policy.assert_read(artifact["path"])
        if not messages or not any(message.get("role") == "user" for message in messages):
            raise ValueError("messages require at least one user message")

        budget = LLMBudgetManager(
            session_root / "llm_budget.json",
            self.max_calls_per_session,
            self.max_tokens_per_session,
        )
        budget.assert_available(max_tokens)
        self.router.audit = LLMAuditLogger(root / ".internal" / "llm_events.jsonl")
        result = self.router.chat(
            ChatRequest(
                messages=messages,
                model=model,
                max_tokens=max_tokens,
                temperature=temperature,
                response_format=response_format,
                metadata={"case_id": case_id, "session_id": session_id, "node_id": node_id},
            )
        )
        budget_state = budget.charge(result.usage, max_tokens)
        for message in messages:
            if message.get("role") == "user":
                self.sessions.append_message(case_id, session_id, "user", message.get("content", ""))
        self.sessions.append_message(case_id, session_id, "assistant", result.content)

        response_id = f"llm-{uuid.uuid4().hex[:12]}"
        response_directory = session_root / "responses"
        response_directory.mkdir(exist_ok=True)
        response_path = response_directory / f"{response_id}.json"
        payload = {
            "schema_version": 1,
            "response_id": response_id,
            "case_id": case_id,
            "session_id": session_id,
            "node_id": node_id,
            "route": result.route_name,
            "model": result.model,
            "usage": result.usage,
            "latency_ms": result.latency_ms,
            "attempts": result.attempts,
            "content": result.content,
            "input_artifact_ids": input_artifact_ids,
        }
        atomic_write_json(response_path, payload)
        status = read_json(root / "status.json")
        artifact = self.artifacts.register_existing(
            case_id,
            response_path.relative_to(root).as_posix(),
            "llm_response",
            "llm",
            run_id=status.get("active_run_id"),
            upstream=input_artifact_ids,
            paper_eligible=False,
        )
        return {
            "response": payload,
            "artifact_id": artifact["artifact_id"],
            "budget": budget_state,
        }


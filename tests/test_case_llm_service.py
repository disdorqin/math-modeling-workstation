import json
import os
from pathlib import Path

import httpx
import pytest

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.checkpoint_manager import CheckpointManager
from mathworkstation.llm.config import RouteConfig, RouterConfig
from mathworkstation.llm.router import LLMRouter
from mathworkstation.llm.service import CaseLLMService
from mathworkstation.session_manager import SessionManager


def service(tmp_path: Path):
    os.environ["CASE_LLM_TEST_KEY"] = "fake-case-service-credential"
    cases = CaseManager(tmp_path / "output")
    artifacts = ArtifactRegistry(cases)
    sessions = SessionManager(cases)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "id": "response-test",
                "choices": [{"message": {"content": "structured answer"}}],
                "usage": {"prompt_tokens": 8, "completion_tokens": 2, "total_tokens": 10},
            },
        )

    router = LLMRouter(
        RouterConfig(
            routes=[
                RouteConfig(
                    name="test",
                    base_url="https://llm.test/v1",
                    api_key_env="CASE_LLM_TEST_KEY",
                    models=["test-model"],
                )
            ]
        ),
        transport=httpx.MockTransport(handler),
    )
    return cases, artifacts, sessions, CaseLLMService(
        cases,
        artifacts,
        sessions,
        CheckpointManager(cases),
        router,
        max_calls_per_session=2,
        max_tokens_per_session=50,
    )


def test_case_llm_response_is_registered_and_audited_without_content(tmp_path: Path) -> None:
    cases, artifacts, sessions, llm = service(tmp_path)
    case = cases.create_case("SM", "LLM")
    session = sessions.create_session(case["case_id"])
    problem = cases.case_root(case["case_id"]) / "input" / "problem" / "original" / "problem.md"
    problem.write_text("private problem", encoding="utf-8")
    problem_artifact = artifacts.register_existing(
        case["case_id"], "input/problem/original/problem.md", "problem_original", "human"
    )
    result = llm.invoke(
        case["case_id"],
        session["session_id"],
        "problem_analysis",
        [{"role": "user", "content": "private prompt"}],
        [problem_artifact["artifact_id"]],
        max_tokens=20,
    )
    assert result["response"]["content"] == "structured answer"
    assert artifacts.get(case["case_id"], result["artifact_id"])["artifact_type"] == "llm_response"
    assert result["budget"]["tokens_used"] == 10
    audit = (cases.case_root(case["case_id"]) / ".internal" / "llm_events.jsonl").read_text(encoding="utf-8")
    assert "private prompt" not in audit
    assert "structured answer" not in audit
    assert "fake-case-service-credential" not in audit
    conversation = (
        cases.case_root(case["case_id"])
        / "sessions"
        / session["session_id"]
        / "conversation.jsonl"
    ).read_text(encoding="utf-8")
    assert "private prompt" in conversation
    assert "structured answer" in conversation


def test_case_llm_enforces_node_artifact_scope_and_budget(tmp_path: Path) -> None:
    cases, artifacts, sessions, llm = service(tmp_path)
    case = cases.create_case("SM", "LLM Guard")
    session = sessions.create_session(case["case_id"])
    result_path = cases.case_root(case["case_id"]) / "results" / "metrics" / "metric.json"
    result_path.write_text("{}", encoding="utf-8")
    result_artifact = artifacts.register_existing(
        case["case_id"], "results/metrics/metric.json", "model_metrics", "python"
    )
    with pytest.raises(Exception, match="cannot read"):
        llm.invoke(
            case["case_id"],
            session["session_id"],
            "problem_analysis",
            [{"role": "user", "content": "x"}],
            [result_artifact["artifact_id"]],
            max_tokens=20,
        )
    with pytest.raises(RuntimeError, match="token budget"):
        llm.invoke(
            case["case_id"],
            session["session_id"],
            "input_validation",
            [{"role": "user", "content": "x"}],
            [],
            max_tokens=51,
        )

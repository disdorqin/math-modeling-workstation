import json
import os
from pathlib import Path

import httpx
import pytest

from mathworkstation.llm.audit import LLMAuditLogger
from mathworkstation.llm.config import RouteConfig, RouterConfig
from mathworkstation.llm.router import AllRoutesFailedError, ChatRequest, LLMRouter


def config() -> RouterConfig:
    os.environ["TEST_PRIMARY_KEY"] = "fake-primary-credential"
    os.environ["TEST_BACKUP_KEY"] = "fake-backup-credential"
    return RouterConfig(
        routes=[
            RouteConfig(
                name="primary",
                base_url="https://primary.test/v1",
                api_key_env="TEST_PRIMARY_KEY",
                models=["test-model"],
                priority=1,
                cooldown_seconds=120,
            ),
            RouteConfig(
                name="backup",
                base_url="https://backup.test/v1",
                api_key_env="TEST_BACKUP_KEY",
                models=["test-model"],
                priority=2,
            ),
        ],
        max_attempts=2,
        max_total_tokens=100,
    )


def test_retryable_failure_switches_route_and_opens_circuit(tmp_path: Path) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.host)
        if request.url.host == "primary.test":
            return httpx.Response(503, json={"error": {"message": "unavailable"}})
        return httpx.Response(
            200,
            json={
                "id": "response-1",
                "choices": [{"message": {"content": "OK"}}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
            },
        )

    audit_path = tmp_path / "audit.jsonl"
    router = LLMRouter(config(), LLMAuditLogger(audit_path), httpx.MockTransport(handler))
    request = ChatRequest([{"role": "user", "content": "secret prompt"}], model="test-model", max_tokens=10)
    result = router.chat(request)
    assert result.route_name == "backup"
    assert result.attempts == 2
    assert calls == ["primary.test", "backup.test"]
    assert not router.health_snapshot()["primary"]["available"]

    calls.clear()
    second = router.chat(request)
    assert second.route_name == "backup"
    assert calls == ["backup.test"]
    audit = audit_path.read_text(encoding="utf-8")
    assert "secret prompt" not in audit
    assert "fake-primary-credential" not in audit


def test_non_retryable_bad_request_stops_failover() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(400, json={"error": {"message": "bad request"}})

    router = LLMRouter(config(), transport=httpx.MockTransport(handler))
    with pytest.raises(AllRoutesFailedError) as caught:
        router.chat(ChatRequest([{"role": "user", "content": "x"}], max_tokens=10))
    assert calls == 1
    assert caught.value.attempts[0]["retryable"] is False


def test_token_budget_rejected_before_network() -> None:
    router = LLMRouter(config(), transport=httpx.MockTransport(lambda request: httpx.Response(500)))
    with pytest.raises(ValueError, match="token budget"):
        router.chat(ChatRequest([{"role": "user", "content": "x"}], max_tokens=101))


def test_route_configuration_contains_environment_names_only(tmp_path: Path) -> None:
    payload = json.loads(Path("config/llm-routes.example.json").read_text(encoding="utf-8"))
    encoded = json.dumps(payload)
    assert "api_key_env" in encoded
    assert "sk-" not in encoded


def test_failover_can_downgrade_to_route_supported_model() -> None:
    os.environ["TEST_PRIMARY_KEY"] = "fake-primary-credential"
    os.environ["TEST_BACKUP_KEY"] = "fake-backup-credential"
    router_config = RouterConfig(
        routes=[
            RouteConfig(
                name="primary",
                base_url="https://primary.test/v1",
                api_key_env="TEST_PRIMARY_KEY",
                models=["mini"],
                priority=1,
            ),
            RouteConfig(
                name="backup",
                base_url="https://backup.test/v1",
                api_key_env="TEST_BACKUP_KEY",
                models=["full"],
                priority=2,
            ),
        ]
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "primary.test":
            return httpx.Response(503, json={"error": "down"})
        assert json.loads(request.content)["model"] == "full"
        return httpx.Response(200, json={"choices": [{"message": {"content": "OK"}}]})

    result = LLMRouter(router_config, transport=httpx.MockTransport(handler)).chat(
        ChatRequest([{"role": "user", "content": "x"}], model="mini")
    )
    assert result.route_name == "backup"
    assert result.model == "full"

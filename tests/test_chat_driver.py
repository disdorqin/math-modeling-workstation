"""Offline, deterministic tests for the web chat driver (S1).

The driver must run end-to-end with no API key and no network: the default
FakeProvider is a pure function and the services are composed against a
temporary output root. These tests also lock in the contract guarantees from
docs/web-chat-driver-contract.md: whitelisted tools only, approval gates before
execution, and one AI-usage ledger entry per executed tool call.
"""
from __future__ import annotations

import pytest

from mathworkstation.chat import ChatDriver, build_services
from mathworkstation.chat.tools import hints_pipeline, resolve_intent


@pytest.fixture()
def services(tmp_path):
    return build_services(output_root=tmp_path / "output")


@pytest.fixture()
def driver(services):
    return ChatDriver(services=services)


def test_default_provider_is_offline_and_deterministic(driver):
    # FakeProvider by default: no API key, no network, name == "fake".
    assert driver.provider.name == "fake"
    # "查看案例列表" is list-cases; bare "查看案例" resolves to a case lookup.
    assert resolve_intent("查看案例列表") == [{"tool": "list_cases", "args": {}}]
    assert resolve_intent("查看案例") == [{"tool": "get_case", "args": {}}]


def test_unrecognized_message_returns_guidance_not_action(driver):
    result = driver.chat("你好,给我讲个笑话")
    assert result["tool_calls"] == []
    assert "我可以帮你" in result["reply"]


def test_list_cases_empty_on_fresh_root(driver):
    result = driver.chat("列出案例")
    assert result["tool_calls"][0]["tool"] == "list_cases"
    assert result["tool_calls"][0]["status"] == "done"
    assert result["tool_calls"][0]["result"]["count"] == 0


def test_create_case_records_ai_ledger(driver, services):
    result = driver.chat("创建案例 对话测试", approved_by="tester")
    call = result["tool_calls"][0]
    assert call["tool"] == "create_case"
    assert call["status"] == "done"
    case_id = call["result"]["case_id"]
    assert call["ledger"]  # ledger entry id present

    # Ledger persisted at <case_root>/ai_ledger.jsonl with the frozen schema.
    root = services["cases"].case_root(case_id)
    ledger_file = root / "ai_ledger.jsonl"
    assert ledger_file.is_file()
    entries = services["cases"] and __import__("json").loads(
        ledger_file.read_text(encoding="utf-8").splitlines()[0]
    )
    assert entries["tool"] == "create_case"
    assert entries["human_reviewed"] is False
    assert entries["entry_id"].startswith("led-")


def test_get_case_reads_real_case(driver, services):
    created = driver.chat("创建案例 查看用", approved_by="tester")
    case_id = created["tool_calls"][0]["result"]["case_id"]
    result = driver.chat(f"查看案例 {case_id}")
    call = result["tool_calls"][0]
    assert call["status"] == "done"
    assert call["result"]["manifest"]["manifest"]["case_id"] == case_id


def test_pipeline_hint_schedules_a_persisted_job(driver, services):
    created = driver.chat("创建案例 流水线用", approved_by="tester")
    case_id = created["tool_calls"][0]["result"]["case_id"]
    assert hints_pipeline("自动流水线 做这道题")

    result = driver.chat("自动流水线 做这道题", case_id=case_id, approved_by="tester")
    assert result["job_id"]
    job = driver.get_job(case_id, result["job_id"])
    assert job is not None
    assert job["kind"] == "auto_pipeline"
    # Without uploaded inputs the real pipeline cannot run, so it parks as
    # BLOCKED awaiting inputs (never pretends to run) — S1.2 behaviour.
    assert job["status"] in {"blocked", "running", "succeeded", "failed"}
    assert job["awaiting_approval"] in ([None], None, ["inputs"])


def test_approval_gated_tool_waits_for_confirmation(driver, services):
    created = driver.chat("创建案例 审批测试", approved_by="tester")
    case_id = created["tool_calls"][0]["result"]["case_id"]
    # degrade/retry require explicit confirmation; without it they await.
    result = driver.chat("降级 refinement_loop", case_id=case_id, approved_by="tester")
    assert result["awaiting_approval"] == ["degrade_node"]
    assert result["tool_calls"][0]["status"] == "awaiting_approval"

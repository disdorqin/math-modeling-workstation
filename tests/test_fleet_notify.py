"""fleet_notify schema tests.

Guards the delivery contract between writers and the inbox_bridge:
every notification must carry a stable ``msg_id`` (shared between the mailbox
and broadcast copies) plus a ``type`` field, so the bridge can deduplicate the
two channels and never double-inject / never silently drop.
"""
from __future__ import annotations

import json
import os

import pytest

from mathworkstation import fleet_notify


@pytest.fixture()
def fleet_tmp(tmp_path, monkeypatch):
    """Point fleet_notify at a temp AI_Memory dir."""
    fleet_dir = tmp_path / "fleet"
    (fleet_dir / "notify").mkdir(parents=True)
    (fleet_dir / "mailbox").mkdir(parents=True)
    monkeypatch.setattr(fleet_notify, "FLEET_DIR", fleet_dir)
    monkeypatch.setattr(fleet_notify, "BROADCAST_LOG", fleet_dir / "notify" / "broadcast.jsonl")
    monkeypatch.setattr(fleet_notify, "MAILBOX_DIR", fleet_dir / "mailbox")
    return fleet_dir


def _read_jsonl(path):
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_notify_task_complete_writes_msg_id_shared_across_channels(fleet_tmp):
    result = fleet_notify.notify_task_complete("freebuff", "t-test-001", "任务完成")

    assert result["broadcast"] is True
    assert "claude_code" in result["mailboxes"]

    broadcast = _read_jsonl(fleet_tmp / "notify" / "broadcast.jsonl")
    mailbox = _read_jsonl(fleet_tmp / "mailbox" / "claude_code.jsonl")

    assert len(broadcast) == 1
    assert len(mailbox) == 1

    b_entry, m_entry = broadcast[0], mailbox[0]
    # Both copies share the same stable msg_id -> bridge dedups them
    assert b_entry["msg_id"] == m_entry["msg_id"]
    assert len(b_entry["msg_id"]) == 16
    # Schema fields present
    assert b_entry["type"] == "broadcast"
    assert m_entry["type"] == "mail"
    assert b_entry["from"] == "freebuff"
    assert b_entry["targets"] == ["claude_code"]
    assert "t-test-001" in b_entry["subject"]


def test_notify_broadcast_writes_mailboxes_with_matching_msg_id(fleet_tmp):
    result = fleet_notify.notify_broadcast("opencode", "通知", "大家好", targets=["freebuff"])

    assert result["broadcast"] is True
    assert "freebuff" in result["mailboxes"]

    broadcast = _read_jsonl(fleet_tmp / "notify" / "broadcast.jsonl")
    mailbox = _read_jsonl(fleet_tmp / "mailbox" / "freebuff.jsonl")

    assert len(broadcast) == 1
    assert len(mailbox) == 1
    assert broadcast[0]["msg_id"] == mailbox[0]["msg_id"]
    assert broadcast[0]["type"] == "broadcast"
    assert mailbox[0]["type"] == "mail"


def test_msg_id_is_stable_for_same_content(fleet_tmp):
    """Same sender/subject/body/timestamp -> same msg_id (dedup reliability)."""
    from datetime import datetime, timezone

    ts = datetime.now(timezone.utc).isoformat()
    a = fleet_notify._entry("freebuff", "主题", "正文", "claude_code", ["claude_code"], ts)
    b = fleet_notify._entry("freebuff", "主题", "正文", "claude_code", ["claude_code"], ts)
    assert a["msg_id"] == b["msg_id"]
    assert a["msg_id"] != fleet_notify._entry("freebuff", "主题", "不同正文", "claude_code", ["claude_code"], ts)["msg_id"]

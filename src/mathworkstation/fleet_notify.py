"""Fleet auto-notify: send completion notifications to commander after task_submit.

Usage from any agent:
    from mathworkstation.fleet_notify import notify_task_complete
    notify_task_complete("opencode", "t1f3dc82d", "学习循环接线完成,292测试通过")

Or via CLI:
    python -m mathworkstation.fleet_notify --agent opencode --task-id t123 --message "done"
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

FLEET_DIR = Path(os.environ.get("AI_MEMORY_DIR", r"D:\AI_Memory\fleet"))
BROADCAST_LOG = FLEET_DIR / "notify" / "broadcast.jsonl"
MAILBOX_DIR = FLEET_DIR / "mailbox"
KNOWN_AGENTS = ["claude_code", "opencode", "freebuff", "workbuddy", "cline"]


def _entry(sender: str, subject: str, body: str, to: str, targets: list[str], now: str) -> dict:
    """Build a schema-consistent entry: msg_id shared across mailbox+broadcast copies
    so the delivery bridge can deduplicate the two channels by stable key."""
    mid = hashlib.sha1("|".join([sender, to, subject, body, now]).encode("utf-8")).hexdigest()[:16]
    return {
        "timestamp": now,
        "from": sender,
        "to": to,
        "subject": subject,
        "body": body,
        "targets": targets,
        "msg_id": mid,
        "type": "mail",
    }


def notify_task_complete(agent: str, task_id: str, message: str, targets: list[str] | None = None) -> dict:
    """Send a task completion notification to commander (and optionally all agents).

    Writes to both broadcast.jsonl and claude_code's mailbox so the
    FleetNotifierPlugin picks it up and shows it in the dialog.
    """
    now = datetime.now(timezone.utc).isoformat()
    subject = f"【任务完成】{task_id}"
    body = f"{agent} 完成任务 {task_id}: {message}"

    entry = _entry(agent, subject, body, "claude_code", targets or ["claude_code"], now)

    results = {"broadcast": False, "mailboxes": []}

    # Write to broadcast log (type=broadcast, same msg_id as mailbox copies)
    broadcast_entry = {**entry, "type": "broadcast"}
    BROADCAST_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(BROADCAST_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(broadcast_entry, ensure_ascii=False) + "\n")
    results["broadcast"] = True

    # Write to target mailboxes (type=mail, same msg_id -> dedup by bridge)
    write_to = targets if targets and targets != ["all"] else ["claude_code"]
    for agent_name in write_to:
        if agent_name == agent:
            continue
        mailbox = MAILBOX_DIR / f"{agent_name}.jsonl"
        mailbox_entry = {**entry, "type": "mail", "to": agent_name}
        try:
            with open(mailbox, "a", encoding="utf-8") as f:
                f.write(json.dumps(mailbox_entry, ensure_ascii=False) + "\n")
            results["mailboxes"].append(agent_name)
        except Exception as e:
            results["mailboxes"].append(f"{agent_name}:ERROR:{e}")

    return results


def notify_broadcast(agent: str, subject: str, body: str, targets: list[str] | None = None) -> dict:
    """Send a general broadcast notification."""
    now = datetime.now(timezone.utc).isoformat()
    entry = _entry(agent, subject, body, "*", targets or ["all"], now)
    entry["type"] = "broadcast"

    results = {"broadcast": False, "mailboxes": []}

    BROADCAST_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(BROADCAST_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    results["broadcast"] = True

    write_to = targets if targets and targets != ["all"] else KNOWN_AGENTS
    for agent_name in write_to:
        if agent_name == agent:
            continue
        mailbox = MAILBOX_DIR / f"{agent_name}.jsonl"
        mailbox_entry = {**entry, "type": "mail", "to": agent_name}
        try:
            with open(mailbox, "a", encoding="utf-8") as f:
                f.write(json.dumps(mailbox_entry, ensure_ascii=False) + "\n")
            results["mailboxes"].append(agent_name)
        except Exception as e:
            results["mailboxes"].append(f"{agent_name}:ERROR:{e}")

    return results


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Fleet auto-notify")
    parser.add_argument("--agent", required=True, help="Sender agent name")
    parser.add_argument("--task-id", default="", help="Task ID")
    parser.add_argument("--message", required=True, help="Notification message")
    parser.add_argument("--to", nargs="*", default=["claude_code"], help="Target agents")
    args = parser.parse_args()

    if args.task_id:
        result = notify_task_complete(args.agent, args.task_id, args.message, args.to)
    else:
        result = notify_broadcast(args.agent, "通知", args.message, args.to)
    print(json.dumps(result, ensure_ascii=False, indent=2))

"""Real-time layer on top of the driver-owned job store (contract 2.2 / 2.5).

Persistence belongs to S1 (``mathworkstation.chat.jobs.JobManager``, files at
``<case_root>/jobs/<job_id>.json``). The shell does **not** keep a second job
store; it adds the two things S1 deliberately left to the web layer:

* an in-process **event bus** that fans job events out to WebSocket clients
  (with a replay buffer so a reconnecting browser misses nothing);
* an async **runner** that advances a job, blocks at the approval gate, and
  publishes ``progress`` / ``approval_required`` / ``ledger`` / ``done``.

S1's ``ChatDriver._schedule_pipeline`` currently only *schedules* a pipeline
("execution lands in S1.1/S3"). Until that lands, the runner advances jobs in
**rehearsal mode**: the event sequence and the approval gate are real, but no
Case evidence is written. Every rehearsal job says so in its payload, its logs,
and its result, so a rehearsal can never be mistaken for a real pipeline run.
"""

from __future__ import annotations

import asyncio
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

from mathworkstation.chat.jobs import JobManager as CoreJobManager

from . import ledger

QUEUED = "queued"
RUNNING = "running"
WAITING_APPROVAL = "waiting_approval"
SUCCEEDED = "succeeded"
FAILED = "failed"
CANCELLED = "cancelled"

# Representative pipeline for rehearsal mode; mirrors the real DAG order and
# stops for approval exactly where the contract requires.
REHEARSAL_NODES: list[tuple[str, bool]] = [
    ("input_validation", False),
    ("data_registration", False),
    ("problem_analysis", False),
    ("eda", False),
    ("model_selection", True),  # human approval gate
    ("model_comparison", False),
    ("sensitivity", False),
    ("paper_draft", False),
    ("consistency_check", False),
    ("export", False),
]


def _now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


# --------------------------------------------------------------------------
# event bus
# --------------------------------------------------------------------------
class EventBus:
    """Fan-out of job events to WebSocket subscribers, with replay buffer."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._history: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._lock = asyncio.Lock()

    async def subscribe(self, job_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        async with self._lock:
            self._subscribers[job_id].append(queue)
            for event in self._history[job_id]:  # replay for reconnects
                queue.put_nowait(event)
        return queue

    async def unsubscribe(self, job_id: str, queue: asyncio.Queue) -> None:
        async with self._lock:
            if queue in self._subscribers.get(job_id, []):
                self._subscribers[job_id].remove(queue)

    async def publish(self, job_id: str, event: dict[str, Any]) -> None:
        event = {"ts": _now(), **event}
        async with self._lock:
            self._history[job_id].append(event)
            if len(self._history[job_id]) > 500:
                self._history[job_id] = self._history[job_id][-500:]
            targets = list(self._subscribers.get(job_id, []))
        for queue in targets:
            queue.put_nowait(event)

    def history(self, job_id: str) -> list[dict[str, Any]]:
        return list(self._history.get(job_id, []))


# --------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------
class JobRunner:
    """Drives jobs and streams their events; storage stays in S1's JobManager."""

    def __init__(self, services: Any, bus: EventBus) -> None:
        self.services = services
        self.bus = bus
        self._tasks: dict[str, asyncio.Task] = {}
        self._approvals: dict[str, asyncio.Event] = {}
        self._cancelled: set[str] = set()
        self._case_of: dict[str, str] = {}

    # -- store access -----------------------------------------------------
    def store(self, case_id: str) -> CoreJobManager:
        return CoreJobManager(self.services.case_root(case_id))

    def get(self, job_id: str, case_id: str | None = None) -> dict[str, Any] | None:
        case_ids = [case_id] if case_id else [self._case_of.get(job_id)] if self._case_of.get(job_id) else []
        if not case_ids:
            case_ids = [c["case_id"] for c in self.services.list_cases()]
        for cid in case_ids:
            if not cid:
                continue
            job = self.store(cid).get(job_id)
            if job is not None:
                job.setdefault("case_id", cid)
                self._case_of[job_id] = cid
                return job
        return None

    def list_for_case(self, case_id: str) -> list[dict[str, Any]]:
        return self.store(case_id).list()

    # -- lifecycle --------------------------------------------------------
    def create(self, case_id: str, kind: str, payload: dict[str, Any], approved_by: str) -> dict[str, Any]:
        payload = dict(payload or {})
        payload.update({"mode": "rehearsal", "requested_by": approved_by, "requested_at": _now()})
        job = self.store(case_id).create(kind=kind, payload=payload, approved_by=approved_by)
        job["case_id"] = case_id
        self._case_of[job["job_id"]] = case_id
        ledger.record(
            self.services.case_root(case_id),
            tool=kind,
            model="deterministic",
            purpose=f"创建后台任务 {kind}(演练模式，未执行真实流水线)",
            stage="job_create",
            user_input=str(payload)[:400],
            output_adopted=False,
            used_ai=False,
            extra={"job_id": job["job_id"], "requested_by": approved_by},
        )
        return job

    def start(self, job: dict[str, Any]) -> None:
        job_id = job["job_id"]
        if job_id in self._tasks and not self._tasks[job_id].done():
            return
        self._approvals.setdefault(job_id, asyncio.Event())
        self._cancelled.discard(job_id)
        self._tasks[job_id] = asyncio.create_task(self._run(job))

    def approve(self, job_id: str) -> bool:
        event = self._approvals.get(job_id)
        if event is None:
            return False
        event.set()
        return True

    def cancel(self, job_id: str) -> None:
        self._cancelled.add(job_id)
        event = self._approvals.get(job_id)
        if event:
            event.set()

    # -- execution --------------------------------------------------------
    async def _run(self, job: dict[str, Any]) -> None:
        job_id = job["job_id"]
        case_id = job.get("case_id") or self._case_of.get(job_id)
        store = self.store(case_id)
        case_root = self.services.case_root(case_id)
        try:
            store.update(job_id, status=RUNNING)
            store.log(job_id, "info", f"任务启动 kind={job.get('kind')} 模式=演练(真实执行待 S1.1/S3)")
            await self.bus.publish(job_id, {"type": "status", "status": RUNNING})

            current = store.get(job_id) or job
            done = set((current.get("payload") or {}).get("completed_nodes") or [])
            total = len(REHEARSAL_NODES)

            for index, (node, needs_approval) in enumerate(REHEARSAL_NODES, start=1):
                if job_id in self._cancelled:
                    store.update(job_id, status=CANCELLED)
                    await self.bus.publish(job_id, {"type": "cancelled"})
                    return
                if node in done:
                    continue

                progress = round((index - 1) / total, 3)
                store.update(job_id, status=RUNNING, current_node=node, progress=progress)
                await self.bus.publish(
                    job_id,
                    {"type": "progress", "node": node, "status": "RUNNING", "progress": progress},
                )
                await asyncio.sleep(0.6)  # rehearsal pacing, not real compute

                if needs_approval:
                    store.update(job_id, status=WAITING_APPROVAL, awaiting_approval=[node])
                    store.log(job_id, "warn", f"节点 {node} 需人工审批，已停等")
                    await self.bus.publish(job_id, {"type": "approval_required", "nodes": [node]})

                    event = self._approvals.setdefault(job_id, asyncio.Event())
                    event.clear()
                    await event.wait()

                    if job_id in self._cancelled:
                        store.update(job_id, status=CANCELLED)
                        await self.bus.publish(job_id, {"type": "cancelled"})
                        return
                    store.update(job_id, status=RUNNING, awaiting_approval=None)
                    store.log(job_id, "info", f"节点 {node} 审批通过，继续执行")

                done.add(node)
                progress = round(index / total, 3)
                payload = dict((store.get(job_id) or {}).get("payload") or {})
                payload["completed_nodes"] = sorted(done)
                store.update(job_id, progress=progress, payload=payload)
                await self.bus.publish(
                    job_id,
                    {"type": "progress", "node": node, "status": "SUCCEEDED", "progress": progress},
                )

                entry = ledger.record(
                    case_root,
                    tool=job.get("kind", "auto_pipeline"),
                    model="deterministic",
                    purpose=f"演练节点 {node}",
                    stage=node,
                    output_adopted=False,
                    used_ai=False,
                    extra={"job_id": job_id, "rehearsal": True},
                )
                await self.bus.publish(job_id, {"type": "ledger", "entry_id": entry["entry_id"]})

            result = {
                "mode": "rehearsal",
                "note": "演练完成：事件序列与审批门已验证；未写入任何 Case 证据。"
                "真实执行由 S1.1/S3 的 AutoPipelineService 接管。",
                "nodes": sorted(done),
            }
            store.update(job_id, status=SUCCEEDED, current_node=None, progress=1.0, result=result)
            store.log(job_id, "info", "任务完成(演练)")
            await self.bus.publish(job_id, {"type": "done", "result": result})
        except asyncio.CancelledError:  # pragma: no cover
            store.update(job_id, status=CANCELLED)
            raise
        except Exception as exc:  # pragma: no cover - defensive
            store.update(job_id, status=FAILED, result={"error": str(exc)})
            await self.bus.publish(job_id, {"type": "error", "message": str(exc)})

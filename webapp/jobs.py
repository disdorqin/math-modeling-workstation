"""Real-time layer on top of the driver-owned job store (contract 2.2 / 2.5).

Persistence belongs to S1 (``mathworkstation.chat.jobs.JobManager``, files at
``<case_root>/jobs/<job_id>.json``). The shell does **not** keep a second job
store; it adds the two things S1 deliberately left to the web layer:

* an in-process **event bus** that fans job events out to WebSocket clients
  (with a replay buffer so a reconnecting browser misses nothing);
* an async **runner** that advances a job, blocks at the approval gate, and
  publishes ``progress`` / ``approval_required`` / ``ledger`` / ``done``.

**S1.3 — real events, no simulation.** S1.2 landed real execution: the driver's
``ChatDriver._schedule_pipeline`` now runs ``AutoPipelineService.run()`` in a
worker thread. When a job carries real inputs (``problem_source`` +
``data_source``) the runner no longer *simulates* anything — it installs the
``progress_callback`` / ``approval_callback`` pair built by
:meth:`JobRunner.build_pipeline_callbacks`, forwards the pipeline's genuine
events onto the bus, and blocks the worker thread at each of the four real
approval nodes (``data_registration``, ``model_selection``, ``paper_ready``,
``final_review``) until a human approves through the web shell.

The legacy **rehearsal mode** survives only as the no-input demo path (a job
created without real sources): its event sequence and approval gate are real,
but no Case evidence is written, and every such job says ``mode=rehearsal`` in
its payload, logs and result — so it can never be mistaken for a real run.
Real jobs are tagged ``mode=real``.
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections import defaultdict
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Callable

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

# Natural order of the real pipeline (mirrors AutoPipelineService); used only to
# estimate the progress bar for the web shell. The authoritative node state
# lives in the workflow checkpoints, not here.
REAL_NODES: list[str] = [
    "problem_ingest",
    "data_registration",
    "problem_analysis",
    "eda",
    "model_selection",
    "model_comparison",
    "sensitivity",
    "paper_draft",
    "paper_ready",
    "consistency_check",
    "final_review",
    "export",
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
        self._tlock = threading.Lock()
        self._loop: "asyncio.AbstractEventLoop | None" = None

    async def subscribe(self, job_id: str) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
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
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            pass
        async with self._lock:
            self._history[job_id].append(event)
            if len(self._history[job_id]) > 500:
                self._history[job_id] = self._history[job_id][-500:]
            targets = list(self._subscribers.get(job_id, []))
        for queue in targets:
            queue.put_nowait(event)

    def history(self, job_id: str) -> list[dict[str, Any]]:
        return list(self._history.get(job_id, []))

    def publish_sync(self, job_id: str, event: dict[str, Any]) -> None:
        """Thread-safe publish for callbacks fired from pipeline worker threads.

        The real pipeline (``PipelineRunner``) emits progress/approval events from
        a worker thread, not the event loop. We append to history under a lock and
        fan out to subscribers via ``loop.call_soon_threadsafe`` so the WebSocket
        layer (which lives on the event loop) receives them safely.
        """
        event = {"ts": _now(), **event}
        with self._tlock:
            self._history[job_id].append(event)
            if len(self._history[job_id]) > 500:
                self._history[job_id] = self._history[job_id][-500:]
            targets = list(self._subscribers.get(job_id, []))
        loop = self._loop
        if loop is not None:
            for queue in targets:
                loop.call_soon_threadsafe(queue.put_nowait, event)
        else:
            for queue in targets:
                try:
                    queue.put_nowait(event)
                except Exception:
                    pass


# --------------------------------------------------------------------------
# runner
# --------------------------------------------------------------------------
class JobRunner:
    """Drives jobs and streams their events; storage stays in S1's JobManager."""

    def __init__(self, services: Any, bus: EventBus, driver: Any = None) -> None:
        self.services = services
        self.bus = bus
        self.driver = driver
        self._tasks: dict[str, asyncio.Task] = {}
        self._approvals: dict[str, asyncio.Event] = {}
        self._thread_approvals: dict[str, threading.Event] = {}
        self._approvers: dict[str, str] = {}
        self._done_events: dict[str, asyncio.Event] = {}
        self._cancelled: set[str] = set()
        self._case_of: dict[str, str] = {}
        self._real_job_of: dict[str, str] = {}

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

    def approve(self, job_id: str, approver: str | None = None) -> bool:
        released = False
        event = self._approvals.get(job_id)
        if event is not None:
            event.set()
            released = True
        # Real pipeline approval gate runs in a worker thread (threading.Event).
        t = self._thread_approvals.get(job_id)
        if t is not None:
            if approver:
                self._approvers[job_id] = approver
            t.set()
            released = True
        return released

    def cancel(self, job_id: str) -> None:
        self._cancelled.add(job_id)
        event = self._approvals.get(job_id)
        if event:
            event.set()

    # -- real pipeline bridge (S1.3) --------------------------------------
    def _real_progress_fraction(self, node: str, status: str) -> float:
        try:
            idx = REAL_NODES.index(node)
        except ValueError:
            idx = len(REAL_NODES) - 1
        total = len(REAL_NODES)
        return (
            round((idx + 1) / total, 3)
            if status in ("SUCCEEDED", "APPROVED")
            else round(idx / total, 3)
        )

    def _resolve_job(self, case_id: str) -> str | None:
        """Find the live real pipeline job for a case.

        The driver creates the job (status=running) *before* its worker thread
        emits the first progress event, so by the time any callback fires the
        job already exists on disk. We resolve it by case id (most recent
        running/blocked real ``auto_pipeline`` job) — no caller-side hand-off of
        the job id is needed, which avoids a publish race on the first event.
        """
        cached = self._real_job_of.get(case_id)
        if cached:
            return cached
        try:
            jobs = self.list_for_case(case_id)
        except Exception:
            return None
        for j in reversed(jobs):
            payload = j.get("payload") or {}
            if (
                j.get("kind") == "auto_pipeline"
                and payload.get("problem_source")
                and payload.get("data_source")
                and j.get("status") in ("running", "waiting_approval")
            ):
                self._real_job_of[case_id] = j["job_id"]
                return j["job_id"]
        return None

    def build_pipeline_callbacks(self, case_id: str) -> tuple[Callable, Callable]:
        """Return (progress_callback, approval_callback) for the real pipeline.

        They forward the driver-owned pipeline's events onto the EventBus and
        gate approvals on a human. The job id is resolved lazily from the case
        (the driver writes the job before its worker thread fires the first
        event), so no caller-side hand-off is required.
        """
        runner = self

        def progress_callback(event: dict[str, Any]) -> None:
            job_id = runner._resolve_job(case_id)
            if not job_id:
                return
            etype = event.get("type")
            if etype == "progress":
                node = event.get("node", "")
                status = event.get("status", "")
                frac = runner._real_progress_fraction(node, status)
                runner.bus.publish_sync(
                    job_id,
                    {
                        "type": "progress",
                        "node": node,
                        "status": status,
                        "progress": frac,
                        "message": event.get("message", ""),
                    },
                )
                if status in ("SUCCEEDED", "APPROVED"):
                    store = runner.store(runner._case_of.get(job_id) or case_id)
                    payload = dict((store.get(job_id) or {}).get("payload") or {})
                    payload["completed_nodes"] = sorted(
                        set(payload.get("completed_nodes", [])) | {node}
                    )
                    store.update(job_id, progress=frac, payload=payload)
            elif etype == "done":
                runner.bus.publish_sync(job_id, {"type": "done", "result": event.get("result")})
                done = runner._done_events.get(job_id)
                if done is not None:
                    done.set()
            else:
                runner.bus.publish_sync(job_id, event)

        def approval_callback(cid: str, node_id: str, who: str, note: str) -> str:
            job_id = runner._resolve_job(case_id)
            if not job_id:
                return who
            store = runner.store(runner._case_of.get(job_id) or case_id)
            store.update(job_id, status=WAITING_APPROVAL, awaiting_approval=[node_id])
            store.log(job_id, "warn", f"真实节点 {node_id} 阻塞等待真人审批")
            runner.bus.publish_sync(
                job_id, {"type": "approval_required", "nodes": [node_id]}
            )
            # Block the pipeline worker thread until a human approves via the
            # web shell (the /api/cases/{id}/approve endpoint sets this Event).
            # A FRESH Event per node is essential: a single shared Event would
            # stay set after the first approval and let every later gate pass
            # without a human decision.
            ev = threading.Event()
            runner._thread_approvals[job_id] = ev
            ev.wait()
            store.update(job_id, status="running", awaiting_approval=None)
            store.log(
                job_id,
                "info",
                f"真实节点 {node_id} 审批通过 by {runner._approvers.get(job_id, who)}",
            )
            return runner._approvers.get(job_id, who)

        return progress_callback, approval_callback

    def attach_real(self, job_id: str, case_id: str) -> None:
        """Register a driver-created real pipeline job with the runner so the
        WebSocket / approval layers can find it. Does NOT start a loop — the
        driver-owned worker thread drives the job.
        """
        job = self.get(job_id, case_id)
        if job is None:
            return
        job.setdefault("case_id", case_id)
        self._case_of[job_id] = case_id
        self._real_job_of[case_id] = job_id
        self._thread_approvals.setdefault(job_id, threading.Event())
        payload = dict((job.get("payload") or {}))
        if payload.get("problem_source") and payload.get("data_source"):
            payload["mode"] = "real"
            self.store(case_id).update(job_id, payload=payload)

    def load_uploaded_inputs(self, case_id: str) -> dict[str, Any] | None:
        root = self.services.case_root(case_id)
        path = root / "input" / "uploaded_inputs.json"
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None

    def record_uploaded_input(
        self,
        case_id: str,
        file_path: str,
        kind: str,
        source_uri: str = "",
        license_name: str = "",
    ) -> None:
        root = self.services.case_root(case_id)
        upload_dir = root / "input"
        upload_dir.mkdir(parents=True, exist_ok=True)
        path = upload_dir / "uploaded_inputs.json"
        data: dict[str, Any] = {}
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                data = {}
        ext = Path(file_path).suffix.lstrip(".").lower()
        data_exts = {"csv", "xlsx", "xls", "parquet", "tsv", "json", "feather", "orc"}
        if kind == "problem" or (kind != "data" and ext not in data_exts):
            data["problem_source"] = file_path
        if kind == "data" or ext in data_exts:
            data["data_source"] = file_path
            if source_uri:
                data["source_uri"] = source_uri
            if license_name:
                data["license_name"] = license_name
        if "dataset_name" not in data:
            data["dataset_name"] = "对话上传数据"
        if "competition_type" not in data:
            data["competition_type"] = "SM"
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # -- execution --------------------------------------------------------
    async def _run(self, job: dict[str, Any]) -> None:
        job_id = job["job_id"]
        case_id = job.get("case_id") or self._case_of.get(job_id)
        store = self.store(case_id)
        payload = (store.get(job_id) or job).get("payload") or {}
        if payload.get("problem_source") and payload.get("data_source"):
            # Real pipeline job: the driver-owned worker thread drives events;
            # the runner only awaits completion (see S1.3). This branch only
            # triggers if something calls start() on a real job.
            await self._run_real(job)
            return
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

    async def _run_real(self, job: dict[str, Any]) -> None:
        """Passive bridge for real pipeline jobs.

        The driver-owned ``PipelineRunner`` runs ``AutoPipelineService.run()`` in
        a worker thread and pushes events onto the EventBus via the callbacks in
        :meth:`build_pipeline_callbacks`. This coroutine only waits for the
        ``done`` event so the task lifecycle stays clean; it performs no work.
        """
        job_id = job["job_id"]
        self._done_events.setdefault(job_id, asyncio.Event())
        await self._done_events[job_id].wait()

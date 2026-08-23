"""Disk-persisted job queue for long-running chat-driven pipelines.

Long operations (``run_auto_pipeline``, ``run_task_paper``) are surfaced to the
frontend as jobs so the web shell can show progress and resume after an
interruption. Jobs live under ``<case_root>/jobs/<job_id>.json``; the payload
keeps every parameter needed to restart from the same point.
"""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from ..io_utils import atomic_write_json, now_iso


class JobManager:
    """Create, read, update, and finish jobs for one Case directory."""

    def __init__(self, case_root: Path) -> None:
        self.root = case_root / "jobs"

    def _path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def create(
        self,
        *,
        kind: str,
        payload: dict[str, Any],
        approved_by: str,
    ) -> dict[str, Any]:
        self.root.mkdir(parents=True, exist_ok=True)
        job_id = "job-" + uuid.uuid4().hex[:12]
        job: dict[str, Any] = {
            "job_id": job_id,
            "kind": kind,
            "status": "queued",
            "payload": payload,
            "approved_by": approved_by,
            "created_at": now_iso(),
            "current_node": None,
            "progress": 0.0,
            "logs": [],
            "awaiting_approval": None,
            "result": None,
        }
        atomic_write_json(self._path(job_id), job)
        return job

    def get(self, job_id: str) -> dict[str, Any] | None:
        path = self._path(job_id)
        if not path.is_file():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def update(self, job_id: str, **changes: Any) -> dict[str, Any] | None:
        job = self.get(job_id)
        if job is None:
            return None
        job.update(changes)
        if "logs" in changes:
            job["logs"] = changes["logs"]
        job.setdefault("updated_at", now_iso())
        job["updated_at"] = now_iso()
        atomic_write_json(self._path(job_id), job)
        return job

    def log(self, job_id: str, level: str, message: str) -> None:
        job = self.get(job_id)
        if job is None:
            return
        job["logs"] = list(job.get("logs", [])) + [
            {"ts": now_iso(), "level": level, "msg": message}
        ]
        atomic_write_json(self._path(job_id), job)

    def list(self) -> list[dict[str, Any]]:
        if not self.root.is_dir():
            return []
        jobs: list[dict[str, Any]] = []
        for path in sorted(self.root.glob("job-*.json")):
            jobs.append(json.loads(path.read_text(encoding="utf-8")))
        return jobs

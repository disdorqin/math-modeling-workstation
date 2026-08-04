"""S1.3 — web shell subscribes to the *real* pipeline events (no rehearsal).

These tests exercise the seam that turns the web shell's event bus into a live
bridge for ``AutoPipelineService.run()``:

* real progress / done events from the driver-owned pipeline are forwarded onto
  the EventBus (so the WebSocket layer streams them to the browser);
* the four approval nodes block the pipeline worker thread until a human approves
  through the web shell's ``/api/cases/{id}/approve`` endpoint.

The heavy ``AutoPipelineService`` is not launched here (that path is covered by
``test_chat_pipeline.py``); instead we drive the exact callbacks the runner
installs, which is the unit under test for S1.3.
"""
from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mathworkstation.chat import ChatDriver
from mathworkstation.chat.jobs import JobManager
from mathworkstation.chat.services import build_services
from webapp.jobs import EventBus, JobRunner


class _FakeServices:
    """Minimal services view: JobRunner only needs ``case_root``."""

    def __init__(self, bag: dict) -> None:
        self._bag = bag
        self.cases = bag["cases"]

    def case_root(self, case_id: str) -> Path:
        return self.cases.case_root(case_id)


def _make(tmp_path: Path):
    bag = build_services(tmp_path / "output")
    services = _FakeServices(bag)
    driver = ChatDriver(services=bag)
    created = driver.chat("创建案例 S1.3", approved_by="tester")
    case_id = created["tool_calls"][0]["result"]["case_id"]
    jm = JobManager(services.case_root(case_id))
    bus = EventBus()
    runner = JobRunner(services, bus)
    return services, case_id, jm, bus, runner


def test_s1_3_progress_and_done_events_forwarded_to_bus(tmp_path):
    _services, case_id, jm, bus, runner = _make(tmp_path)
    job = jm.create(
        kind="auto_pipeline",
        payload={"problem_source": "p.txt", "data_source": "d.csv"},
        approved_by="tester",
    )
    state = {"job_id": job["job_id"], "case_id": case_id}
    progress_cb, _ = runner.build_pipeline_callbacks(case_id)
    runner.attach_real(job["job_id"], case_id)

    progress_cb({"type": "progress", "node": "model_selection", "status": "NEEDS_REVIEW", "message": "等待审批"})
    progress_cb({"type": "progress", "node": "model_selection", "status": "APPROVED", "message": "已批准"})
    progress_cb({"type": "done", "result": {"ok": True, "paper": "paper/final.md"}})

    hist = bus.history(job["job_id"])
    types = [e["type"] for e in hist]
    assert "progress" in types
    assert "done" in types

    prog = next(e for e in hist if e["type"] == "progress")
    assert prog["node"] == "model_selection"
    assert "progress" in prog and isinstance(prog["progress"], float)
    assert prog["status"] == "NEEDS_REVIEW"

    done = next(e for e in hist if e["type"] == "done")
    assert done["result"] == {"ok": True, "paper": "paper/final.md"}


def test_s1_3_approval_gate_blocks_until_human_approves(tmp_path):
    _services, case_id, jm, bus, runner = _make(tmp_path)
    job = jm.create(
        kind="auto_pipeline",
        payload={"problem_source": "p.txt", "data_source": "d.csv"},
        approved_by="tester",
    )
    state = {"job_id": job["job_id"], "case_id": case_id}
    _, approval_cb = runner.build_pipeline_callbacks(case_id)
    runner.attach_real(job["job_id"], case_id)

    captured: dict[str, str] = {}

    def trigger() -> None:
        # Runs in the pipeline worker thread; blocks until a human approves.
        captured["who"] = approval_cb("cid", "model_selection", "pipeline-trigger", "note")

    t = threading.Thread(target=trigger)
    t.start()
    time.sleep(0.2)
    # Still blocked waiting for a human decision.
    assert t.is_alive()
    job_mid = jm.get(job["job_id"])
    assert job_mid["status"] == "waiting_approval"
    assert job_mid["awaiting_approval"] == ["model_selection"]

    # The web shell's approve endpoint releases the gate.
    assert runner.approve(job["job_id"], approver="real-human")
    t.join(timeout=2)
    assert not t.is_alive()

    # The approval callback returns the *human* approver, not the trigger id.
    assert captured["who"] == "real-human"
    assert jm.get(job["job_id"])["status"] == "running"

    approval_events = [e for e in bus.history(job["job_id"]) if e["type"] == "approval_required"]
    assert approval_events and approval_events[0]["nodes"] == ["model_selection"]

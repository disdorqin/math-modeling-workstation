"""FastAPI web shell for the math modeling workstation.

Implements the frozen contract in ``docs/web-chat-driver-contract.md``.

Design rules honoured here:
* the shell owns no domain logic and no parallel store - jobs and the AI
  ledger stay in the driver-owned files under ``<case_root>/``;
* every write goes through an existing service, so the evidence gate and the
  approval flow cannot be bypassed from the browser;
* ``approved_by`` must be a human identifier - AI-looking identities are
  rejected with HTTP 400.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from fastapi import (
    Body,
    FastAPI,
    File,
    Form,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import ledger
from .driver import REAL_DRIVER_IMPORT_PATH, ChatDriverAdapter
from .jobs import WAITING_APPROVAL, EventBus, JobRunner
from .services import get_services

STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="Math Modeling Workstation - Web Shell",
    version="0.1.0",
    description="FastAPI shell over the existing evidence-first workstation services.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8000", "http://localhost:8000"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

services = get_services()
bus = EventBus()
driver = ChatDriverAdapter(services)
runner = JobRunner(services, bus, driver)


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
_AI_IDENTITIES = {
    "ai", "agent", "llm", "gpt", "bot", "assistant", "model", "auto",
    "workbuddy", "claude", "claude_code", "codex", "cursor", "copilot",
    "chatgpt", "deepseek", "qwen", "system", "chat-human", "chat_human",
}


def require_human(value: str | None, field: str = "approved_by") -> str:
    """Reject AI identities on any approval-bearing field (iron rule)."""
    name = (value or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail=f"{field} 不能为空，必须填写真人标识")
    normalized = name.lower().replace("-", "_")
    if normalized in _AI_IDENTITIES or normalized.startswith("ai_"):
        raise HTTPException(
            status_code=400,
            detail=f"{field}='{name}' 看起来是 AI 或占位标识；审批必须由真人署名，请填写你本人的标识。",
        )
    return name


def ensure_case(case_id: str) -> Path:
    try:
        root = services.case_root(case_id)
    except Exception as exc:
        raise HTTPException(status_code=404, detail=f"Case 不存在: {case_id}") from exc
    if not root.exists():
        raise HTTPException(status_code=404, detail=f"Case 不存在: {case_id}")
    return root


# --------------------------------------------------------------------------
# request models
# --------------------------------------------------------------------------
class ChatRequest(BaseModel):
    case_id: str | None = None
    session_id: str | None = None
    message: str
    context: dict[str, Any] = Field(default_factory=dict)


class JobRequest(BaseModel):
    case_id: str
    kind: str = Field(pattern="^(auto_pipeline|task_paper)$")
    payload: dict[str, Any] = Field(default_factory=dict)
    approved_by: str


class ApproveRequest(BaseModel):
    node_id: str
    note: str = ""
    approved_by: str


class RetryRequest(BaseModel):
    node_id: str
    reason: str
    requested_by: str


class DegradeRequest(BaseModel):
    node_id: str
    reason: str
    approved_by: str


# --------------------------------------------------------------------------
# meta
# --------------------------------------------------------------------------
@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "output_root": str(services.output_root.resolve()),
        "driver": {
            "real_driver_available": not driver.is_stub,
            "expected_import": REAL_DRIVER_IMPORT_PATH,
            "model": driver.model,
            "init_error": driver.init_error,
        },
        "tools": driver.tool_table(),
    }


# --------------------------------------------------------------------------
# 2.1 chat
# --------------------------------------------------------------------------
@app.post("/api/chat")
async def chat(request: ChatRequest) -> dict[str, Any]:
    root = ensure_case(request.case_id) if request.case_id else None

    context = dict(request.context or {})
    confirmed = bool(context.get("confirmed"))
    supplied = context.get("approved_by")
    if confirmed:
        # Executing an approval-gated tool: the signer must be a real person.
        who = require_human(supplied, "context.approved_by")
    elif supplied:
        who = require_human(supplied, "context.approved_by")
    else:
        who = "chat-unconfirmed"

    # S1.3: if this message triggers a pipeline, let the real pipeline push its
    # live events onto the EventBus and gate approvals on a human. The callbacks
    # resolve the job id from the case, so no caller-side hand-off is needed.
    # They are harmless for non-pipeline messages (the driver simply ignores them).
    progress_cb, approval_cb = runner.build_pipeline_callbacks(request.case_id)
    context.setdefault("pipeline", {})
    context["pipeline"]["progress_callback"] = progress_cb
    context["pipeline"]["approval_callback"] = approval_cb
    uploaded = runner.load_uploaded_inputs(request.case_id) if request.case_id else None
    if uploaded:
        context["pipeline"]["inputs"] = {**context["pipeline"].get("inputs", {}), **uploaded}

    # driver.chat is synchronous and can be slow; run it off the event loop.
    result = await asyncio.to_thread(
        driver.chat,
        request.case_id, request.session_id, request.message, context, approved_by=who
    )

    # The driver writes its own ledger entry for every audited tool it runs.
    # Only top up when it did not, so the audit trail never double-counts. A
    # pipeline job already logs its own run_auto_pipeline entry, so skip it.
    entry_id = result.ledger_entry_id
    if entry_id is None and root is not None and result.job_id is None:
        entry = ledger.record(
            root,
            tool="chat",
            model=result.model,
            purpose="聊天驱动请求(未触发已审计工具)",
            stage=str(context.get("stage", "chat")),
            user_input=request.message[:1000],
            prompt_ref=request.session_id,
            output_adopted=False,
            used_ai=result.used_ai,
            extra={"driver_stub": driver.is_stub},
        )
        entry_id = entry["entry_id"]

    # A pipeline intent schedules a real job inside the driver; attach it to the
    # runner (no rehearsal loop) so the browser gets live events over the WS.
    if result.job_id and request.case_id:
        runner.attach_real(result.job_id, request.case_id)

    payload = result.as_dict()
    payload["ledger"] = {"entry_id": entry_id, "used_ai": result.used_ai}
    payload["driver_stub"] = driver.is_stub
    payload["approved_by"] = who
    return payload


# --------------------------------------------------------------------------
# 2.2 jobs
# --------------------------------------------------------------------------
@app.post("/api/jobs")
async def create_job(request: JobRequest) -> dict[str, Any]:
    ensure_case(request.case_id)
    who = require_human(request.approved_by)
    payload = dict(request.payload or {})

    # S1.3: if the request carries (or the case has uploaded) real inputs,
    # run the genuine pipeline via the driver with the shell's event/approval
    # callbacks; otherwise fall back to the deterministic rehearsal demo.
    has_real = bool(payload.get("problem_source") and payload.get("data_source"))
    if not has_real:
        uploaded = runner.load_uploaded_inputs(request.case_id)
        if uploaded and uploaded.get("problem_source") and uploaded.get("data_source"):
            payload = {**payload, **uploaded}
            has_real = True

    if has_real and driver.is_stub is False:
        progress_cb, approval_cb = runner.build_pipeline_callbacks(request.case_id)
        message = payload.get("message") or "自动流水线(Web 手动触发)"
        # The real pipeline requires an active session (LLM responses persist
        # under <case>/sessions/<session_id>). Create one if none was supplied.
        session_id = payload.get("session_id")
        if not session_id:
            try:
                session = services.sessions.create_session(request.case_id)
                session_id = session["session_id"]
            except Exception:
                session_id = None
        context: dict[str, Any] = {
            "pipeline": {
                "inputs": {
                    "problem_source": payload["problem_source"],
                    "data_source": payload["data_source"],
                    "dataset_name": payload.get("dataset_name", "Web 触发数据"),
                    "target_column": payload.get("target_column"),
                    "competition_type": payload.get("competition_type", "SM"),
                    "session_id": session_id,
                    "source_uri": payload.get("source_uri"),
                    "license_name": payload.get("license_name"),
                    "data_description": payload.get("data_description", ""),
                },
                "progress_callback": progress_cb,
                "approval_callback": approval_cb,
            }
        }
        job_id = await asyncio.to_thread(
            driver.schedule_pipeline, request.case_id, message, who, context
        )
        if job_id:
            runner.attach_real(job_id, request.case_id)
            return {"job_id": job_id, "status": "running", "mode": "real"}

    # Rehearsal demo mode (no real inputs, or real driver unavailable).
    job = runner.create(request.case_id, request.kind, payload, who)
    runner.start(job)
    return {"job_id": job["job_id"], "status": job["status"]}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, case_id: str | None = None) -> dict[str, Any]:
    job = runner.get(job_id, case_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job 不存在: {job_id}")
    return {
        "job_id": job["job_id"],
        "case_id": job.get("case_id"),
        "kind": job.get("kind"),
        "status": job.get("status"),
        "current_node": job.get("current_node"),
        "progress": job.get("progress", 0.0),
        "logs": job.get("logs", []),
        "awaiting_approval": job.get("awaiting_approval"),
        "result": job.get("result"),
        "mode": (job.get("payload") or {}).get("mode"),
        "events": bus.history(job_id),
    }


@app.get("/api/cases/{case_id}/jobs")
def list_jobs(case_id: str) -> list[dict[str, Any]]:
    ensure_case(case_id)
    return [
        {
            "job_id": j["job_id"],
            "kind": j.get("kind"),
            "status": j.get("status"),
            "progress": j.get("progress", 0.0),
            "created_at": j.get("created_at"),
        }
        for j in runner.list_for_case(case_id)
    ]


@app.post("/api/jobs/{job_id}/resume")
async def resume_job(job_id: str, case_id: str | None = None) -> dict[str, Any]:
    job = runner.get(job_id, case_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job 不存在: {job_id}")
    if job.get("status") == WAITING_APPROVAL:
        raise HTTPException(
            status_code=409,
            detail="该任务停在审批门，请先通过 POST /api/cases/{case_id}/approve 审批对应节点。",
        )
    runner.start(job)
    return {"job_id": job_id, "status": "resumed"}


@app.post("/api/jobs/{job_id}/cancel")
async def cancel_job(job_id: str, case_id: str | None = None) -> dict[str, Any]:
    job = runner.get(job_id, case_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job 不存在: {job_id}")
    runner.cancel(job_id)
    return {"job_id": job_id, "status": "cancelling"}


# --------------------------------------------------------------------------
# 2.3 approvals - delegated to WorkflowService
# --------------------------------------------------------------------------
@app.post("/api/cases/{case_id}/approve")
async def approve(case_id: str, request: ApproveRequest) -> dict[str, Any]:
    root = ensure_case(case_id)
    who = require_human(request.approved_by)

    # 1) Release any rehearsal job blocked on this node first. Rehearsal gates
    #    use simulated node names (e.g. "model_selection") that do not exist in
    #    the real workflow DAG, so the real approve below would otherwise reject
    #    them and strand the job forever.
    waiting = [
        job
        for job in runner.list_for_case(case_id)
        if job.get("status") == WAITING_APPROVAL
        and request.node_id in (job.get("awaiting_approval") or [])
    ]
    released = []
    for job in waiting:
        if runner.approve(job["job_id"], approver=who):
            released.append(job["job_id"])

    # 2) Real workflow node approval (only when no rehearsal gate matched).
    result = None
    if not waiting:
        try:
            result = services.workflow.approve_node(
                case_id, request.node_id, who, request.note
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    ledger.record(
        root,
        tool="approve_node",
        model="human",
        purpose=f"人工审批节点 {request.node_id}",
        stage=request.node_id,
        user_input=request.note,
        output_adopted=True,
        human_reviewed=True,
        review_note=request.note,
        used_ai=False,
        extra={"approved_by": who, "released_jobs": released},
    )
    return {"ok": True, "node": result, "released_jobs": released}


@app.post("/api/cases/{case_id}/retry")
def retry(case_id: str, request: RetryRequest) -> dict[str, Any]:
    root = ensure_case(case_id)
    who = require_human(request.requested_by, "requested_by")
    try:
        result = services.workflow.retry_node(case_id, request.node_id, who, request.reason)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ledger.record(
        root,
        tool="retry_node",
        model="human",
        purpose=f"人工重试节点 {request.node_id}",
        stage=request.node_id,
        user_input=request.reason,
        human_reviewed=True,
        used_ai=False,
        extra={"requested_by": who},
    )
    return {"ok": True, "node": result}


@app.post("/api/cases/{case_id}/degrade")
def degrade(case_id: str, request: DegradeRequest) -> dict[str, Any]:
    root = ensure_case(case_id)
    who = require_human(request.approved_by)
    try:
        result = services.workflow.degrade_node(case_id, request.node_id, who, request.reason)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ledger.record(
        root,
        tool="degrade_node",
        model="human",
        purpose=f"人工降级节点 {request.node_id}",
        stage=request.node_id,
        user_input=request.reason,
        human_reviewed=True,
        used_ai=False,
        extra={"approved_by": who},
    )
    return {"ok": True, "node": result}


# --------------------------------------------------------------------------
# 2.4 views
# --------------------------------------------------------------------------
@app.get("/api/cases")
def list_cases() -> list[dict[str, Any]]:
    return [
        {
            "case_id": item.get("case_id"),
            "title": item.get("title"),
            "competition_type": item.get("competition_type"),
            "updated_at": item.get("updated_at") or item.get("created_at"),
            "status": item.get("status"),
        }
        for item in services.list_cases()
    ]


@app.get("/api/cases/{case_id}")
def get_case(case_id: str) -> dict[str, Any]:
    ensure_case(case_id)
    try:
        return services.case_snapshot(case_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/cases/{case_id}/paper")
def get_paper(case_id: str) -> dict[str, Any]:
    root = ensure_case(case_id)
    markdown = ""
    source = None
    for candidate in ("paper/current.md", "paper/final.md", "paper/paper.md"):
        path = root / candidate
        if path.is_file():
            markdown = path.read_text(encoding="utf-8")
            source = candidate
            break

    consistency = None
    consistency_path = root / "review" / "consistency" / "paper_consistency.json"
    if consistency_path.is_file():
        try:
            consistency = json.loads(consistency_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            consistency = {"gate": "UNPARSEABLE"}

    refinement = None
    refinement_path = root / "memory" / "refinement_state.json"
    if refinement_path.is_file():
        try:
            refinement = json.loads(refinement_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            refinement = None

    return {
        "markdown": markdown,
        "source": source,
        "consistency_gate": (consistency or {}).get("gate", "UNKNOWN"),
        "consistency": consistency,
        "refinement": refinement,
    }


@app.get("/api/cases/{case_id}/ledger")
def get_ledger(case_id: str) -> dict[str, Any]:
    root = ensure_case(case_id)
    entries = ledger.read_all(root)
    return {"entries": entries, "summary": ledger.summarize(entries)}


@app.get("/api/cases/{case_id}/figures/{figure_index}")
def get_figure(case_id: str, figure_index: int):
    root = ensure_case(case_id)
    figures = services.figures.list_figures(case_id)
    if figure_index < 0 or figure_index >= len(figures):
        raise HTTPException(status_code=404, detail="figure 不存在")
    path = root / figures[figure_index]["path"]
    if not path.is_file():
        raise HTTPException(status_code=404, detail="figure 文件缺失")
    return FileResponse(path)


@app.post("/api/cases/{case_id}/export")
def export_pdf(case_id: str, profile: str = Body("SM", embed=True)) -> dict[str, Any]:
    """Contract tool `export_pdf` -> SubmissionService.prepare (audited)."""
    root = ensure_case(case_id)
    try:
        result = services.submission.prepare(case_id, profile_name=profile)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    ledger.record(
        root,
        tool="export_pdf",
        model="deterministic",
        purpose=f"生成投稿包 profile={profile}",
        stage="export",
        output_adopted=True,
        used_ai=False,
    )
    return {"ok": True, "result": result}


@app.post("/api/upload")
async def upload(
    case_id: str = Form(...),
    kind: str = Form("input"),
    source_uri: str = Form(""),
    license_name: str = Form(""),
    file: UploadFile = File(...),
) -> dict[str, Any]:
    """Store an uploaded file and register it through ArtifactRegistry.

    ``source_uri`` / ``license_name`` are optional provenance metadata recorded
    with the input so the research audit can verify the data source (the real
    pipeline blocks on SOURCE_URI_MISSING otherwise).
    """
    root = ensure_case(case_id)
    staging = root / "input" / "uploads"
    staging.mkdir(parents=True, exist_ok=True)
    filename = Path(file.filename or "upload.bin").name
    target = staging / filename
    target.write_bytes(await file.read())

    try:
        artifact = services.artifacts.ingest_file(
            case_id,
            target,
            destination_directory="input/uploads",
            artifact_type=kind,
            created_by="web-upload",
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"注册产物失败: {exc}") from exc
    # S1.3: remember uploaded problem/data paths per case (with optional
    # provenance) so a later pipeline intent can run the real pipeline without
    # the client re-sending them.
    runner.record_uploaded_input(
        case_id, str(target), kind, source_uri=source_uri, license_name=license_name
    )

    ledger.record(
        root,
        tool="upload_inputs",
        model="deterministic",
        purpose=f"上传并注册输入文件 {filename}",
        stage="input",
        user_input=filename,
        output_adopted=True,
        used_ai=False,
        extra={"artifact_id": artifact.get("artifact_id")},
    )
    return {"ok": True, "artifact": artifact}


# --------------------------------------------------------------------------
# 2.5 websocket
# --------------------------------------------------------------------------
@app.websocket("/ws/jobs/{job_id}")
async def ws_job(websocket: WebSocket, job_id: str) -> None:
    await websocket.accept()
    queue = await bus.subscribe(job_id)
    try:
        job = runner.get(job_id)
        await websocket.send_json(
            {
                "type": "hello",
                "job_id": job_id,
                "status": (job or {}).get("status", "unknown"),
                "progress": (job or {}).get("progress", 0.0),
            }
        )
        while True:
            event = await queue.get()
            await websocket.send_json(event)
    except WebSocketDisconnect:
        pass
    except Exception:  # pragma: no cover - transport level
        pass
    finally:
        await bus.unsubscribe(job_id, queue)


# --------------------------------------------------------------------------
# static frontend
# --------------------------------------------------------------------------
if STATIC_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
def index():
    page = STATIC_DIR / "index.html"
    if not page.is_file():
        return JSONResponse({"detail": "前端未找到"}, status_code=404)
    return FileResponse(page)

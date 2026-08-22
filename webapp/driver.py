"""Chat Driver adapter.

The driver itself is owned by claude_code (stage S1) and lives at the path the
frozen contract names::

    from mathworkstation.chat.driver import ChatDriver

Its real signature is::

    ChatDriver(services: dict | None = None, provider=None, router_config: str | None = None)
    ChatDriver.chat(message, *, case_id=None, session_id=None,
                    approved_by="chat-human", context=None) -> dict

The shell adapts the contract's HTTP body onto that signature and normalises
the reply. If the driver is ever unavailable (rollback, partial checkout), a
stub keeps the routes and the frontend alive - and says loudly that nothing
was executed, so no evidence gate can be bypassed by accident.

Provider policy: default is S1's ``FakeProvider`` - deterministic, offline, no
API key (contract acceptance #5). A real route config may be supplied through
the ``MATHWS_ROUTER_CONFIG`` environment variable, which holds a *path*, never
a key; keys stay in ``.env.local``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

REAL_DRIVER_IMPORT_PATH = "mathworkstation.chat.driver.ChatDriver"
ROUTER_CONFIG_ENV = "MATHWS_ROUTER_CONFIG"

# Fallback description of the whitelist (contract section 1), used only when
# the real driver is unavailable. When it is available we publish its actual
# tool table instead of this copy.
FALLBACK_WHITELIST: dict[str, tuple[str, bool]] = {
    "list_cases": ("CaseManager.list_cases", False),
    "get_case": ("CaseManager.show_case + snapshot", False),
    "create_case": ("CaseManager.create_case", False),
    "get_research_interview": ("ResearchPreferenceInterview", False),
    "get_research_preferences": ("ResearchPreferenceService.load", False),
    "set_research_preferences": ("ResearchPreferenceService.save", False),
    "upload_inputs": ("ProblemIngestion / DatasetRegistry", False),
    "run_auto_pipeline": ("AutoPipelineService.run", True),
    "run_task_paper": ("AutoPipelineService.run_task_paper_pipeline", True),
    "approve_node": ("WorkflowService.approve_node", False),
    "retry_node": ("WorkflowService.retry_node", True),
    "degrade_node": ("WorkflowService.degrade_node", True),
    "read_paper": ("paper/current.md", False),
    "export_pdf": ("SubmissionService.prepare", False),
    "list_artifacts": ("ArtifactRegistry.list_artifacts", False),
    "list_claims": ("ClaimRegistry.list_claims", False),
    "list_figures": ("FigureRegistry.list_figures", False),
    "ask_human": ("-", True),
}


def load_real_driver() -> type | None:
    try:
        from mathworkstation.chat.driver import ChatDriver  # type: ignore

        return ChatDriver
    except Exception:
        return None


@dataclass
class DriverReply:
    reply: str
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    job_id: str | None = None
    awaiting_approval: list[str] = field(default_factory=list)
    model: str = "stub/none"
    used_ai: bool = False
    ledger_entry_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "reply": self.reply,
            "tool_calls": self.tool_calls,
            "job_id": self.job_id,
            "awaiting_approval": self.awaiting_approval,
        }


class StubChatDriver:
    """Honest placeholder: parses nothing, executes nothing, writes nothing."""

    model = "stub/none"

    def chat(self, message: str, **kwargs: Any) -> dict[str, Any]:
        return {
            "reply": (
                "【驱动层不可用】Web 外壳可运行，但 "
                f"{REAL_DRIVER_IMPORT_PATH} 未能导入，本次**没有执行任何工具、"
                "没有写入任何 Case 数据**。只读视图与人工审批通道仍然可用。"
            ),
            "tool_calls": [],
            "job_id": None,
            "awaiting_approval": [],
            "ledger": None,
        }


class ChatDriverAdapter:
    """Uniform entry point used by the API layer."""

    def __init__(self, services: Any) -> None:
        self.services = services
        self.init_error: str | None = None
        real = load_real_driver()
        if real is None:
            self._impl: Any = StubChatDriver()
            self.is_stub = True
            self.init_error = f"cannot import {REAL_DRIVER_IMPORT_PATH}"
            return
        try:
            router_config = os.environ.get(ROUTER_CONFIG_ENV) or None
            # `services.bag` is the very dict build_services() produced, so the
            # driver and the shell operate on the same service instances.
            self._impl = real(services=services.bag, router_config=router_config)
            self.is_stub = False
        except Exception as exc:
            self._impl = StubChatDriver()
            self.is_stub = True
            self.init_error = f"{type(exc).__name__}: {exc}"

    # -- introspection ----------------------------------------------------
    @property
    def model(self) -> str:
        provider = getattr(self._impl, "provider", None)
        name = getattr(provider, "name", None)
        return name or getattr(self._impl, "model", "unknown")

    def tool_table(self) -> dict[str, dict[str, Any]]:
        tools = getattr(self._impl, "tools", None)
        if isinstance(tools, dict) and tools:
            table: dict[str, dict[str, Any]] = {}
            for name, spec in tools.items():
                table[name] = {
                    "description": getattr(spec, "description", ""),
                    "requires_approval": bool(getattr(spec, "needs_approval", False)),
                    "audited": bool(getattr(spec, "audited", False)),
                }
            return table
        return {
            name: {"description": target, "requires_approval": approval, "audited": True}
            for name, (target, approval) in FALLBACK_WHITELIST.items()
        }

    # -- chat -------------------------------------------------------------
    def chat(
        self,
        case_id: str | None,
        session_id: str | None,
        message: str,
        context: dict[str, Any] | None = None,
        approved_by: str = "chat-human",
    ) -> DriverReply:
        result = self._impl.chat(
            message,
            case_id=case_id,
            session_id=session_id,
            approved_by=approved_by,
            context=context or {},
        )
        if not isinstance(result, dict):
            raise TypeError(f"Unsupported driver reply type: {type(result)!r}")

        led = result.get("ledger") or {}
        if not isinstance(led, dict):
            led = {}
        return DriverReply(
            reply=result.get("reply", ""),
            tool_calls=result.get("tool_calls") or [],
            job_id=result.get("job_id"),
            awaiting_approval=result.get("awaiting_approval") or [],
            model=self.model,
            used_ai=bool(led.get("used_ai", not self.is_stub)),
            ledger_entry_id=led.get("entry_id"),
        )

    # -- real pipeline scheduling (S1.3) --------------------------------
    def schedule_pipeline(
        self,
        case_id: str,
        message: str,
        approved_by: str,
        context: dict[str, Any] | None = None,
    ) -> str | None:
        """Drive the real pipeline for an already-built context.

        Used by the web shell's job API (and, indirectly, the chat path) to run
        the genuine ``AutoPipelineService`` with the shell-supplied
        ``progress_callback`` / ``approval_callback`` from
        ``JobRunner.build_pipeline_callbacks``. Returns the created job id, or
        ``None`` when the real driver is unavailable (stub).
        """
        if self.is_stub or not hasattr(self._impl, "_schedule_pipeline"):
            return None
        try:
            return self._impl._schedule_pipeline(
                case_id, message, approved_by, None, context=context or {}
            )
        except Exception as exc:  # pragma: no cover - surfaced to the caller
            self.init_error = f"schedule_pipeline failed: {type(exc).__name__}: {exc}"
            raise

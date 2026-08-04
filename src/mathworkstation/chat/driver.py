"""ChatDriver: turn conversational input into gated, audited workstation actions.

The driver is the single entry point a web shell calls for chat input. It:

  1. resolves the message to whitelisted tool calls (deterministic rules first;
     an LLM provider is an opt-in backstop for free-form requests);
  2. enforces the ``needs_approval`` gate *before* execution;
  3. executes each tool against the existing services — never a parallel store;
  4. writes one AI-usage ledger entry per executed tool call;
  5. returns a natural-language reply plus a machine-readable trace.

With the default ``FakeProvider`` the whole pipeline is deterministic and needs
no API key, so the driver is testable offline (see ``tests/test_chat_driver.py``).
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..io_utils import now_iso
from .jobs import JobManager
from .ledger import AILedger
from .provider import FakeProvider, RouterProvider
from .services import build_services
from .tools import (
    ToolSpec,
    build_tools,
    extract_case_id,
    extract_node_id,
    hints_pipeline,
    resolve_intent,
)

#: Free-form commands the driver recognises but does not auto-execute; it asks
#: the human to confirm by picking the matching explicit command instead.
_HELP_TEXT = (
    "我可以帮你:\n"
    "· 创建案例:『创建案例 标题』\n"
    "· 查看案例:『查看案例 <case_id>』\n"
    "· 跑自动流水线:『自动流水线 做这道题』(需先上传题面+数据)\n"
    "· 审批:『批准 <node>』\n"
    "· 查看论文:『查看论文』· 查看 AI 台账:『查看台账』\n"
    "请明确说出你想做的操作;涉及关键节点的动作需要你人工确认。"
)


def default_provider(config_path: str | None = None) -> Any:
    """Return the deterministic FakeProvider (offline, no key) by default.

    Pass a valid route config path to get a real RouterProvider that routes
    through the workstation's OpenAI-compatible routes (e.g. a DeepSeek route
    added to ``config/llm-routes.local.json``).
    """
    if config_path:
        from .provider import provider_from_router_config

        return provider_from_router_config(config_path)
    return FakeProvider()


class ChatDriver:
    def __init__(
        self,
        services: dict[str, Any] | None = None,
        provider: Any | None = None,
        router_config: str | None = None,
    ) -> None:
        self.services = services if services is not None else build_services()
        #: Offline-deterministic by default; pass router_config (or a real
        #: provider) to enable free-form intent understanding in production.
        if provider is None:
            provider = default_provider(router_config)
        self.provider = provider
        self.tools: dict[str, ToolSpec] = build_tools(self.services)

    # ------------------------------------------------------------------ public

    def chat(
        self,
        message: str,
        *,
        case_id: str | None = None,
        session_id: str | None = None,
        approved_by: str = "chat-human",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Process one conversational turn against a (possibly None) Case."""
        context = context or {}
        resolved_case_id = self._resolve_case_id(message, case_id)
        ledger = AILedger(self.services["cases"].case_root(resolved_case_id)) if resolved_case_id else None

        # Pipeline intent is not a plain tool: it schedules a background job so
        # the web shell can stream progress and gate on approval.
        if hints_pipeline(message) and not resolve_intent(message):
            if resolved_case_id is None:
                return {
                    "reply": "要跑自动流水线,请先指定或创建一个案例,并上传题面与数据。",
                    "tool_calls": [],
                    "job_id": None,
                    "awaiting_approval": [],
                    "ledger": None,
                }
            job_id = self._schedule_pipeline(resolved_case_id, message, approved_by, ledger, context)
            return {
                "reply": f"已为你排程自动流水线(job {job_id}),完成后可查看论文。",
                "tool_calls": [{"tool": "run_auto_pipeline", "status": "scheduled", "job_id": job_id}],
                "job_id": job_id,
                "awaiting_approval": [],
                "ledger": {"entry_id": None, "used_ai": True},
            }

        calls = resolve_intent(message)
        if not calls and not hints_pipeline(message):
            # Rule-based path found nothing and it's not a pipeline request:
            # let the real LLM (when configured) map free-form language to a
            # whitelisted tool. FakeProvider always returns confident=False, so
            # offline runs never guess.
            llm_hint = getattr(self.provider, "resolve_intent_llm", None)
            if callable(llm_hint):
                parsed = llm_hint(message)
                if isinstance(parsed, dict) and parsed.get("confident"):
                    tool = str(parsed.get("tool") or "").strip()
                    if tool in self.tools:
                        calls = [{"tool": tool, "args": parsed.get("args") or {}}]
        tool_calls: list[dict[str, Any]] = []
        awaiting: list[str] = []
        for call in calls:
            spec = self.tools.get(call["tool"])
            if spec is None:
                continue
            if spec.needs_approval and not context.get("confirmed"):
                awaiting.append(call["tool"])
                tool_calls.append({"tool": call["tool"], "status": "awaiting_approval"})
                continue
            try:
                self._fill_missing_args(call, message, resolved_case_id)
                result = spec.handler(call["args"], self._ctx(resolved_case_id, approved_by))
                entry_id = None
                # create_case creates the case root, so its ledger can only be
                # written after execution; every other audited tool writes into
                # the (already existing) case ledger.
                if ledger is None and call["tool"] == "create_case" and result.get("case_id"):
                    ledger = AILedger(self.services["cases"].case_root(result["case_id"]))
                if spec.audited and ledger is not None:
                    entry = ledger.record(
                        tool=call["tool"],
                        model=self.provider.name,
                        purpose=self.tools[call["tool"]].description,
                        stage="chat_tool",
                        user_input=message,
                        output_adopted=True,
                        human_reviewed=True if spec.name == "approve_node" else False,
                    )
                    entry_id = entry["entry_id"]
                tool_calls.append({"tool": call["tool"], "status": "done", "result": result, "ledger": entry_id})
            except Exception as error:  # noqa: BLE001 - surface to user as a friendly reply
                tool_calls.append({"tool": call["tool"], "status": "failed", "error": str(error)})

        reply = self._build_reply(tool_calls, message)
        return {
            "reply": reply,
            "tool_calls": tool_calls,
            "job_id": None,
            "awaiting_approval": awaiting,
            "ledger": {"entry_id": tool_calls[-1].get("ledger") if tool_calls else None, "used_ai": bool(ledger)},
        }

    def get_job(self, case_id: str, job_id: str) -> dict[str, Any] | None:
        root = self.services["cases"].case_root(case_id)
        return JobManager(root).get(job_id)

    # ------------------------------------------------------------- internals

    def _resolve_case_id(self, message: str, case_id: str | None) -> str | None:
        if case_id:
            return case_id
        known = [m["case_id"] for m in self.services["cases"].list_cases(include_archived=True)]
        return extract_case_id(message, known)

    def _ctx(self, case_id: str | None, approved_by: str) -> dict[str, Any]:
        ctx = dict(self.services)
        ctx["case_id"] = case_id
        ctx["approved_by"] = approved_by
        if case_id:
            ctx["ledger"] = AILedger(self.services["cases"].case_root(case_id))
        return ctx

    def _fill_missing_args(self, call: dict[str, Any], message: str, case_id: str | None) -> None:
        args = call.get("args", {})
        tool = call["tool"]
        if tool in {"get_case", "retry_node", "degrade_node"} and not args.get("case_id") and case_id:
            args["case_id"] = case_id
        if tool in {"approve_node", "retry_node", "degrade_node"} and not args.get("node_id"):
            case_root = self.services["cases"].case_root(case_id) if case_id else None
            nodes = list(self.services["checkpoints"].snapshot(case_id)["nodes"]) if case_id else []
            node = extract_node_id(message, nodes)
            if node:
                args["node_id"] = node
        call["args"] = args

    def _schedule_pipeline(
        self,
        case_id: str,
        message: str,
        approved_by: str,
        ledger: AILedger | None,
        context: dict[str, Any] | None = None,
    ) -> str:
        """Schedule and run the real pipeline against the case.

        The web shell may pass ``context["pipeline"]`` with the input paths the
        user uploaded (problem_source, data_source, dataset_name, target_column,
        competition_type). Without those inputs we still create the job and mark
        it BLOCKED waiting for inputs, so the shell can prompt the user to
        upload before the real execution starts.
        """
        context = context or {}
        root = self.services["cases"].case_root(case_id)
        jobs = JobManager(root)
        pipeline_inputs = (context.get("pipeline") or {}).get("inputs") or {}
        job = jobs.create(
            kind="auto_pipeline",
            payload={"message": message, "scheduled_by": approved_by, "scheduled_at": now_iso(), **pipeline_inputs},
            approved_by=approved_by,
        )
        jobs.update(job["job_id"], status="running")
        jobs.log(job["job_id"], "info", "pipeline scheduled via chat")

        # Gather the approval + progress hooks the web shell provides.
        approval_cb = (context.get("pipeline") or {}).get("approval_callback")
        progress_cb = (context.get("pipeline") or {}).get("progress_callback")

        if pipeline_inputs.get("problem_source") and pipeline_inputs.get("data_source"):
            from .pipeline import PipelineRunner

            # The real pipeline persists LLM responses under
            # <case>/sessions/<session_id>; create one if the shell didn't.
            if not pipeline_inputs.get("session_id"):
                try:
                    pipeline_inputs["session_id"] = self.services["sessions"].create_session(case_id)["session_id"]
                    jobs.update(job["job_id"], payload={**job.get("payload", {}), **pipeline_inputs})
                except Exception:
                    pass

            runner = PipelineRunner(self.services, self.provider)

            def _on_start(event: dict[str, Any]) -> None:
                if event.get("ok"):
                    jobs.update(job["job_id"], status="succeeded", result=event["result"])
                    jobs.log(job["job_id"], "info", "pipeline completed")
                else:
                    jobs.update(job["job_id"], status="failed", result=event)
                    jobs.log(job["job_id"], "error", f"pipeline failed: {event.get('error')}")

            runner.run_async(
                on_start=_on_start,
                case_id=case_id,
                session_id=pipeline_inputs.get("session_id"),
                problem_source=pipeline_inputs["problem_source"],
                data_source=pipeline_inputs["data_source"],
                dataset_name=pipeline_inputs.get("dataset_name", "对话上传数据"),
                target_column=pipeline_inputs.get("target_column"),
                competition_type=pipeline_inputs.get("competition_type", "SM"),
                source_uri=pipeline_inputs.get("source_uri"),
                license_name=pipeline_inputs.get("license_name"),
                data_description=pipeline_inputs.get("data_description", ""),
                approved_by=approved_by,
                progress_callback=progress_cb,
                approval_callback=approval_cb,
                refinement_config=(context.get("pipeline") or {}).get("refinement_config"),
            )
            jobs.update(job["job_id"], status="running")
        else:
            jobs.update(job["job_id"], status="blocked", awaiting_approval=["inputs"])
            jobs.log(job["job_id"], "warn", "缺少题面/数据输入，等待上传后再执行")

        if ledger is not None:
            ledger.record(
                tool="run_auto_pipeline",
                model=self.provider.name,
                purpose="schedule automatic paper pipeline",
                stage="chat",
                user_input=message,
                output_adopted=True,
                human_reviewed=False,
                job_id=job["job_id"],
            )
        return job["job_id"]

    def _build_reply(self, tool_calls: list[dict[str, Any]], message: str) -> str:
        if not tool_calls:
            return _HELP_TEXT
        done = [t for t in tool_calls if t["status"] == "done"]
        waiting = [t for t in tool_calls if t["status"] == "awaiting_approval"]
        failed = [t for t in tool_calls if t["status"] == "failed"]
        lines: list[str] = []
        for t in done:
            lines.append(f"✅ {t['tool']} 完成")
        for t in waiting:
            lines.append(f"⏸ {t['tool']} 需要你确认后再执行")
        for t in failed:
            lines.append(f"❌ {t['tool']} 失败: {t['error']}")
        return "\n".join(lines) if lines else "我无法确定你想做什么,请说得更明确些。"

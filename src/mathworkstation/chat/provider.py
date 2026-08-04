"""LLM providers for the web chat driver.

The driver needs two kinds of provider:

* :class:`FakeProvider` — deterministic, offline. Pure function of
  ``(task, prompt, seed)``; used by default and by every test so the chat layer
  is reproducible in CI with no API key (this is the contract's S1 guarantee).
* :class:`RouterProvider` — wraps the existing ``mathworkstation.llm.LLMRouter``
  so the driver talks to the same OpenAI-compatible routes the rest of the
  workstation uses (gpt-5.x relays today, a DeepSeek route added to
  ``config/llm-routes.local.json`` when its key is available). It is never
  imported by tests.

Design note: intent resolution stays *rule-based and deterministic* (see
``tools.resolve_intent``). The provider only enriches free-form requests the
rules do not confidently cover — it can *suggest* tool calls, never bypass the
whitelist or the approval gates.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..m2.provider import CompletionRequest, CompletionResult, Provider

#: JSON schema handed to the LLM so it can only *propose* a tool call from the
#: frozen whitelist — never bypass it (contract: tools are the only write path).
_TOOL_CALL_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "tool": {
            "type": "string",
            "description": "One whitelisted tool name, e.g. list_cases, create_case, get_case, read_paper, list_ledger, approve_node, retry_node, degrade_node",
        },
        "args": {"type": "object", "description": "Tool arguments (keys depend on the tool)."},
        "pipeline": {
            "type": "boolean",
            "description": "True when the user wants to run the full automatic paper pipeline (submit problem + data, produce a paper).",
        },
        "confident": {
            "type": "boolean",
            "description": "True only when you are confident the user's intent maps to a tool; False when unsure (do not guess).",
        },
    },
    "required": ["confident"],
}


class FakeProvider(Provider):
    """Deterministic offline provider; re-exports the M2 implementation.

    The m2 layer already ships a pure ``(task, prompt, seed)`` fake. Reusing it
    keeps one deterministic provider across both layers instead of duplicating a
    second fake. ``task="chat"`` falls back to a terse acknowledgment, which is
    all a rule-resolved driver needs.
    """

    name = "fake"

    def __init__(self, seed: int = 0) -> None:
        from ..m2.provider import FakeProvider as _Fake

        self._impl = _Fake(seed)
        self.seed = seed

    def complete(self, req: CompletionRequest) -> CompletionResult:
        return self._impl.complete(req)

    def complete_json(self, req: CompletionRequest) -> dict[str, Any]:
        text = self.complete(req).text
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {}

    def resolve_intent_llm(self, message: str) -> dict[str, Any]:
        """Offline fallback: never guess, always report 'not confident'."""
        return {"confident": False}


class RouterProvider(Provider):
    """Adapters the workstation's ``LLMRouter`` to the provider interface.

    This is the *real* LLM path (used in production / non-CI). It sends a chat
    turn through the same OpenAI-compatible routes as the rest of the
    workstation, so a DeepSeek route configured in
    ``config/llm-routes.local.json`` (OpenAI-compatible, key via
    ``DEEPSEEK_API_KEY``) is picked up automatically.
    """

    name = "router"

    def __init__(self, router: Any, *, default_model: str | None = None) -> None:
        self.router = router
        self.default_model = default_model

    def complete(self, req: CompletionRequest) -> CompletionResult:
        messages = [{"role": m.role, "content": m.content} for m in req.messages]
        if not messages:
            messages = [{"role": "system", "content": req.system or ""}]
            if req.prompt:
                messages.append({"role": "user", "content": req.prompt})
        result = self.router.chat(
            # ChatRequest lives in mathworkstation.llm.router; import lazily to
            # keep the offline path free of the router dependency.
            __import__(
                "mathworkstation.llm.router",
                fromlist=["ChatRequest"],
            ).ChatRequest(
                messages=messages,
                model=self.default_model,
                max_tokens=req.max_tokens,
                temperature=req.temperature,
            )
        )
        return CompletionResult(
            text=result.content,
            model=result.model,
            provider=result.route_name,
            usage=dict(result.usage),
            raw={
                "latency_ms": result.latency_ms,
                "attempts": result.attempts,
                "raw_id": result.raw_id,
            },
        )

    def resolve_intent_llm(self, message: str) -> dict[str, Any]:
        """Use the real LLM to map free-form language to a whitelisted tool call.

        The model is constrained to a JSON schema and told it may only *propose*
        tools from the frozen whitelist. It returns ``{"confident": False}``
        when unsure — the driver then falls back to guidance instead of guessing
        at a destructive action.
        """
        system = (
            "You are the intent parser for a math-modeling workstation. "
            "Map the user's request to exactly one whitelisted tool or the "
            "full paper pipeline. Available tools: list_cases (list cases), "
            "get_case (view a case's DAG/artifacts/claims), create_case (create "
            "a case), read_paper (read the current paper), list_ledger (AI-usage "
            "ledger), approve_node / retry_node / degrade_node (human control). "
            "If the user wants a whole paper produced from problem+data, set "
            "pipeline=true. Only set confident=true when you are sure."
        )
        req = CompletionRequest(
            system=system,
            prompt=message,
            task="intent",
            max_tokens=200,
            response_schema=_TOOL_CALL_SCHEMA,
            temperature=0.0,
        )
        try:
            parsed = self.complete_json(req)
        except Exception:  # noqa: BLE001 - a failed parse must not fabricate a tool call
            return {"confident": False}
        if not isinstance(parsed, dict) or not parsed.get("confident"):
            return {"confident": False}
        tool = str(parsed.get("tool") or "").strip()
        args = parsed.get("args") if isinstance(parsed.get("args"), dict) else {}
        return {"confident": True, "tool": tool, "args": args, "pipeline": bool(parsed.get("pipeline"))}


def provider_from_router_config(config_path: str | None = None) -> RouterProvider:
    """Build a RouterProvider from ``config/llm-routes.local.json`` (or given path).

    Falls back to the deterministic FakeProvider if no valid route config / key
    is available, so the driver never hard-fails on a missing key — a missing
    key must degrade to reproducibility, never to fabrication.
    """
    from ..llm.config import RouterConfig
    from ..llm.router import LLMRouter
    from ..cli import _load_env_file

    _load_env_file(Path(".env.local"))
    path = config_path or "config/llm-routes.local.json"
    config = RouterConfig.model_validate_json(Path(path).read_text(encoding="utf-8"))
    return RouterProvider(LLMRouter(config))

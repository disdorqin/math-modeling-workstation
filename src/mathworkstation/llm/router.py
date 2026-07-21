from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .audit import LLMAuditLogger
from .config import RouteConfig, RouterConfig
from .redaction import safe_error


RETRYABLE_STATUS = {401, 403, 408, 409, 425, 429, 500, 502, 503, 504, 524}


@dataclass(frozen=True)
class ChatRequest:
    messages: list[dict[str, str]]
    model: str | None = None
    max_tokens: int = 2000
    temperature: float = 0.2
    response_format: dict[str, Any] | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ChatResult:
    content: str
    route_name: str
    model: str
    usage: dict[str, int]
    latency_ms: int
    attempts: int
    raw_id: str | None = None


@dataclass
class RouteHealth:
    consecutive_failures: int = 0
    cooldown_until: float = 0.0
    success_count: int = 0
    failure_count: int = 0
    latency_ewma_ms: float | None = None

    def available(self, now: float) -> bool:
        return now >= self.cooldown_until


class AllRoutesFailedError(RuntimeError):
    def __init__(self, attempts: list[dict[str, Any]]) -> None:
        summary = "; ".join(
            f"{item.get('route', 'unknown')} status={item.get('status_code')} error={item.get('error') or 'request failed'}"
            for item in attempts
        )
        super().__init__(f"all configured LLM routes failed: {summary}")
        self.attempts = attempts


class LLMRouter:
    def __init__(
        self,
        config: RouterConfig,
        audit: LLMAuditLogger | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self.audit = audit or LLMAuditLogger(None)
        self.transport = transport
        self.health = {route.name: RouteHealth() for route in config.routes}

    def chat(self, request: ChatRequest) -> ChatResult:
        if request.max_tokens > self.config.max_total_tokens:
            raise ValueError("request max_tokens exceeds configured token budget")
        attempts: list[dict[str, Any]] = []
        for number, route in enumerate(self._candidates(request.model)[: self.config.max_attempts], start=1):
            model = request.model if request.model in route.models else route.models[0]
            event = self._try_route(route, model, request, number)
            attempts.append(event)
            self.audit.write(event)
            if event["success"]:
                return ChatResult(
                    content=event["content"],
                    route_name=route.name,
                    model=model,
                    usage=event["usage"],
                    latency_ms=event["latency_ms"],
                    attempts=number,
                    raw_id=event.get("response_id"),
                )
            if not event["retryable"]:
                break
        raise AllRoutesFailedError(attempts)

    def health_snapshot(self) -> dict[str, dict[str, Any]]:
        now = time.monotonic()
        return {
            name: {
                "available": state.available(now),
                "consecutive_failures": state.consecutive_failures,
                "success_count": state.success_count,
                "failure_count": state.failure_count,
                "latency_ewma_ms": state.latency_ewma_ms,
                "cooldown_remaining_seconds": max(0.0, state.cooldown_until - now),
            }
            for name, state in self.health.items()
        }

    def _candidates(self, model: str | None) -> list[RouteConfig]:
        now = time.monotonic()
        routes = [
            route
            for route in self.config.routes
            if route.enabled
            and route.kind == "chat"
            and self.health[route.name].available(now)
        ]
        return sorted(
            routes,
            key=lambda route: (
                route.priority,
                self.health[route.name].latency_ewma_ms or float("inf"),
                route.name,
            ),
        )

    def _try_route(self, route: RouteConfig, model: str, request: ChatRequest, number: int) -> dict[str, Any]:
        started = time.perf_counter()
        payload: dict[str, Any] = {
            "model": model,
            "messages": request.messages,
            "max_tokens": request.max_tokens,
            "temperature": request.temperature,
        }
        if request.response_format:
            payload["response_format"] = request.response_format
        try:
            with httpx.Client(timeout=route.timeout_seconds, follow_redirects=True, transport=self.transport) as client:
                response = client.post(
                    route.base_url.rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {route.api_key}", "Content-Type": "application/json"},
                    json=payload,
                )
            latency = int((time.perf_counter() - started) * 1000)
            if response.is_success:
                body = response.json()
                choices = body.get("choices") or []
                content = str((choices[0].get("message") or {}).get("content") or "") if choices else ""
                if not content:
                    raise ValueError("response contains no message content")
                usage = {
                    key: int(value)
                    for key, value in (body.get("usage") or {}).items()
                    if key in {"prompt_tokens", "completion_tokens", "total_tokens"} and isinstance(value, int)
                }
                self._success(route, latency)
                return {
                    "event": "llm_attempt",
                    "route": route.name,
                    "base_url": route.base_url,
                    "model": model,
                    "attempt": number,
                    "status_code": response.status_code,
                    "latency_ms": latency,
                    "success": True,
                    "retryable": False,
                    "usage": usage,
                    "content": content,
                    "response_id": body.get("id"),
                    "risk_flags": route.risk_flags,
                    **request.metadata,
                }
            self._failure(route)
            return self._failure_event(
                route,
                model,
                number,
                latency,
                response.status_code,
                response.status_code in RETRYABLE_STATUS,
                self._response_error(response),
                request,
            )
        except (httpx.TimeoutException, httpx.NetworkError) as error:
            self._failure(route)
            return self._failure_event(
                route,
                model,
                number,
                int((time.perf_counter() - started) * 1000),
                None,
                True,
                f"{type(error).__name__}: {safe_error(error)}",
                request,
            )
        except Exception as error:
            self._failure(route)
            return self._failure_event(
                route,
                model,
                number,
                int((time.perf_counter() - started) * 1000),
                None,
                True,
                f"{type(error).__name__}: {safe_error(error)}",
                request,
            )

    def _success(self, route: RouteConfig, latency: int) -> None:
        state = self.health[route.name]
        state.consecutive_failures = 0
        state.success_count += 1
        state.latency_ewma_ms = latency if state.latency_ewma_ms is None else 0.7 * state.latency_ewma_ms + 0.3 * latency

    def _failure(self, route: RouteConfig) -> None:
        state = self.health[route.name]
        state.consecutive_failures += 1
        state.failure_count += 1
        if state.consecutive_failures >= route.failure_threshold:
            state.cooldown_until = time.monotonic() + route.cooldown_seconds

    @staticmethod
    def _response_error(response: httpx.Response) -> str:
        try:
            body = response.json()
            return safe_error(RuntimeError(str(body.get("error") or body.get("message") or "request failed")))
        except Exception:
            return safe_error(RuntimeError(response.text[:240]))

    @staticmethod
    def _failure_event(
        route: RouteConfig,
        model: str,
        number: int,
        latency: int,
        status_code: int | None,
        retryable: bool,
        detail: str,
        request: ChatRequest,
    ) -> dict[str, Any]:
        return {
            "event": "llm_attempt",
            "route": route.name,
            "base_url": route.base_url,
            "model": model,
            "attempt": number,
            "status_code": status_code,
            "latency_ms": latency,
            "success": False,
            "retryable": retryable,
            "error": detail,
            **request.metadata,
        }

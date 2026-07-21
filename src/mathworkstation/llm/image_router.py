from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from .audit import LLMAuditLogger
from .config import RouterConfig
from .redaction import safe_error
from .router import AllRoutesFailedError, RETRYABLE_STATUS


@dataclass(frozen=True)
class ImageRequest:
    prompt: str
    model: str | None = None
    size: str = "1024x1024"
    quality: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ImageResult:
    content: bytes
    route_name: str
    model: str
    latency_ms: int
    revised_prompt: str | None = None


class ImageRouter:
    def __init__(
        self,
        config: RouterConfig,
        audit: LLMAuditLogger | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.config = config
        self.audit = audit or LLMAuditLogger(None)
        self.transport = transport

    def generate(self, request: ImageRequest) -> ImageResult:
        routes = sorted(
            [route for route in self.config.routes if route.enabled and route.kind == "image"],
            key=lambda route: (route.priority, route.name),
        )
        attempts: list[dict[str, Any]] = []
        for number, route in enumerate(routes[: self.config.max_attempts], start=1):
            model = request.model if request.model in route.models else route.models[0]
            started = time.perf_counter()
            payload: dict[str, Any] = {"model": model, "prompt": request.prompt, "size": request.size, "n": 1}
            if request.quality:
                payload["quality"] = request.quality
            try:
                with httpx.Client(timeout=route.timeout_seconds, follow_redirects=True, transport=self.transport) as client:
                    response = client.post(
                        route.base_url.rstrip("/") + "/images/generations",
                        headers={"Authorization": f"Bearer {route.api_key}", "Content-Type": "application/json"},
                        json=payload,
                    )
                    latency = int((time.perf_counter() - started) * 1000)
                    if response.is_success:
                        body = response.json()
                        item = (body.get("data") or [None])[0] or {}
                        if item.get("b64_json"):
                            content = base64.b64decode(item["b64_json"], validate=True)
                        elif item.get("url"):
                            image_response = client.get(item["url"])
                            image_response.raise_for_status()
                            content = image_response.content
                        else:
                            raise ValueError("image response has neither b64_json nor url")
                        event = self._event(route.name, model, number, response.status_code, latency, True, False, request)
                        self.audit.write(event)
                        return ImageResult(content, route.name, model, latency, item.get("revised_prompt"))
                    event = self._event(
                        route.name,
                        model,
                        number,
                        response.status_code,
                        latency,
                        False,
                        response.status_code in RETRYABLE_STATUS,
                        request,
                        self._response_error(response),
                    )
            except Exception as error:
                event = self._event(
                    route.name,
                    model,
                    number,
                    None,
                    int((time.perf_counter() - started) * 1000),
                    False,
                    True,
                    request,
                    f"{type(error).__name__}: {safe_error(error)}",
                )
            attempts.append(event)
            self.audit.write(event)
            if not event["retryable"]:
                break
        raise AllRoutesFailedError(attempts)

    @staticmethod
    def _response_error(response: httpx.Response) -> str:
        try:
            body = response.json()
            detail = body.get("error") or body.get("message") or "request failed"
            return safe_error(RuntimeError(str(detail)))
        except Exception:
            return safe_error(RuntimeError(response.text[:240]))

    @staticmethod
    def _event(
        route: str,
        model: str,
        attempt: int,
        status_code: int | None,
        latency_ms: int,
        success: bool,
        retryable: bool,
        request: ImageRequest,
        error: str | None = None,
    ) -> dict[str, Any]:
        return {
            "event": "image_attempt",
            "route": route,
            "model": model,
            "attempt": attempt,
            "status_code": status_code,
            "latency_ms": latency_ms,
            "success": success,
            "retryable": retryable,
            "error": error,
            **request.metadata,
        }

"""Smoke-test the ChatDriver against a real LLM route.

Verifies the RouterProvider path actually talks to an OpenAI-compatible route
configured in ``config/llm-routes.local.json`` (gpt-5.x relays today; a DeepSeek
route can be added the same way). This is a live-network test — it needs a real
key and network, so it is NOT part of the offline pytest suite.

Usage:
    python scripts/smoke_chat_router.py                 # uses config/llm-routes.local.json
    MMW_ROUTES=config/llm-routes.local.json python scripts/smoke_chat_router.py
"""
from __future__ import annotations

import os
from pathlib import Path

from mathworkstation.chat import ChatDriver
from mathworkstation.chat.provider import RouterProvider
from mathworkstation.m2.provider import CompletionRequest


def main() -> None:
    config_path = os.environ.get("MMW_ROUTES", "config/llm-routes.local.json")
    driver = ChatDriver(router_config=config_path)
    print(f"provider = {driver.provider.name}")

    if not isinstance(driver.provider, RouterProvider):
        print("RouterProvider not active; run with a valid route config + key in .env.local")
        return

    # Direct provider call to prove the route works before wiring intent.
    req = CompletionRequest(
        system="You are the intent parser for a math-modeling workstation.",
        prompt="Reply with exactly: OK-ROUTE",
        task="chat",
    )
    result = driver.provider.complete(req)
    print(f"route={result.provider} model={result.model} reply={result.text.strip()!r}")
    print(f"usage={result.usage}")

    # Now drive a real conversational turn through the driver.
    reply = driver.chat("你好,帮我看看现在有哪些案例", approved_by="smoke")
    print("\n--- driver.chat reply ---")
    print(reply["reply"])
    print(f"tool_calls={reply['tool_calls']}")


if __name__ == "__main__":
    main()

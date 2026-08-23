"""Web chat driver: turn conversational input into gated workstation actions.

This package is the interface layer between a web shell (FastAPI, built by
WorkBuddy) and the existing evidence-first workstation services. Its contract is
frozen in ``docs/web-chat-driver-contract.md`` (v1.0).

Design invariants:
  * The LLM (or chat input) may only *suggest* tool calls. Every call must map
    to a whitelisted tool in :mod:`mathworkstation.chat.tools` that routes back
    into the existing registries / workflow state machine — the evidence gates
    and human-approval gates can never be bypassed by conversational text.
  * Every interaction that touches a Case is written to the AI-usage ledger
    (:class:`AILedger`), the data source for the 2026 CUMCM AI-disclosure
    material.
  * Long pipelines run through a disk-persisted job queue
    (:class:`JobManager`), so the frontend can show progress and resume.
"""
from __future__ import annotations

from .driver import ChatDriver
from .jobs import JobManager
from .ledger import AILedger
from .provider import FakeProvider, RouterProvider
from .services import build_services

__all__ = [
    "AILedger",
    "ChatDriver",
    "FakeProvider",
    "JobManager",
    "RouterProvider",
    "build_services",
]

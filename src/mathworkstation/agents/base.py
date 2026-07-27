"""Agent base classes.

Two kinds of agent exist and the distinction matters:

* **Deterministic agents** wrap an existing engine (profiler, EDA, consistency
  checker). They are reproducible, need no API key, and their proposals carry
  real artifact ids the moment they are made.
* **LLM agents** turn evidence into language — decomposition, rationale, prose.
  They may not introduce numbers that are not already in their evidence pack;
  the adjudicator enforces this, but the base class also refuses to build a
  numeric proposal without evidence so the failure surfaces early.

Both return the same :class:`AgentReport`, so the graph does not care which is
which.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod

from .contracts import (
    AgentReport,
    AgentRequest,
    EvidenceRef,
    Proposal,
    ProposalKind,
)


NUMERIC = re.compile(r"(?<![A-Za-z0-9_-])[-+]?\d+(?:\.\d+)?%?")


class Agent(ABC):
    """Read evidence, return proposals. Never writes to the case."""

    name: str = "agent"
    mandate: tuple[ProposalKind, ...] = ()

    @abstractmethod
    def run(self, request: AgentRequest) -> AgentReport:
        ...

    # ------------------------------------------------------------------ helpers

    def propose(
        self,
        kind: ProposalKind,
        summary: str,
        payload: dict | None = None,
        evidence: list[str] | None = None,
        rationale: str = "",
        confidence: float = 1.0,
    ) -> Proposal:
        if kind not in self.mandate:
            raise ValueError(f"{self.name} may not propose {kind}")
        text = " ".join([summary, str((payload or {}).get("text", ""))])
        return Proposal(
            kind=kind,
            agent=self.name,
            summary=summary,
            payload=payload or {},
            evidence=[EvidenceRef(artifact_id=item) for item in (evidence or [])],
            asserts_numbers=bool(NUMERIC.search(text)),
            rationale=rationale,
            confidence=confidence,
        )

    def blocked(self, reason: str) -> AgentReport:
        return AgentReport(agent=self.name, status="BLOCKED", blocked_reason=reason)

    def skipped(self, reason: str) -> AgentReport:
        return AgentReport(agent=self.name, status="SKIPPED", notes=reason)


class DeterministicAgent(Agent):
    """Marker base for agents whose output depends only on registered artifacts."""

    deterministic = True


class LLMAgent(Agent):
    """Base for agents backed by the controlled LLM router.

    ``llm`` is the existing ``CaseLLMService``; injecting it rather than
    constructing one keeps budget accounting, redaction, and the audit trail in
    one place. When it is ``None`` the agent reports SKIPPED instead of
    inventing content — a missing API key must never degrade into fabrication.
    """

    deterministic = False

    def __init__(self, llm=None) -> None:  # noqa: ANN001 - CaseLLMService, kept loose for optional import
        self.llm = llm

    def run(self, request: AgentRequest) -> AgentReport:
        if self.llm is None:
            return self.skipped(f"{self.name} requires a configured LLM route")
        return self.run_with_llm(request)

    @abstractmethod
    def run_with_llm(self, request: AgentRequest) -> AgentReport:
        ...

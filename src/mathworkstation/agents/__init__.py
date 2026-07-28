"""Multi-agent layer.

Design rule, in one line: **agents propose, the workflow adjudicates.**

Agents never touch the case directory. They read a read-only view of registered
evidence and return typed :class:`~mathworkstation.agents.contracts.Proposal`
objects. Every write to the case — a claim, a figure promotion, a section draft,
a DAG transition — happens inside
:class:`~mathworkstation.agents.adjudicator.Adjudicator`, which applies the same
gates the manual CLI path applies and records an append-only decision log.

That boundary is what keeps "No Evidence, No Claim" true when the proposer is a
language model: a fabricated number cannot become a claim, because the claim
registry still requires a `paper_eligible` artifact behind it.
"""

from .contracts import (
    AgentReport,
    AgentRequest,
    EvidenceRef,
    Proposal,
    ProposalKind,
    RejectionCode,
    Verdict,
    VerdictStatus,
    WorkstationState,
)

__all__ = [
    "AgentReport",
    "AgentRequest",
    "EvidenceRef",
    "Proposal",
    "ProposalKind",
    "RejectionCode",
    "Verdict",
    "VerdictStatus",
    "WorkstationState",
]

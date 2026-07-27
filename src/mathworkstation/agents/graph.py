"""Orchestration.

The graph is built on LangGraph when it is installed, and on an equivalent
in-process runner when it is not. Both execute the same node function, mutate
the same :class:`WorkstationState`, and produce the same decision log — the
fallback exists so that installing an agent framework is not a precondition for
running, testing, or reproducing a case.

One node per agent. Each node: build the request → run the agent → adjudicate
every proposal → fold the verdicts into state. A node that returns BLOCKED, or
whose proposals draw a BLOCK-severity review finding, halts the run rather than
letting later agents build on unsound ground.
"""

from __future__ import annotations

from typing import Any, Callable

from .adjudicator import Adjudicator
from .base import Agent
from .contracts import AgentRequest, VerdictStatus, WorkstationState


def langgraph_available() -> bool:
    try:  # pragma: no cover - depends on the environment
        import langgraph.graph  # noqa: F401
    except ImportError:
        return False
    return True


def make_node(agent: Agent, adjudicator: Adjudicator) -> Callable[[WorkstationState], dict[str, Any]]:
    """Wrap one agent as a graph node.

    Returns a partial state update (LangGraph merges it; the fallback runner
    applies it), never the whole state, so nodes cannot clobber each other.
    """

    def node(state: WorkstationState) -> dict[str, Any]:
        if state.get("halted"):
            return {}
        request = AgentRequest(
            case_id=state["case_id"],
            session_id=state.get("session_id"),
            goal=state.get("goal", "complete the modeling case"),
            inputs={
                "dataset_id": state.get("dataset_id"),
                "target_column": state.get("target_column"),
            },
        )
        report = agent.run(request)
        reports = [*state.get("reports", []), report.model_dump(mode="json")]

        if report.status == "BLOCKED":
            return {
                "reports": reports,
                "blocked": [*state.get("blocked", []), agent.name],
                "halted": True,
                "halt_reason": f"{agent.name}: {report.blocked_reason}",
            }

        verdicts = list(state.get("verdicts", []))
        accepted = list(state.get("accepted", []))
        needs_human: list[str] = []
        for proposal in report.proposals:
            verdict = adjudicator.decide(state["case_id"], proposal)
            verdicts.append(verdict.model_dump(mode="json"))
            if verdict.status is VerdictStatus.ACCEPTED:
                accepted.append(
                    {
                        "agent": agent.name,
                        "kind": proposal.kind.value,
                        "summary": proposal.summary,
                        "produced": verdict.produced,
                    }
                )
            elif verdict.status is VerdictStatus.NEEDS_HUMAN:
                needs_human.append(f"{proposal.kind.value}: {verdict.message}")

        update: dict[str, Any] = {
            "reports": reports,
            "verdicts": verdicts,
            "accepted": accepted,
        }
        if needs_human:
            update["halted"] = True
            update["halt_reason"] = f"{agent.name} 需要人工裁决: " + "; ".join(needs_human[:3])
        return update

    node.__name__ = f"node_{agent.name}"
    return node


def run_sequence(
    agents: list[Agent],
    adjudicator: Adjudicator,
    state: WorkstationState,
) -> WorkstationState:
    """Dependency-free executor with LangGraph's merge semantics."""
    current: WorkstationState = dict(state)  # type: ignore[assignment]
    for agent in agents:
        update = make_node(agent, adjudicator)(current)
        current.update(update)  # type: ignore[arg-type]
    return current


def build_langgraph(agents: list[Agent], adjudicator: Adjudicator):  # pragma: no cover - optional dep
    """Compile the same node sequence into a LangGraph ``StateGraph``.

    Linear today because the deterministic slice is linear. The shape to grow
    into is fan-out at the modeling stage (several candidate architects in
    parallel) followed by a judge node — LangGraph's conditional edges and
    checkpointer are why this seam exists at all.
    """
    from langgraph.graph import END, START, StateGraph

    graph = StateGraph(WorkstationState)
    previous = START
    for agent in agents:
        name = f"node_{agent.name}"
        graph.add_node(name, make_node(agent, adjudicator))
        graph.add_edge(previous, name)
        previous = name
    graph.add_edge(previous, END)
    return graph.compile()


def run(
    agents: list[Agent],
    adjudicator: Adjudicator,
    state: WorkstationState,
    prefer_langgraph: bool = True,
) -> tuple[WorkstationState, str]:
    """Execute the pipeline, returning the final state and the runtime used."""
    if prefer_langgraph and langgraph_available():
        compiled = build_langgraph(agents, adjudicator)
        return compiled.invoke(state), "langgraph"
    return run_sequence(agents, adjudicator, state), "builtin"

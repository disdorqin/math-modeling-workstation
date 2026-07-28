"""Execute the new modeling-agent fan-out against a real, already-run case.

Not a permanent CLI command yet (see docs/multi-agent-architecture.md for why:
this is execution evidence for one concrete case, not a general entrypoint).
Prints every artifact/verdict id it produces so the run can be inspected by id
afterwards, and refuses to guess a winner -- the judge decides from the
evaluation evidence, and this script only reports what actually happened.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mathworkstation.agents.adjudicator import Adjudicator
from mathworkstation.agents.contracts import AgentRequest
from mathworkstation.agents.modeling import build_modeling_agents, build_modeling_protocol
from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.claims import ClaimRegistry
from mathworkstation.datasets import DatasetRegistry
from mathworkstation.figure_registry import FigureRegistry


def main() -> None:
    output_root = sys.argv[1]
    case_id = sys.argv[2]
    dataset_id = sys.argv[3]
    target_column = sys.argv[4]
    feature_columns = sys.argv[5].split(",")

    cases = CaseManager(output_root)
    artifacts = ArtifactRegistry(cases)
    datasets = DatasetRegistry(cases, artifacts)
    claims = ClaimRegistry(cases, artifacts, datasets)
    figures = FigureRegistry(cases, artifacts)
    adjudicator = Adjudicator(cases, artifacts, claims, figures)

    print("== building modeling protocol ==")
    built = build_modeling_protocol(
        cases, artifacts, datasets, case_id, dataset_id, target_column, feature_columns,
        primary_metric="rmse", n_splits=5, random_state=42,
    )
    protocol_artifact_id = built["protocol_artifact_id"]
    print(json.dumps({
        "protocol_artifact_id": protocol_artifact_id,
        "protocol_hash": built["protocol_hash"],
        "n_rows": built["protocol"]["n_rows"],
        "n_splits": built["protocol"]["n_splits"],
    }, ensure_ascii=False, indent=2))

    agents = build_modeling_agents(cases, artifacts)
    request_base = dict(case_id=case_id, goal="modeling fan-out execution evidence")

    print("\n== running candidate agents (no self-selection) ==")
    for name in ("linear_model_agent", "tree_model_agent", "robust_baseline_agent"):
        agent = agents[name]
        request = AgentRequest(**request_base, inputs={"protocol_artifact_id": protocol_artifact_id})
        report = agent.run(request)
        print(f"-- {name}: status={report.status} notes={report.notes!r}")
        for proposal in report.proposals:
            verdict = adjudicator.decide(case_id, proposal)
            print(f"   proposal={proposal.proposal_id} verdict={verdict.status} produced={verdict.produced}")

    print("\n== running model_evaluation_agent ==")
    eval_agent = agents["model_evaluation_agent"]
    eval_request = AgentRequest(**request_base, inputs={"protocol_artifact_id": protocol_artifact_id})
    eval_report = eval_agent.run(eval_request)
    print(f"-- model_evaluation_agent: status={eval_report.status} notes={eval_report.notes!r}")
    comparison_artifact_id = None
    for proposal in eval_report.proposals:
        verdict = adjudicator.decide(case_id, proposal)
        print(f"   proposal={proposal.proposal_id} verdict={verdict.status} produced={verdict.produced}")
        comparison_artifact_id = proposal.payload.get("comparison_artifact_id") or comparison_artifact_id

    if comparison_artifact_id is None:
        print("no comparison artifact produced; stopping before judge")
        return

    print("\n== running model_judge_agent ==")
    judge_agent = agents["model_judge_agent"]
    judge_request = AgentRequest(**request_base, inputs={"comparison_artifact_id": comparison_artifact_id})
    judge_report = judge_agent.run(judge_request)
    print(f"-- model_judge_agent: status={judge_report.status} notes={judge_report.notes!r}")
    for proposal in judge_report.proposals:
        verdict = adjudicator.decide(case_id, proposal)
        print(f"   proposal={proposal.proposal_id} verdict={verdict.status} codes={verdict.codes} produced={verdict.produced}")

    print("\n== comparison artifact contents ==")
    comparison_artifact = artifacts.get(case_id, comparison_artifact_id)
    comparison_path = cases.case_root(case_id) / comparison_artifact["path"]
    print(comparison_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()

from __future__ import annotations

from pathlib import Path

from .paper_contracts import SubproblemContract

MCM2024_C_DATA_DIR = Path(__file__).resolve().parents[2] / "examples" / "mcm2024-c"


def mcm2024_c_contracts() -> list[SubproblemContract]:
    """Contracts for the 2024 MCM C showcase.

    This intentionally defines problem structure only. Solver evidence and
    narrative are produced by the normal research-state pipeline.
    """
    return [
        SubproblemContract(
            subproblem_id="SP1",
            title="Serve-adjusted flow and empirical momentum evidence",
            objective="Define a measurable match-flow quantity after removing the structural server advantage, then test whether apparent persistence exceeds a serve-conditioned random baseline.",
            inputs=["official point-level Wimbledon data", "server identity", "point winner", "within-match order"],
            outputs=["serve-adjusted Flow Score", "match-level persistence/null-test evidence", "featured-final flow description"],
            constraints=["do not interpret a visual run as causal psychological momentum", "preserve within-match order", "condition the null model on the observed server sequence"],
            evaluation_metrics=["Ljung-Box p-value", "server-conditioned simulation p-value", "flow excursion"],
        ),
        SubproblemContract(
            subproblem_id="SP2",
            title="Probabilistic structure of local flow reversal",
            objective="Model the probability that a non-neutral local flow state reverses within a short future horizon using only information available at the current point.",
            inputs=["SP1 serve-adjusted flow state", "current score context", "recent technical and workload indicators"],
            outputs=["swing-event definition", "conditional swing risk", "interpretable state/feature effects"],
            constraints=["future points may label the target but may not enter predictors", "complete matches must remain grouped in validation", "predictive associations are not causal effects"],
            evaluation_metrics=["grouped ROC AUC", "balanced accuracy", "calibration/holdout behavior"],
        ),
        SubproblemContract(
            subproblem_id="SP3",
            title="Cross-match validation and coaching decision support",
            objective="Stress-test the swing-risk framework on unseen matches, inspect sensitivity to the flow definition, and translate accepted probabilistic evidence into bounded coaching guidance.",
            inputs=["SP2 swing-risk model", "held-out match predictions", "flow-window sensitivity results"],
            outputs=["full-final holdout assessment", "cross-match generalization", "sensitivity evidence", "coaching decision rules"],
            constraints=["do not claim deterministic swing control", "distinguish structural transfer from numerical parameter transfer", "recommendations must inherit accepted SP1-SP2 evidence"],
            evaluation_metrics=["held-out final AUC", "match-level AUC distribution", "window sensitivity"],
        ),
    ]


def link_mcm2024_c_dependencies(graph):
    sp1 = graph.node("SP1")
    sp1.task_family = "exploratory_analysis"
    sp1.execution_kind = "ANALYSIS"
    sp1.plan.task_family = "exploratory_analysis"
    sp1.plan.execution_kind = "ANALYSIS"
    sp1.plan.candidate_methods = ["serve adjusted flow and null tests"]
    sp1.plan.validation_protocol = ["serve-conditioned null and residual persistence audit"]
    sp1.plan.requires_model_execution = False
    sp1.plan.executor_family = "exploratory_analysis"
    sp1.plan.executor_available = True
    if sp1.experiments:
        sp1.experiments[0].method = sp1.plan.candidate_methods[0]
        sp1.experiments[0].validation_protocol = list(sp1.plan.validation_protocol)

    sp2 = graph.node("SP2")
    sp2.task_family = "classification"
    sp2.execution_kind = "MODEL"
    sp2.plan.task_family = "classification"
    sp2.plan.execution_kind = "MODEL"
    sp2.plan.candidate_methods = ["grouped swing hazard classification"]
    sp2.plan.validation_protocol = ["grouped match holdout probability validation"]
    sp2.plan.requires_model_execution = True
    sp2.plan.executor_family = "classification"
    sp2.plan.executor_available = True
    if sp2.experiments:
        sp2.experiments[0].method = sp2.plan.candidate_methods[0]
        sp2.experiments[0].validation_protocol = list(sp2.plan.validation_protocol)

    sp3 = graph.node("SP3")
    sp3.task_family = "classification"
    sp3.execution_kind = "MODEL"
    sp3.plan.task_family = "classification"
    sp3.plan.execution_kind = "MODEL"
    sp3.plan.candidate_methods = ["heldout swing risk generalization"]
    sp3.plan.validation_protocol = ["unseen-final holdout and flow-window sensitivity"]
    sp3.plan.requires_model_execution = True
    sp3.plan.executor_family = "classification"
    sp3.plan.executor_available = True
    if sp3.experiments:
        sp3.experiments[0].method = sp3.plan.candidate_methods[0]
        sp3.experiments[0].validation_protocol = list(sp3.plan.validation_protocol)

    sp2.dependencies = ["SP1"]
    sp3.dependencies = ["SP1", "SP2"]
    return graph

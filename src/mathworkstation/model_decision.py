from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .io_utils import atomic_write_json, now_iso

TIE_TOLERANCE = 0.01

# Structural complexity only. Models sharing a rank are deliberately not
# separated by arbitrary preference; if they are within tolerance and no
# strictly simpler candidate exists, the decision remains TIE and the raw
# metric leader is only a provisional downstream choice.
COMPLEXITY_RANK: dict[str, int] = {
    "linear": 0,
    "logistic": 0,
    "ridge": 1,
    "lasso": 1,
    "elastic_net": 1,
    "random_forest": 2,
    "gradient_boosting": 3,
}


@dataclass(frozen=True)
class CanonicalModelDecision:
    outcome: str
    selected_model: str | None
    raw_best_model: str | None
    tied_models: tuple[str, ...]
    provisional: bool
    rationale: str


class CanonicalModelJudge:
    """Judge the canonical comparison used by paper evidence.

    The evaluation engine supplies the numeric comparison. This judge does not
    retrain models or invent scores; it only applies the workstation policy:
    primary metric direction, 1% equivalence tolerance, then simpler-model
    preference. Unresolved equal-complexity ties remain explicit rather than
    being falsely narrated as a unique winner.
    """

    def __init__(self, cases: CaseManager, artifacts: ArtifactRegistry) -> None:
        self.cases = cases
        self.artifacts = artifacts

    def decide(
        self,
        case_id: str,
        comparison: dict[str, Any],
        comparison_artifact_id: str,
        *,
        created_by: str = "canonical_model_judge",
    ) -> dict[str, Any]:
        primary_metric = str(comparison["primary_metric"])
        models = comparison.get("models", {})
        direction = "MINIMIZE" if primary_metric in {"rmse", "mae"} else "MAXIMIZE"
        key = f"{primary_metric}_mean"
        valid = {
            str(name): payload
            for name, payload in models.items()
            if isinstance(payload, dict) and isinstance(payload.get(key), (int, float))
        }
        decision = decide_canonical_model(valid, primary_metric)
        experiment_id = str(comparison.get("experiment_id", ""))
        payload = {
            "schema_version": 1,
            "case_id": case_id,
            "experiment_id": experiment_id,
            "comparison_artifact_id": comparison_artifact_id,
            "primary_metric": primary_metric,
            "metric_direction": direction,
            "tie_tolerance": TIE_TOLERANCE,
            "outcome": decision.outcome,
            "selected_model": decision.selected_model,
            "raw_best_model": decision.raw_best_model,
            "tied_models": list(decision.tied_models),
            "provisional": decision.provisional,
            "rationale": decision.rationale,
            "complexity_rank": {
                name: COMPLEXITY_RANK.get(name)
                for name in decision.tied_models
            },
            "generated_at": now_iso(),
        }
        root = self.cases.case_root(case_id)
        path = root / "analysis" / "canonical_model_decision.json"
        atomic_write_json(path, payload)
        artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "canonical_model_decision",
            created_by,
            upstream=[comparison_artifact_id],
            paper_eligible=False,
        )
        return {**payload, "artifact_id": artifact["artifact_id"]}


def decide_canonical_model(
    models: dict[str, dict[str, Any]],
    primary_metric: str,
) -> CanonicalModelDecision:
    key = f"{primary_metric}_mean"
    candidates = [
        (name, float(payload[key]))
        for name, payload in models.items()
        if isinstance(payload.get(key), (int, float))
    ]
    if not candidates:
        return CanonicalModelDecision(
            outcome="NO_ACCEPTABLE_WINNER",
            selected_model=None,
            raw_best_model=None,
            tied_models=(),
            provisional=False,
            rationale="no candidate has a valid primary-metric mean",
        )

    minimize = primary_metric in {"rmse", "mae"}
    ordered = sorted(candidates, key=lambda item: item[1], reverse=not minimize)
    raw_best, raw_value = ordered[0]
    tied = [name for name, value in ordered if _within_tolerance(raw_value, value)]
    if len(tied) == 1:
        return CanonicalModelDecision(
            outcome="WINNER",
            selected_model=raw_best,
            raw_best_model=raw_best,
            tied_models=(raw_best,),
            provisional=False,
            rationale=f"{raw_best} is strictly best outside the {TIE_TOLERANCE:.0%} equivalence tolerance",
        )

    ranks = {name: COMPLEXITY_RANK.get(name, 10_000) for name in tied}
    simplest_rank = min(ranks.values())
    simplest = [name for name in tied if ranks[name] == simplest_rank]
    if len(simplest) == 1:
        selected = simplest[0]
        return CanonicalModelDecision(
            outcome="WINNER",
            selected_model=selected,
            raw_best_model=raw_best,
            tied_models=tuple(tied),
            provisional=False,
            rationale=(
                f"{', '.join(tied)} are within the {TIE_TOLERANCE:.0%} equivalence tolerance; "
                f"selected strictly simpler model {selected}"
            ),
        )

    # Keep the pipeline executable for sensitivity/paper diagnostics, but mark
    # the choice provisional. The outer auditor turns this TIE into a model-plan
    # repair finding, so a recurrent run cannot silently converge on it.
    return CanonicalModelDecision(
        outcome="TIE",
        selected_model=raw_best,
        raw_best_model=raw_best,
        tied_models=tuple(tied),
        provisional=True,
        rationale=(
            f"{', '.join(tied)} are within the {TIE_TOLERANCE:.0%} equivalence tolerance and share the "
            f"same minimum structural complexity rank; {raw_best} is provisional only"
        ),
    )


def _within_tolerance(best_value: float, other_value: float) -> bool:
    denominator = abs(best_value) or 1.0
    return abs(other_value - best_value) / denominator <= TIE_TOLERANCE

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from .corpus_distillation import (
    CorpusPaperFingerprint,
    _weighted_layout_prior,
    _weighted_list_prevalence,
    _weighted_prevalence,
    _weighted_prior,
)
from .io_utils import atomic_write_json, now_iso, read_json


class PriorSlice(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slice_id: str
    scope: dict[str, Any]
    paper_count: int
    parsed_count: int
    visual_only_count: int
    style_metrics: dict[str, float] = Field(default_factory=dict)
    layout_metrics: dict[str, float] = Field(default_factory=dict)
    modeling_metrics: dict[str, float] = Field(default_factory=dict)
    figure_purpose_prevalence: dict[str, float] = Field(default_factory=dict)
    validation_prevalence: dict[str, float] = Field(default_factory=dict)
    question_type_prevalence: dict[str, float] = Field(default_factory=dict)
    model_selection_rationale_prevalence: dict[str, float] = Field(default_factory=dict)
    model_transition_prevalence: dict[str, float] = Field(default_factory=dict)


class CorpusPriorBank(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    generated_at: str
    corpus_papers: int
    parsed_papers: int
    visual_only_papers: int
    policies: dict[str, Any]
    slices: dict[str, PriorSlice]
    students: dict[str, dict[str, Any]]
    universal_rules: list[str]


class PriorRoute(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    competition: str
    task_families: list[str]
    skills: list[str]
    selected_slice_ids: list[str]
    selected_slices: list[PriorSlice]
    guidance: list[str]


_TASK_ALIASES = {
    "optimization": "optimization",
    "graph_optimization": "optimization",
    "forecasting": "forecasting",
    "distribution_forecasting": "forecasting",
    "prediction": "forecasting",
    "regression": "statistical_analysis",
    "statistics": "statistical_analysis",
    "statistical_analysis": "statistical_analysis",
    "classification": "classification_or_scoring",
    "classification_or_scoring": "classification_or_scoring",
    "ranking": "classification_or_scoring",
    "evaluation": "classification_or_scoring",
    "resource_allocation": "resource_allocation",
    "simulation": "simulation",
    "uncertainty": "uncertainty_or_stochastic",
    "uncertainty_or_stochastic": "uncertainty_or_stochastic",
    "spatial": "spatial_or_layout_design",
    "layout": "spatial_or_layout_design",
    "spatial_or_layout_design": "spatial_or_layout_design",
    "decision": "decision_strategy",
    "decision_strategy": "decision_strategy",
    "mechanistic_modeling": "mechanistic_modeling",
    "scheduling": "scheduling",
}


def build_prior_bank(
    fingerprints: Iterable[CorpusPaperFingerprint],
    *,
    min_slice_papers: int = 3,
) -> CorpusPriorBank:
    items = list(fingerprints)
    slices: dict[str, PriorSlice] = {}

    def add(slice_id: str, values: list[CorpusPaperFingerprint], scope: dict[str, Any]) -> None:
        if len(values) < min_slice_papers:
            return
        slices[slice_id] = _build_slice(slice_id, values, scope)

    for competition in ("MCM", "CUMCM"):
        competition_items = [item for item in items if item.source.competition == competition]
        add(f"competition:{competition}", competition_items, {"competition": competition})
        add(
            f"competition:{competition}:modern",
            [item for item in competition_items if item.source.year >= 2023],
            {"competition": competition, "era": "2023+"},
        )
        add(
            f"competition:{competition}:C",
            [item for item in competition_items if item.source.c_problem],
            {"competition": competition, "problem_letter": "C"},
        )
        add(
            f"competition:{competition}:C:modern",
            [item for item in competition_items if item.source.c_problem and item.source.year >= 2023],
            {"competition": competition, "problem_letter": "C", "era": "2023+"},
        )

    era_ranges = {
        "classic": lambda year: year and year <= 2019,
        "transition": lambda year: 2020 <= year <= 2022,
        "modern": lambda year: year >= 2023,
    }
    for era, predicate in era_ranges.items():
        add(f"era:{era}", [item for item in items if predicate(item.source.year)], {"era": era})

    c_items = [item for item in items if item.source.c_problem]
    add("problem:C", c_items, {"problem_letter": "C"})
    task_names = sorted({name for item in c_items for name in item.question_types})
    for task_name in task_names:
        add(
            f"task:{task_name}",
            [item for item in c_items if task_name in item.question_types],
            {"problem_letter": "C", "task_family": task_name},
        )

    universal_rules = _universal_rules(slices)
    students = {
        "abstract": {
            "preferred_slices": ["competition:{competition}:C:modern", "competition:{competition}:C"],
            "purpose": "Calibrate information density and supported-result coverage; never copy source wording.",
        },
        "figures": {
            "preferred_slices": ["competition:{competition}:modern", "competition:{competition}:C:modern"],
            "purpose": "Choose evidence-serving figure roles and modern visual density without raw figure quotas.",
        },
        "layout": {
            "preferred_slices": ["competition:{competition}:modern"],
            "purpose": "Use recent layout/page signals only where extraction is reliable; scanned-page signals stay separate.",
        },
        "validation": {
            "preferred_slices": ["task:{task_family}", "competition:{competition}:C"],
            "purpose": "Recommend validation families that match the task; corpus frequency never fabricates an experiment.",
        },
        "narrative": {
            "preferred_slices": ["competition:{competition}:C", "task:{task_family}"],
            "purpose": "Maintain a problem-data-method-validation-result-decision chain rather than a fixed paper template.",
        },
    }
    return CorpusPriorBank(
        generated_at=now_iso(),
        corpus_papers=len(items),
        parsed_papers=sum(item.status == "PARSED" for item in items),
        visual_only_papers=sum(item.status == "VISUAL_ONLY" for item in items),
        policies={
            "learn_patterns_not_wording": True,
            "c_modeling_prior_only_from_c_papers": True,
            "non_c_style_only": True,
            "recent_style_preferred": True,
            "classic_modeling_logic_retained": True,
            "no_global_style_monopoly": True,
            "minimum_slice_papers": min_slice_papers,
        },
        slices=dict(sorted(slices.items())),
        students=students,
        universal_rules=universal_rules,
    )


def persist_prior_bank(path: str | Path, bank: CorpusPriorBank) -> None:
    atomic_write_json(Path(path), bank.model_dump(mode="json"))


def load_prior_bank(path: str | Path) -> CorpusPriorBank:
    return CorpusPriorBank.model_validate(read_json(Path(path)))


class PriorRouter:
    def __init__(self, bank: CorpusPriorBank | str | Path) -> None:
        self.bank = load_prior_bank(bank) if isinstance(bank, (str, Path)) else bank

    def route(
        self,
        profile_id: str,
        *,
        task_families: Iterable[str] = (),
        skills: Iterable[str] = ("abstract", "figures", "layout", "validation", "narrative"),
    ) -> PriorRoute:
        competition = "CUMCM" if profile_id == "CUMCM_C" else "MCM"
        normalized_tasks = sorted(
            {
                _TASK_ALIASES.get(str(value).strip().lower(), str(value).strip().lower())
                for value in task_families
                if str(value).strip()
            }
        )
        requested_skills = [str(value) for value in skills]
        candidate_ids: list[str] = [
            f"competition:{competition}:C",
            f"competition:{competition}:C:modern",
            f"competition:{competition}:modern",
        ]
        candidate_ids.extend(f"task:{task}" for task in normalized_tasks)
        selected_ids = [value for value in dict.fromkeys(candidate_ids) if value in self.bank.slices]
        selected = [self.bank.slices[value] for value in selected_ids]
        guidance = list(self.bank.universal_rules)
        guidance.extend(_route_guidance(selected, requested_skills))
        return PriorRoute(
            profile_id=profile_id,
            competition=competition,
            task_families=normalized_tasks,
            skills=requested_skills,
            selected_slice_ids=selected_ids,
            selected_slices=selected,
            guidance=list(dict.fromkeys(guidance)),
        )


def _build_slice(
    slice_id: str,
    items: list[CorpusPaperFingerprint],
    scope: dict[str, Any],
) -> PriorSlice:
    parsed = [item for item in items if item.status == "PARSED"]
    visual = [item for item in items if item.status in {"PARSED", "VISUAL_ONLY"}]
    c_parsed = [item for item in parsed if item.source.c_problem]
    return PriorSlice(
        slice_id=slice_id,
        scope=scope,
        paper_count=len(items),
        parsed_count=len(parsed),
        visual_only_count=sum(item.status == "VISUAL_ONLY" for item in items),
        style_metrics=_weighted_prior(parsed, weight_name="style_weight"),
        layout_metrics=_weighted_layout_prior(visual, weight_name="style_weight"),
        modeling_metrics=_weighted_prior(c_parsed, weight_name="modeling_weight"),
        figure_purpose_prevalence=_weighted_prevalence(parsed, "figure_purposes", "style_weight"),
        validation_prevalence=_weighted_list_prevalence(c_parsed, "validation_types", "modeling_weight"),
        question_type_prevalence=_weighted_list_prevalence(c_parsed, "question_types", "modeling_weight"),
        model_selection_rationale_prevalence=_weighted_list_prevalence(
            c_parsed, "model_selection_rationales", "modeling_weight"
        ),
        model_transition_prevalence=_weighted_list_prevalence(
            c_parsed, "model_transition_patterns", "modeling_weight"
        ),
    )


def _universal_rules(slices: dict[str, PriorSlice]) -> list[str]:
    rules = [
        "Prefer a coherent problem-data-method-validation-result-decision chain over model complexity.",
        "Every figure or table must serve an evidence or explanation role; corpus counts are calibration signals, not quotas.",
        "Use recent papers mainly for presentation/style and retain classic C papers for modeling logic.",
        "Never introduce an algorithm, metric, comparison, or experiment merely because it is common in excellent papers.",
    ]
    mcm = slices.get("competition:MCM:C")
    cumcm = slices.get("competition:CUMCM:C")
    if mcm and cumcm:
        shared_validation = [
            name
            for name in set(mcm.validation_prevalence) & set(cumcm.validation_prevalence)
            if mcm.validation_prevalence.get(name, 0.0) >= 0.35
            and cumcm.validation_prevalence.get(name, 0.0) >= 0.35
        ]
        if shared_validation:
            rules.append(
                "When task semantics permit, check at least one appropriate robustness/validation mechanism observed across both MCM-C and CUMCM-C corpora: "
                + ", ".join(sorted(shared_validation))
                + "."
            )
    return rules


def _route_guidance(slices: list[PriorSlice], skills: list[str]) -> list[str]:
    guidance: list[str] = []
    if "abstract" in skills:
        candidates = [s for s in slices if s.style_metrics.get("weighted_median_abstract_units", 0) > 0]
        if candidates:
            # Abstract style should stay C-specific when enough C evidence exists;
            # non-C modern papers may teach presentation, but must not dominate the
            # task/result density of a C-problem abstract merely by sample count.
            modern = max(
                candidates,
                key=lambda s: (
                    ":C:modern" in s.slice_id,
                    s.slice_id.endswith(":C"),
                    "modern" in s.slice_id,
                    s.parsed_count,
                ),
            )
            units = modern.style_metrics.get("weighted_median_abstract_units", 0.0)
            numbers = modern.style_metrics.get("weighted_median_abstract_numeric_tokens", 0.0)
            guidance.append(
                f"Abstract calibration reference from {modern.slice_id}: information units≈{units:.1f}, numeric tokens≈{numbers:.1f}; use only supported results."
            )
    if "figures" in skills:
        candidates = [s for s in slices if s.figure_purpose_prevalence]
        if candidates:
            modern = max(candidates, key=lambda s: ("modern" in s.slice_id, s.parsed_count))
            top = list(modern.figure_purpose_prevalence.items())[:4]
            if top:
                guidance.append(
                    "High-value recent figure roles include "
                    + ", ".join(f"{name}({value:.0%})" for name, value in top)
                    + "; select only roles supported by current evidence."
                )
    if "validation" in skills:
        task_slices = [s for s in slices if s.slice_id.startswith("task:") and s.validation_prevalence]
        for task_slice in task_slices[:2]:
            top = list(task_slice.validation_prevalence.items())[:3]
            if top:
                guidance.append(
                    f"For {task_slice.scope.get('task_family')}, common validation families are "
                    + ", ".join(name for name, _value in top)
                    + "; choose by task semantics, not frequency."
                )
    if "narrative" in skills:
        candidates = [s for s in slices if s.model_transition_prevalence]
        if candidates:
            c_specific = max(
                candidates,
                key=lambda s: (
                    ":C:modern" in s.slice_id,
                    s.slice_id.endswith(":C"),
                    s.parsed_count,
                ),
            )
            top = list(c_specific.model_transition_prevalence.items())[:3]
            if top:
                guidance.append(
                    "Narrative progression patterns in the selected C corpus include "
                    + ", ".join(f"{name}({value:.0%})" for name, value in top)
                    + "; use them only when the actual subproblem dependency graph supports the transition."
                )
    if "layout" in skills:
        candidates = [s for s in slices if s.layout_metrics.get("weighted_median_page_count", 0) > 0]
        if candidates:
            modern = max(
                candidates,
                key=lambda s: (
                    ":C:modern" in s.slice_id,
                    "modern" in s.slice_id,
                    s.parsed_count,
                ),
            )
            pages = modern.layout_metrics.get("weighted_median_page_count", 0.0)
            scan_ratio = modern.layout_metrics.get("weighted_median_scan_page_ratio", 0.0)
            if scan_ratio < 0.5:
                guidance.append(
                    f"Layout reference from {modern.slice_id}: median page count≈{pages:.1f}; treat this as compression context, never a target that justifies padding."
                )
    return guidance

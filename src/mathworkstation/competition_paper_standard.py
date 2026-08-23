from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .io_utils import read_json


ProfileId = Literal["MCM_C", "CUMCM_C"]


class ResearchRefreshPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_before_each_v3_stage: bool
    sources: list[str] = Field(min_length=3)
    sequence: list[str] = Field(min_length=5)


class FormulaBudget(BaseModel):
    model_config = ConfigDict(extra="forbid")

    A_core: list[str] = Field(default_factory=list)
    B_optional_standard: list[str] = Field(default_factory=list)
    C_appendix_preferred: list[str] = Field(default_factory=list)


class CompetitionPaperStandardProfile(BaseModel):
    """Machine-readable competition standard for one C-problem paper profile.

    The object deliberately keeps official constraints separate from soft excellent-
    paper priors.  The two have different semantics: violating an official constraint
    can make a submission invalid, while a soft prior should only influence planning,
    review, or presentation when the current problem evidence supports it.
    """

    model_config = ConfigDict(extra="forbid")

    profile_id: ProfileId
    competition: str
    language: Literal["zh", "en"]
    official_hard_constraints: dict[str, Any]
    ai_use_hard_constraints: dict[str, Any] = Field(default_factory=dict)
    soft_structural_priors: dict[str, Any] = Field(default_factory=dict)
    formula_budget: FormulaBudget
    visual_priors: dict[str, Any] = Field(default_factory=dict)

    @property
    def official_font_is_fixed(self) -> bool | None:
        value = self.official_hard_constraints.get("officially_fixed_font")
        return value if isinstance(value, bool) else None

    @property
    def body_page_limit(self) -> int | None:
        value = self.official_hard_constraints.get("body_max_pages")
        if isinstance(value, int):
            return value
        value = self.official_hard_constraints.get("total_page_limit")
        return value if isinstance(value, int) else None

    def hard_constraint(self, key: str, default: Any = None) -> Any:
        return self.official_hard_constraints.get(key, default)

    def soft_prior(self, key: str, default: Any = None) -> Any:
        return self.soft_structural_priors.get(key, default)


class CompetitionPaperStandardRegistry:
    """Load and validate the Stage-V3 competition-paper standard.

    This registry is intentionally small.  It is a stable machine-facing boundary
    between research-derived configuration and downstream renderer/auditor code.
    """

    def __init__(self, *, config_path: Path | None = None) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.config_path = config_path or (
            repo_root / "config" / "ref_models" / "competition_paper_standard_v2.json"
        )
        payload = read_json(self.config_path)
        if str(payload.get("scope")) != "C_PROBLEM_PRIMARY":
            raise ValueError("COMPETITION_PAPER_STANDARD_SCOPE_MUST_BE_C_PROBLEM_PRIMARY")

        self.schema_version = int(payload.get("schema_version", 0))
        if self.schema_version < 2:
            raise ValueError("COMPETITION_PAPER_STANDARD_REQUIRES_SCHEMA_V2")

        self.research_refresh_policy = ResearchRefreshPolicy.model_validate(
            payload.get("research_refresh_policy") or {}
        )
        if not self.research_refresh_policy.required_before_each_v3_stage:
            raise ValueError("V3_RESEARCH_REFRESH_MUST_BE_REQUIRED")

        raw_profiles = payload.get("profiles") or {}
        self._profiles: dict[str, CompetitionPaperStandardProfile] = {}
        for profile_id, value in raw_profiles.items():
            data = dict(value)
            data["profile_id"] = profile_id
            profile = CompetitionPaperStandardProfile.model_validate(data)
            self._profiles[profile_id] = profile

        required_profiles = {"MCM_C", "CUMCM_C"}
        if set(self._profiles) != required_profiles:
            raise ValueError("COMPETITION_PAPER_STANDARD_REQUIRES_MCM_C_AND_CUMCM_C")

        self.cross_competition_modeling_rules = dict(
            payload.get("cross_competition_modeling_rules") or {}
        )
        self.engineering_borrow_map = dict(payload.get("engineering_borrow_map") or {})
        self.evidence_hierarchy = list(payload.get("evidence_hierarchy") or [])
        self._validate_semantics()

    def resolve(self, competition: str) -> CompetitionPaperStandardProfile:
        normalized = competition.strip().lower().replace("-", "_").replace("/", "_")
        if "cumcm" in normalized or "高教" in competition or "国赛" in competition:
            return self._profiles["CUMCM_C"]
        if "mcm" in normalized:
            return self._profiles["MCM_C"]
        raise ValueError(f"UNSUPPORTED_COMPETITION_PAPER_STANDARD:{competition}")

    def _validate_semantics(self) -> None:
        hierarchy = self.evidence_hierarchy
        if not hierarchy or hierarchy[0] != "official_hard_constraints":
            raise ValueError("OFFICIAL_HARD_CONSTRAINTS_MUST_HAVE_HIGHEST_PRIORITY")
        if "task_specific_evidence" not in hierarchy:
            raise ValueError("TASK_SPECIFIC_EVIDENCE_MISSING_FROM_HIERARCHY")
        if hierarchy.index("task_specific_evidence") > hierarchy.index("excellent_paper_soft_priors"):
            raise ValueError("TASK_EVIDENCE_MUST_OUTRANK_EXCELLENT_PAPER_SOFT_PRIORS")

        forbidden = set(self.cross_competition_modeling_rules.get("forbidden_default_behavior") or [])
        required_forbidden = {
            "one_unrelated_model_per_question",
            "algorithm_zoo_for_prestige",
            "equation_count_as_modeling_depth",
            "figure_count_as_visual_quality",
        }
        missing = required_forbidden - forbidden
        if missing:
            raise ValueError(
                "COMPETITION_PAPER_STANDARD_MISSING_ANTI_PATTERNS:" + ",".join(sorted(missing))
            )

        cumcm = self._profiles["CUMCM_C"]
        if cumcm.hard_constraint("table_of_contents") != "FORBIDDEN":
            raise ValueError("CUMCM_TABLE_OF_CONTENTS_MUST_BE_FORBIDDEN")
        if cumcm.official_font_is_fixed is not False:
            raise ValueError("CUMCM_OFFICIAL_FONT_MUST_NOT_BE_HARDCODED")

        mcm = self._profiles["MCM_C"]
        if mcm.hard_constraint("summary_sheet_first_page") is not True:
            raise ValueError("MCM_SUMMARY_SHEET_MUST_BE_FIRST_PAGE")
        if mcm.hard_constraint("minimum_font_pt") != 12:
            raise ValueError("MCM_MINIMUM_FONT_PT_MUST_BE_12")

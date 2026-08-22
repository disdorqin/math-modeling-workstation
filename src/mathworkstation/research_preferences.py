from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .io_utils import atomic_write_json


ModelingStyle = Literal[
    "probabilistic_graphical",
    "dynamic_system",
    "mechanistic",
    "optimization",
    "statistical_inference",
    "simulation",
    "data_driven",
    "hybrid",
]
Priority = Literal[
    "mathematical_structure",
    "logical_rigor",
    "mechanism_depth",
    "interpretability",
    "robustness",
    "visual_storytelling",
    "predictive_accuracy",
]
HumanLoopMode = Literal["OFF", "OPTIONAL", "REQUIRED"]


class ResearchPreferenceProfile(BaseModel):
    """Human preferences that guide research style without overriding evidence gates."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    preferred_modeling_styles: list[ModelingStyle] = Field(default_factory=list)
    priorities: list[Priority] = Field(
        default_factory=lambda: ["mathematical_structure", "logical_rigor", "robustness"]
    )
    claim_strength: Literal["conservative", "balanced", "award_ambitious"] = "balanced"
    paper_style: Literal["restrained", "award_rich", "balanced"] = "balanced"
    visual_density: Literal["adaptive", "compact", "rich"] = "adaptive"
    unified_framework_preferred: bool = True
    predictive_accuracy_is_primary: bool = False
    human_loop_mode: HumanLoopMode = "OFF"
    human_checkpoints: list[Literal["problem_interpretation", "model_direction", "story_visual_plan", "final_pdf"]] = Field(
        default_factory=lambda: ["problem_interpretation", "model_direction", "story_visual_plan", "final_pdf"]
    )
    notes: list[str] = Field(default_factory=list)


class ResearchPreferenceInterview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    questions: list[str]
    default_profile: ResearchPreferenceProfile


def default_interview() -> ResearchPreferenceInterview:
    """Questions suitable for a human pre-run conversation.

    The workstation may ask these before a formal contest run.  During system
    development `human_loop_mode=OFF`, so lack of answers never blocks testing.
    """

    return ResearchPreferenceInterview(
        questions=[
            "Which matters most for this problem: mathematical structure, mechanism depth, interpretability, robustness, or predictive accuracy?",
            "Do you prefer a mechanistic/dynamic, probabilistic graphical, optimization, statistical, simulation, data-driven, or hybrid modeling style?",
            "Should claims remain conservative, balanced, or be moderately ambitious when evidence permits?",
            "Should the questions share one unified framework unless a new mechanism/constraint genuinely requires a separate model?",
            "Do you prefer an adaptive visual plan, a compact paper, or a richer award-paper visual narrative?",
            "During a formal contest run, which checkpoints should require human direction: interpretation, model direction, story/visual plan, final PDF?",
        ],
        default_profile=ResearchPreferenceProfile(),
    )


class ResearchPreferenceService:
    """Persist/read per-case preferences; absence means non-blocking defaults."""

    def __init__(self, cases: Any, artifacts: Any | None = None) -> None:
        self.cases = cases
        self.artifacts = artifacts

    def path(self, case_id: str) -> Path:
        return self.cases.case_root(case_id) / ".internal" / "research_preferences.json"

    def save(self, case_id: str, profile: ResearchPreferenceProfile) -> dict[str, Any]:
        path = self.path(case_id)
        atomic_write_json(path, profile.model_dump(mode="json"))
        result: dict[str, Any] = {"profile": profile, "path": path}
        if self.artifacts is not None:
            artifact = self.artifacts.register_existing(
                case_id,
                path.relative_to(self.cases.case_root(case_id)).as_posix(),
                "research_preference_profile",
                "research_preference_service",
                paper_eligible=False,
            )
            result["artifact"] = artifact
        return result

    def load(self, case_id: str) -> ResearchPreferenceProfile:
        path = self.path(case_id)
        if not path.is_file():
            return ResearchPreferenceProfile()
        import json

        return ResearchPreferenceProfile.model_validate(json.loads(path.read_text(encoding="utf-8")))

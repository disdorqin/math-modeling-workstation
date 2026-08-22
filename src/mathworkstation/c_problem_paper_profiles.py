from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .competition_paper_standard import CompetitionPaperStandardProfile, CompetitionPaperStandardRegistry
from .io_utils import read_json


ProfileId = Literal["MCM_C", "CUMCM_C"]


class CProblemPaperProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: ProfileId
    competition: str
    language: Literal["en", "zh"]
    summary_headings: list[str] = Field(min_length=1)
    render_summary_heading: str
    required_sections: list[str] = Field(min_length=1)
    forbidden_foreign_headings: list[str] = Field(default_factory=list)
    deliverable_policy: str
    summary_policy: str
    reference_policy: str


class CProblemPaperProfileRegistry:
    model_config = ConfigDict(extra="forbid")

    def __init__(self, *, config_path: Path | None = None) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.config_path = config_path or (repo_root / "config" / "ref_models" / "c_problem_paper_profiles_v1.json")
        payload = read_json(self.config_path)
        if str(payload.get("scope")) != "C_PROBLEM_ONLY":
            raise ValueError("PAPER_PROFILE_SCOPE_MUST_BE_C_PROBLEM_ONLY")
        raw_profiles = payload.get("profiles") or {}
        self._profiles: dict[str, CProblemPaperProfile] = {}
        for profile_id, value in raw_profiles.items():
            data = dict(value)
            data["profile_id"] = profile_id
            profile = CProblemPaperProfile.model_validate(data)
            self._profiles[profile_id] = profile
        if set(self._profiles) != {"MCM_C", "CUMCM_C"}:
            raise ValueError("C_PROBLEM_PAPER_PROFILES_REQUIRE_MCM_C_AND_CUMCM_C")
        self.standards = CompetitionPaperStandardRegistry()

    def resolve(self, competition: str) -> CProblemPaperProfile:
        normalized = competition.strip().lower().replace("-", "_").replace("/", "_")
        if "cumcm" in normalized or "高教" in competition or "国赛" in competition:
            return self._profiles["CUMCM_C"]
        if "mcm" in normalized:
            return self._profiles["MCM_C"]
        raise ValueError(f"UNSUPPORTED_C_PROBLEM_PAPER_PROFILE:{competition}")

    def resolve_standard(self, competition: str) -> CompetitionPaperStandardProfile:
        """Return the current official/soft-prior standard paired with this profile."""

        return self.standards.resolve(competition)


def profile_structure_findings(text: str, profile: CProblemPaperProfile) -> list[dict[str, str]]:
    """Return document-only profile findings; never infer research defects."""

    findings: list[dict[str, str]] = []
    lowered = text.lower()
    if not any(_heading_present(text, heading) for heading in profile.summary_headings):
        findings.append(
            {
                "code": "COMPETITION_PROFILE_SUMMARY_HEADING_MISSING",
                "message": f"{profile.profile_id} paper lacks an allowed summary heading {profile.summary_headings}",
                "section": "abstract",
            }
        )
    for section in profile.required_sections:
        if not _heading_present(text, section):
            findings.append(
                {
                    "code": "COMPETITION_PROFILE_REQUIRED_SECTION_MISSING",
                    "message": f"{profile.profile_id} paper lacks required section: {section}",
                    "section": "structure",
                }
            )
    for heading in profile.forbidden_foreign_headings:
        if heading.lower() in lowered:
            findings.append(
                {
                    "code": "COMPETITION_PROFILE_CROSS_CONTAMINATION",
                    "message": f"{profile.profile_id} paper contains foreign-profile heading: {heading}",
                    "section": "structure",
                }
            )
    return findings


def _heading_present(text: str, heading: str) -> bool:
    target = heading.strip().lower()
    for line in text.splitlines():
        value = line.strip().lstrip("#").strip().lower()
        value = _drop_numeric_prefix(value)
        if value == target:
            return True
    return False


def _drop_numeric_prefix(value: str) -> str:
    parts = value.split(".", 1)
    if len(parts) == 2 and parts[0].strip().isdigit():
        return parts[1].strip()
    if value and value[0].isdigit():
        rest = value[1:].lstrip(".、 ")
        return rest
    return value

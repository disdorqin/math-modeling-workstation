from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from .io_utils import atomic_write_json, now_iso


CoverageGate = Literal["PASS", "REVIEW", "BLOCK"]


class DataCoverageFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: Literal["BLOCK", "REVIEW"]
    code: str
    message: str
    required_entities: list[str] = Field(default_factory=list)
    observed_entities: list[str] = Field(default_factory=list)
    repair_phase: str = "data_registration"


class ResearchDataCoverageAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str | None = None
    gate: CoverageGate
    required_entities: list[str] = Field(default_factory=list)
    observed_entities: list[str] = Field(default_factory=list)
    findings: list[DataCoverageFinding] = Field(default_factory=list)
    checked_at: str


class ResearchDataCoverageAuditor:
    """Fail closed when a multi-entity problem is backed by partial entity data.

    This is intentionally conservative and deterministic. It extracts explicit
    two/three-letter entity abbreviations from problem prose (e.g. CA/AZ/NM/TX)
    and compares them with a registered entity column or dataset filename hints.
    It does not guess that one entity's panel can answer a four-entity task.
    """

    ENTITY_COLUMNS = ("state", "state_code", "region", "region_code", "entity", "entity_code")

    def audit(
        self,
        problem_text: str,
        frames: list[pd.DataFrame],
        *,
        source_names: list[str] | None = None,
        case_id: str | None = None,
    ) -> ResearchDataCoverageAssessment:
        required = _required_entity_codes(problem_text)
        observed = _observed_entity_codes(frames, source_names or [], required)
        findings: list[DataCoverageFinding] = []
        if len(required) >= 2:
            missing = sorted(set(required) - set(observed))
            if missing:
                findings.append(
                    DataCoverageFinding(
                        severity="BLOCK",
                        code="MULTI_ENTITY_DATA_COVERAGE_MISSING",
                        message=(
                            f"Problem explicitly requires entities {required}, but registered input coverage only identifies "
                            f"{observed or ['none']}; missing {missing}."
                        ),
                        required_entities=required,
                        observed_entities=observed,
                    )
                )
        gate: CoverageGate = "BLOCK" if any(item.severity == "BLOCK" for item in findings) else "REVIEW" if findings else "PASS"
        return ResearchDataCoverageAssessment(
            case_id=case_id,
            gate=gate,
            required_entities=required,
            observed_entities=observed,
            findings=findings,
            checked_at=now_iso(),
        )

    def persist(
        self,
        cases: Any,
        artifacts: Any,
        case_id: str,
        assessment: ResearchDataCoverageAssessment,
        *,
        source_artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        root = cases.case_root(case_id)
        path = root / "review" / "research" / "data_coverage.json"
        atomic_write_json(path, assessment.model_dump(mode="json"))
        artifact = artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "research_data_coverage_assessment",
            "research_data_coverage_auditor",
            upstream=list(source_artifact_ids or []),
            paper_eligible=False,
        )
        return {"assessment": assessment, "artifact": artifact}


def _required_entity_codes(problem_text: str) -> list[str]:
    # Match explicit labels such as California (CA), Arizona (AZ), New Mexico
    # (NM), Texas (TX). Restrict to 2–3 letters so organization acronyms such as
    # WIEC do not become required data entities.
    values = re.findall(r"\(([A-Z]{2,3})\)", problem_text)
    return list(dict.fromkeys(values))


def _observed_entity_codes(
    frames: list[pd.DataFrame],
    source_names: list[str],
    required: list[str],
) -> list[str]:
    observed: list[str] = []
    required_set = set(required)
    for frame in frames:
        for column in ResearchDataCoverageAuditor.ENTITY_COLUMNS:
            if column not in frame.columns:
                continue
            for value in frame[column].dropna().astype(str).str.upper().unique().tolist():
                if value in required_set:
                    observed.append(value)
    for name in source_names:
        stem = Path(name).stem.upper()
        tokens = set(re.split(r"[^A-Z0-9]+", stem))
        for code in required:
            if code in tokens or stem.endswith("_" + code) or stem.endswith("-" + code):
                observed.append(code)
    return list(dict.fromkeys(observed))

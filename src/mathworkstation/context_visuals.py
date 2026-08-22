from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from .io_utils import atomic_write_json, now_iso


ContextVisualGate = Literal["PASS", "REJECT"]


class ContextVisualCandidate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    title: str
    page_url: HttpUrl
    asset_url: HttpUrl
    provider: str
    author: str
    license_id: str
    license_url: HttpUrl | None = None
    source_date: str = ""
    description: str = ""
    content_class: Literal["REALITY_CONTEXT"] = "REALITY_CONTEXT"
    ai_generated: bool = False


class ContextVisualAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    gate: ContextVisualGate
    reasons: list[str] = Field(default_factory=list)
    attribution_text: str = ""
    checked_at: str


class ContextVisualRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    candidate: ContextVisualCandidate
    assessment: ContextVisualAssessment
    relative_path: str
    attribution_artifact_id: str
    figure_id: str
    retrieved_at: str


class ContextVisualPolicy:
    """Safety/provenance gate for real-world background images.

    A reality/background visual must be a real externally sourced image with an
    explicit reuse license. AI-generated imagery is rejected from this lane by
    construction.  The allowlist is intentionally conservative and can be
    extended by configuration later without changing paper logic.
    """

    TRUSTED_HOST_SUFFIXES = (
        "commons.wikimedia.org",
        "upload.wikimedia.org",
        "nasa.gov",
        "noaa.gov",
        "usda.gov",
        "gov.cn",
        "edu.cn",
    )
    ALLOWED_LICENSE_PREFIXES = (
        "CC0",
        "CC BY",
        "CC-BY",
        "PUBLIC DOMAIN",
        "PDM",
    )

    def assess(self, candidate: ContextVisualCandidate) -> ContextVisualAssessment:
        reasons: list[str] = []
        if candidate.ai_generated:
            reasons.append("REALITY_CONTEXT_CANNOT_BE_AI_GENERATED")
        page_host = (urllib.parse.urlparse(str(candidate.page_url)).hostname or "").lower()
        asset_host = (urllib.parse.urlparse(str(candidate.asset_url)).hostname or "").lower()
        if not any(page_host == suffix or page_host.endswith("." + suffix) for suffix in self.TRUSTED_HOST_SUFFIXES):
            reasons.append("SOURCE_PAGE_HOST_NOT_TRUSTED")
        if not any(asset_host == suffix or asset_host.endswith("." + suffix) for suffix in self.TRUSTED_HOST_SUFFIXES):
            reasons.append("ASSET_HOST_NOT_TRUSTED")
        license_id = candidate.license_id.upper().strip()
        if not any(license_id.startswith(prefix) for prefix in self.ALLOWED_LICENSE_PREFIXES):
            reasons.append("REUSE_LICENSE_NOT_ALLOWED")
        if not candidate.author.strip():
            reasons.append("AUTHOR_MISSING")
        if not candidate.provider.strip():
            reasons.append("PROVIDER_MISSING")
        gate: ContextVisualGate = "PASS" if not reasons else "REJECT"
        attribution = ""
        if gate == "PASS":
            attribution = f"{candidate.title} — {candidate.author}; {candidate.provider}; {candidate.license_id}; source: {candidate.page_url}"
        return ContextVisualAssessment(
            candidate_id=candidate.candidate_id,
            gate=gate,
            reasons=reasons,
            attribution_text=attribution,
            checked_at=now_iso(),
        )


class ContextVisualService:
    """Materialize an already-retrieved trusted candidate into a case.

    Search itself remains a pluggable external capability. This service handles
    the invariant local side: license/source validation, download, attribution,
    artifact registration and a context-only FigureRegistry record.
    """

    def __init__(self, cases: Any, artifacts: Any, figures: Any, policy: ContextVisualPolicy | None = None) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.figures = figures
        self.policy = policy or ContextVisualPolicy()

    def materialize(
        self,
        case_id: str,
        candidate: ContextVisualCandidate,
        *,
        timeout: float = 30.0,
    ) -> ContextVisualRecord:
        assessment = self.policy.assess(candidate)
        if assessment.gate != "PASS":
            raise ValueError("CONTEXT_VISUAL_REJECTED:" + ",".join(assessment.reasons))

        root = self.cases.case_root(case_id)
        suffix = _asset_suffix(str(candidate.asset_url))
        filename = _slug(candidate.candidate_id or candidate.title) + suffix
        relative = Path("figures") / "context" / filename
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        request = urllib.request.Request(
            str(candidate.asset_url),
            headers={"User-Agent": "math-modeling-workstation/1.0 (+context-visual-attribution)"},
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            content_type = str(response.headers.get("Content-Type") or "").lower()
            if not content_type.startswith("image/"):
                raise ValueError(f"CONTEXT_VISUAL_NOT_IMAGE:{content_type}")
            payload = response.read()
        if len(payload) < 4096:
            raise ValueError("CONTEXT_VISUAL_ASSET_TOO_SMALL")
        destination.write_bytes(payload)

        attribution_relative = Path("evidence") / "context_visuals" / f"{_slug(candidate.candidate_id)}.json"
        attribution_path = root / attribution_relative
        atomic_write_json(
            attribution_path,
            {
                "schema_version": 1,
                "case_id": case_id,
                "candidate": candidate.model_dump(mode="json"),
                "assessment": assessment.model_dump(mode="json"),
                "retrieved_at": now_iso(),
                "local_path": relative.as_posix(),
                "bytes": len(payload),
            },
        )
        attribution_artifact = self.artifacts.register_existing(
            case_id,
            attribution_relative.as_posix(),
            "context_visual_attribution",
            "context_visual_retrieval",
            paper_eligible=False,
        )
        figure = self.figures.register(
            case_id,
            relative.as_posix(),
            candidate.title,
            [attribution_artifact["artifact_id"]],
            "context_visual_retrieval",
            {
                "semantic_kind": "context_reality",
                "paper_role": "context",
                "purpose": candidate.description or "Provide a real-world visual anchor for the problem background; it is not quantitative evidence.",
                "context_only": True,
                "ai_generated": False,
                "source_page_url": str(candidate.page_url),
                "asset_url": str(candidate.asset_url),
                "source_author": candidate.author,
                "source_provider": candidate.provider,
                "source_license": candidate.license_id,
                "source_license_url": str(candidate.license_url or ""),
                "source_attribution": assessment.attribution_text,
                "license_verified": True,
                "caption_first": True,
            },
            run_id=None,
            status="FINAL",
        )
        return ContextVisualRecord(
            candidate=candidate,
            assessment=assessment,
            relative_path=relative.as_posix(),
            attribution_artifact_id=attribution_artifact["artifact_id"],
            figure_id=figure["figure_id"],
            retrieved_at=now_iso(),
        )


def _asset_suffix(url: str) -> str:
    path = urllib.parse.urlparse(url).path.lower()
    for suffix in (".jpg", ".jpeg", ".png", ".webp"):
        if suffix in path:
            return ".jpg" if suffix == ".jpeg" else suffix
    return ".jpg"


def _slug(value: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9._-]+", "-", value.strip().lower()).strip("-._")
    return text[:80] or "context-visual"

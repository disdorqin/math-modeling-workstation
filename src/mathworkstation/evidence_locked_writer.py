from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .competition_paper_auditor import CompetitionPaperAuditor, CompetitionPaperAssessment
from .io_utils import atomic_write_json, atomic_write_text, now_iso
from .narrative_graph import NarrativeGraph


WriterGate = Literal["PASS", "BLOCK"]

_NUMERIC = re.compile(r"(?<![A-Za-z0-9_])[-+]?\d+(?:\.\d+)?%?")
_DISPLAY_MATH = re.compile(r"\$\$(.*?)\$\$", re.DOTALL)
_INTERNAL_ID = re.compile(r"\b(?:artifact|result|table|claim|figure)-[A-Za-z0-9_-]+\b", re.IGNORECASE)
_REFERENCE_LINE = re.compile(r"(?m)^\s*\[(\d+)\]\s+(.+?)\s*$")

# High-risk method names: if a prose-only rewrite introduces one that the
# canonical draft never mentioned, it is almost certainly fabricating a new
# modeling claim rather than improving prose.
_MODEL_TERMS = (
    "arima",
    "random forest",
    "xgboost",
    "lightgbm",
    "neural network",
    "lstm",
    "transformer",
    "support vector machine",
    "svm",
    "markov",
    "kalman",
    "monte carlo",
    "topsis",
    "analytic hierarchy process",
    "ahp",
    "genetic algorithm",
    "particle swarm",
)


class WriterFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    code: str
    detail: str


class EvidenceLockedWriterAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    gate: WriterGate
    findings: list[WriterFinding] = Field(default_factory=list)
    competition_gate: str
    checked_at: str


class EvidenceLockedWriterService:
    """Allow prose improvement while freezing research facts.

    The canonical Research-State paper is the fact ledger. A candidate writer
    may reorganize sentences and transitions, but may not introduce new numeric
    tokens, equations, references, high-risk model families, internal ids, or
    omit a required question. CompetitionPaperAuditor is run again after these
    invariants.
    """

    def __init__(self, auditor: CompetitionPaperAuditor | None = None) -> None:
        self.auditor = auditor or CompetitionPaperAuditor()

    def persist_packet(
        self,
        cases: Any,
        artifacts: Any,
        case_id: str,
        canonical_artifact_id: str,
        canonical_text: str,
        narrative_summary: str,
        *,
        narrative_artifact_id: str | None = None,
    ) -> dict[str, Any]:
        root = cases.case_root(case_id)
        path = root / "analysis" / "research_state" / "writer_packet.json"
        payload = {
            "schema_version": 1,
            "case_id": case_id,
            "rules": {
                "new_numeric_facts": "FORBIDDEN",
                "new_equations": "FORBIDDEN",
                "new_model_families": "FORBIDDEN",
                "bibliography_changes": "FORBIDDEN",
                "internal_registry_ids": "FORBIDDEN",
                "drop_subproblem": "FORBIDDEN",
                "allowed_changes": ["wording", "transitions", "paragraph organization", "conciseness"],
            },
            "canonical_paper": canonical_text,
            "narrative_summary": narrative_summary,
            "generated_at": now_iso(),
        }
        atomic_write_json(path, payload)
        upstream = [canonical_artifact_id]
        if narrative_artifact_id:
            upstream.append(narrative_artifact_id)
        artifact = artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "evidence_locked_writer_packet",
            "evidence_locked_writer",
            upstream=upstream,
            paper_eligible=False,
        )
        return {"packet": payload, "artifact": artifact}

    def validate(
        self,
        canonical_text: str,
        candidate_text: str,
        narrative: NarrativeGraph,
        *,
        case_id: str | None = None,
    ) -> tuple[EvidenceLockedWriterAssessment, CompetitionPaperAssessment]:
        findings: list[WriterFinding] = []
        if _INTERNAL_ID.search(candidate_text):
            findings.append(
                WriterFinding(
                    code="WRITER_INTERNAL_ID_LEAK",
                    detail="candidate prose contains an internal registry id",
                )
            )

        canonical_numbers = set(_NUMERIC.findall(canonical_text))
        candidate_numbers = set(_NUMERIC.findall(candidate_text))
        added_numbers = sorted(candidate_numbers - canonical_numbers)
        if added_numbers:
            findings.append(
                WriterFinding(
                    code="WRITER_ADDED_NUMERIC_FACT",
                    detail="candidate introduced numeric tokens not present in canonical Research State: "
                    + ", ".join(added_numbers[:20]),
                )
            )

        canonical_math = {_normalize_math(value) for value in _DISPLAY_MATH.findall(canonical_text)}
        candidate_math = {_normalize_math(value) for value in _DISPLAY_MATH.findall(candidate_text)}
        added_math = sorted(candidate_math - canonical_math)
        if added_math:
            findings.append(
                WriterFinding(
                    code="WRITER_ADDED_EQUATION",
                    detail=f"candidate introduced {len(added_math)} display equation(s) absent from canonical Research State",
                )
            )

        canonical_refs = _reference_entries(canonical_text)
        candidate_refs = _reference_entries(candidate_text)
        if candidate_refs != canonical_refs:
            findings.append(
                WriterFinding(
                    code="WRITER_CHANGED_BIBLIOGRAPHY",
                    detail="candidate references differ from the verified canonical bibliography",
                )
            )

        canonical_lower = canonical_text.lower()
        candidate_lower = candidate_text.lower()
        added_models = [
            term for term in _MODEL_TERMS
            if term in candidate_lower and term not in canonical_lower
        ]
        if added_models:
            findings.append(
                WriterFinding(
                    code="WRITER_ADDED_MODEL_FAMILY",
                    detail="candidate introduced model families absent from canonical execution: "
                    + ", ".join(added_models),
                )
            )

        for index, _node in enumerate(narrative.nodes, start=1):
            if f"question {index}" not in candidate_lower:
                findings.append(
                    WriterFinding(
                        code="WRITER_DROPPED_SUBPROBLEM",
                        detail=f"candidate no longer visibly covers Question {index}",
                    )
                )

        competition = self.auditor.audit(candidate_text, narrative, case_id=case_id)
        if competition.block_count:
            findings.append(
                WriterFinding(
                    code="WRITER_COMPETITION_BLOCK",
                    detail=f"CompetitionPaperAuditor returned {competition.block_count} BLOCK finding(s)",
                )
            )
        gate: WriterGate = "BLOCK" if findings else "PASS"
        return (
            EvidenceLockedWriterAssessment(
                gate=gate,
                findings=findings,
                competition_gate=competition.gate,
                checked_at=now_iso(),
            ),
            competition,
        )

    def accept_and_persist(
        self,
        cases: Any,
        artifacts: Any,
        case_id: str,
        canonical_artifact_id: str,
        candidate_text: str,
        narrative: NarrativeGraph,
        *,
        writer_artifact_id: str | None = None,
    ) -> dict[str, Any]:
        canonical_artifact = artifacts.get(case_id, canonical_artifact_id)
        canonical_text = (
            cases.case_root(case_id) / canonical_artifact["path"]
        ).read_text(encoding="utf-8")
        assessment, competition = self.validate(
            canonical_text,
            candidate_text,
            narrative,
            case_id=case_id,
        )
        root = cases.case_root(case_id)
        assessment_path = root / "review" / "competition" / "writer_assessment.json"
        atomic_write_json(
            assessment_path,
            {
                "writer": assessment.model_dump(mode="json"),
                "competition": competition.model_dump(mode="json"),
            },
        )
        upstream = [canonical_artifact_id]
        if writer_artifact_id:
            upstream.append(writer_artifact_id)
        review_artifact = artifacts.register_existing(
            case_id,
            assessment_path.relative_to(root).as_posix(),
            "evidence_locked_writer_assessment",
            "evidence_locked_writer",
            upstream=upstream,
            paper_eligible=False,
        )
        if assessment.gate != "PASS":
            return {
                "accepted": False,
                "assessment": assessment,
                "competition_assessment": competition,
                "review_artifact": review_artifact,
                "paper_artifact": None,
            }
        paper_path = root / "paper" / "research_state" / "polished.md"
        atomic_write_text(paper_path, candidate_text.rstrip() + "\n")
        paper_artifact = artifacts.register_existing(
            case_id,
            paper_path.relative_to(root).as_posix(),
            "research_state_paper_polished",
            "evidence_locked_writer",
            upstream=[*upstream, review_artifact["artifact_id"]],
            paper_eligible=False,
        )
        return {
            "accepted": True,
            "assessment": assessment,
            "competition_assessment": competition,
            "review_artifact": review_artifact,
            "paper_artifact": paper_artifact,
        }


def _normalize_math(value: str) -> str:
    return re.sub(r"\s+", "", value)


def _reference_entries(text: str) -> list[str]:
    return [f"[{number}] {entry.strip()}" for number, entry in _REFERENCE_LINE.findall(text)]

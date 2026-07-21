from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .claims import ClaimRegistry
from .figure_registry import FigureRegistry
from .io_utils import atomic_write_json, atomic_write_text, now_iso, read_json
from .paper_outline import PaperOutline


class PaperSectionWorkspace:
    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        claims: ClaimRegistry,
        figures: FigureRegistry,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.claims = claims
        self.figures = figures

    def initialize(self, case_id: str, outline_artifact_id: str) -> dict[str, Any]:
        outline_artifact = self.artifacts.get(case_id, outline_artifact_id)
        if outline_artifact["artifact_type"] != "paper_outline":
            raise ValueError("section workspace requires a paper_outline artifact")
        root = self.cases.case_root(case_id)
        payload = read_json(root / outline_artifact["path"])
        outline = PaperOutline.model_validate(payload["outline"])
        known_claims = {item["claim_id"]: item for item in self.claims.list_claims(case_id)}
        known_figures = {item["figure_id"]: item for item in self.figures.list_figures(case_id)}
        sections: list[dict[str, Any]] = []
        for index, section in enumerate(outline.sections, start=1):
            section_directory = root / "paper" / "sections" / section.section_id
            section_directory.mkdir(parents=True, exist_ok=True)
            context = {
                "schema_version": 1,
                "case_id": case_id,
                "section_id": section.section_id,
                "title": section.title,
                "purpose": section.purpose,
                "allowed_claims": [known_claims[claim_id] for claim_id in section.claim_ids],
                "allowed_figures": [known_figures[figure_id] for figure_id in section.figure_ids],
                "evidence_pack": _build_evidence_pack(
                    root,
                    self.artifacts,
                    [artifact_id for claim in [known_claims[claim_id] for claim_id in section.claim_ids] for artifact_id in claim["evidence_artifact_ids"]],
                    [figure["artifact_id"] for figure in [known_figures[figure_id] for figure_id in section.figure_ids]],
                ),
                "control_rules": [
                    "Do not introduce numerical results outside allowed_claims.",
                    "Cite claim_id for every material factual or numerical statement.",
                    "Cite figure_id when discussing a figure.",
                    "Mark missing evidence as [NEEDS_EVIDENCE].",
                    "Do not change other paper sections.",
                ],
                "generated_at": now_iso(),
            }
            context["evidence_digest"] = _build_evidence_digest(
                context["allowed_claims"], context["evidence_pack"]
            )
            context_path = section_directory / "context.json"
            draft_path = section_directory / "draft.md"
            atomic_write_json(context_path, context)
            if not draft_path.exists():
                atomic_write_text(
                    draft_path,
                    f"# {index}. {section.title}\n\n[SECTION_DRAFT_PENDING]\n",
                )
            context_artifact = self.artifacts.register_existing(
                case_id,
                context_path.relative_to(root).as_posix(),
                "paper_section_context",
                "python",
                upstream=[
                    outline_artifact_id,
                    *[artifact_id for claim in context["allowed_claims"] for artifact_id in claim["evidence_artifact_ids"]],
                    *[figure["artifact_id"] for figure in context["allowed_figures"]],
                ],
            )
            draft_artifact = self.artifacts.register_existing(
                case_id,
                draft_path.relative_to(root).as_posix(),
                "paper_section_draft",
                "python",
                upstream=[context_artifact["artifact_id"]],
            )
            sections.append(
                {
                    "section_id": section.section_id,
                    "context_artifact_id": context_artifact["artifact_id"],
                    "draft_artifact_id": draft_artifact["artifact_id"],
                }
            )
        manifest = {
            "schema_version": 1,
            "case_id": case_id,
            "outline_artifact_id": outline_artifact_id,
            "sections": sections,
            "created_at": now_iso(),
        }
        manifest_path = root / "paper" / "sections" / "manifest.json"
        atomic_write_json(manifest_path, manifest)
        manifest_artifact = self.artifacts.register_existing(
            case_id,
            manifest_path.relative_to(root).as_posix(),
            "paper_sections_manifest",
            "python",
            upstream=[outline_artifact_id, *[item["context_artifact_id"] for item in sections]],
        )
        return {"manifest": manifest, "manifest_artifact_id": manifest_artifact["artifact_id"]}

    def update_draft(
        self,
        case_id: str,
        section_id: str,
        content: str,
        created_by: str,
    ) -> dict[str, Any]:
        if not content.strip():
            raise ValueError("section draft cannot be empty")
        root = self.cases.case_root(case_id)
        context_path = root / "paper" / "sections" / section_id / "context.json"
        if not context_path.is_file():
            raise KeyError(f"section context not found: {section_id}")
        context_artifact = next(
            item
            for item in self.artifacts.list_artifacts(case_id)
            if item["path"] == context_path.relative_to(root).as_posix() and item["status"] == "ACTIVE"
        )
        draft_path = root / "paper" / "sections" / section_id / "draft.md"
        atomic_write_text(draft_path, content.rstrip() + "\n")
        return self.artifacts.register_existing(
            case_id,
            draft_path.relative_to(root).as_posix(),
            "paper_section_draft",
            created_by,
            upstream=[context_artifact["artifact_id"]],
        )


def _build_evidence_pack(root: Path, artifacts: ArtifactRegistry, artifact_ids: list[str], figure_artifact_ids: list[str]) -> list[dict[str, Any]]:
    pack: list[dict[str, Any]] = []
    for artifact_id in dict.fromkeys([*artifact_ids, *figure_artifact_ids]):
        artifact = artifacts.get(root.name, artifact_id)
        path = root / artifact["path"]
        excerpt = ""
        if path.is_file() and path.suffix.lower() in {".json", ".md", ".txt", ".csv"}:
            excerpt = path.read_text(encoding="utf-8-sig", errors="replace")[:12000]
        pack.append(
            {
                "artifact_id": artifact_id,
                "artifact_type": artifact["artifact_type"],
                "path": artifact["path"],
                "paper_eligible": artifact.get("paper_eligible", False),
                "excerpt": excerpt,
            }
        )
    return pack


def _build_evidence_digest(claims: list[dict[str, Any]], evidence_pack: list[dict[str, Any]]) -> dict[str, Any]:
    """Provide a compact, model-friendly evidence index beside raw excerpts."""
    excerpts = {
        item["artifact_id"]: item.get("excerpt", "")
        for item in evidence_pack
    }
    return {
        "claim_rules": [
            {
                "claim_id": claim["claim_id"],
                "claim_type": claim.get("claim_type", ""),
                "text": claim.get("text", ""),
                "evidence_artifact_ids": claim.get("evidence_artifact_ids", []),
            }
            for claim in claims
        ],
        "artifact_excerpts": [
            {
                "artifact_id": artifact_id,
                "excerpt": excerpt[:6000],
            }
            for artifact_id, excerpt in excerpts.items()
            if excerpt
        ],
    }

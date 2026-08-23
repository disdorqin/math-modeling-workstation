from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .io_utils import read_json


VisualIntentKind = Literal[
    "numeric_evidence",
    "statistical_summary",
    "workflow_diagram",
    "mechanism_diagram",
    "model_architecture",
]
VisualBackend = Literal[
    "deterministic_plot",
    "deterministic_vector",
    "editable_vector",
    "ai_image",
    "ppt_mcp",
]


class FigureIntent(BaseModel):
    """Semantic visual request before choosing a renderer.

    This object records *what the figure must communicate* and the evidence
    boundary. It intentionally contains no fixed palette, geometry, or chart
    layout so a cloud model, an agent skill, PowerPoint MCP, or a deterministic
    renderer can all operate on the same brief.
    """

    model_config = ConfigDict(extra="forbid")

    intent_id: str
    kind: VisualIntentKind
    profile_id: str
    purpose: str
    source_summary: str
    evidence_refs: list[str] = Field(default_factory=list)
    required_content: list[str] = Field(default_factory=list)
    forbidden_content: list[str] = Field(default_factory=list)
    editable_preferred: bool = False
    notes: list[str] = Field(default_factory=list)


class VisualRenderPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: FigureIntent
    preferred_backends: list[VisualBackend]
    available_backends: list[VisualBackend]
    primary_backend: VisualBackend
    publication_backend: VisualBackend
    visual_review_required: bool
    numeric_fidelity_required: bool
    rationale: str


class VisualIntentRouter:
    """Capability router for figures; never chooses a fixed aesthetic template."""

    def __init__(self, config_path: str | Path | None = None) -> None:
        repo_root = Path(__file__).resolve().parents[2]
        self.config_path = Path(config_path) if config_path else (
            repo_root / "config" / "ref_models" / "visual_rendering_policy_v2.json"
        )
        self.policy = read_json(self.config_path)
        if int(self.policy.get("schema_version", 0)) != 2:
            raise ValueError("VISUAL_RENDERING_POLICY_V2_REQUIRED")

    def route(self, intent: FigureIntent, *, capabilities: dict[str, bool] | None = None) -> VisualRenderPlan:
        capabilities = dict(capabilities or {})
        route = (self.policy.get("intent_routes") or {}).get(intent.kind)
        if not isinstance(route, dict):
            raise ValueError(f"VISUAL_INTENT_ROUTE_MISSING:{intent.kind}")
        preferred = [str(value) for value in route.get("preferred_backends") or []]
        if not preferred:
            raise ValueError(f"VISUAL_INTENT_ROUTE_EMPTY:{intent.kind}")

        available = [
            backend
            for backend in preferred
            if bool(capabilities.get(backend, backend in {"deterministic_plot", "deterministic_vector", "editable_vector"}))
        ]
        if not available:
            raise ValueError(f"VISUAL_BACKEND_UNAVAILABLE:{intent.kind}")

        primary = available[0]
        numeric_fidelity = bool(route.get("numeric_fidelity_required"))
        review_required = bool(route.get("visual_review_required"))

        # A generative candidate may be the preferred creative route, but it is
        # not silently promoted to the manuscript. Publication uses the first
        # available backend that the policy marks paper-eligible without visual
        # review. This preserves an evidence-safe fallback while still letting
        # GPT Image / PowerPoint agents lead the design exploration.
        publication = primary
        capability_specs = self.policy.get("capabilities") or {}
        for backend in available:
            spec = capability_specs.get(backend) or {}
            if bool(spec.get("paper_eligible_without_visual_review")):
                publication = backend
                break

        if primary != publication:
            rationale = (
                f"{primary} is preferred for design exploration, while {publication} remains the "
                "paper-safe fallback until visual review or editable redraw is accepted."
            )
        else:
            rationale = f"{primary} is the highest-priority available backend allowed by the evidence-fidelity policy."

        return VisualRenderPlan(
            intent=intent,
            preferred_backends=preferred,
            available_backends=available,
            primary_backend=primary,  # type: ignore[arg-type]
            publication_backend=publication,  # type: ignore[arg-type]
            visual_review_required=review_required,
            numeric_fidelity_required=numeric_fidelity,
            rationale=rationale,
        )


def build_visual_brief(intent: FigureIntent, *, semantic_payload: dict[str, Any]) -> str:
    """Create a backend-neutral brief suitable for GPT Image or an agent skill."""

    required = "\n".join(f"- {item}" for item in intent.required_content) or "- Use the semantic payload faithfully."
    forbidden = "\n".join(f"- {item}" for item in intent.forbidden_content) or "- Do not invent unsupported claims or numbers."
    return (
        f"# Visual Brief — {intent.intent_id}\n\n"
        f"## Purpose\n{intent.purpose}\n\n"
        f"## Source summary\n{intent.source_summary}\n\n"
        f"## Required content\n{required}\n\n"
        f"## Forbidden content\n{forbidden}\n\n"
        "## Design freedom\n"
        "Choose the composition, hierarchy, palette, iconography, and visual rhythm adaptively. "
        "Do not force a fixed house diagram or one-color template. Prefer a restrained academic-paper aesthetic, "
        "clear hierarchy, generous whitespace, and concise labels. If reference figures are available to the agent, "
        "learn their visual grammar without copying a specific composition.\n\n"
        "## Editability\n"
        + ("An editable redraw is preferred after visual approval.\n\n" if intent.editable_preferred else "Editability is optional.\n\n")
        + "## Semantic payload\n```json\n"
        + __import__("json").dumps(semantic_payload, ensure_ascii=False, indent=2)
        + "\n```\n"
    )


def build_editable_redraw_job(
    intent: FigureIntent,
    *,
    semantic_payload: dict[str, Any],
    visual_master: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Describe the render–rebuild–compare loop used by editable figure agents.

    The job is intentionally server-neutral. Mature implementations such as a
    PowerPoint MCP server, an unflatten skill, or a scientific-figure skill can
    consume the same contract: use the approved raster as a visual master,
    rebuild editable text/shapes/connectors, render the slide, compare it, and
    iterate.  When no master exists yet the job remains WAITING rather than
    fabricating a path or pretending the editable redraw happened.
    """

    master = dict(visual_master or {})
    master_path = str(master.get("path") or "").strip()
    return {
        "schema_version": 1,
        "kind": "editable_figure_redraw_job",
        "status": "READY" if master_path else "WAITING_FOR_VISUAL_MASTER",
        "intent_id": intent.intent_id,
        "visual_master": master or None,
        "semantic_payload": semantic_payload,
        "required_outputs": [
            "editable_pptx_or_equivalent",
            "rendered_png_preview",
            "layout_check_report",
            "semantic_fidelity_review",
        ],
        "workflow": [
            "Inspect the visual master and semantic payload; inventory text, panels, arrows, icons, and repeated components.",
            "Rebuild text, boxes, connectors, and simple icons as native editable objects; keep complex illustration assets separate when necessary.",
            "Run layout checks for overlap, clipping, out-of-bounds shapes, and unreadable text.",
            "Render the editable figure back to PNG and compare with the visual master and semantic payload.",
            "Iterate only on diagnosed mismatches; preserve accepted content and dependency directions.",
            "Promote the editable output only after semantic fidelity and visual-quality review pass.",
        ],
        "guardrails": [
            "The visual master is a design/layout reference, not evidence for new numerical claims.",
            "Do not rasterize the entire master as one background image and call it editable.",
            "Do not silently correct or rewrite model names, numbers, or dependency arrows during redraw.",
            "If text in a generated master is malformed, use the semantic payload as the source of truth.",
        ],
    }


def build_ppt_mcp_handoff(intent: FigureIntent, *, semantic_payload: dict[str, Any]) -> dict[str, Any]:
    """Backend-neutral handoff for a future PowerPoint MCP / presentation skill."""

    return {
        "schema_version": 1,
        "kind": "editable_powerpoint_figure_handoff",
        "intent": intent.model_dump(mode="json"),
        "semantic_payload": semantic_payload,
        "instructions": [
            "Create one editable PowerPoint figure using native text, shapes, connectors, and optional icons.",
            "Infer layout and visual hierarchy from the semantic structure; do not map every field to a box mechanically.",
            "Keep labels concise and preserve all dependency directions.",
            "Use an academic low-saturation palette selected by the design agent rather than a hard-coded palette.",
            "Render a preview, inspect overlap/text overflow/legibility, revise, then export PPTX plus high-resolution PNG/SVG if supported.",
            "Do not add numeric claims, model names, or dependencies that are absent from the semantic payload.",
        ],
    }

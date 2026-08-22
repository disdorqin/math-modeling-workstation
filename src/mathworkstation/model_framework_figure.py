from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

from .io_utils import atomic_write_json, now_iso
from .paper_model_equations import select_equations_for_paper
from .plot_style import get_profile_colors, publication_context


class ModelFrameworkFigureService:
    """Render one explanatory mathematical-architecture figure from NarrativeGraph.

    This is intentionally different from the research workflow figure.  The
    workflow says *what the research process does*; this figure says *what the
    mathematical model contains* (observations, states/latent variables,
    structural relations, question-specific extensions, validation and outputs).
    It never fabricates numeric evidence.
    """

    def __init__(self, cases: Any, artifacts: Any, figures: Any) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.figures = figures

    def ensure(
        self,
        case_id: str,
        graph: Any,
        *,
        profile_id: str,
        narrative_artifact_id: str,
        run_id: str | None = None,
    ) -> dict[str, Any] | None:
        research_nodes = [
            node for node in graph.nodes
            if getattr(node, "role", "") == "RESEARCH" and getattr(node, "model_structure", None) is not None
        ]
        if not research_nodes:
            return None
        existing = [
            item
            for item in self.figures.list_figures(case_id)
            if item.get("status") == "FINAL"
            and (item.get("parameters") or {}).get("semantic_kind") == "model_framework"
            and (item.get("parameters") or {}).get("profile_id") == profile_id
            and narrative_artifact_id in item.get("source_artifact_ids", [])
        ]
        if existing:
            return existing[-1]

        root = self.cases.case_root(case_id)
        directory = root / "figures" / "research_state" / "model_framework"
        directory.mkdir(parents=True, exist_ok=True)
        spec = self._build_spec(research_nodes, profile_id)
        spec_path = directory / "model-framework-spec.json"
        png_path = directory / "model-framework.png"
        svg_path = directory / "model-framework.svg"
        atomic_write_json(spec_path, spec)
        spec_artifact = self.artifacts.register_existing(
            case_id,
            spec_path.relative_to(root).as_posix(),
            "model_framework_spec",
            "model_framework_figure",
            run_id=run_id,
            upstream=[narrative_artifact_id],
            paper_eligible=False,
        )
        self._render(spec, png_path, svg_path, profile_id)
        svg_artifact = self.artifacts.register_existing(
            case_id,
            svg_path.relative_to(root).as_posix(),
            "editable_vector_figure",
            "model_framework_figure",
            run_id=run_id,
            upstream=[narrative_artifact_id, spec_artifact["artifact_id"]],
            paper_eligible=False,
        )
        return self.figures.register(
            case_id,
            png_path.relative_to(root).as_posix(),
            "Unified mathematical model framework",
            [narrative_artifact_id, spec_artifact["artifact_id"]],
            "model_framework_figure.py",
            {
                "semantic_kind": "model_framework",
                "paper_role": "primary",
                "profile_id": profile_id,
                "document_layer": True,
                "numeric_evidence": False,
                "dpi": 600,
                "vector_source": True,
                "caption_first": True,
                "editable_source_artifact_ids": [svg_artifact["artifact_id"], spec_artifact["artifact_id"]],
                "visual_review_required": True,
                "visual_review_status": "REVIEW_PENDING",
                "generated_from": "NarrativeGraph.model_structure",
                "purpose": "Explain the shared mathematical architecture and how question-specific extensions inherit or modify it.",
            },
            run_id,
            status="FINAL",
        )

    def _build_spec(self, nodes: list[Any], profile_id: str) -> dict[str, Any]:
        anchor = next(
            (node for node in nodes if getattr(node.model_structure, "framework_role", "") == "CORE_MODEL"),
            nodes[0],
        )
        structure = anchor.model_structure
        observations = _compact(
            [item for node in nodes for item in (node.model_structure.observed_variables or [])],
            fallback=["Observed data / context"],
            limit=4,
        )
        state_items = _compact(
            [*structure.state_variables, *structure.latent_variables],
            fallback=["Shared mathematical state / mechanism"],
            limit=4,
        )
        executed_equations = select_equations_for_paper(str(getattr(anchor, "method", "") or ""), budget=4)
        relation_items = _compact(
            [equation.label for equation in executed_equations] or structure.core_relations,
            fallback=["Core structural relation"],
            limit=4,
        )
        question_blocks = []
        for node in nodes:
            plan = node.model_structure
            question_blocks.append(
                {
                    "id": node.subproblem_id,
                    "title": node.title,
                    "role": plan.framework_role,
                    "new_structure": _compact(plan.new_structure, fallback=[node.objective], limit=2),
                    "validation": _compact(plan.validation_requirements, fallback=["claim-specific validation"], limit=2),
                }
            )
        return {
            "schema_version": 1,
            "profile_id": profile_id,
            "title": "Unified mathematical model framework",
            "anchor_subproblem_id": anchor.subproblem_id,
            "observations": observations,
            "states": state_items,
            "relations": relation_items,
            "questions": question_blocks,
            "generated_at": now_iso(),
        }

    def _render(self, spec: dict[str, Any], png_path: Path, svg_path: Path, profile_id: str) -> None:
        colors = get_profile_colors(profile_id)
        n_questions = max(1, len(spec["questions"]))
        height = max(4.8, 1.45 * n_questions + 2.0)
        with publication_context(profile_id):
            fig, ax = plt.subplots(figsize=(8.6, height))
            ax.set_xlim(0, 1)
            ax.set_ylim(0, 1)
            ax.axis("off")

            title = "Unified Mathematical Model Framework" if profile_id != "CUMCM_C" else "统一数学建模框架"
            ax.text(0.5, 0.97, title, ha="center", va="top", fontsize=13, fontweight="semibold")

            _box(ax, 0.03, 0.64, 0.22, 0.23, "Observed Layer" if profile_id != "CUMCM_C" else "观测层", spec["observations"], colors[0])
            _box(ax, 0.31, 0.64, 0.27, 0.23, "State / Mechanism" if profile_id != "CUMCM_C" else "状态 / 机理层", spec["states"], colors[2 % len(colors)])
            _box(ax, 0.64, 0.64, 0.32, 0.23, "Core Relations" if profile_id != "CUMCM_C" else "核心关系层", spec["relations"], colors[1 % len(colors)])
            _arrow(ax, (0.25, 0.755), (0.31, 0.755))
            _arrow(ax, (0.58, 0.755), (0.64, 0.755))

            y_top = 0.53
            usable = 0.43
            step = usable / n_questions
            for index, question in enumerate(spec["questions"]):
                y = y_top - (index + 0.5) * step
                role = question["role"].replace("_", " ").title()
                label = f"{question['id']} · {role}"
                detail = [question["title"], *question["new_structure"]]
                _box(ax, 0.08, y - step * 0.34, 0.52, step * 0.68, label, detail, colors[(index + 3) % len(colors)], fontsize=8.3)
                validation_title = "Validation" if profile_id != "CUMCM_C" else "检验"
                _box(ax, 0.68, y - step * 0.34, 0.26, step * 0.68, validation_title, question["validation"], colors[(index + 5) % len(colors)], fontsize=7.7)
                _arrow(ax, (0.60, y), (0.68, y))
                _arrow(ax, (0.79, 0.64), (0.34, y + step * 0.34), connectionstyle="arc3,rad=0.05")

            footer = (
                "Algorithms estimate or solve this structure; they do not define the model."
                if profile_id != "CUMCM_C"
                else "算法只负责估计或求解上述数学结构，不替代模型本身。"
            )
            ax.text(0.5, 0.025, footer, ha="center", va="bottom", fontsize=8.4, style="italic")
            fig.tight_layout(pad=0.6)
            fig.savefig(png_path, dpi=600, bbox_inches="tight")
            fig.savefig(svg_path, bbox_inches="tight")
            plt.close(fig)


def _compact(values: list[str], *, fallback: list[str], limit: int) -> list[str]:
    seen: list[str] = []
    for value in values:
        text = " ".join(str(value).split())
        if text and text not in seen:
            seen.append(text)
    return seen[:limit] or fallback


def _box(
    ax: Any,
    x: float,
    y: float,
    w: float,
    h: float,
    title: str,
    items: list[str],
    edge_color: str,
    *,
    fontsize: float = 8.0,
) -> None:
    patch = FancyBboxPatch(
        (x, y),
        w,
        h,
        boxstyle="round,pad=0.012,rounding_size=0.012",
        linewidth=1.2,
        edgecolor=edge_color,
        facecolor="white",
    )
    ax.add_patch(patch)
    ax.text(x + 0.015, y + h - 0.025, title, ha="left", va="top", fontsize=fontsize + 0.8, fontweight="semibold", color=edge_color)
    wrapped: list[str] = []
    width = max(20, int(w * 90))
    for item in items:
        line = "\n".join(textwrap.wrap(str(item), width=width, break_long_words=False, break_on_hyphens=False))
        wrapped.append("• " + line)
    ax.text(x + 0.015, y + h - 0.065, "\n".join(wrapped), ha="left", va="top", fontsize=fontsize, linespacing=1.25)


def _arrow(ax: Any, start: tuple[float, float], end: tuple[float, float], *, connectionstyle: str = "arc3") -> None:
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=11,
            linewidth=0.9,
            color="#555555",
            connectionstyle=connectionstyle,
        )
    )

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .figure_color_director import FigureColorDirector


class FigureArtBrief(BaseModel):
    """Document-layer art direction for a scientific figure.

    The brief may change presentation only. It must never change x/y values,
    solver outputs, labels derived from data, or the evidence lineage.
    """

    model_config = ConfigDict(extra="forbid")

    semantic_kind: str
    visual_family: str
    layout: Literal["single", "wide", "panel", "matrix"]
    aspect_hint: str
    annotation_policy: str
    legend_policy: str
    grid_policy: str
    marker_policy: str
    emphasis: list[str] = Field(default_factory=list)
    palette_family: str
    palette_mode: str
    rationale: str


class FigureArtDirector:
    """Soft-prior scientific figure director inspired by publication figures.

    Existing deterministic plotting code remains the source of numeric truth.
    This layer only applies visual grammar after the data artists already exist.
    """

    def __init__(self, color_director: FigureColorDirector | None = None) -> None:
        self.color_director = color_director or FigureColorDirector()

    def plan(
        self,
        semantic_kind: str,
        *,
        identity: str = "",
        panel_count: int = 1,
        series_count: int = 0,
    ) -> FigureArtBrief:
        value = str(semantic_kind or "").lower()
        color = self.color_director.select(semantic_kind, identity=identity)

        if any(token in value for token in ("correlation", "association", "heatmap", "matrix")):
            visual_family = "signed_matrix" if any(token in value for token in ("correlation", "association", "effect")) else "matrix"
            layout = "matrix"
            aspect_hint = "near-square"
            grid_policy = "none"
            marker_policy = "none"
            legend_policy = "colorbar-or-none"
            annotation_policy = "annotate only sparse/high-value cells when renderer already has evidence"
            emphasis = ["neutral midpoint for signed values", "legible row/column labels"]
        elif panel_count > 1 or "panel" in value:
            visual_family = "coordinated_panel"
            layout = "panel"
            aspect_hint = "wide"
            grid_policy = "light-y"
            marker_policy = "series-dependent"
            legend_policy = "shared-or-outside when already present"
            annotation_policy = "panel labels and solver-derived callouts only"
            emphasis = ["same scales where comparison requires it", "balanced panel footprint"]
        elif any(token in value for token in ("sensitivity", "robust", "stress")):
            visual_family = "response_curve"
            layout = "wide"
            aspect_hint = "landscape"
            grid_policy = "light-y"
            marker_policy = "sparse-hollow"
            legend_policy = "frameless"
            annotation_policy = "highlight registered baseline or threshold only"
            emphasis = ["baseline", "direction and stability"]
        elif any(token in value for token in ("comparison", "scenario", "assortment", "category", "distribution", "ranking", "score")):
            visual_family = "comparative"
            layout = "wide" if series_count > 1 else "single"
            aspect_hint = "landscape"
            grid_policy = "light-y"
            marker_policy = "none-for-bars"
            legend_policy = "frameless"
            annotation_policy = "direct labels only when values are already registered"
            emphasis = ["rank/order", "between-group contrast"]
        else:
            visual_family = "evidence_curve"
            layout = "wide" if series_count > 1 else "single"
            aspect_hint = "landscape"
            grid_policy = "light-y"
            marker_policy = "sparse-hollow"
            legend_policy = "frameless"
            annotation_policy = "solver-derived extrema/thresholds only"
            emphasis = ["primary trend", "uncertainty when available"]

        return FigureArtBrief(
            semantic_kind=semantic_kind,
            visual_family=visual_family,
            layout=layout,
            aspect_hint=aspect_hint,
            annotation_policy=annotation_policy,
            legend_policy=legend_policy,
            grid_policy=grid_policy,
            marker_policy=marker_policy,
            emphasis=emphasis,
            palette_family=str(color["family"]),
            palette_mode=str(color["mode"]),
            rationale="Presentation is selected from semantic purpose and rendered artist structure; numeric artists remain unchanged.",
        )

    def apply(
        self,
        axis: Any,
        semantic_kind: str,
        *,
        identity: str = "",
        panel_count: int = 1,
    ) -> FigureArtBrief:
        series_count = len(getattr(axis, "lines", [])) + len(getattr(axis, "patches", []))
        brief = self.plan(
            semantic_kind,
            identity=identity,
            panel_count=panel_count,
            series_count=series_count,
        )
        self.color_director.apply(axis, semantic_kind, identity=identity)

        if brief.grid_policy == "none":
            axis.grid(False)
        elif brief.grid_policy == "light-y":
            axis.grid(False)
            axis.grid(axis="y", linewidth=0.6, alpha=0.18)

        for name in ("top", "right"):
            spine = getattr(axis, "spines", {}).get(name)
            if spine is not None:
                spine.set_visible(False)

        legend = axis.get_legend()
        if legend is not None and brief.legend_policy == "frameless":
            legend.set_frame_on(False)

        if brief.marker_policy == "sparse-hollow":
            for line in getattr(axis, "lines", []):
                try:
                    x = list(line.get_xdata())
                    y = list(line.get_ydata())
                except Exception:
                    continue
                if len(x) < 2 or len(y) < 2:
                    continue
                if max(x) == min(x) or max(y) == min(y):
                    continue
                if line.get_marker() in {None, "None", "", " "} and len(x) <= 16:
                    line.set_marker("o")
                    line.set_markersize(3.6)
                    line.set_markerfacecolor("white")
                    line.set_markeredgewidth(0.8)

        return brief

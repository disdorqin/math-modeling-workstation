from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.patches import FancyArrowPatch
from pydantic import BaseModel, ConfigDict, Field

from .plot_style import finalize_publication_figure, get_chart_template, get_publication_figsize, publication_context
from .figure_color_director import FigureColorDirector


ChartType = Literal[
    "line",
    "scatter",
    "heatmap",
    "boxplot",
    "radar",
    "state_transition",
    "association_network",
    "ranking",
    "uncertainty",
]


class ScientificFigureSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chart_type: ChartType
    title: str
    profile_id: str = "CUMCM_C"
    xlabel: str = ""
    ylabel: str = ""
    figsize_preset: Literal["single_column", "wide"] = "single_column"
    parameters: dict[str, Any] = Field(default_factory=dict)


class ScientificFigureFactory:
    """Small publication-ready chart vocabulary for competition papers.

    The factory deliberately supports a broad but finite set of argumentative
    chart families.  It is not a chart-zoo generator: the caller must choose a
    chart whose semantics match the evidence.  Every render exports both PNG
    and SVG so later PowerPoint/draw.io/manual refinement never needs to start
    from a low-resolution screenshot.
    """

    def __init__(self) -> None:
        self.color_director = FigureColorDirector()

    def render(
        self,
        spec: ScientificFigureSpec,
        data: dict[str, Any],
        output_base: str | Path,
    ) -> dict[str, Path]:
        base = Path(output_base)
        base.parent.mkdir(parents=True, exist_ok=True)
        png_path = base.with_suffix(".png")
        svg_path = base.with_suffix(".svg")
        with publication_context(spec.profile_id, chart_type=spec.chart_type) as style:
            figsize = get_publication_figsize(spec.profile_id, spec.figsize_preset)
            if spec.chart_type == "radar":
                figure, axis = plt.subplots(figsize=figsize, subplot_kw={"projection": "polar"})
            else:
                figure, axis = plt.subplots(figsize=figsize)
            renderer = getattr(self, f"_render_{spec.chart_type}")
            renderer(axis, data, style["palette"], get_chart_template(spec.chart_type), spec.parameters)
            semantic_kind = str(spec.parameters.get("semantic_kind") or spec.chart_type)
            if not bool(spec.parameters.get("preserve_renderer_colors", False)):
                self.color_director.apply(
                    axis,
                    semantic_kind,
                    identity=str(spec.parameters.get("figure_identity") or spec.title),
                )
            if spec.xlabel and spec.chart_type not in {"radar", "heatmap", "state_transition", "association_network"}:
                axis.set_xlabel(spec.xlabel)
            if spec.ylabel and spec.chart_type not in {"radar", "heatmap", "state_transition", "association_network"}:
                axis.set_ylabel(spec.ylabel)
            finalize_publication_figure(
                figure,
                axis,
                chart_type=spec.chart_type,
                title=spec.title,
                caption_first=bool(spec.parameters.get("caption_first", True)),
            )
            figure.savefig(png_path, dpi=600, bbox_inches="tight", facecolor="white")
            figure.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
            plt.close(figure)
        return {"png": png_path, "svg": svg_path}

    def _render_line(self, axis, data, palette, template, parameters) -> None:
        x = np.asarray(data["x"])
        series = dict(data["series"])
        for index, (label, values) in enumerate(series.items()):
            axis.plot(
                x,
                np.asarray(values, dtype=float),
                label=str(label),
                linewidth=float(template.get("linewidth", 1.8)),
                marker=parameters.get("marker", template.get("marker")),
                color=palette[index % len(palette)],
            )
        if len(series) > 1:
            axis.legend()
        axis.spines[["top", "right"]].set_visible(False)

    def _render_scatter(self, axis, data, palette, template, parameters) -> None:
        groups = data.get("groups")
        if groups:
            for index, (label, values) in enumerate(dict(groups).items()):
                axis.scatter(
                    values["x"], values["y"], label=str(label),
                    s=float(template.get("s", 40)), alpha=float(template.get("alpha", 0.75)),
                    edgecolors="white", linewidths=0.45, color=palette[index % len(palette)],
                )
            axis.legend()
        else:
            axis.scatter(
                data["x"], data["y"], s=float(template.get("s", 40)),
                alpha=float(template.get("alpha", 0.75)), edgecolors="white",
                linewidths=0.45, color=palette[0],
            )
        if parameters.get("reference_diagonal"):
            values = np.asarray([*data.get("x", []), *data.get("y", [])], dtype=float)
            if values.size:
                low, high = float(np.min(values)), float(np.max(values))
                axis.plot([low, high], [low, high], linestyle="--", linewidth=1.0, color="#555555")
        axis.spines[["top", "right"]].set_visible(False)

    def _render_heatmap(self, axis, data, palette, template, parameters) -> None:
        matrix = np.asarray(data["matrix"], dtype=float)
        image = axis.imshow(matrix, aspect="auto", cmap=parameters.get("cmap", template.get("cmap", "RdBu_r")))
        xlabels = [str(value) for value in data.get("xlabels", range(matrix.shape[1]))]
        ylabels = [str(value) for value in data.get("ylabels", range(matrix.shape[0]))]
        axis.set_xticks(range(matrix.shape[1]), xlabels, rotation=35, ha="right")
        axis.set_yticks(range(matrix.shape[0]), ylabels)
        annotate = bool(parameters.get("annot", template.get("annot", matrix.size <= 100)))
        if annotate:
            fmt = parameters.get("fmt", template.get("fmt", ".2f"))
            threshold = float(np.nanmean(matrix)) if matrix.size else 0.0
            for row in range(matrix.shape[0]):
                for col in range(matrix.shape[1]):
                    value = matrix[row, col]
                    if np.isfinite(value):
                        axis.text(col, row, format(float(value), fmt), ha="center", va="center", fontsize=7.2,
                                  color="white" if value > threshold else "#222222")
        axis.figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)

    def _render_boxplot(self, axis, data, palette, template, parameters) -> None:
        groups = dict(data["groups"])
        labels = list(groups)
        values = [np.asarray(groups[label], dtype=float) for label in labels]
        box = axis.boxplot(values, tick_labels=labels, patch_artist=True, showfliers=bool(template.get("showfliers", True)))
        for index, patch in enumerate(box["boxes"]):
            patch.set_facecolor(palette[index % len(palette)])
            patch.set_alpha(0.35)
            patch.set_edgecolor(palette[index % len(palette)])
        for median in box["medians"]:
            median.set_linewidth(float(template.get("median_linewidth", 1.5)))
            median.set_color("#222222")
        axis.spines[["top", "right"]].set_visible(False)

    def _render_radar(self, axis, data, palette, template, parameters) -> None:
        categories = [str(value) for value in data["categories"]]
        series = dict(data["series"])
        count = len(categories)
        angles = np.linspace(0, 2 * np.pi, count, endpoint=False).tolist()
        angles += angles[:1]
        for index, (label, values) in enumerate(series.items()):
            row = list(map(float, values))
            row += row[:1]
            axis.plot(angles, row, linewidth=float(template.get("linewidth", 1.6)), color=palette[index % len(palette)], label=str(label))
            axis.fill(angles, row, alpha=float(template.get("fill_alpha", 0.14)), color=palette[index % len(palette)])
        axis.set_xticks(angles[:-1], categories)
        axis.set_yticklabels([])
        if len(series) > 1:
            axis.legend(loc="upper right", bbox_to_anchor=(1.18, 1.1))

    def _render_state_transition(self, axis, data, palette, template, parameters) -> None:
        matrix = np.asarray(data["matrix"], dtype=float)
        states = [str(value) for value in data["states"]]
        image = axis.imshow(matrix, aspect="equal", cmap=parameters.get("cmap", template.get("cmap", "Blues")), vmin=0.0, vmax=max(1.0, float(np.nanmax(matrix))))
        axis.set_xticks(range(len(states)), states, rotation=30, ha="right")
        axis.set_yticks(range(len(states)), states)
        axis.set_xlabel("Next state")
        axis.set_ylabel("Current state")
        for row in range(matrix.shape[0]):
            for col in range(matrix.shape[1]):
                axis.text(col, row, f"{matrix[row, col]:.2f}", ha="center", va="center", fontsize=7.2)
        axis.figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)

    def _render_association_network(self, axis, data, palette, template, parameters) -> None:
        nodes = [str(value) for value in data["nodes"]]
        edges = list(data["edges"])
        count = len(nodes)
        angles = np.linspace(0, 2 * np.pi, count, endpoint=False)
        positions = {node: np.array([np.cos(angle), np.sin(angle)]) for node, angle in zip(nodes, angles)}
        strengths = [float(edge.get("weight", edge.get("lift", 1.0))) for edge in edges] or [1.0]
        max_strength = max(strengths)
        for edge in edges:
            left, right = str(edge["source"]), str(edge["target"])
            if left not in positions or right not in positions:
                continue
            weight = float(edge.get("weight", edge.get("lift", 1.0)))
            arrow = FancyArrowPatch(
                positions[left], positions[right], arrowstyle="-|>", mutation_scale=8,
                linewidth=0.7 + 2.0 * weight / max_strength, alpha=float(template.get("edge_alpha", 0.65)),
                color="#6B7280", connectionstyle="arc3,rad=0.08",
            )
            axis.add_patch(arrow)
        for index, node in enumerate(nodes):
            point = positions[node]
            axis.scatter([point[0]], [point[1]], s=float(template.get("node_size", 520)), color=palette[index % len(palette)], alpha=0.28, edgecolors=palette[index % len(palette)])
            axis.text(point[0], point[1], node, ha="center", va="center", fontsize=7.2)
        axis.set_xlim(-1.25, 1.25)
        axis.set_ylim(-1.25, 1.25)
        axis.set_aspect("equal")
        axis.axis("off")

    def _render_ranking(self, axis, data, palette, template, parameters) -> None:
        labels = np.asarray([str(value) for value in data["labels"]], dtype=object)
        scores = np.asarray(data["scores"], dtype=float)
        order = np.argsort(scores)
        ordered_labels = labels[order]
        ordered_scores = scores[order]
        y_positions = np.arange(len(ordered_labels))
        axis.barh(y_positions, ordered_scores, color=palette[0], alpha=0.72, height=float(template.get("bar_height", 0.62)))
        axis.set_yticks(y_positions, ordered_labels.tolist())
        top_k = min(int(template.get("annotate_top_k", 5)), len(ordered_labels))
        for y_position in y_positions[-top_k:]:
            value = float(ordered_scores[y_position])
            axis.text(value, float(y_position), f" {value:.3g}", va="center", fontsize=7.2)
        axis.spines[["top", "right"]].set_visible(False)

    def _render_uncertainty(self, axis, data, palette, template, parameters) -> None:
        x = np.asarray(data["x"])
        point = np.asarray(data["point"], dtype=float)
        lower = np.asarray(data["lower"], dtype=float)
        upper = np.asarray(data["upper"], dtype=float)
        axis.plot(x, point, color=palette[0], linewidth=float(template.get("linewidth", 1.8)), label=str(data.get("label", "estimate")))
        axis.fill_between(x, lower, upper, color=palette[0], alpha=float(template.get("interval_alpha", 0.18)), linewidth=0)
        axis.spines[["top", "right"]].set_visible(False)
        if data.get("label"):
            axis.legend()

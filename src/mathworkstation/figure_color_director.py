from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from matplotlib.colors import LinearSegmentedColormap


class FigureColorDirector:
    """Apply intent-aware, figure-varying publication colors after plotting.

    Plotting code stays evidence-focused and does not carry problem-specific RGB
    constants.  This director classifies the semantic purpose of a figure, picks
    a compatible palette family from configuration, and varies the family across
    figures using a stable identity hash.  The result is coherent within one
    paper without turning every chart into the same blue template.
    """

    def __init__(self, bank_path: str | Path | None = None) -> None:
        if bank_path is None:
            bank_path = Path(__file__).resolve().parents[2] / "config" / "ref_models" / "figure_palette_bank_v1.json"
        self.bank_path = Path(bank_path)
        self.bank = json.loads(self.bank_path.read_text(encoding="utf-8"))

    def select(self, semantic_kind: str, *, identity: str = "") -> dict[str, Any]:
        semantic_class = _semantic_class(semantic_kind)
        route = self.bank.get("semantic_routes", {}).get(
            semantic_class,
            self.bank.get("semantic_routes", {}).get("default", {"mode": "discrete", "families": []}),
        )
        mode = str(route.get("mode") or "discrete")
        families = [str(value) for value in route.get("families", [])]
        if not families:
            families = list(self.bank.get("discrete_families", {}))
            mode = "discrete"
        token = f"{semantic_kind}|{identity}".encode("utf-8")
        index = int(hashlib.sha256(token).hexdigest()[:8], 16) % len(families)
        family = families[index]
        palette = list(self.bank.get(f"{mode}_families", {}).get(family, []))
        if not palette:
            mode = "discrete"
            family = next(iter(self.bank.get("discrete_families", {})))
            palette = list(self.bank["discrete_families"][family])
        return {
            "semantic_class": semantic_class,
            "mode": mode,
            "family": family,
            "colors": palette,
        }

    def apply(self, axis: Any, semantic_kind: str, *, identity: str = "") -> dict[str, Any]:
        selection = self.select(semantic_kind, identity=identity)
        colors = selection["colors"]
        mode = selection["mode"]
        if not colors:
            return selection

        # Heatmaps/images should use a continuous map rather than categorical
        # patch colors.  Correlation/effect maps retain a neutral midpoint.
        for image in getattr(axis, "images", []):
            image.set_cmap(LinearSegmentedColormap.from_list(f"mathws-{selection['family']}", colors))

        patches = [patch for patch in getattr(axis, "patches", []) if getattr(patch, "get_visible", lambda: True)()]
        if patches:
            if mode == "sequential":
                patch_colors = _resample(colors, len(patches))
            else:
                patch_colors = [colors[index % len(colors)] for index in range(len(patches))]
            for patch, color in zip(patches, patch_colors):
                try:
                    patch.set_facecolor(color)
                    patch.set_alpha(0.9)
                except (AttributeError, ValueError):
                    continue

        data_lines = []
        reference_lines = []
        for line in getattr(axis, "lines", []):
            try:
                x = list(line.get_xdata())
                y = list(line.get_ydata())
            except Exception:
                data_lines.append(line)
                continue
            constant_x = len(x) >= 2 and max(x) == min(x)
            constant_y = len(y) >= 2 and max(y) == min(y)
            if constant_x or constant_y:
                reference_lines.append(line)
            else:
                data_lines.append(line)
        line_colors = _resample(colors, len(data_lines)) if mode == "sequential" else [colors[i % len(colors)] for i in range(len(data_lines))]
        for line, color in zip(data_lines, line_colors):
            line.set_color(color)
            marker = line.get_marker()
            if marker not in {None, "None", "", " "}:
                line.set_markerfacecolor("white")
                line.set_markeredgecolor(color)
        for line in reference_lines:
            line.set_color("#7A7F83")
            line.set_alpha(0.75)

        collections = list(getattr(axis, "collections", []))
        for index, collection in enumerate(collections):
            color = colors[index % len(colors)]
            try:
                collection.set_facecolor(color)
                collection.set_edgecolor("white")
                collection.set_alpha(0.78)
            except (AttributeError, ValueError):
                continue
        return selection


def _semantic_class(semantic_kind: str) -> str:
    value = str(semantic_kind or "").lower()
    if "correlation" in value or "association" in value:
        return "correlation"
    if "effect" in value or "coefficient" in value:
        return "effect"
    if "profile_heatmap" in value:
        return "ranking"
    if any(token in value for token in ("sensitivity", "robust", "stress")):
        return "sensitivity"
    if any(token in value for token in ("comparison", "scenario", "before_after")):
        return "comparison"
    if any(token in value for token in ("ranking", "score", "importance")):
        return "ranking"
    if any(token in value for token in ("replenishment", "assortment", "distribution", "probabilities", "state_shares", "category")):
        return "category"
    return "default"


def _resample(colors: list[str], count: int) -> list[str]:
    if count <= 0:
        return []
    if count == 1:
        return [colors[len(colors) // 2]]
    if count <= len(colors):
        step = (len(colors) - 1) / (count - 1)
        return [colors[round(index * step)] for index in range(count)]
    return [colors[index % len(colors)] for index in range(count)]

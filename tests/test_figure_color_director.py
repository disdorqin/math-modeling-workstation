from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from mathworkstation.figure_color_director import FigureColorDirector


def test_color_director_uses_semantic_palette_and_multicolor_bars() -> None:
    director = FigureColorDirector()
    figure, axis = plt.subplots()
    axis.bar(["A", "B", "C", "D"], [1, 2, 3, 4])

    selection = director.apply(axis, "retail_category_assortment_counts", identity="case:SP3")
    colors = {tuple(round(value, 4) for value in patch.get_facecolor()) for patch in axis.patches}

    assert selection["semantic_class"] == "category"
    assert selection["family"]
    assert len(colors) >= 3
    plt.close(figure)


def test_color_director_assigns_diverging_map_to_correlation_heatmap() -> None:
    director = FigureColorDirector()
    figure, axis = plt.subplots()
    image = axis.imshow(np.asarray([[1.0, -0.5], [-0.5, 1.0]]), vmin=-1.0, vmax=1.0)

    selection = director.apply(axis, "correlation_heatmap", identity="case:SP1")

    assert selection["semantic_class"] == "correlation"
    assert selection["mode"] == "diverging"
    assert image.get_cmap().name.startswith("mathws-")
    plt.close(figure)

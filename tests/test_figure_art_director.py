from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from mathworkstation.figure_art_director import FigureArtDirector


def test_signed_heatmap_gets_matrix_art_direction() -> None:
    director = FigureArtDirector()
    brief = director.plan("sales_correlation_heatmap", identity="case:sp1")
    assert brief.visual_family == "signed_matrix"
    assert brief.layout == "matrix"
    assert brief.grid_policy == "none"
    assert brief.palette_mode == "diverging"


def test_sensitivity_curve_gets_response_curve_direction() -> None:
    director = FigureArtDirector()
    brief = director.plan("parameter_sensitivity_curve", identity="case:sp2", series_count=2)
    assert brief.visual_family == "response_curve"
    assert brief.layout == "wide"
    assert brief.marker_policy == "sparse-hollow"


def test_apply_never_changes_numeric_line_data() -> None:
    director = FigureArtDirector()
    figure, axis = plt.subplots()
    line, = axis.plot([0.0, 1.0, 2.0], [2.0, 3.5, 2.5])
    before_x = list(line.get_xdata())
    before_y = list(line.get_ydata())

    brief = director.apply(axis, "parameter_sensitivity_curve", identity="case:sp2")

    assert list(line.get_xdata()) == before_x
    assert list(line.get_ydata()) == before_y
    assert brief.visual_family == "response_curve"
    assert line.get_marker() == "o"
    plt.close(figure)

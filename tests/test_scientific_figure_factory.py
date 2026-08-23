from __future__ import annotations

from pathlib import Path

import numpy as np

from mathworkstation.scientific_figure_factory import ScientificFigureFactory, ScientificFigureSpec


def _assert_rendered(tmp_path: Path, name: str, spec: ScientificFigureSpec, data: dict) -> None:
    paths = ScientificFigureFactory().render(spec, data, tmp_path / name)
    assert paths["png"].is_file() and paths["png"].stat().st_size > 500
    assert paths["svg"].is_file() and paths["svg"].stat().st_size > 500
    assert "<svg" in paths["svg"].read_text(encoding="utf-8")[:1000]


def test_factory_covers_line_scatter_heatmap_and_boxplot(tmp_path: Path) -> None:
    x = np.arange(8)
    _assert_rendered(
        tmp_path,
        "line",
        ScientificFigureSpec(chart_type="line", title="Trend", profile_id="MCM_C", xlabel="t", ylabel="y"),
        {"x": x, "series": {"A": x * 0.5, "B": x * 0.3 + 1}},
    )
    _assert_rendered(
        tmp_path,
        "scatter",
        ScientificFigureSpec(chart_type="scatter", title="Clusters", profile_id="CUMCM_C", xlabel="x", ylabel="y"),
        {"groups": {"g1": {"x": [1, 2, 3], "y": [2, 2.5, 3]}, "g2": {"x": [4, 5, 6], "y": [1, 1.5, 2]}}},
    )
    _assert_rendered(
        tmp_path,
        "heatmap",
        ScientificFigureSpec(chart_type="heatmap", title="Heatmap", profile_id="SCI_CLEAN"),
        {"matrix": [[1.0, 0.3], [0.3, 1.0]], "xlabels": ["x1", "x2"], "ylabels": ["x1", "x2"]},
    )
    _assert_rendered(
        tmp_path,
        "boxplot",
        ScientificFigureSpec(chart_type="boxplot", title="Distribution comparison", profile_id="CUMCM_C"),
        {"groups": {"member": [1, 2, 3, 4], "non-member": [0.5, 1.0, 1.4, 2.0]}},
    )


def test_factory_covers_radar_transition_association_ranking_and_uncertainty(tmp_path: Path) -> None:
    _assert_rendered(
        tmp_path,
        "radar",
        ScientificFigureSpec(chart_type="radar", title="Profile radar", profile_id="CUMCM_C"),
        {"categories": ["R", "F", "M", "S"], "series": {"A": [0.8, 0.6, 0.7, 0.9], "B": [0.4, 0.8, 0.5, 0.6]}},
    )
    _assert_rendered(
        tmp_path,
        "transition",
        ScientificFigureSpec(chart_type="state_transition", title="State transitions", profile_id="CUMCM_C"),
        {"states": ["active", "dormant", "lost"], "matrix": [[0.7, 0.2, 0.1], [0.3, 0.5, 0.2], [0.1, 0.2, 0.7]]},
    )
    _assert_rendered(
        tmp_path,
        "association",
        ScientificFigureSpec(chart_type="association_network", title="Basket associations", profile_id="MCM_C"),
        {"nodes": ["A", "B", "C"], "edges": [{"source": "A", "target": "B", "lift": 2.2}, {"source": "B", "target": "C", "lift": 1.5}]},
    )
    _assert_rendered(
        tmp_path,
        "ranking",
        ScientificFigureSpec(chart_type="ranking", title="Member ranking", profile_id="SCI_CLEAN", xlabel="Score"),
        {"labels": ["A", "B", "C", "D"], "scores": [0.8, 0.3, 0.6, 0.9]},
    )
    _assert_rendered(
        tmp_path,
        "uncertainty",
        ScientificFigureSpec(chart_type="uncertainty", title="Forecast interval", profile_id="MCM_C", xlabel="time", ylabel="value"),
        {"x": [1, 2, 3, 4], "point": [2.0, 2.5, 2.8, 3.1], "lower": [1.7, 2.1, 2.4, 2.6], "upper": [2.3, 2.9, 3.2, 3.6], "label": "forecast"},
    )

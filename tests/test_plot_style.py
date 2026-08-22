"""测试 plot_style 模块"""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pytest

from mathworkstation.plot_style import (
    apply_style,
    classify_figure,
    create_figure,
    finalize_publication_figure,
    get_chart_template,
    get_color,
    get_colors,
    get_figsize,
    get_line_cycle,
    get_linestyles,
    get_markers,
    get_profile_colors,
    get_publication_figsize,
    get_publication_profile,
    publication_context,
    plot_with_style,
    save_figure,
)


class TestPlotStyleConfig:
    """测试配置加载"""

    def test_load_config(self):
        """测试配置文件可以加载"""
        from mathworkstation.plot_style import _load_config
        config = _load_config()
        assert "matplotlib" in config
        assert "colors" in config
        assert "linestyles" in config
        assert "markers" in config
        assert "figsize_presets" in config
        assert "chart_templates" in config
        assert "figure_categories" in config
        assert "publication_profiles" in config

    def test_colors(self):
        """测试配色列表"""
        colors = get_colors()
        assert len(colors) >= 5
        assert all(c.startswith("#") for c in colors)

    def test_linestyles(self):
        """测试线型列表"""
        linestyles = get_linestyles()
        assert len(linestyles) >= 4
        assert "-" in linestyles
        assert "--" in linestyles
        assert "-." in linestyles
        assert ":" in linestyles

    def test_markers(self):
        """测试标记点列表"""
        markers = get_markers()
        assert len(markers) >= 5

    def test_figsize_presets(self):
        """测试预设尺寸"""
        assert get_figsize("single") == (8, 5)
        assert get_figsize("distribution") == (10, 6)
        assert get_figsize("heatmap") == (8, 7)
        assert get_figsize("comparison") == (10, 5)
        assert get_figsize("sensitivity") == (8, 5)
        assert get_figsize("workflow") == (16, 4.6)
        assert get_figsize("unknown") == (8, 5)

    def test_get_color(self):
        """测试获取命名颜色"""
        assert get_color("primary") == "#1f77b4"
        assert get_color("secondary") == "#ff7f0e"
        assert get_color("success") == "#2ca02c"
        assert get_color("danger") == "#d62728"
        assert get_color("unknown") == "#1f77b4"

    def test_publication_profiles_are_destination_specific(self):
        cumcm = get_publication_profile("CUMCM_C")
        mcm = get_publication_profile("MCM_C")
        sci = get_publication_profile("SCI_CLEAN")
        assert cumcm["rc"]["font.family"] == "sans-serif"
        assert mcm["rc"]["font.family"] == "serif"
        assert sci["figsize"]["single_column"][0] < cumcm["figsize"]["single_column"][0]
        assert get_profile_colors("CUMCM_C") != get_profile_colors("MCM_C")
        assert get_publication_figsize("MCM_C", "wide") == (7.2, 4.1)

    def test_publication_context_restores_global_rcparams(self):
        before_family = list(plt.rcParams["font.family"])
        before_grid = plt.rcParams["axes.grid"]
        with publication_context("MCM_C", chart_type="time_series") as spec:
            assert plt.rcParams["font.family"][0] == "Times New Roman"
            assert any(name in plt.rcParams["font.family"] for name in ("Noto Serif SC", "Source Han Serif SC", "SimSun"))
            assert plt.rcParams["axes.grid"] is False
            assert spec["chart_template"]["confidence_alpha"] == 0.18
        assert list(plt.rcParams["font.family"]) == before_family
        assert plt.rcParams["axes.grid"] == before_grid

    def test_extended_chart_template_coverage(self):
        for chart_type in (
            "boxplot",
            "time_series",
            "radar",
            "state_transition",
            "association",
            "ranking",
            "uncertainty",
        ):
            assert get_chart_template(chart_type), chart_type

    def test_get_chart_template(self):
        """测试获取图表模板"""
        template = get_chart_template("histogram")
        assert "bins" in template
        assert "edgecolor" in template

        template = get_chart_template("bar")
        assert "width" in template

        template = get_chart_template("line")
        assert "linewidth" in template

        template = get_chart_template("unknown")
        assert template == {}


class TestApplyStyle:
    """测试样式应用"""

    def test_apply_style(self):
        """测试应用样式到 rcParams"""
        apply_style()
        assert plt.rcParams["axes.unicode_minus"] is False
        assert plt.rcParams["axes.grid"] is True
        assert plt.rcParams["figure.dpi"] == 600

    def test_get_line_cycle(self):
        """测试线型标记组合循环"""
        cycle = get_line_cycle()
        assert len(cycle) >= 16  # 4 linestyles * 4+ markers

        cycle_4 = get_line_cycle(4)
        assert len(cycle_4) == 4
        assert all(isinstance(c, tuple) and len(c) == 2 for c in cycle_4)


class TestFigureCreation:
    """测试图表创建"""

    def test_create_figure(self):
        """测试创建图表"""
        apply_style()
        fig, ax = create_figure()
        assert isinstance(fig, plt.Figure)
        assert isinstance(ax, plt.Axes)
        plt.close(fig)

    def test_create_figure_custom_dpi(self):
        """测试创建自定义 DPI 图表"""
        apply_style()
        fig, ax = create_figure(dpi=120)
        assert fig.dpi == 120
        plt.close(fig)

    def test_create_figure_preset(self):
        """测试使用预设尺寸创建图表"""
        apply_style()
        fig, ax = create_figure(figsize_preset="distribution")
        width, height = fig.get_size_inches()
        assert width == 10
        assert height == 6
        plt.close(fig)

    def test_save_figure(self):
        """测试保存图表"""
        apply_style()
        fig, ax = create_figure()
        ax.plot([1, 2, 3], [1, 4, 9])
        
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            path = f.name
        
        save_figure(fig, path)
        assert Path(path).exists()
        
        Path(path).unlink()

    def test_finalize_publication_figure_uses_caption_first_and_readable_axes(self):
        with publication_context("MCM_C"):
            fig, ax = plt.subplots()
            ax.bar([0, 1], [2.0, 3.0], label="candidate")
            ax.set_xticks([0, 1], ["A very long category", "Another long category"])
            finalize_publication_figure(fig, ax, chart_type="bar", title="Duplicated paper caption")
            assert ax.get_title() == ""
            assert ax.spines["top"].get_visible() is False
            assert ax.spines["right"].get_visible() is False
            assert ax.get_legend() is not None
            plt.close(fig)

    def test_plot_with_style(self):
        """测试使用统一风格绘图"""
        apply_style()
        
        def my_plot(fig, ax):
            ax.plot([1, 2, 3], [1, 4, 9])
        
        fig = plot_with_style(
            my_plot,
            title="Test Plot",
            xlabel="X",
            ylabel="Y",
        )
        assert isinstance(fig, plt.Figure)
        assert fig.axes[0].get_title() == "Test Plot"
        assert fig.axes[0].get_xlabel() == "X"
        assert fig.axes[0].get_ylabel() == "Y"
        plt.close(fig)


class TestClassifyFigure:
    """测试图表分类"""

    def test_classify_distribution(self):
        """测试分布图分类"""
        assert classify_figure("数值变量分布") == "data_analysis"
        assert classify_figure("Distribution Plot") == "data_analysis"
        assert classify_figure("Histogram of Data") == "data_analysis"
        assert classify_figure("EDA Summary") == "data_analysis"

    def test_classify_comparison(self):
        """测试对比图分类"""
        assert classify_figure("模型比较") == "results"
        assert classify_figure("Model Comparison") == "results"
        assert classify_figure("Cross-Validation Results") == "results"

    def test_classify_sensitivity(self):
        """测试敏感性图分类"""
        assert classify_figure("敏感性分析") == "sensitivity"
        assert classify_figure("Sensitivity Analysis") == "sensitivity"
        assert classify_figure("Robustness Check") == "sensitivity"

    def test_classify_workflow(self):
        """测试工作流图分类"""
        assert classify_figure("工作流总览") == "overview"
        assert classify_figure("Workflow Overview") == "overview"
        assert classify_figure("Process Flow") == "overview"

    def test_classify_unknown(self):
        """测试未知图表分类"""
        assert classify_figure("Some Random Figure") is None
        assert classify_figure("自定义图表") is None

    def test_classify_with_keywords(self):
        """测试使用关键词分类"""
        assert classify_figure("Figure 1", ["分布", "histogram"]) == "data_analysis"
        assert classify_figure("Chart", ["comparison", "model"]) == "results"

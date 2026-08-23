"""数学建模论文统一绘图风格模块

加载 config/plot-style.json 配置，提供统一的 matplotlib 风格设置和图表模板。
确保所有图表黑白可区分（线型/标记循环），符合数模论文打印评审要求。
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from cycler import cycler
from matplotlib import font_manager


_CONFIG_PATH = Path(__file__).resolve().parent.parent.parent / "config" / "plot-style.json"
_config: dict[str, Any] | None = None


def _load_config() -> dict[str, Any]:
    """延迟加载配置文件"""
    global _config
    if _config is None:
        with _CONFIG_PATH.open("r", encoding="utf-8") as f:
            _config = json.load(f)
    return _config


def apply_style() -> None:
    """应用统一的 matplotlib 风格到全局 rcParams"""
    config = _load_config()
    rc = config["matplotlib"]
    
    plt.rcParams["font.sans-serif"] = rc["font"]["sans-serif"]
    plt.rcParams["font.serif"] = rc["font"]["serif"]
    plt.rcParams["font.monospace"] = rc["font"]["monospace"]
    plt.rcParams["font.size"] = rc["font"]["size"]
    plt.rcParams["font.family"] = rc["font"]["family"]
    
    plt.rcParams["axes.unicode_minus"] = rc["axes"]["unicode_minus"]
    plt.rcParams["axes.linewidth"] = rc["axes"]["linewidth"]
    plt.rcParams["axes.edgecolor"] = rc["axes"]["edgecolor"]
    plt.rcParams["axes.grid"] = rc["axes"]["grid"]
    plt.rcParams["axes.labelsize"] = rc["axes"]["labelsize"]
    plt.rcParams["axes.titlesize"] = rc["axes"]["titlesize"]
    plt.rcParams["axes.titleweight"] = rc["axes"]["titleweight"]
    plt.rcParams["axes.labelweight"] = rc["axes"]["labelweight"]
    
    plt.rcParams["figure.dpi"] = rc["figure"]["dpi"]
    plt.rcParams["figure.figsize"] = rc["figure"]["figsize"]
    plt.rcParams["figure.facecolor"] = rc["figure"]["facecolor"]
    plt.rcParams["figure.edgecolor"] = rc["figure"]["edgecolor"]
    
    plt.rcParams["savefig.dpi"] = rc["savefig"]["dpi"]
    plt.rcParams["savefig.facecolor"] = rc["savefig"]["facecolor"]
    plt.rcParams["savefig.edgecolor"] = rc["savefig"]["edgecolor"]
    plt.rcParams["savefig.pad_inches"] = rc["savefig"]["pad_inches"]
    
    plt.rcParams["legend.fontsize"] = rc["legend"]["fontsize"]
    plt.rcParams["legend.frameon"] = rc["legend"]["frameon"]
    plt.rcParams["legend.framealpha"] = rc["legend"]["framealpha"]
    plt.rcParams["legend.edgecolor"] = rc["legend"]["edgecolor"]
    
    plt.rcParams["xtick.labelsize"] = rc["xtick"]["labelsize"]
    plt.rcParams["xtick.direction"] = rc["xtick"]["direction"]
    plt.rcParams["ytick.labelsize"] = rc["ytick"]["labelsize"]
    plt.rcParams["ytick.direction"] = rc["ytick"]["direction"]
    
    plt.rcParams["lines.linewidth"] = rc["lines"]["linewidth"]
    plt.rcParams["lines.markersize"] = rc["lines"]["markersize"]


def get_colors() -> list[str]:
    """获取配色列表"""
    config = _load_config()
    return config["colors"]["palette"]


def get_linestyles() -> list[str]:
    """获取线型循环列表（黑白可区分）"""
    config = _load_config()
    return config["linestyles"]["cycle"]


def get_markers() -> list[str]:
    """获取标记点循环列表"""
    config = _load_config()
    return config["markers"]["cycle"]


def get_figsize(preset: str = "single") -> tuple[float, float]:
    """获取预设尺寸"""
    config = _load_config()
    sizes = config["figsize_presets"]
    if preset in sizes:
        return tuple(sizes[preset])
    return tuple(sizes["single"])


def get_chart_template(chart_type: str) -> dict[str, Any]:
    """获取图表模板参数"""
    config = _load_config()
    return config["chart_templates"].get(chart_type, {})


def get_publication_profile(profile: str = "CUMCM_C") -> dict[str, Any]:
    """Return one publication profile without mutating matplotlib global state."""

    profiles = _load_config().get("publication_profiles", {})
    try:
        value = profiles[profile]
    except KeyError as error:
        raise KeyError(f"unknown publication profile: {profile}") from error
    return {
        **value,
        "palette": list(value.get("palette", [])),
        "figsize": dict(value.get("figsize", {})),
        "rc": dict(value.get("rc", {})),
    }


def get_profile_colors(profile: str = "CUMCM_C") -> list[str]:
    """Get a print-safe palette for a specific competition/publication profile."""

    colors = list(get_publication_profile(profile).get("palette", []))
    return colors or get_colors()


def get_publication_figsize(profile: str = "CUMCM_C", preset: str = "single_column") -> tuple[float, float]:
    """Figure dimensions that reflect the destination paper rather than screen size."""

    sizes = get_publication_profile(profile).get("figsize", {})
    if preset in sizes:
        return tuple(float(value) for value in sizes[preset])
    if "single_column" in sizes:
        return tuple(float(value) for value in sizes["single_column"])
    return get_figsize("single")


def _publication_font_stack(profile: str) -> list[str]:
    """Return an installed Latin+CJK font stack for the destination profile."""

    available = {entry.name for entry in font_manager.fontManager.ttflist}
    if profile == "CUMCM_C":
        preferred = [
            "Microsoft YaHei",
            "Noto Sans SC",
            "Source Han Sans CN",
            "SimHei",
            "DejaVu Sans",
        ]
    else:
        preferred = [
            "Times New Roman",
            "Noto Serif SC",
            "Source Han Serif SC",
            "Source Han Serif CN",
            "SimSun",
            "DejaVu Serif",
        ]
    selected = [name for name in preferred if name in available]
    return selected or (["sans-serif"] if profile == "CUMCM_C" else ["serif"])


@contextmanager
def publication_context(
    profile: str = "CUMCM_C",
    *,
    chart_type: str | None = None,
) -> Iterator[dict[str, Any]]:
    """Apply a publication profile locally and restore rcParams on exit.

    The design follows the stateless TUEplots-style principle: one figure may be
    rendered for CUMCM, another for MCM, and a third for a journal without a
    previous call silently changing later figures.  ``chart_type`` is returned
    as a template hint but is not blindly copied into rcParams.
    """

    spec = get_publication_profile(profile)
    rc = dict(spec.get("rc", {}))
    palette = list(spec.get("palette", []))
    if palette:
        rc["axes.prop_cycle"] = cycler(color=palette)
    # Keep CJK fallbacks available for every publication profile.  Some evidence
    # figures are rendered with SCI_CLEAN even when Chinese category/item labels
    # come from a CUMCM dataset; a serif-only Latin stack would silently drop those
    # glyphs.  Matplotlib keeps the requested Latin family first and falls back per
    # glyph to the configured Windows/Noto CJK fonts when needed.
    font_config = _load_config()["matplotlib"]["font"]
    rc.setdefault("font.sans-serif", font_config["sans-serif"])
    rc.setdefault("font.serif", font_config["serif"])
    # Matplotlib does not reliably perform per-glyph fallback when font.family is
    # only the generic token ``serif``/``sans-serif``.  Supplying the installed
    # family stack directly keeps Times/YaHei as the visual primary while allowing
    # Chinese category/item labels to fall through to Noto/Source Han/SimSun.
    rc["font.family"] = _publication_font_stack(profile)
    with plt.rc_context(rc=rc):
        yield {
            "profile": profile,
            "palette": get_profile_colors(profile),
            "figsize": dict(spec.get("figsize", {})),
            "chart_template": get_chart_template(chart_type) if chart_type else {},
        }


def finalize_publication_axis(
    axis: Any,
    *,
    chart_type: str | None = None,
    title: str | None = None,
    caption_first: bool = True,
) -> None:
    """Apply the final paper-facing polish after semantic plotting.

    Competition figures are captioned in the paper, so repeating a long title
    inside the axes wastes vertical space and creates the common AI-paper look of
    ``title + caption`` saying the same thing twice.  Data figures therefore use
    caption-first presentation by default; workflow diagrams remain free to keep
    their own title because they are standalone compositions.

    The function intentionally does not choose chart semantics or colors.  It only
    normalizes presentation of an already-correct plot: spine weight, restrained
    guide lines, legend density and categorical tick readability.
    """

    kind = str(chart_type or "").lower()
    if title and not caption_first:
        axis.set_title(title)
    elif caption_first:
        axis.set_title("")

    composition_tokens = ("heatmap", "radar", "transition", "network", "workflow", "flowchart")
    plot_like = not any(token in kind for token in composition_tokens)
    if plot_like:
        for name in ("top", "right"):
            spine = axis.spines.get(name)
            if spine is not None:
                spine.set_visible(False)
        axis.set_axisbelow(True)
        axis.grid(axis="y", linewidth=0.45, alpha=0.18)

    handles, labels = axis.get_legend_handles_labels()
    if labels:
        # Long legends are easier to scan in two columns than as one tall block,
        # while short legends should remain compact.
        ncol = 1 if len(labels) <= 4 else 2 if len(labels) <= 8 else 3
        axis.legend(frameon=False, ncol=ncol)

    tick_labels = [item.get_text() for item in axis.get_xticklabels()]
    nonempty = [value for value in tick_labels if value]
    if len(nonempty) >= 7 and any(len(value) >= 8 for value in nonempty):
        for label in axis.get_xticklabels():
            label.set_rotation(25)
            label.set_horizontalalignment("right")


def finalize_publication_figure(
    figure: Any,
    axis: Any,
    *,
    chart_type: str | None = None,
    title: str | None = None,
    caption_first: bool = True,
) -> None:
    """Finalize one publication figure without changing its evidence semantics."""

    finalize_publication_axis(
        axis,
        chart_type=chart_type,
        title=title,
        caption_first=caption_first,
    )
    figure.tight_layout(pad=0.65)


def get_color(name: str) -> str:
    """获取命名颜色"""
    config = _load_config()
    return config["colors"].get(name, config["colors"]["primary"])


def classify_figure(title: str, keywords: list[str] | None = None) -> str | None:
    """根据标题和关键词分类图表，返回目标章节名
    
    用于图表自动晋升：确定图表应该嵌入论文的哪个章节。
    
    Args:
        title: 图表标题
        keywords: 额外的关键词列表
        
    Returns:
        目标章节名（data_analysis/results/sensitivity/overview），无法分类返回 None
    """
    config = _load_config()
    categories = config["figure_categories"]
    
    search_text = title.lower()
    if keywords:
        search_text += " " + " ".join(k.lower() for k in keywords)
    
    for category_name, category_info in categories.items():
        for keyword in category_info["keywords"]:
            if keyword.lower() in search_text:
                return category_info["target_section"]
    return None


def create_figure(
    figsize_preset: str = "single",
    dpi: int | None = None,
    **kwargs: Any,
) -> tuple[plt.Figure, plt.Axes]:
    """创建统一风格的图表对象
    
    Args:
        figsize_preset: 预设尺寸名称
        dpi: 分辨率（默认使用配置值）
        **kwargs: 传递给 plt.subplots 的额外参数
        
    Returns:
        (figure, axes) 元组
    """
    config = _load_config()
    figsize = get_figsize(figsize_preset)
    if dpi is None:
        dpi = config["matplotlib"]["figure"]["dpi"]
    
    fig, ax = plt.subplots(figsize=figsize, dpi=dpi, **kwargs)
    return fig, ax


def save_figure(
    fig: plt.Figure,
    path: str | Path,
    dpi: int | None = None,
    close: bool = True,
) -> None:
    """保存图表到文件
    
    Args:
        fig: matplotlib Figure 对象
        path: 保存路径
        dpi: 分辨率（默认使用配置值）
        close: 保存后是否关闭图表
    """
    config = _load_config()
    savefig_config = config["matplotlib"]["savefig"]
    if dpi is None:
        dpi = savefig_config["dpi"]
    
    fig.savefig(
        path,
        dpi=dpi,
        bbox_inches="tight",
        facecolor=savefig_config["facecolor"],
        edgecolor=savefig_config["edgecolor"],
        pad_inches=savefig_config["pad_inches"],
    )
    if close:
        plt.close(fig)


def plot_with_style(
    plot_func: Any,
    figsize_preset: str = "single",
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    save_path: str | Path | None = None,
    dpi: int | None = None,
    **kwargs: Any,
) -> plt.Figure:
    """使用统一风格执行绘图函数
    
    Args:
        plot_func: 绘图函数，接受 (fig, ax) 参数
        figsize_preset: 预设尺寸名称
        title: 图表标题
        xlabel: X 轴标签
        ylabel: Y 轴标签
        save_path: 保存路径（None 则不保存）
        dpi: 分辨率
        **kwargs: 传递给 plot_func 的额外参数
        
    Returns:
        matplotlib Figure 对象
    """
    fig, ax = create_figure(figsize_preset, dpi)
    plot_func(fig, ax, **kwargs)
    
    if title:
        ax.set_title(title, fontweight="bold")
    if xlabel:
        ax.set_xlabel(xlabel)
    if ylabel:
        ax.set_ylabel(ylabel)
    
    fig.tight_layout()
    
    if save_path:
        save_figure(fig, save_path)
    
    return fig


def get_line_cycle(n: int | None = None) -> list[tuple[str, str]]:
    """获取线型和标记的组合循环
    
    Args:
        n: 返回的组合数量（None 则返回全部）
        
    Returns:
        [(linestyle, marker), ...] 列表
    """
    linestyles = get_linestyles()
    markers = get_markers()
    cycle = [(ls, mk) for ls in linestyles for mk in markers]
    if n is not None:
        return cycle[:n]
    return cycle

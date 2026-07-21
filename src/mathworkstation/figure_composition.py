from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

plt.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei", "Noto Sans SC", "DejaVu Sans"]
plt.rcParams["axes.unicode_minus"] = False

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .figure_registry import FigureRegistry
from .io_utils import now_iso


class FigureCompositionService:
    """Creates deterministic, publication-oriented overview figures.

    The visual staging follows the referenced Draw.io Scientific Illustrator idea:
    named logical regions, editable-style primitives, explicit arrows, and a reviewable
    source record. Raster and vector exports remain ordinary case artifacts.
    """

    def __init__(self, cases: CaseManager, artifacts: ArtifactRegistry, figures: FigureRegistry) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.figures = figures

    def create_workflow_overview(
        self,
        case_id: str,
        upstream_artifact_ids: list[str],
        run_id: str | None = None,
    ) -> dict[str, Any]:
        root = self.cases.case_root(case_id)
        directory = root / "figures" / "final"
        directory.mkdir(parents=True, exist_ok=True)
        png_path = directory / "modeling-workflow-overview.png"
        svg_path = directory / "modeling-workflow-overview.svg"
        steps = [
            ("题目与数据", "问题定义\n来源快照与质量检查", "#E8F1FB"),
            ("探索分析", "分布、相关性\n异常与变量筛选", "#EAF6EE"),
            ("模型构建", "基线、候选模型\n目标函数与假设", "#FFF4D6"),
            ("实验验证", "交叉验证、误差\n敏感性与稳健性", "#FCE8E6"),
            ("证据论文", "图表、结论\n摘要与可复现导出", "#F0EAF8"),
        ]
        figure, axis = plt.subplots(figsize=(16, 4.6), dpi=180)
        axis.set_xlim(0, len(steps) * 3.0)
        axis.set_ylim(0, 4.6)
        axis.axis("off")
        for index, (title, detail, color) in enumerate(steps):
            x = index * 3.0 + 0.25
            box = FancyBboxPatch(
                (x, 1.35), 2.35, 1.85,
                boxstyle="round,pad=0.04,rounding_size=0.08",
                linewidth=1.3, edgecolor="#263238", facecolor=color,
            )
            axis.add_patch(box)
            axis.text(x + 1.175, 2.72, title, ha="center", va="center", fontsize=13, fontweight="bold", color="#17202A")
            axis.text(x + 1.175, 1.95, detail, ha="center", va="center", fontsize=10, linespacing=1.5, color="#37474F")
            if index < len(steps) - 1:
                axis.annotate(
                    "", xy=(x + 2.78, 2.28), xytext=(x + 2.37, 2.28),
                    arrowprops={"arrowstyle": "-|>", "lw": 1.5, "color": "#455A64"},
                )
        axis.text(0.25, 0.62, "每一步均产生可追溯证据；异常进入审查/恢复分支，不静默跳过。", fontsize=11, color="#455A64")
        axis.text(0.25, 4.15, "数学建模研究工作流", fontsize=18, fontweight="bold", color="#102A43")
        figure.tight_layout()
        figure.savefig(png_path, dpi=240, bbox_inches="tight", facecolor="white")
        figure.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
        plt.close(figure)
        png_figure = self.figures.register(
            case_id,
            png_path.relative_to(root).as_posix(),
            "数学建模研究工作流总览",
            upstream_artifact_ids,
            "mathworkstation.figure_composition:workflow_overview",
            {"format": ["png", "svg"], "dpi": 240, "generated_at": now_iso()},
            run_id,
        )
        svg_artifact = self.artifacts.register_existing(
            case_id,
            svg_path.relative_to(root).as_posix(),
            "scientific_workflow_vector",
            "python",
            run_id=run_id,
            upstream=[png_figure["artifact_id"], *upstream_artifact_ids],
        )
        return {"figure": png_figure, "svg_artifact_id": svg_artifact["artifact_id"]}

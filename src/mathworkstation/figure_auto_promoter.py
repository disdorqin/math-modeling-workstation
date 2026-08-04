"""图表自动晋升模块

paper_ready 审批通过后，自动将 DRAFT 数据图晋升为 FINAL 并嵌入对应章节。
复用既有 FigureRegistry.promote_to_paper 机制。
"""

from __future__ import annotations

from typing import Any

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .figure_registry import FigureRegistry
from .io_utils import now_iso
from .plot_style import classify_figure


class FigureAutoPromoter:
    """自动晋升 DRAFT 图表到 FINAL

    在 paper_ready 审批通过后调用，将所有符合证据门的 DRAFT 图表
    根据标题和关键词分类到对应论文章节，并晋升为 FINAL 状态。
    """

    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        figures: FigureRegistry,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.figures = figures

    def promote_all_draft_figures(
        self,
        case_id: str,
        approval_artifact_id: str,
        approved_by: str = "system",
        note: str = "auto-promoted after paper_ready approval",
    ) -> dict[str, Any]:
        """将所有 DRAFT 图表晋升为 FINAL

        Args:
            case_id: 案例 ID
            approval_artifact_id: paper_ready_approval 产物 ID
            approved_by: 审批人（默认 system）
            note: 审批备注

        Returns:
            晋升结果字典，包含 promoted_figures 和 skipped_figures
        """
        approval = self.artifacts.get(case_id, approval_artifact_id)
        if approval["artifact_type"] != "paper_ready_approval":
            raise ValueError(
                f"approval artifact is not a paper_ready_approval: {approval_artifact_id}"
            )

        all_figures = self.figures.list_figures(case_id)
        draft_figures = [f for f in all_figures if f["status"] == "DRAFT"]

        promoted: list[dict[str, Any]] = []
        skipped: list[dict[str, Any]] = []

        for figure in draft_figures:
            try:
                promoted_figure = self.figures.promote(
                    case_id,
                    figure["figure_id"],
                    approval_artifact_id,
                    approved_by,
                    note,
                )
                promoted.append(promoted_figure)
            except Exception as e:
                skipped.append({
                    "figure_id": figure["figure_id"],
                    "title": figure.get("title", ""),
                    "reason": str(e),
                })

        return {
            "case_id": case_id,
            "approval_artifact_id": approval_artifact_id,
            "total_figures": len(all_figures),
            "draft_figures": len(draft_figures),
            "promoted_count": len(promoted),
            "skipped_count": len(skipped),
            "promoted_figures": promoted,
            "skipped_figures": skipped,
            "promoted_at": now_iso(),
        }

    def promote_figures_by_category(
        self,
        case_id: str,
        approval_artifact_id: str,
        approved_by: str = "system",
        note: str = "auto-promoted by category after paper_ready",
    ) -> dict[str, Any]:
        """按分类晋升 DRAFT 图表

        根据图表标题和关键词自动分类，将 DRAFT 图表晋升并关联到对应论文章节。

        Args:
            case_id: 案例 ID
            approval_artifact_id: paper_ready_approval 产物 ID
            approved_by: 审批人
            note: 审批备注

        Returns:
            按章节分类的晋升结果
        """
        approval = self.artifacts.get(case_id, approval_artifact_id)
        if approval["artifact_type"] != "paper_ready_approval":
            raise ValueError(
                f"approval artifact is not a paper_ready_approval: {approval_artifact_id}"
            )

        all_figures = self.figures.list_figures(case_id)
        draft_figures = [f for f in all_figures if f["status"] == "DRAFT"]

        section_figures: dict[str, list[dict[str, Any]]] = {
            "data_analysis": [],
            "results": [],
            "sensitivity": [],
            "overview": [],
            "uncategorized": [],
        }

        for figure in draft_figures:
            title = figure.get("title", "")
            source_script = figure.get("source_script", "")
            keywords = [source_script] if source_script else []
            section = classify_figure(title, keywords)
            if section and section in section_figures:
                section_figures[section].append(figure)
            else:
                section_figures["uncategorized"].append(figure)

        promoted_by_section: dict[str, list[dict[str, Any]]] = {}
        skipped: list[dict[str, Any]] = []

        for section, figures in section_figures.items():
            promoted_by_section[section] = []
            for figure in figures:
                try:
                    promoted_figure = self.figures.promote(
                        case_id,
                        figure["figure_id"],
                        approval_artifact_id,
                        approved_by,
                        f"{note} -> {section}",
                    )
                    promoted_by_section[section].append(promoted_figure)
                except Exception as e:
                    skipped.append({
                        "figure_id": figure["figure_id"],
                        "title": figure.get("title", ""),
                        "section": section,
                        "reason": str(e),
                    })

        return {
            "case_id": case_id,
            "approval_artifact_id": approval_artifact_id,
            "total_figures": len(all_figures),
            "draft_figures": len(draft_figures),
            "promoted_by_section": {
                section: len(figures) for section, figures in promoted_by_section.items()
            },
            "promoted_figures": promoted_by_section,
            "skipped_figures": skipped,
            "promoted_at": now_iso(),
        }

    def get_promotion_summary(self, case_id: str) -> dict[str, Any]:
        """获取图表晋升摘要

        Args:
            case_id: 案例 ID

        Returns:
            包含各状态图表统计的摘要
        """
        all_figures = self.figures.list_figures(case_id)
        status_count: dict[str, int] = {}
        for figure in all_figures:
            status = figure.get("status", "UNKNOWN")
            status_count[status] = status_count.get(status, 0) + 1

        return {
            "case_id": case_id,
            "total_figures": len(all_figures),
            "status_count": status_count,
            "has_paper_ready_approval": self._has_approval(case_id),
        }

    def _has_approval(self, case_id: str) -> bool:
        """检查是否存在 paper_ready_approval"""
        root = self.cases.case_root(case_id)
        approval_dir = root / "review" / "reproducibility"
        if not approval_dir.exists():
            return False
        for path in approval_dir.glob("paper-ready-*.json"):
            try:
                approval = self.artifacts.get(case_id, path.stem)
                if approval.get("artifact_type") == "paper_ready_approval":
                    return True
            except (KeyError, Exception):
                continue
        return False

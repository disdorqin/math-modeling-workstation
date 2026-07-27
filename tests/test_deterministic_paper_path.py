"""Regression tests for the deterministic (no-API) problem-to-submission path.

Each test here pins a defect found while driving a real case end to end on
2026-07-26; see `docs/端到端实跑报告-2026-07-26.md` for the run record.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mathworkstation.paper_consistency import MATH_SPAN, NUMBER
from mathworkstation.stage_service import _render_final_manuscript
from mathworkstation.submission import (
    PROFILES,
    SubmissionService,
    markdown_to_latex,
)
from mathworkstation.workflow import (
    NodeDefinition,
    NodeStatus,
    WorkflowController,
    WorkflowGraph,
    default_workflow_graph,
)


def _scan_numbers(text: str) -> list[str]:
    return NUMBER.findall(MATH_SPAN.sub(" ", text))


class TestNumberScanIgnoresMath:
    """Math notation is not an empirical number and must not be flagged."""

    def test_inline_and_display_math_are_ignored(self) -> None:
        text = r"惩罚项为 $\lVert\beta\rVert_2^2$ 与 $L_1$，损失 $$\frac{1}{2n}\sum_i (y_i-\hat y_i)^2$$"
        assert _scan_numbers(text) == []

    def test_equation_environment_is_ignored(self) -> None:
        text = r"\begin{equation}x_1 + x_2 = 4\end{equation} 共 8 个可行点。"
        assert _scan_numbers(text) == ["8"]

    def test_real_results_are_still_detected(self) -> None:
        assert _scan_numbers("RMSE 为 54.825，波动 4.07%。") == ["54.825", "4.07%"]

    def test_number_next_to_math_is_still_detected(self) -> None:
        assert _scan_numbers(r"以 $L_2$ 正则化得到 RMSE 54.825。") == ["54.825"]


class TestFinalManuscriptRendering:
    """Cited figures must survive into the manuscript, not just be numbered."""

    ASSETS = {
        "figure-aaaaaaaaaaaa": {"path": "figures/draft/target.png", "title": "目标变量分布"},
        "figure-bbbbbbbbbbbb": {"path": "figures/draft/cv.png", "title": "候选模型比较"},
    }

    def test_internal_anchors_are_removed(self) -> None:
        rendered = _render_final_manuscript(
            "结论稳健 [claim-0123456789ab]。", {}
        )
        assert "claim-" not in rendered

    def test_figure_citation_is_numbered_and_embedded(self) -> None:
        source = "分布见图 [figure-aaaaaaaaaaaa]。\n\n下一段。"
        rendered = _render_final_manuscript(source, self.ASSETS)
        assert "（图 1）" in rendered
        assert "![图 1 目标变量分布](figures/draft/target.png)" in rendered

    def test_each_figure_is_embedded_once(self) -> None:
        source = (
            "求解见图 [figure-bbbbbbbbbbbb]。\n\n"
            "结果同样见图 [figure-bbbbbbbbbbbb]。\n\n"
        )
        rendered = _render_final_manuscript(source, self.ASSETS)
        assert rendered.count("![图 1 候选模型比较]") == 1
        assert rendered.count("（图 1）") == 2

    def test_numbering_is_keyed_by_full_figure_id(self) -> None:
        """The numbering map must join against the figure registry."""
        source = "见图 [figure-aaaaaaaaaaaa] 与图 [figure-bbbbbbbbbbbb]。"
        rendered = _render_final_manuscript(source, self.ASSETS)
        assert "figures/draft/target.png" in rendered
        assert "figures/draft/cv.png" in rendered

    def test_unknown_figure_is_numbered_but_not_embedded(self) -> None:
        rendered = _render_final_manuscript("见图 [figure-cccccccccccc]。", self.ASSETS)
        assert "（图 1）" in rendered
        assert "![" not in rendered

    def test_missing_assets_argument_keeps_legacy_behaviour(self) -> None:
        rendered = _render_final_manuscript("见图 [figure-aaaaaaaaaaaa]。")
        assert "（图 1）" in rendered
        assert "![" not in rendered


class TestLatexFigureConversion:
    def test_markdown_image_becomes_includegraphics(self) -> None:
        latex = markdown_to_latex(
            "# 标题\n\n![图 1 目标变量分布](figures/draft/target.png)\n",
            PROFILES["CUMCM"],
        )
        assert "\\includegraphics[width=0.85\\textwidth]{figures/draft/target.png}" in latex
        assert "\\caption{图 1 目标变量分布}" in latex
        assert "\\begin{figure}[htbp]" in latex


class TestPreflightFigureResolution:
    """Figure paths are POSIX in the registry and must resolve on every platform."""

    def _service(self, tmp_path: Path) -> tuple[SubmissionService, str]:
        class _Cases:
            def case_root(self, case_id: str) -> Path:
                return tmp_path

        return SubmissionService(_Cases(), None), "case"  # type: ignore[arg-type]

    def test_existing_nested_figure_passes(self, tmp_path: Path) -> None:
        target = tmp_path / "figures" / "draft" / "target.png"
        target.parent.mkdir(parents=True)
        target.write_bytes(b"png")
        service, case_id = self._service(tmp_path)
        latex = "\\includegraphics[width=0.85\\textwidth]{figures/draft/target.png}"
        report = service.preflight(case_id, "摘要 模型建立 结果分析 结论", latex, PROFILES["CUMCM"])
        assert report["gate"] == "PASS"

    def test_missing_figure_still_blocks(self, tmp_path: Path) -> None:
        service, case_id = self._service(tmp_path)
        latex = "\\includegraphics{figures/draft/absent.png}"
        report = service.preflight(case_id, "摘要 模型建立 结果分析 结论", latex, PROFILES["CUMCM"])
        assert report["gate"] == "BLOCK"
        assert any(item["code"] == "FIGURE_MISSING" for item in report["findings"])


class TestDegradeTransition:
    """An optional branch can be omitted by decision without blocking the DAG."""

    def _controller(self) -> WorkflowController:
        return WorkflowController(
            WorkflowGraph(
                [
                    NodeDefinition("root"),
                    NodeDefinition("optional", ("root",), may_degrade=True),
                    NodeDefinition("required", ("root",)),
                    NodeDefinition("tail", ("optional",)),
                ]
            )
        )

    def test_degraded_node_unblocks_descendants(self) -> None:
        controller = self._controller()
        controller.start("root", "run-1")
        controller.succeed("root")
        controller.degrade("optional", "human", "no API available")
        assert controller.runtimes["optional"].status is NodeStatus.DEGRADED
        assert controller.unmet_dependencies("tail") == []

    def test_degrade_records_the_decision(self) -> None:
        controller = self._controller()
        controller.degrade("optional", "reviewer", "branch intentionally omitted")
        review = controller.runtimes["optional"].review
        assert review is not None
        assert review["approved_by"] == "reviewer"
        assert review["reason"] == "branch intentionally omitted"

    def test_degrade_requires_a_reason(self) -> None:
        with pytest.raises(ValueError):
            self._controller().degrade("optional", "human", "   ")

    def test_nodes_without_may_degrade_are_rejected(self) -> None:
        from mathworkstation.errors import InvalidTransitionError

        with pytest.raises(InvalidTransitionError):
            self._controller().degrade("required", "human", "reason")

    def test_refinement_loop_is_degradable(self) -> None:
        """The LLM refinement loop must not be a hard requirement for export."""
        graph = default_workflow_graph()
        assert graph.definitions["refinement_loop"].may_degrade is True

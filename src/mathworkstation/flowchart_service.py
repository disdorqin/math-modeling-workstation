from __future__ import annotations

import json
from typing import Any

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .figure_composition import FigureCompositionService
from .figure_registry import FigureRegistry
from .io_utils import atomic_write_json, atomic_write_text, now_iso
from .llm.image_service import CaseImageService


class FlowchartService:
    """Optional AI-assisted flowchart branch kept outside data/model execution."""

    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        figures: FigureRegistry,
        composition: FigureCompositionService,
        image_service: CaseImageService | None = None,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.figures = figures
        self.composition = composition
        self.image_service = image_service

    def create(
        self,
        case_id: str,
        upstream_artifact_ids: list[str],
        run_id: str | None = None,
        model: str | None = None,
    ) -> dict[str, Any]:
        root = self.cases.case_root(case_id)
        design = {
            "schema_version": 1,
            "title": "数学建模研究工作流",
            "nodes": [
                {"id": "input", "label": "题目与数据", "detail": "问题定义、来源快照、质量检查"},
                {"id": "eda", "label": "探索分析", "detail": "分布、相关性、异常与变量筛选"},
                {"id": "model", "label": "模型构建", "detail": "基线、候选模型、目标函数与假设"},
                {"id": "experiment", "label": "实验验证", "detail": "交叉验证、误差、敏感性与稳健性"},
                {"id": "paper", "label": "证据论文", "detail": "图表、摘要、结论与可复现导出"},
            ],
            "edges": [["input", "eda"], ["eda", "model"], ["model", "experiment"], ["experiment", "paper"]],
            "style": {"direction": "left-to-right", "background": "white", "editable": True},
            "upstream_artifact_ids": upstream_artifact_ids,
            "generated_at": now_iso(),
        }
        design_path = root / "figures" / "final" / "workflow-design.json"
        atomic_write_json(design_path, design)
        design_artifact = self.artifacts.register_existing(
            case_id,
            design_path.relative_to(root).as_posix(),
            "flowchart_design",
            "python",
            run_id=run_id,
            upstream=upstream_artifact_ids,
        )
        prompt = _drawio_prompt(design)
        prompt_path = root / "figures" / "final" / "drawio-flowchart-prompt.md"
        atomic_write_text(prompt_path, prompt)
        prompt_artifact = self.artifacts.register_existing(
            case_id,
            prompt_path.relative_to(root).as_posix(),
            "drawio_flowchart_prompt",
            "python",
            run_id=run_id,
            upstream=[design_artifact["artifact_id"]],
        )
        deterministic = self.composition.create_workflow_overview(
            case_id, [*upstream_artifact_ids, design_artifact["artifact_id"]], run_id
        )
        result: dict[str, Any] = {
            "design": design,
            "design_artifact_id": design_artifact["artifact_id"],
            "prompt_artifact_id": prompt_artifact["artifact_id"],
            "figure": deterministic["figure"],
            "svg_artifact_id": deterministic["svg_artifact_id"],
            "ai_reference": None,
        }
        if self.image_service is not None:
            try:
                result["ai_reference"] = self.image_service.generate(
                    case_id,
                    "流程图视觉参考",
                    _image_prompt(design),
                    source_artifact_ids=[design_artifact["artifact_id"], *upstream_artifact_ids],
                    model=model,
                    size="1536x1024",
                )
            except Exception as error:
                result["ai_reference"] = {"status": "DEGRADED", "error": f"{type(error).__name__}: {error}"}
        return result


def _image_prompt(design: dict[str, Any]) -> str:
    nodes = " -> ".join(node["label"] for node in design["nodes"])
    return (
        "Create a clean academic mathematical-modeling workflow diagram as a visual reference for an editable draw.io redraw. "
        "Use five left-to-right stages with clear arrows, restrained blue/green/gold/red/purple accents, white background, "
        "high contrast, generous spacing, no decorative 3D effects, no fake data, no logos, and minimal readable Chinese labels. "
        f"Stages: {nodes}. Keep the composition suitable for a Chinese competition paper."
    )


def _drawio_prompt(design: dict[str, Any]) -> str:
    return (
        "# Draw.io Scientific Illustrator Task\n\n"
        "Use the visible draw.io graph API to recreate this workflow as editable primitives. Do not use OS mouse/keyboard automation.\n\n"
        f"```json\n{json.dumps(design, ensure_ascii=False, indent=2)}\n```\n\n"
        "Requirements: left-to-right layout, orthogonal arrows, editable labels, white background, consistent typography, "
        "export both `.drawio` and a 2000px PNG, then visually inspect spacing and text overflow.\n"
    )

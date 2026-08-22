from __future__ import annotations

import shutil
import subprocess
import textwrap
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .editable_figure_pipeline import EditableFigurePipeline
from .io_utils import atomic_write_json, atomic_write_text, now_iso
from .paper_humanization import PaperHumanizationAdapter
from .plot_style import get_profile_colors, get_publication_figsize, publication_context
from .visual_intent import (
    FigureIntent,
    VisualIntentRouter,
    build_editable_redraw_job,
    build_ppt_mcp_handoff,
    build_visual_brief,
)


FlowchartStage = Literal["DATA", "ANALYSIS", "MODEL", "VALIDATION", "DECISION"]


class FlowchartNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    node_id: str
    label: str
    detail: str = ""
    role: Literal["ROOT", "RESEARCH", "SYNTHESIS"]
    stage: FlowchartStage
    task_family: str = ""
    subproblem_id: str = ""


class FlowchartEdge(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: str
    target: str
    relation: str
    kind: Literal["FLOW", "DEPENDENCY"] = "FLOW"


class FlowchartSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    profile_id: str
    direction: Literal["LR", "TB"]
    title: str
    nodes: list[FlowchartNode] = Field(min_length=2)
    edges: list[FlowchartEdge]
    generated_at: str


class ResearchFlowchartRenderer:
    """Render the actual research-question dependency graph as editable sources.

    The renderer is document-only.  Visible nodes come from the NarrativeGraph,
    while DOT and Mermaid sources remain editable hand-off formats for draw.io,
    PowerPoint or human refinement.  Graphviz is preferred for deterministic
    layout; a small matplotlib fallback keeps paper generation functional on
    machines without the ``dot`` executable.
    """

    def __init__(self, cases: Any, artifacts: Any, figures: Any, image_service: Any | None = None) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.figures = figures
        self.image_service = image_service
        self.visual_router = VisualIntentRouter()

    def build_spec(self, graph: Any, *, profile_id: str) -> FlowchartSpec:
        """Build a five-layer technical route instead of a box-per-question DAG.

        Each research question occupies one lane through analysis, modeling,
        validation and decision. Cross-question dependencies are retained as
        secondary edges, but they do not dictate the main layer geometry.
        """

        language = "zh" if profile_id == "CUMCM_C" else "en"
        research_nodes = [node for node in graph.nodes if getattr(node, "role", "") == "RESEARCH"]
        synthesis_nodes = [node for node in graph.nodes if getattr(node, "role", "") == "SYNTHESIS"]
        visible: list[FlowchartNode] = [
            FlowchartNode(
                node_id="data",
                label="赛题数据与业务约束" if language == "zh" else "Problem data and operational constraints",
                detail="口径统一 · 数据边界 · 题意约束" if language == "zh" else "schema · evidence boundary · constraints",
                role="ROOT",
                stage="DATA",
            )
        ]
        edges: list[FlowchartEdge] = []
        research_ids = {node.subproblem_id for node in research_nodes}

        for index, node in enumerate(research_nodes, start=1):
            subproblem_id = str(node.subproblem_id)
            task_family = str(node.task_family)
            method = PaperHumanizationAdapter.method_label(node.method, language=language)
            family = _task_family_label(task_family, language=language)
            analysis_id = f"analysis_{subproblem_id}"
            model_id = f"model_{subproblem_id}"
            validation_id = f"validation_{subproblem_id}"
            decision_id = f"decision_{subproblem_id}"
            analysis_label = _analysis_stage_label(node, index=index, language=language)
            analysis_detail = family
            validation = _validation_stage_label(node, language=language)
            visible.extend(
                [
                    FlowchartNode(
                        node_id=analysis_id,
                        label=_wrap_label(analysis_label, 17 if language == "zh" else 25),
                        detail=analysis_detail,
                        role="RESEARCH",
                        stage="ANALYSIS",
                        task_family=task_family,
                        subproblem_id=subproblem_id,
                    ),
                    FlowchartNode(
                        node_id=model_id,
                        label=_wrap_label(method, 18 if language == "zh" else 26),
                        detail="",
                        role="RESEARCH",
                        stage="MODEL",
                        task_family=task_family,
                        subproblem_id=subproblem_id,
                    ),
                    FlowchartNode(
                        node_id=validation_id,
                        label=_wrap_label(validation, 18 if language == "zh" else 28),
                        detail="通过" if language == "zh" and str(getattr(node, "validation_gate", "")).upper() == "PASS" else "",
                        role="RESEARCH",
                        stage="VALIDATION",
                        task_family=task_family,
                        subproblem_id=subproblem_id,
                    ),
                    FlowchartNode(
                        node_id=decision_id,
                        label=_decision_stage_label(node, index=index, language=language),
                        detail="已验证输出" if language == "zh" else "accepted output",
                        role="RESEARCH",
                        stage="DECISION",
                        task_family=task_family,
                        subproblem_id=subproblem_id,
                    ),
                ]
            )
            edges.extend(
                [
                    FlowchartEdge(source="data", target=analysis_id, relation="数据供给" if language == "zh" else "data"),
                    FlowchartEdge(source=analysis_id, target=model_id, relation="构建" if language == "zh" else "model"),
                    FlowchartEdge(source=model_id, target=validation_id, relation="检验" if language == "zh" else "validate"),
                    FlowchartEdge(source=validation_id, target=decision_id, relation="接受" if language == "zh" else "accept"),
                ]
            )
            for dependency in getattr(node, "dependencies", []) or []:
                if dependency in research_ids:
                    edges.append(
                        FlowchartEdge(
                            source=f"decision_{dependency}",
                            target=analysis_id,
                            relation="承接上问" if language == "zh" else "builds on prior result",
                            kind="DEPENDENCY",
                        )
                    )

        for node in synthesis_nodes:
            dependency_count = len(getattr(node, "dependencies", []) or [])
            synthesis_id = f"synthesis_{node.subproblem_id}"
            visible.append(
                FlowchartNode(
                    node_id=synthesis_id,
                    label=_wrap_label("综合决策与建议" if language == "zh" else "Integrated decision and recommendations", 18 if language == "zh" else 28),
                    detail=_wrap_label(
                        f"{node.title} · 整合{dependency_count}项已验证结果"
                        if language == "zh"
                        else f"{node.title} · {dependency_count} accepted upstream results",
                        22 if language == "zh" else 32,
                    ),
                    role="SYNTHESIS",
                    stage="DECISION",
                    task_family=str(node.task_family),
                    subproblem_id=str(node.subproblem_id),
                )
            )
            for dependency in getattr(node, "dependencies", []) or []:
                source = f"decision_{dependency}" if dependency in research_ids else "data"
                edges.append(
                    FlowchartEdge(
                        source=source,
                        target=synthesis_id,
                        relation="综合" if language == "zh" else "synthesize",
                    )
                )

        return FlowchartSpec(
            profile_id=profile_id,
            direction="TB",
            title="数据—分析—模型—验证—决策技术路线" if language == "zh" else "Data-analysis-model-validation-decision workflow",
            nodes=visible,
            edges=edges,
            generated_at=now_iso(),
        )

    def render(
        self,
        case_id: str,
        graph: Any,
        *,
        profile_id: str,
        upstream_artifact_ids: list[str],
        run_id: str | None = None,
        model_spine: Any | None = None,
    ) -> dict[str, Any]:
        root = self.cases.case_root(case_id)
        directory = root / "figures" / "research_state" / "workflow"
        directory.mkdir(parents=True, exist_ok=True)
        spec = self.build_spec(graph, profile_id=profile_id)

        spec_path = directory / "research-workflow-spec.json"
        mermaid_path = directory / "research-workflow.mmd"
        dot_path = directory / "research-workflow.dot"
        svg_path = directory / "research-workflow.svg"
        png_path = directory / "research-workflow.png"
        atomic_write_json(spec_path, spec.model_dump(mode="json"))
        atomic_write_text(mermaid_path, _to_mermaid(spec))
        atomic_write_text(dot_path, _to_dot(spec))

        spec_artifact = self.artifacts.register_existing(
            case_id,
            spec_path.relative_to(root).as_posix(),
            "research_flowchart_spec",
            "research_flowchart",
            run_id=run_id,
            upstream=upstream_artifact_ids,
        )
        mermaid_artifact = self.artifacts.register_existing(
            case_id,
            mermaid_path.relative_to(root).as_posix(),
            "editable_mermaid_flowchart",
            "research_flowchart",
            run_id=run_id,
            upstream=[spec_artifact["artifact_id"], *upstream_artifact_ids],
        )
        dot_artifact = self.artifacts.register_existing(
            case_id,
            dot_path.relative_to(root).as_posix(),
            "graphviz_dot_flowchart",
            "research_flowchart",
            run_id=run_id,
            upstream=[spec_artifact["artifact_id"], *upstream_artifact_ids],
        )

        intent = FigureIntent(
            intent_id=f"{case_id}:research-workflow",
            kind="workflow_diagram",
            profile_id=profile_id,
            purpose="Explain the accepted question dependency, modeling route, validation, and downstream synthesis without introducing new research claims.",
            source_summary="NarrativeGraph-derived research workflow; labels and dependencies are accepted research-state content.",
            evidence_refs=list(upstream_artifact_ids),
            required_content=[
                "Preserve every research subproblem and the direction of its accepted dependencies.",
                "Make the main modeling route legible before decorative detail.",
                "Visually distinguish foundation, core-model, extension, and synthesis roles when the model-spine payload provides them.",
                "Give core modeling nodes more visual emphasis than inherited extensions; later questions should look downstream when they reuse earlier models or constraints.",
                "Use meaningful academic icons or small visual motifs when they improve at-a-glance comprehension, without turning the figure into decorative clip-art.",
            ],
            forbidden_content=[
                "Do not invent numerical results, algorithms, subproblems, or dependency arrows.",
                "Do not turn every metadata field into a separate box.",
                "Do not copy one fixed palette or layout merely because another competition paper used it.",
            ],
            editable_preferred=True,
            notes=["Generative output is a design candidate; the paper keeps a deterministic vector fallback until review."],
        )
        visual_plan = self.visual_router.route(
            intent,
            capabilities={
                "ai_image": self.image_service is not None,
                "ppt_mcp": False,
                "deterministic_vector": True,
            },
        )
        semantic_payload = _visual_semantic_payload(graph, profile_id=profile_id, model_spine=model_spine)
        intent_path = directory / "research-workflow-visual-intent.json"
        brief_path = directory / "research-workflow-visual-brief.md"
        ppt_handoff_path = directory / "research-workflow-ppt-mcp-handoff.json"
        atomic_write_json(intent_path, visual_plan.model_dump(mode="json"))
        atomic_write_text(brief_path, build_visual_brief(intent, semantic_payload=semantic_payload))
        atomic_write_json(ppt_handoff_path, build_ppt_mcp_handoff(intent, semantic_payload=semantic_payload))
        intent_artifact = self.artifacts.register_existing(
            case_id,
            intent_path.relative_to(root).as_posix(),
            "visual_render_plan",
            "visual_intent_router",
            run_id=run_id,
            upstream=[spec_artifact["artifact_id"], *upstream_artifact_ids],
        )
        brief_artifact = self.artifacts.register_existing(
            case_id,
            brief_path.relative_to(root).as_posix(),
            "visual_design_brief",
            "visual_intent_router",
            run_id=run_id,
            upstream=[intent_artifact["artifact_id"]],
        )
        ppt_handoff_artifact = self.artifacts.register_existing(
            case_id,
            ppt_handoff_path.relative_to(root).as_posix(),
            "ppt_mcp_figure_handoff",
            "visual_intent_router",
            run_id=run_id,
            upstream=[intent_artifact["artifact_id"]],
        )

        ai_candidate = None
        if visual_plan.primary_backend == "ai_image" and self.image_service is not None:
            try:
                ai_candidate = self.image_service.generate(
                    case_id,
                    "研究技术路线 AI 视觉候选",
                    build_visual_brief(intent, semantic_payload=semantic_payload),
                    source_artifact_ids=[brief_artifact["artifact_id"], spec_artifact["artifact_id"], *upstream_artifact_ids],
                    size="1536x1024",
                )
            except Exception as error:  # noqa: BLE001 - preserve deterministic paper fallback
                ai_candidate = {"status": "DEGRADED", "error": f"{type(error).__name__}: {error}"}

        candidate_figure = (ai_candidate.get("figure") or {}) if isinstance(ai_candidate, dict) else {}
        redraw_job_path = directory / "research-workflow-editable-redraw-job.json"
        atomic_write_json(
            redraw_job_path,
            build_editable_redraw_job(
                intent,
                semantic_payload=semantic_payload,
                visual_master=(
                    {
                        "figure_id": candidate_figure.get("figure_id"),
                        "artifact_id": candidate_figure.get("artifact_id"),
                        "path": candidate_figure.get("path"),
                        "title": candidate_figure.get("title"),
                    }
                    if candidate_figure.get("path")
                    else None
                ),
            ),
        )
        redraw_job_artifact = self.artifacts.register_existing(
            case_id,
            redraw_job_path.relative_to(root).as_posix(),
            "editable_figure_redraw_job",
            "visual_intent_router",
            run_id=run_id,
            upstream=[brief_artifact["artifact_id"], ppt_handoff_artifact["artifact_id"]],
            paper_eligible=False,
        )
        editable_pipeline = EditableFigurePipeline().initial(
            intent.intent_id,
            visual_master_artifact_id=str(candidate_figure.get("artifact_id") or ""),
        )
        editable_state_path = directory / "research-workflow-editable-pipeline-state.json"
        atomic_write_json(editable_state_path, editable_pipeline.model_dump(mode="json"))
        editable_state_artifact = self.artifacts.register_existing(
            case_id,
            editable_state_path.relative_to(root).as_posix(),
            "editable_figure_pipeline_state",
            "editable_figure_pipeline",
            run_id=run_id,
            upstream=[redraw_job_artifact["artifact_id"], *([str(candidate_figure.get("artifact_id"))] if candidate_figure.get("artifact_id") else [])],
            paper_eligible=False,
        )

        if profile_id == "CUMCM_C" and model_spine is not None:
            self._render_model_spine_roadmap(
                graph,
                model_spine,
                profile_id=profile_id,
                svg_path=svg_path,
                png_path=png_path,
            )
            backend = "matplotlib_model_spine_v1"
        else:
            backend = self._render_graphviz(dot_path, svg_path, png_path)
            if backend is None:
                self._render_matplotlib_fallback(spec, svg_path, png_path)
                backend = "matplotlib_fallback"

        vector_artifact = self.artifacts.register_existing(
            case_id,
            svg_path.relative_to(root).as_posix(),
            "scientific_workflow_vector",
            "research_flowchart",
            run_id=run_id,
            upstream=[dot_artifact["artifact_id"], mermaid_artifact["artifact_id"], intent_artifact["artifact_id"]],
        )
        figure = self.figures.register(
            case_id,
            png_path.relative_to(root).as_posix(),
            spec.title,
            [*upstream_artifact_ids, spec_artifact["artifact_id"]],
            "mathworkstation.research_flowchart:ResearchFlowchartRenderer",
            {
                "semantic_kind": "research_workflow",
                "purpose": "show the actual research-question dependency structure and final synthesis route",
                "subproblem_ids": [node.subproblem_id for node in graph.nodes],
                "profile_id": profile_id,
                "backend": backend,
                "visual_primary_backend": visual_plan.primary_backend,
                "visual_publication_backend": visual_plan.publication_backend,
                "visual_review_required": visual_plan.visual_review_required,
                "ai_candidate_figure_id": (
                    (ai_candidate.get("figure") or {}).get("figure_id")
                    if isinstance(ai_candidate, dict)
                    else None
                ),
                "editable_sources": {
                    "mermaid_artifact_id": mermaid_artifact["artifact_id"],
                    "dot_artifact_id": dot_artifact["artifact_id"],
                    "svg_artifact_id": vector_artifact["artifact_id"],
                    "visual_brief_artifact_id": brief_artifact["artifact_id"],
                    "ppt_mcp_handoff_artifact_id": ppt_handoff_artifact["artifact_id"],
                    "editable_redraw_job_artifact_id": redraw_job_artifact["artifact_id"],
                    "editable_pipeline_state_artifact_id": editable_state_artifact["artifact_id"],
                },
                "vector_source": True,
                "dpi": 600,
                "caption_first": True,
                "workflow_node_count": len(spec.nodes),
                "workflow_edge_count": len(spec.edges),
                "argument_phase": "overview",
            },
            run_id=run_id,
            status="FINAL",
        )
        return {
            "spec": spec,
            "figure": figure,
            "spec_artifact": spec_artifact,
            "mermaid_artifact": mermaid_artifact,
            "dot_artifact": dot_artifact,
            "svg_artifact": vector_artifact,
            "visual_plan": visual_plan,
            "visual_intent_artifact": intent_artifact,
            "visual_brief_artifact": brief_artifact,
            "ppt_mcp_handoff_artifact": ppt_handoff_artifact,
            "editable_redraw_job_artifact": redraw_job_artifact,
            "editable_pipeline_state": editable_pipeline,
            "editable_pipeline_state_artifact": editable_state_artifact,
            "ai_candidate": ai_candidate,
            "backend": backend,
        }

    def _render_graphviz(self, dot_path: Path, svg_path: Path, png_path: Path) -> str | None:
        executable = shutil.which("dot")
        if not executable:
            return None
        try:
            subprocess.run([executable, "-Tsvg", str(dot_path), "-o", str(svg_path)], check=True, capture_output=True, timeout=30)
            subprocess.run([executable, "-Tpng", "-Gdpi=600", str(dot_path), "-o", str(png_path)], check=True, capture_output=True, timeout=30)
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None
        return "graphviz_dot"

    def _render_model_spine_roadmap(
        self,
        graph: Any,
        model_spine: Any,
        *,
        profile_id: str,
        svg_path: Path,
        png_path: Path,
    ) -> None:
        """Render a paper-facing roadmap from the inferred whole-problem model spine.

        Unlike the editable Mermaid/DOT sources, this deterministic fallback is
        not a box-per-metadata DAG.  It compresses the accepted research state
        into five semantic layers and gives the inferred core model more visual
        weight.  GPT Image / PowerPoint agents remain free to create a richer
        candidate from the same semantic payload.
        """

        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

        language = "zh" if profile_id == "CUMCM_C" else "en"
        graph_nodes = {str(node.subproblem_id): node for node in graph.nodes}
        spine_nodes = list(getattr(model_spine, "nodes", []) or [])
        role_groups = {
            "FOUNDATION": [item for item in spine_nodes if getattr(item, "role", "") == "FOUNDATION"],
            "CORE_MODEL": [item for item in spine_nodes if getattr(item, "role", "") == "CORE_MODEL"],
            "EXTENSION": [item for item in spine_nodes if getattr(item, "role", "") == "EXTENSION"],
            "INDEPENDENT_MODEL": [item for item in spine_nodes if getattr(item, "role", "") == "INDEPENDENT_MODEL"],
            "SYNTHESIS": [item for item in spine_nodes if getattr(item, "role", "") == "SYNTHESIS"],
        }
        # Independent models sit beside extensions unless they are the only
        # substantive model layer; this avoids inventing an extra universal row.
        extension_nodes = [*role_groups["EXTENSION"], *role_groups["INDEPENDENT_MODEL"]]
        layers: list[tuple[str, str, list[Any]]] = [
            ("DATA", "数据基础" if language == "zh" else "Data foundation", []),
        ]
        if role_groups["FOUNDATION"]:
            layers.append(("FOUNDATION", "规律与分析" if language == "zh" else "Structure & analysis", role_groups["FOUNDATION"]))
        if role_groups["CORE_MODEL"]:
            layers.append(("CORE_MODEL", "核心建模" if language == "zh" else "Core modeling", role_groups["CORE_MODEL"]))
        if extension_nodes:
            layers.append(("EXTENSION", "模型扩展" if language == "zh" else "Model extension", extension_nodes))
        if role_groups["SYNTHESIS"]:
            layers.append(("SYNTHESIS", "综合决策" if language == "zh" else "Synthesis & decision", role_groups["SYNTHESIS"]))

        palette = get_profile_colors(profile_id)
        color_indices = [2, 6, 0, 1, 4, 3]
        layer_colors = [palette[index % len(palette)] for index in color_indices]
        row_height = 0.14
        row_gap = 0.028
        total_height = len(layers) * row_height + (len(layers) - 1) * row_gap
        top = 0.93
        bottom = max(0.04, top - total_height)

        with publication_context(profile_id, chart_type="workflow"):
            figure, axis = plt.subplots(figsize=(12.0, max(5.7, 1.15 * len(layers))))
            axis.set_xlim(0, 1)
            axis.set_ylim(0, 1)
            axis.axis("off")

            card_positions: dict[str, tuple[float, float, float, float]] = {}
            row_centers: list[float] = []
            for layer_index, (role, label, items) in enumerate(layers):
                y_top = top - layer_index * (row_height + row_gap)
                y = y_top - row_height
                row_centers.append(y + row_height / 2.0)
                accent = layer_colors[layer_index % len(layer_colors)]
                face = _mix_with_white(accent, 0.90 if role != "CORE_MODEL" else 0.86)

                label_box = FancyBboxPatch(
                    (0.025, y),
                    0.155,
                    row_height,
                    boxstyle="round,pad=0.008,rounding_size=0.014",
                    linewidth=1.0,
                    edgecolor=accent,
                    facecolor=face,
                )
                axis.add_patch(label_box)
                axis.text(0.047, y + row_height * 0.72, str(layer_index + 1), ha="center", va="center", fontsize=12.0, fontweight="bold", color=accent)
                axis.text(0.105, y + row_height * 0.50, label, ha="center", va="center", fontsize=10.2, fontweight="bold", color=accent)

                content_box = FancyBboxPatch(
                    (0.195, y),
                    0.78,
                    row_height,
                    boxstyle="round,pad=0.008,rounding_size=0.014",
                    linewidth=1.0 if role == "CORE_MODEL" else 0.8,
                    edgecolor=accent,
                    facecolor=_mix_with_white(accent, 0.96),
                )
                axis.add_patch(content_box)

                if role == "DATA":
                    data_label = (
                        "赛题数据  ·  业务语境  ·  题意约束  ·  统一数据口径"
                        if language == "zh"
                        else "Problem data  ·  domain context  ·  prompt constraints  ·  unified data contract"
                    )
                    axis.text(0.585, y + row_height / 2.0, data_label, ha="center", va="center", fontsize=9.2, fontweight="semibold", color="#374151")
                    continue

                count = max(1, len(items))
                inner_left, inner_right = 0.215, 0.955
                gap = 0.018
                width = (inner_right - inner_left - gap * (count - 1)) / count
                for item_index, spine_node in enumerate(items):
                    sid = str(spine_node.subproblem_id)
                    node = graph_nodes.get(sid)
                    if node is None:
                        continue
                    x = inner_left + item_index * (width + gap)
                    card_y = y + 0.019
                    card_h = row_height - 0.038
                    card_face = _mix_with_white(accent, 0.91 if role == "CORE_MODEL" else 0.95)
                    card = FancyBboxPatch(
                        (x, card_y),
                        width,
                        card_h,
                        boxstyle="round,pad=0.006,rounding_size=0.012",
                        linewidth=1.1 if role == "CORE_MODEL" else 0.75,
                        edgecolor=accent,
                        facecolor=card_face,
                    )
                    axis.add_patch(card)
                    q_index = _research_question_index(graph, sid)
                    role_tag = {
                        "FOUNDATION": "分析基础",
                        "CORE_MODEL": "核心模型",
                        "EXTENSION": "继承扩展",
                        "INDEPENDENT_MODEL": "独立模型",
                        "SYNTHESIS": "综合输出",
                    }.get(str(spine_node.role), str(spine_node.role)) if language == "zh" else str(spine_node.role).replace("_", " ").title()
                    title = _compact_visual_text(str(getattr(node, "title", "") or ""), 24 if language == "zh" else 42)
                    method = PaperHumanizationAdapter.method_label(str(getattr(node, "method", "") or ""), language=language)
                    method = _compact_visual_text(method, 25 if language == "zh" else 44)
                    axis.text(x + 0.012, card_y + card_h * 0.78, f"Q{q_index} · {role_tag}", ha="left", va="center", fontsize=8.4, fontweight="bold", color=accent)
                    axis.text(x + 0.012, card_y + card_h * 0.50, title, ha="left", va="center", fontsize=8.2, color="#1F2937")
                    if method:
                        axis.text(x + 0.012, card_y + card_h * 0.22, method, ha="left", va="center", fontsize=7.1, color="#5B6470")
                    card_positions[sid] = (x, card_y, width, card_h)

            # Main vertical reading route: soft arrows between semantic layers.
            for source_y, target_y in zip(row_centers[:-1], row_centers[1:]):
                arrow = FancyArrowPatch(
                    (0.185, source_y - row_height * 0.50),
                    (0.185, target_y + row_height * 0.50),
                    arrowstyle="-|>",
                    mutation_scale=10,
                    linewidth=1.0,
                    color="#8A929A",
                )
                axis.add_patch(arrow)

            # Cross-question inheritance is secondary and therefore drawn as a
            # thin dashed connector rather than making the entire figure a DAG.
            for spine_node in spine_nodes:
                target_sid = str(spine_node.subproblem_id)
                target_box = card_positions.get(target_sid)
                if target_box is None:
                    continue
                for source_sid in getattr(spine_node, "inherits_from", []) or []:
                    source_box = card_positions.get(str(source_sid))
                    if source_box is None:
                        continue
                    sx, sy, sw, sh = source_box
                    tx, ty, tw, th = target_box
                    start = (sx + sw * 0.50, sy)
                    end = (tx + tw * 0.50, ty + th)
                    arrow = FancyArrowPatch(
                        start,
                        end,
                        arrowstyle="-|>",
                        mutation_scale=8,
                        linewidth=0.8,
                        linestyle=(0, (3, 2)),
                        color="#7C8792",
                        connectionstyle="arc3,rad=0.05",
                    )
                    axis.add_patch(arrow)

            axis.text(
                0.585,
                bottom - 0.012,
                "模型主线：由数据认识到核心模型，再以约束/场景扩展形成决策"
                if language == "zh"
                else "Modeling spine: data understanding → core model → constrained/scenario extension → decision",
                ha="center",
                va="top",
                fontsize=7.5,
                color="#68737D",
            )
            figure.tight_layout(pad=0.45)
            figure.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
            figure.savefig(png_path, dpi=600, bbox_inches="tight", facecolor="white")
            plt.close(figure)

    def _render_matplotlib_fallback(self, spec: FlowchartSpec, svg_path: Path, png_path: Path) -> None:
        import matplotlib.pyplot as plt
        from matplotlib.patches import FancyBboxPatch

        levels = _node_levels(spec)
        max_level = max(levels.values()) if levels else 0
        by_level: dict[int, list[FlowchartNode]] = {}
        for node in spec.nodes:
            by_level.setdefault(levels.get(node.node_id, 0), []).append(node)
        profile = spec.profile_id if spec.profile_id in {"CUMCM_C", "MCM_C", "SCI_CLEAN"} else "SCI_CLEAN"
        with publication_context(profile, chart_type="workflow") as style:
            width, height = get_publication_figsize(profile, "workflow")
            figure, axis = plt.subplots(figsize=(width, max(height, 1.7 * max(len(value) for value in by_level.values()))))
            axis.axis("off")
            positions: dict[str, tuple[float, float]] = {}
            palette = style["palette"]
            stage_colors = _flowchart_stage_colors(palette)
            for level in sorted(by_level):
                nodes = by_level[level]
                for index, node in enumerate(nodes):
                    x = level / max(1, max_level)
                    y = 1.0 - (index + 1) / (len(nodes) + 1)
                    positions[node.node_id] = (x, y)
                    color = stage_colors.get(node.stage, "#E9EEF2")
                    box = FancyBboxPatch(
                        (x - 0.09, y - 0.075),
                        0.18,
                        0.15,
                        boxstyle="round,pad=0.015,rounding_size=0.015",
                        linewidth=0.9,
                        edgecolor="#4B5563",
                        facecolor=color,
                        alpha=0.18,
                    )
                    axis.add_patch(box)
                    axis.text(x, y + 0.018, node.label, ha="center", va="center", fontsize=8.2, fontweight="semibold")
                    if node.detail:
                        axis.text(x, y - 0.04, node.detail, ha="center", va="center", fontsize=6.9, color="#4B5563")
            for edge in spec.edges:
                if edge.source in positions and edge.target in positions:
                    source = positions[edge.source]
                    target = positions[edge.target]
                    axis.annotate(
                        "",
                        xy=target,
                        xytext=source,
                        arrowprops={"arrowstyle": "-|>", "lw": 0.9, "color": "#6B7280", "shrinkA": 25, "shrinkB": 25},
                    )
                    midpoint = ((source[0] + target[0]) / 2.0, (source[1] + target[1]) / 2.0)
                    if edge.kind == "DEPENDENCY":
                        axis.text(
                            midpoint[0],
                            midpoint[1] + 0.025,
                            edge.relation,
                            ha="center",
                            va="center",
                            fontsize=6.2,
                            color="#68737D",
                        )
            axis.set_xlim(-0.15, 1.15)
            axis.set_ylim(-0.05, 1.05)
            figure.tight_layout(pad=0.65)
            figure.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
            figure.savefig(png_path, dpi=600, bbox_inches="tight", facecolor="white")
            plt.close(figure)


def _visual_semantic_payload(graph: Any, *, profile_id: str, model_spine: Any | None = None) -> dict[str, Any]:
    """Expose research semantics to AI/PPT renderers without prescribing geometry.

    The deterministic fallback has a five-stage node graph because Graphviz needs
    explicit geometry hints.  A generative or PowerPoint agent should instead see
    the accepted research questions, dependencies, methods, validation and outputs,
    then infer its own hierarchy/composition.  This keeps the design layer adaptive
    and avoids encoding one competition paper's visual grammar as a universal rule.
    """

    language = "zh" if profile_id == "CUMCM_C" else "en"
    research_nodes = [node for node in graph.nodes if getattr(node, "role", "") == "RESEARCH"]
    synthesis_nodes = [node for node in graph.nodes if getattr(node, "role", "") == "SYNTHESIS"]
    dependents: dict[str, list[str]] = {str(node.subproblem_id): [] for node in research_nodes}
    for node in research_nodes:
        target = str(node.subproblem_id)
        for dependency in getattr(node, "dependencies", []) or []:
            key = str(dependency)
            if key in dependents:
                dependents[key].append(target)

    spine_by_id = {
        str(item.subproblem_id): item
        for item in (getattr(model_spine, "nodes", []) or [])
    }
    questions: list[dict[str, Any]] = []
    for index, node in enumerate(research_nodes, start=1):
        protocol = str(getattr(node, "validation_protocol_id", "") or "").strip()
        validation = (
            PaperHumanizationAdapter.validation_label(protocol, language=language)
            if protocol
            else ("任务匹配检验" if language == "zh" else "task-matched validation")
        )
        spine_node = spine_by_id.get(str(node.subproblem_id))
        questions.append(
            {
                "subproblem_id": str(node.subproblem_id),
                "question_index": index,
                "title": str(node.title),
                "task_family": str(node.task_family),
                "method": PaperHumanizationAdapter.method_label(str(node.method), language=language),
                "validation": validation,
                "validation_gate": str(getattr(node, "validation_gate", "") or ""),
                "dependencies": [str(value) for value in (getattr(node, "dependencies", []) or [])],
                "downstream_dependents": dependents.get(str(node.subproblem_id), []),
                "output_summary": _compact_visual_text(str(getattr(node, "answer", "") or ""), 110),
                "modeling_role": str(getattr(spine_node, "role", "") or ""),
                "inherits_from": [str(value) for value in (getattr(spine_node, "inherits_from", []) or [])],
                "inheritance_kind": str(getattr(spine_node, "inheritance_kind", "") or ""),
                "paper_emphasis": float(getattr(spine_node, "paper_emphasis", 1.0) or 1.0),
            }
        )

    synthesis = [
        {
            "subproblem_id": str(node.subproblem_id),
            "title": str(node.title),
            "dependencies": [str(value) for value in (getattr(node, "dependencies", []) or [])],
            "output_summary": _compact_visual_text(str(getattr(node, "answer", "") or ""), 120),
        }
        for node in synthesis_nodes
    ]
    return {
        "profile_id": profile_id,
        "language": language,
        "data_context": "赛题数据、业务语境与题意约束" if language == "zh" else "problem data, domain context, and prompt constraints",
        "research_questions": questions,
        "modeling_spine": {
            "core_subproblem_ids": [str(value) for value in (getattr(model_spine, "core_subproblem_ids", []) or [])],
            "storyline": [str(value) for value in (getattr(model_spine, "storyline", []) or [])],
        },
        "synthesis_outputs": synthesis,
        "design_instruction": (
            "根据研究依赖、方法重要性和后续复用关系自行推断视觉层级；不要默认每个字段一个框，也不要默认所有小问等权。"
            if language == "zh"
            else "Infer visual hierarchy from research dependencies, modeling importance, and downstream reuse; do not map every field to a box or give every question equal visual weight."
        ),
    }


def _research_question_index(graph: Any, subproblem_id: str) -> int:
    research_nodes = [node for node in graph.nodes if getattr(node, "role", "") == "RESEARCH"]
    for index, node in enumerate(research_nodes, start=1):
        if str(getattr(node, "subproblem_id", "")) == str(subproblem_id):
            return index
    return 0


def _compact_visual_text(value: str, limit: int) -> str:
    text = " ".join(str(value).split())
    if len(text) <= limit:
        return text
    return text[: max(1, limit - 1)].rstrip("，,。.;；:： ") + "…"


def _task_family_label(task_family: str, *, language: str) -> str:
    zh = {
        "forecasting": "预测",
        "classification": "分类",
        "distribution_forecasting": "分布预测",
        "explanatory_inference": "解释分析",
        "exploratory_analysis": "数据探索",
        "optimization": "优化决策",
        "simulation": "仿真",
        "ranking": "综合评价",
        "synthesis": "综合输出",
    }
    en = {
        "forecasting": "Forecasting",
        "classification": "Classification",
        "distribution_forecasting": "Distribution forecast",
        "explanatory_inference": "Explanatory analysis",
        "exploratory_analysis": "Exploration",
        "optimization": "Decision optimization",
        "simulation": "Simulation",
        "ranking": "Evaluation/ranking",
        "synthesis": "Synthesis",
    }
    mapping = zh if language == "zh" else en
    return mapping.get(task_family, "建模" if language == "zh" else "Modeling")


def _analysis_stage_label(node: Any, *, index: int, language: str) -> str:
    """Use the accepted question title instead of a problem-specific visual template."""

    title = " ".join(str(getattr(node, "title", "") or "").split())
    if not title:
        title = _task_family_label(str(getattr(node, "task_family", "") or ""), language=language)
    prefix = f"问题{index}｜" if language == "zh" else f"Q{index} | "
    return prefix + title


def _validation_stage_label(node: Any, *, language: str) -> str:
    label = _validation_flow_label(node, language=language)
    if label:
        return label
    return "检验：任务匹配" if language == "zh" else "Validation: task-matched"


def _decision_stage_label(node: Any, *, index: int, language: str) -> str:
    detail = _decision_stage_detail(node, language=language)
    prefix = f"问题{index}｜" if language == "zh" else f"Q{index} | "
    return _wrap_label(prefix + detail, 18 if language == "zh" else 28)


def _validation_flow_label(node: Any, *, language: str) -> str:
    protocol = str(getattr(node, "validation_protocol_id", "") or "").strip()
    gate = str(getattr(node, "validation_gate", "") or "").upper()
    if not protocol and not gate:
        return ""
    protocol_label = (
        PaperHumanizationAdapter.validation_label(protocol, language=language)
        if protocol
        else ("专用检验" if language == "zh" else "registered validation")
    )
    if language == "zh":
        gate_label = "通过" if gate == "PASS" else "复核" if gate else ""
        return f"检验：{protocol_label}" + (f"（{gate_label}）" if gate_label else "")
    gate_label = "pass" if gate == "PASS" else "review" if gate else ""
    return f"Validation: {protocol_label}" + (f" ({gate_label})" if gate_label else "")


def _decision_stage_detail(node: Any, *, language: str) -> str:
    family = str(getattr(node, "task_family", "") or "")
    if language == "zh":
        mapping = {
            "exploratory_analysis": "稳定结构与异常特征",
            "forecasting": "预测结果与不确定性",
            "distribution_forecasting": "分布预测与区间",
            "classification": "分类结果与类别风险",
            "explanatory_inference": "关联效应与适用边界",
            "optimization": "可执行决策方案",
            "simulation": "情景结果与风险边界",
            "ranking": "综合评价与排序",
        }
        return mapping.get(family, "已验证中间结论")
    mapping = {
        "exploratory_analysis": "stable structure and anomalies",
        "forecasting": "forecast with uncertainty",
        "distribution_forecasting": "distribution forecast and interval",
        "classification": "class decisions and risks",
        "explanatory_inference": "associations and scope limits",
        "optimization": "feasible decision policy",
        "simulation": "scenario outcomes and risk bounds",
        "ranking": "evaluation and ranking",
    }
    return mapping.get(family, "accepted intermediate result")


def _flowchart_stage_colors(palette: list[str]) -> dict[str, str]:
    base = palette or ["#486581", "#627D98", "#7B8794", "#829AB1", "#9FB3C8"]
    return {
        "DATA": _mix_with_white(base[0 % len(base)], 0.16),
        "ANALYSIS": _mix_with_white(base[1 % len(base)], 0.78),
        "MODEL": _mix_with_white(base[2 % len(base)], 0.80),
        "VALIDATION": _mix_with_white(base[3 % len(base)], 0.84),
        "DECISION": _mix_with_white(base[4 % len(base)], 0.78),
    }


def _wrap_label(value: str, width: int) -> str:
    text = " ".join(str(value).split())
    if not text:
        return ""
    if any("\u4e00" <= char <= "\u9fff" for char in text):
        chunks = [text[index:index + width] for index in range(0, len(text), width)]
        return "\n".join(chunks[:3])
    return "\n".join(textwrap.wrap(text, width=width)[:3])


def _dot_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _mermaid_escape(value: str) -> str:
    return value.replace('"', "'").replace("\n", "<br/>")


def _to_dot(spec: FlowchartSpec) -> str:
    font_name = "Microsoft YaHei" if spec.profile_id == "CUMCM_C" else "Times New Roman"
    stage_fill = {
        "DATA": "#405A73",
        "ANALYSIS": "#F2F6F9",
        "MODEL": "#EDF3F0",
        "VALIDATION": "#F3F4F5",
        "DECISION": "#F4F1EA",
    }
    stage_border = {
        "DATA": "#405A73",
        "ANALYSIS": "#6D8191",
        "MODEL": "#587266",
        "VALIDATION": "#7A8187",
        "DECISION": "#7B6D55",
    }
    lines = [
        "digraph research_workflow {",
        f"  rankdir={spec.direction};",
        '  graph [bgcolor="white", pad="0.14", nodesep="0.20", ranksep="0.46", splines=ortho, outputorder=edgesfirst, newrank=true];',
        f'  node [shape=box, style="rounded,filled", fontname="{font_name}", fontsize=8.4, fontcolor="#23313B", penwidth=0.9, margin="0.12,0.08", width=2.35, height=0.55];',
        f'  edge [fontname="{font_name}", fontsize=6.6, color="#89939A", arrowsize=0.56, penwidth=0.78];',
    ]
    for node in spec.nodes:
        fill = stage_fill[node.stage]
        border = stage_border[node.stage]
        fontcolor = "white" if node.stage == "DATA" else "#23313B"
        penwidth = "1.15" if node.role == "SYNTHESIS" else "0.90"
        label = node.label + ("\n" + node.detail if node.detail else "")
        lines.append(
            f'  "{_dot_escape(node.node_id)}" [label="{_dot_escape(label)}", fillcolor="{fill}", '
            f'color="{border}", fontcolor="{fontcolor}", penwidth={penwidth}];'
        )
    for stage in ("DATA", "ANALYSIS", "MODEL", "VALIDATION", "DECISION"):
        ids = [node.node_id for node in spec.nodes if node.stage == stage]
        if ids:
            quoted = "; ".join(f'"{_dot_escape(node_id)}"' for node_id in ids)
            lines.append(f"  {{ rank=same; {quoted}; }}")
    for edge in spec.edges:
        source = _dot_escape(edge.source)
        target = _dot_escape(edge.target)
        if edge.kind == "DEPENDENCY":
            lines.append(
                f'  "{source}" -> "{target}" [style=dashed, color="#A0A8AD", penwidth=0.70, constraint=false];'
            )
        else:
            lines.append(f'  "{source}" -> "{target}";')
    lines.append("}")
    return "\n".join(lines) + "\n"


def _to_mermaid(spec: FlowchartSpec) -> str:
    lines = [f"flowchart {spec.direction}"]
    for node in spec.nodes:
        label = _mermaid_escape(node.label + ("\n" + node.detail if node.detail else ""))
        lines.append(f'    {node.node_id}["{label}"]')
    for edge in spec.edges:
        arrow = "-.->" if edge.kind == "DEPENDENCY" else "-->"
        lines.append(f'    {edge.source} {arrow}|{_mermaid_escape(edge.relation)}| {edge.target}')
    lines.extend(
        [
            "    classDef data fill:#405A73,stroke:#405A73,color:#FFFFFF,stroke-width:1px;",
            "    classDef analysis fill:#F2F6F9,stroke:#6D8191,color:#23313B,stroke-width:1px;",
            "    classDef model fill:#EDF3F0,stroke:#587266,color:#23313B,stroke-width:1px;",
            "    classDef validation fill:#F3F4F5,stroke:#7A8187,color:#23313B,stroke-width:1px;",
            "    classDef decision fill:#F4F1EA,stroke:#7B6D55,color:#23313B,stroke-width:1px;",
        ]
    )
    for stage, class_name in (
        ("DATA", "data"),
        ("ANALYSIS", "analysis"),
        ("MODEL", "model"),
        ("VALIDATION", "validation"),
        ("DECISION", "decision"),
    ):
        ids = [node.node_id for node in spec.nodes if node.stage == stage]
        if ids:
            lines.append("    class " + ",".join(ids) + f" {class_name};")
    return "\n".join(lines) + "\n"


def _node_levels(spec: FlowchartSpec) -> dict[str, int]:
    stage_level = {"DATA": 0, "ANALYSIS": 1, "MODEL": 2, "VALIDATION": 3, "DECISION": 4}
    return {node.node_id: stage_level[node.stage] for node in spec.nodes}


def _mix_with_white(hex_color: str, white_fraction: float) -> str:
    value = hex_color.lstrip("#")
    if len(value) != 6:
        return "#EAF2F8"
    rgb = [int(value[index:index + 2], 16) for index in (0, 2, 4)]
    mixed = [round(channel * (1.0 - white_fraction) + 255 * white_fraction) for channel in rgb]
    return "#" + "".join(f"{channel:02X}" for channel in mixed)

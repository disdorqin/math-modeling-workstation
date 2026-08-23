from __future__ import annotations

from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from .claims import ClaimInput
from .io_utils import atomic_write_json, read_json
from .figure_art_director import FigureArtDirector
from .paper_contracts import SubproblemAnswerRecord
from .plot_style import finalize_publication_axis, finalize_publication_figure, get_chart_template, get_publication_figsize, publication_context
from .visual_intent import FigureIntent, VisualIntentRouter


class SubproblemPaperEvidenceBridge:
    """Project one completed ProblemGraph node into the existing paper evidence layer."""

    def __init__(self, cases: Any, artifacts: Any, contracts: Any, claims: Any, figures: Any) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.contracts = contracts
        self.claims = claims
        self.figures = figures
        self.art_director = FigureArtDirector()
        self.visual_router = VisualIntentRouter()

    def project(
        self,
        case_id: str,
        subproblem_id: str,
        engine_result: dict[str, Any],
        *,
        dataset_ids: list[str] | None = None,
        created_by: str = "subproblem_engine",
    ) -> dict[str, Any]:
        graph = self._load_graph(case_id)
        node = graph.node(subproblem_id)
        if node.answer is None or node.state.status != "COMPLETED":
            raise ValueError("SUBPROBLEM_NOT_COMPLETED_FOR_PAPER_PROJECTION")
        execution = engine_result["execution"]
        result = execution["result"]
        source_artifact_id = execution["artifact"]["artifact_id"]
        rows = _numeric_rows(node.task_family, result)
        if not rows:
            raise ValueError(f"SUBPROBLEM_HAS_NO_NUMERIC_PAPER_RESULT:{node.task_family}")
        result_type = _result_type(node.task_family)
        records = [
            self.contracts.create_result(
                case_id,
                result_type=result_type,
                metric=metric,
                value=value,
                std=None,
                model_name=str(result.get("model") or result.get("method") or node.plan.selected_method or ""),
                dataset_id=(dataset_ids or [None])[0],
                experiment_id=(node.experiments[0].experiment_id if node.experiments else None),
                direction=direction,
                scope=f"{subproblem_id} {node.task_family} independent research result",
                source_artifact_ids=[source_artifact_id],
                section_ids=["results", "conclusion"],
                metadata={"subproblem_id": subproblem_id, **metadata},
            )
            for metric, value, direction, metadata in rows
        ]
        table, table_artifact = self.contracts.create_table(
            case_id,
            title=f"{subproblem_id}：{node.title}",
            columns=["指标", "数值", "说明"],
            rows=[
                [record.metric, record.formatted_value(), record.scope]
                for record in records
            ],
            result_ids=[record.result_id for record in records],
            source_artifact_ids=[source_artifact_id],
            section_ids=["results", "conclusion"],
            metadata={
                "subproblem_id": subproblem_id,
                "table_role": "summary_metrics",
                "paper_role": "supporting_summary",
            },
        )
        auxiliary_tables = self._create_auxiliary_tables(
            case_id,
            subproblem_id,
            node.task_family,
            result,
            records,
            source_artifact_id,
        )
        figure = self._create_figure(
            case_id,
            subproblem_id,
            node.task_family,
            result,
            records,
            source_artifact_id,
        )
        auxiliary_figures = self._create_auxiliary_figures(
            case_id,
            subproblem_id,
            node.task_family,
            result,
            source_artifact_id,
        )
        answer_record = SubproblemAnswerRecord(
            answer_id=node.answer.answer_id,
            subproblem_id=subproblem_id,
            method=node.answer.method,
            result_record_ids=[record.result_id for record in records],
            answer=node.answer.answer,
            limitation=node.answer.limitation,
            source_artifact_ids=[source_artifact_id],
            section_id="conclusion",
        )
        self.contracts.persist_analysis_records(case_id, answers=[answer_record])
        claim = self.claims.create(
            case_id,
            ClaimInput(
                text=node.answer.answer,
                claim_type=f"subproblem_{node.task_family}",
                evidence_artifact_ids=[
                    source_artifact_id,
                    table_artifact["artifact_id"],
                    *[item["artifact"]["artifact_id"] for item in auxiliary_tables],
                    figure["artifact_id"],
                    *[item["artifact_id"] for item in auxiliary_figures],
                ],
                dataset_ids=dataset_ids or [],
                section_hint="results",
                result_record_ids=[record.result_id for record in records],
                table_record_ids=[table.table_id, *[item["table"].table_id for item in auxiliary_tables]],
                subproblem_ids=[subproblem_id],
            ),
            created_by,
        )
        self._update_index(
            case_id,
            subproblem_id,
            [record.result_id for record in records],
            [table.table_id, *[item["table"].table_id for item in auxiliary_tables]],
            [
                source_artifact_id,
                table_artifact["artifact_id"],
                *[item["artifact"]["artifact_id"] for item in auxiliary_tables],
                figure["artifact_id"],
                *[item["artifact_id"] for item in auxiliary_figures],
            ],
        )
        return {
            "subproblem_id": subproblem_id,
            "result_records": records,
            "answer_record": answer_record,
            "table": table,
            "table_artifact": table_artifact,
            "auxiliary_tables": auxiliary_tables,
            "figure": figure,
            "auxiliary_figures": auxiliary_figures,
            "claim": claim,
        }

    def project_synthesis(
        self,
        case_id: str,
        subproblem_id: str,
        synthesis_result: dict[str, Any],
    ) -> SubproblemAnswerRecord:
        graph = self._load_graph(case_id)
        node = graph.node(subproblem_id)
        if node.answer is None or node.execution_kind != "DELIVERABLE":
            raise ValueError("SYNTHESIS_NODE_NOT_COMPLETED")
        artifact_id = synthesis_result["artifact"]["artifact_id"]
        answer = SubproblemAnswerRecord(
            answer_id=node.answer.answer_id,
            subproblem_id=subproblem_id,
            method=node.answer.method,
            result_record_ids=[],
            answer=node.answer.answer,
            limitation=node.answer.limitation,
            source_artifact_ids=[artifact_id],
            section_id="conclusion",
        )
        self.contracts.persist_analysis_records(case_id, answers=[answer])
        self._update_index(case_id, subproblem_id, [], [], [artifact_id])
        return answer

    def activate_if_complete(self, case_id: str, generation: int | None = None) -> dict[str, Any] | None:
        graph = self._load_graph(case_id)
        from .problem_graph import assess_problem_graph

        if assess_problem_graph(graph).research_gate != "PASS":
            return None
        path = self._index_path(case_id)
        if not path.is_file():
            return None
        payload = read_json(path)
        nodes = payload.get("subproblems", {})
        result_ids = [value for item in nodes.values() for value in item.get("result_ids", [])]
        table_ids = [value for item in nodes.values() for value in item.get("table_ids", [])]
        source_artifact_ids = [
            value for item in nodes.values() for value in item.get("source_artifact_ids", [])
        ]
        if not result_ids or not table_ids:
            return None
        return self.contracts.activate_evidence_lineage(
            case_id,
            list(dict.fromkeys(result_ids)),
            list(dict.fromkeys(table_ids)),
            source_artifact_ids=list(dict.fromkeys(source_artifact_ids)),
            generation=generation,
        )

    def _index_path(self, case_id: str):
        return self.cases.case_root(case_id) / "results" / "contracts" / "subproblem_evidence_index.json"

    def _update_index(
        self,
        case_id: str,
        subproblem_id: str,
        result_ids: list[str],
        table_ids: list[str],
        source_artifact_ids: list[str],
    ) -> None:
        path = self._index_path(case_id)
        payload = read_json(path) if path.is_file() else {"schema_version": 1, "case_id": case_id, "subproblems": {}}
        payload.setdefault("subproblems", {})[subproblem_id] = {
            "result_ids": list(result_ids),
            "table_ids": list(table_ids),
            "source_artifact_ids": list(dict.fromkeys(source_artifact_ids)),
        }
        atomic_write_json(path, payload)

    def _load_graph(self, case_id: str):
        from .problem_graph import ProblemGraphService

        return ProblemGraphService(self.cases, self.artifacts).load(case_id)

    def _create_auxiliary_tables(
        self,
        case_id: str,
        subproblem_id: str,
        family: str,
        result: dict[str, Any],
        records: list[Any],
        source_artifact_id: str,
    ) -> list[dict[str, Any]]:
        """Create paper-facing tables when the executed result has real tabular semantics.

        A compact metric summary is useful for auditability, but it must not replace
        an executable decision schedule or a small relationship matrix.  These tables
        are derived only from persisted solver output and carry explicit paper roles
        so the renderer can place them where the argument first needs them.
        """

        if family != "optimization":
            return []
        solver_method = str(result.get("solver_method") or "").lower()
        result_ids = [record.result_id for record in records]
        outputs: list[dict[str, Any]] = []

        if solver_method == "retail_category_pricing_replenishment":
            strategy = list(result.get("strategy") or [])
            if strategy:
                table, artifact = self.contracts.create_table(
                    case_id,
                    title="未来一周各蔬菜品类定价与补货策略",
                    columns=["日期", "品类", "需求预测/kg", "补货量/kg", "售价/(元/kg)", "加价率", "预期收益/元"],
                    rows=[
                        [
                            str(item.get("date") or ""),
                            str(item.get("entity") or ""),
                            f"{float(item.get('demand_forecast', 0.0)):.2f}",
                            f"{float(item.get('replenishment_quantity', 0.0)):.2f}",
                            f"{float(item.get('sale_price', 0.0)):.2f}",
                            f"{float(item.get('markup_rate', 0.0)):.1%}",
                            f"{float(item.get('expected_profit', 0.0)):.2f}",
                        ]
                        for item in strategy
                    ],
                    result_ids=result_ids,
                    source_artifact_ids=[source_artifact_id],
                    section_ids=["results", "conclusion"],
                    metadata={
                        "subproblem_id": subproblem_id,
                        "table_role": "decision_schedule",
                        "paper_role": "primary_decision",
                        "argument_phase": "decision",
                    },
                )
                outputs.append({"table": table, "artifact": artifact})
            relationships = list(result.get("price_demand_relationship") or [])
            if relationships:
                table, artifact = self.contracts.create_table(
                    case_id,
                    title="各蔬菜品类成本加成与销量关系的时间留出估计",
                    columns=["品类", "需求形式", "一次项系数", "二次项系数", "验证RMSE", "验证MAE", "历史加价率区间"],
                    rows=[_retail_relationship_table_row(item) for item in relationships],
                    result_ids=result_ids,
                    source_artifact_ids=[source_artifact_id],
                    section_ids=["results"],
                    metadata={
                        "subproblem_id": subproblem_id,
                        "table_role": "relationship_validation",
                        "paper_role": "supporting_mechanism",
                        "argument_phase": "model_evidence",
                    },
                )
                outputs.append({"table": table, "artifact": artifact})

        if solver_method == "retail_item_pricing_replenishment":
            strategy = list(result.get("strategy") or [])
            if strategy:
                table, artifact = self.contracts.create_table(
                    case_id,
                    title="7月1日单品定价与补货执行方案",
                    columns=["单品编码", "品类", "补货量/kg", "售价/(元/kg)", "预计销量/kg", "分配比例", "预期收益/元"],
                    rows=[
                        [
                            str(item.get("entity") or ""),
                            str(item.get("category") or ""),
                            f"{float(item.get('replenishment_quantity', 0.0)):.2f}",
                            f"{float(item.get('sale_price', 0.0)):.2f}",
                            f"{float(item.get('expected_sales', 0.0)):.2f}",
                            f"{float(item.get('allocation_share', 0.0)):.1%}",
                            f"{float(item.get('expected_profit', 0.0)):.2f}",
                        ]
                        for item in strategy
                    ],
                    result_ids=result_ids,
                    source_artifact_ids=[source_artifact_id],
                    section_ids=["results", "conclusion"],
                    metadata={
                        "subproblem_id": subproblem_id,
                        "table_role": "decision_schedule",
                        "paper_role": "primary_decision",
                        "argument_phase": "decision",
                    },
                )
                outputs.append({"table": table, "artifact": artifact})
        return outputs

    def _create_figure(
        self,
        case_id: str,
        subproblem_id: str,
        family: str,
        result: dict[str, Any],
        records: list[Any],
        source_artifact_id: str,
    ) -> dict[str, Any]:
        root = self.cases.case_root(case_id)
        profile = self._publication_profile(case_id)
        path = root / "figures" / "draft" / f"subproblem-{subproblem_id}-evidence.png"
        svg_path = path.with_suffix(".svg")
        with publication_context(profile):
            figure, axis = plt.subplots(figsize=get_publication_figsize(profile, "wide"))
            semantic_kind, title, purpose = _plot_semantic_evidence(axis, family, result, records)
            art_brief = self.art_director.apply(
                axis,
                semantic_kind,
                identity=f"{case_id}:{subproblem_id}:primary",
            )
            finalize_publication_figure(
                figure,
                axis,
                chart_type=semantic_kind,
                title=title,
                caption_first=True,
            )
            figure.savefig(path, dpi=600, bbox_inches="tight", facecolor="white")
            figure.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
            plt.close(figure)
        vector_artifact = self.artifacts.register_existing(
            case_id,
            svg_path.relative_to(root).as_posix(),
            "scientific_data_figure_vector",
            "mathworkstation.subproblem_paper_bridge",
            upstream=[source_artifact_id],
            paper_eligible=False,
        )
        visual_plan = self._numeric_visual_plan(
            case_id=case_id,
            subproblem_id=subproblem_id,
            profile=profile,
            title=title,
            purpose=purpose,
            source_artifact_id=source_artifact_id,
        )
        return self.figures.register(
            case_id,
            path.relative_to(root).as_posix(),
            title,
            [source_artifact_id, vector_artifact["artifact_id"]],
            "mathworkstation.subproblem_paper_bridge",
            {
                "subproblem_id": subproblem_id,
                "task_family": family,
                "semantic_kind": semantic_kind,
                "purpose": purpose,
                "publication_profile": profile,
                "dpi": 600,
                "vector_source": True,
                "svg_artifact_id": vector_artifact["artifact_id"],
                "paper_role": "primary",
                "caption_first": True,
                "palette_family": art_brief.palette_family,
                "palette_mode": art_brief.palette_mode,
                "figure_art_brief": art_brief.model_dump(mode="json"),
                "art_visual_family": art_brief.visual_family,
                "art_layout": art_brief.layout,
                "visual_intent_kind": visual_plan["intent"]["kind"],
                "visual_primary_backend": visual_plan["primary_backend"],
                "visual_publication_backend": visual_plan["publication_backend"],
                "visual_review_required": visual_plan["visual_review_required"],
            },
            None,
            status="FINAL",
        )

    def _create_auxiliary_figures(
        self,
        case_id: str,
        subproblem_id: str,
        family: str,
        result: dict[str, Any],
        source_artifact_id: str,
    ) -> list[dict[str, Any]]:
        """Render extra evidence plots only when the executed solver produced them.

        These are not decorative chart quotas.  A supplementary figure exists only
        when the solver result already contains a robustness or scenario-comparison
        payload whose semantics are clearer as a plot than as another prose sentence.
        """

        specs = _auxiliary_figure_specs(family, result)
        if not specs:
            return []
        root = self.cases.case_root(case_id)
        profile = self._publication_profile(case_id)
        outputs: list[dict[str, Any]] = []
        for spec in specs:
            semantic_kind = str(spec["semantic_kind"])
            path = root / "figures" / "draft" / f"subproblem-{subproblem_id}-{semantic_kind}.png"
            svg_path = path.with_suffix(".svg")
            with publication_context(profile):
                chart_type = str(spec.get("chart_type") or semantic_kind)
                if chart_type == "two_bar_panel":
                    figure, axes = plt.subplots(1, 2, figsize=get_publication_figsize(profile, "wide"))
                    _render_auxiliary_panel(axes, spec)
                    art_brief = None
                    for axis in axes:
                        art_brief = self.art_director.apply(
                            axis,
                            semantic_kind,
                            identity=f"{case_id}:{subproblem_id}:{semantic_kind}",
                            panel_count=len(axes),
                        )
                        finalize_publication_axis(axis, chart_type="bar", caption_first=True)
                    figure.tight_layout(pad=0.7, w_pad=1.2)
                else:
                    figure, axis = plt.subplots(figsize=get_publication_figsize(profile, "wide"))
                    _render_auxiliary_figure(axis, spec)
                    art_brief = self.art_director.apply(
                        axis,
                        semantic_kind,
                        identity=f"{case_id}:{subproblem_id}:{semantic_kind}",
                    )
                    finalize_publication_figure(
                        figure,
                        axis,
                        chart_type=chart_type,
                        title=str(spec["title"]),
                        caption_first=True,
                    )
                figure.savefig(path, dpi=600, bbox_inches="tight", facecolor="white")
                figure.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
                plt.close(figure)
            vector_artifact = self.artifacts.register_existing(
                case_id,
                svg_path.relative_to(root).as_posix(),
                "scientific_data_figure_vector",
                "mathworkstation.subproblem_paper_bridge",
                upstream=[source_artifact_id],
                paper_eligible=False,
            )
            visual_plan = self._numeric_visual_plan(
                case_id=case_id,
                subproblem_id=subproblem_id,
                profile=profile,
                title=str(spec["title"]),
                purpose=str(spec["purpose"]),
                source_artifact_id=source_artifact_id,
            )
            outputs.append(
                self.figures.register(
                    case_id,
                    path.relative_to(root).as_posix(),
                    str(spec["title"]),
                    [source_artifact_id, vector_artifact["artifact_id"]],
                    "mathworkstation.subproblem_paper_bridge",
                    {
                        "subproblem_id": subproblem_id,
                        "task_family": family,
                        "semantic_kind": semantic_kind,
                        "purpose": str(spec["purpose"]),
                        "publication_profile": profile,
                        "dpi": 600,
                        "vector_source": True,
                        "svg_artifact_id": vector_artifact["artifact_id"],
                        "paper_role": "supplementary_evidence",
                        "caption_first": True,
                        "palette_family": art_brief.palette_family,
                        "palette_mode": art_brief.palette_mode,
                        "figure_art_brief": art_brief.model_dump(mode="json"),
                        "art_visual_family": art_brief.visual_family,
                        "art_layout": art_brief.layout,
                        "visual_intent_kind": visual_plan["intent"]["kind"],
                        "visual_primary_backend": visual_plan["primary_backend"],
                        "visual_publication_backend": visual_plan["publication_backend"],
                        "visual_review_required": visual_plan["visual_review_required"],
                    },
                    None,
                    status="FINAL",
                )
            )
        return outputs

    def _numeric_visual_plan(
        self,
        *,
        case_id: str,
        subproblem_id: str,
        profile: str,
        title: str,
        purpose: str,
        source_artifact_id: str,
    ) -> dict[str, Any]:
        intent = FigureIntent(
            intent_id=f"{case_id}:{subproblem_id}:{title}",
            kind="numeric_evidence",
            profile_id=profile,
            purpose=purpose,
            source_summary=f"Executed evidence for {subproblem_id}.",
            evidence_refs=[source_artifact_id],
            required_content=["Preserve the plotted numeric values and axis semantics from the executed evidence."],
            forbidden_content=["Do not synthesize or visually alter data values to improve appearance."],
            editable_preferred=True,
        )
        return self.visual_router.route(
            intent,
            capabilities={"deterministic_plot": True, "editable_vector": True, "ai_image": False},
        ).model_dump(mode="json")

    def _publication_profile(self, case_id: str) -> str:
        """Route paper figures by competition metadata stored in the case manifest."""

        manifest = read_json(self.cases.case_root(case_id) / "manifest.json")
        competition = str(manifest.get("competition_type") or "").strip().upper()
        if competition == "CUMCM":
            return "CUMCM_C"
        if competition in {"MCM", "ICM"}:
            return "MCM_C"
        return "SCI_CLEAN"


def _auxiliary_figure_specs(family: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    if family == "exploratory_analysis":
        discoveries = result.get("discoveries") or {}
        outliers = [item for item in discoveries.get("highest_outlier_rates", []) if isinstance(item, dict)][:6]
        shifts = [item for item in discoveries.get("largest_mean_shift_candidates", []) if isinstance(item, dict)][:6]
        if outliers and shifts:
            specs.append(
                {
                    "semantic_kind": "exploratory_diagnostics_panel",
                    "title": "Robust exploratory diagnostics",
                    "purpose": "Pairs IQR outlier prevalence with standardized mean-shift strength so abnormal volatility and stage changes are not hidden behind one correlation chart.",
                    "chart_type": "two_bar_panel",
                    "panels": [
                        {
                            "labels": [str(item["column"]) for item in outliers],
                            "values": [float(item["iqr_outlier_rate"]) for item in outliers],
                            "title": "IQR outlier prevalence",
                            "ylabel": "Outlier rate",
                        },
                        {
                            "labels": [str(item["column"]) for item in shifts],
                            "values": [float(item["standardized_mean_shift"]) for item in shifts],
                            "title": "Stage-change strength",
                            "ylabel": "Standardized mean shift",
                        },
                    ],
                }
            )
        return specs
    if family != "optimization":
        return []
    sensitivity_runs = result.get("sensitivity_runs")
    if isinstance(sensitivity_runs, list) and sensitivity_runs:
        factor_keys = sorted(
            {
                key
                for run in sensitivity_runs
                if isinstance(run, dict)
                for key in run
                if str(key).endswith("_factor")
            }
        )
        if len(factor_keys) == 1 and "objective_value" in result:
            factor_key = factor_keys[0]
            points = [(1.0, float(result["objective_value"]))]
            for run in sensitivity_runs:
                if factor_key in run and "objective_value" in run:
                    points.append((float(run[factor_key]), float(run["objective_value"])))
            points = sorted(dict(points).items())
            if len(points) >= 3:
                parameter = factor_key.removesuffix("_factor").replace("_", " ")
                specs.append(
                    {
                        "semantic_kind": "parameter_sensitivity_curve",
                        "title": f"Objective sensitivity to {parameter}",
                        "purpose": "Shows how the optimized objective changes under the solver's registered parameter perturbation, including the accepted baseline.",
                        "chart_type": "line",
                        "x": [item[0] for item in points],
                        "y": [item[1] for item in points],
                        "xlabel": f"{parameter} factor",
                        "ylabel": "Optimized objective value",
                    }
                )
    solver_method = str(result.get("solver_method") or "").lower()
    if solver_method == "retail_category_pricing_replenishment":
        relationships = [item for item in result.get("price_demand_relationship", []) if isinstance(item, dict)]
        if relationships:
            specs.append(
                {
                    "semantic_kind": "retail_price_demand_relationship",
                    "title": "Observed markup-demand response and validation error by vegetable category",
                    "purpose": "Pairs each selected demand model's local markup-response slope at the midpoint of its observed support with chronological holdout RMSE, so quadratic models are not misrepresented by their linear term alone.",
                    "chart_type": "two_bar_panel",
                    "panels": [
                        {
                            "labels": [str(item["entity"]) for item in relationships],
                            "values": [_markup_response_slope_at_support_midpoint(item) for item in relationships],
                            "title": "Markup-response slope at support midpoint",
                            "ylabel": "Local association slope",
                        },
                        {
                            "labels": [str(item["entity"]) for item in relationships],
                            "values": [float(item["validation_rmse"]) for item in relationships],
                            "title": "Chronological holdout error",
                            "ylabel": "RMSE",
                        },
                    ],
                }
            )
    if solver_method == "retail_item_pricing_replenishment":
        quotas = result.get("category_quotas")
        if isinstance(quotas, dict) and quotas:
            specs.append(
                {
                    "semantic_kind": "retail_category_assortment_counts",
                    "title": "Selected item count by vegetable category",
                    "purpose": "Shows how the executed 27-33 item assortment covers every positive-demand category without replacing the full item-level decision table.",
                    "chart_type": "lollipop",
                    "labels": [str(key) for key in quotas],
                    "values": [float(value) for value in quotas.values()],
                    "xlabel": "Selected item count",
                }
            )

    no_shared = result.get("no_shared_comparison")
    if isinstance(no_shared, dict) and "objective_value" in no_shared and "objective_value" in result:
        specs.append(
            {
                "semantic_kind": "scenario_cost_comparison",
                "title": "Shared versus no-shared layout cost comparison",
                "purpose": "Compares the accepted shared-layout objective with the explicitly re-optimized no-shared scenario using the same cost definition.",
                "chart_type": "bar",
                "labels": ["Shared layout", "No-shared layout"],
                "values": [float(result["objective_value"]), float(no_shared["objective_value"])],
                "ylabel": "Optimized objective value",
            }
        )
    return specs


def _retail_relationship_table_row(item: dict[str, Any]) -> list[str]:
    variant = str(item.get("feature_variant") or "linear_markup")
    variant_label = {
        "simple_markup": "简约线性响应",
        "linear_markup": "时序校正线性响应",
        "quadratic_markup": "时序校正二次响应",
    }.get(variant, variant)
    beta1 = float(item.get("markup_response_coefficient", 0.0))
    beta2 = float(item.get("markup_quadratic_coefficient", 0.0))
    support = item.get("historical_markup_range") or [0.0, 0.0]
    low, high = [float(value) for value in support[:2]]
    return [
        str(item.get("entity") or ""),
        variant_label,
        f"{beta1:.4f}",
        f"{beta2:.4f}" if variant == "quadratic_markup" else "-",
        f"{float(item.get('validation_rmse', 0.0)):.3f}",
        f"{float(item.get('validation_mae', 0.0)):.3f}",
        f"{low:.1%}-{high:.1%}",
    ]


def _markup_response_slope_at_support_midpoint(item: dict[str, Any]) -> float:
    beta1 = float(item.get("markup_response_coefficient", 0.0))
    if str(item.get("feature_variant") or "") != "quadratic_markup":
        return beta1
    support = item.get("historical_markup_range") or [0.0, 0.0]
    low, high = [float(value) for value in support[:2]]
    midpoint = 0.5 * (low + high)
    beta2 = float(item.get("markup_quadratic_coefficient", 0.0))
    return beta1 + 2.0 * beta2 * midpoint


def _render_auxiliary_panel(axes: Any, spec: dict[str, Any]) -> None:
    panels = list(spec.get("panels") or [])
    if len(panels) != 2:
        raise ValueError("AUXILIARY_TWO_BAR_PANEL_REQUIRES_TWO_PANELS")
    for axis, panel in zip(axes, panels):
        labels = [str(value) for value in panel.get("labels") or []]
        values = [float(value) for value in panel.get("values") or []]
        positions = list(range(len(labels)))
        axis.barh(positions, values)
        axis.set_yticks(positions)
        axis.set_yticklabels(labels)
        axis.invert_yaxis()
        axis.set_xlabel(str(panel.get("ylabel") or ""))
        axis.text(
            0.0,
            1.03,
            str(panel.get("title") or ""),
            transform=axis.transAxes,
            ha="left",
            va="bottom",
            fontsize=8.2,
            fontweight="semibold",
        )


def _render_auxiliary_figure(axis: Any, spec: dict[str, Any]) -> None:
    chart_type = str(spec.get("chart_type") or "")
    if chart_type == "line":
        axis.plot(spec["x"], spec["y"], marker="o")
        axis.set_xlabel(str(spec.get("xlabel") or ""))
        axis.set_ylabel(str(spec.get("ylabel") or ""))
        return
    if chart_type == "bar":
        labels = list(spec.get("labels") or [])
        values = [float(value) for value in spec.get("values") or []]
        positions = list(range(len(labels)))
        bars = axis.bar(positions, values, width=0.58)
        axis.set_xticks(positions)
        axis.set_xticklabels(labels)
        axis.set_ylabel(str(spec.get("ylabel") or ""))
        axis.grid(axis="y", alpha=0.18, linewidth=0.7)
        axis.set_axisbelow(True)
        for bar, value in zip(bars, values):
            axis.text(bar.get_x() + bar.get_width() / 2.0, value, f"{value:g}", ha="center", va="bottom", fontsize=8)
        if len(values) == 2:
            difference = values[1] - values[0]
            axis.text(
                0.5,
                max(values) if values else 0.0,
                f"difference={difference:.4g}",
                ha="center",
                va="bottom",
            )
        return
    if chart_type == "lollipop":
        labels = [str(value) for value in spec.get("labels") or []]
        values = [float(value) for value in spec.get("values") or []]
        positions = list(range(len(labels)))
        axis.hlines(positions, 0.0, values, linewidth=1.5, color="#C8CDD2", zorder=1)
        for position, value in zip(positions, values):
            axis.scatter([value], [position], s=72, zorder=3, edgecolors="white", linewidths=0.8)
            axis.text(value + 0.08, position, f"{value:g}", va="center", ha="left", fontsize=8.2)
        axis.set_yticks(positions)
        axis.set_yticklabels(labels)
        axis.set_xlabel(str(spec.get("xlabel") or ""))
        axis.set_xlim(left=0.0, right=max(values) + max(0.8, 0.18 * max(values)) if values else 1.0)
        axis.grid(axis="x", alpha=0.16, linewidth=0.7)
        axis.set_axisbelow(True)
        axis.invert_yaxis()
        return
    raise ValueError(f"UNSUPPORTED_AUXILIARY_FIGURE:{chart_type}")


def _plot_semantic_evidence(axis: Any, family: str, result: dict[str, Any], records: list[Any]) -> tuple[str, str, str]:
    """Render a figure that answers a research question instead of a metric dashboard."""

    if family == "forecasting" and isinstance(result.get("forecast"), dict):
        forecast = result["forecast"]
        point = float(forecast["point"])
        lower, upper = [float(value) for value in forecast["interval"]]
        axis.errorbar(["future target"], [point], yerr=[[point - lower], [upper - point]], fmt="o", capsize=8)
        axis.set_ylabel("Forecast value")
        return (
            "forecast_interval",
            "Future forecast with 95% prediction interval",
            "Shows the requested future prediction together with its uncertainty rather than only validation error.",
        )

    if family == "forecasting" and isinstance(result.get("trend_grid"), list) and result["trend_grid"]:
        trends = list(result["trend_grid"])
        labels = [f"{item['entity']}\n{str(item['target']).replace('_', ' ')}" for item in trends]
        slopes = [float(item["annual_slope"]) for item in trends]
        axis.barh(list(reversed(labels)), list(reversed(slopes)))
        axis.axvline(0.0, linewidth=1)
        axis.set_xlabel("Estimated annual change")
        return (
            "panel_trend_characterization",
            "Historical energy-profile trend by state and indicator",
            "Compares the direction and annual magnitude of observed historical change across all registered entity-profile series.",
        )

    if family == "forecasting" and isinstance(result.get("forecast_grid"), list) and result["forecast_grid"]:
        grid = list(result["forecast_grid"])
        labels = [
            f"{item['entity']}\n{str(item['target']).replace('_', ' ')}\n{str(item['future_time'])[:4]}"
            for item in grid
        ]
        points = [float(item["point"]) for item in grid]
        lowers = [float(item["interval"][0]) for item in grid]
        uppers = [float(item["interval"][1]) for item in grid]
        errors = [
            [point - low for point, low in zip(points, lowers)],
            [high - point for point, high in zip(points, uppers)],
        ]
        axis.errorbar(range(len(grid)), points, yerr=errors, fmt="o", capsize=3)
        axis.set_xticks(range(len(grid)))
        axis.set_xticklabels(labels, rotation=55, ha="right")
        axis.set_ylabel("Forecast value")
        return (
            "panel_forecast_intervals",
            "Multi-entity future profile forecasts with 95% intervals",
            "Shows every registered entity-target-horizon forecast rather than collapsing a panel problem to one scalar prediction.",
        )

    solver_method = str(result.get("solver_method") or "").lower()

    if family == "explanatory_inference" and solver_method == "activation_promotion_association":
        values = result.get("metrics", {})
        labels = ["Promotion exposed", "No promotion"]
        rates = [
            float(values.get("promotion_activation_rate", 0.0)),
            float(values.get("nonpromotion_activation_rate", 0.0)),
        ]
        axis.bar(labels, rates)
        axis.set_ylim(0.0, 1.0)
        axis.set_ylabel("Observed next-window activation rate")
        return (
            "activation_rate_comparison",
            "Member activation rate by promotion exposure",
            "Compares observed inactive-to-active transition rates for promotion-exposed and non-exposed windows; the association is not interpreted as causal.",
        )

    if family == "explanatory_inference" and result.get("effects"):
        effects = list(result["effects"])[:8]
        names = [str(item["feature"]) for item in reversed(effects)]
        values = [float(item["standardized_coefficient"]) for item in reversed(effects)]
        lowers = [float(item["bootstrap_ci_95"][0]) for item in reversed(effects)]
        uppers = [float(item["bootstrap_ci_95"][1]) for item in reversed(effects)]
        xerr = [
            [value - low for value, low in zip(values, lowers)],
            [high - value for value, high in zip(values, uppers)],
        ]
        axis.barh(names, values, xerr=xerr, capsize=4)
        axis.axvline(0.0, linewidth=1)
        axis.set_xlabel("Standardized coefficient")
        return (
            "effect_intervals",
            "Standardized feature effects with bootstrap intervals",
            "Compares effect direction, magnitude, and uncertainty for the explanatory question.",
        )

    if family == "distribution_forecasting" and isinstance(result.get("future_distribution"), dict):
        distribution = result["future_distribution"]
        uncertainty = result.get("future_uncertainty_95") or {}
        labels = list(distribution)
        values = [float(distribution[label]) for label in labels]
        errors = None
        if all(label in uncertainty for label in labels):
            lower = [float(uncertainty[label][0]) for label in labels]
            upper = [float(uncertainty[label][1]) for label in labels]
            errors = [
                [value - low for value, low in zip(values, lower)],
                [high - value for value, high in zip(values, upper)],
            ]
        axis.bar(labels, values, yerr=errors, capsize=4 if errors else 0)
        axis.set_ylabel("Predicted share (%)")
        axis.tick_params(axis="x", rotation=30)
        return (
            "distribution_uncertainty",
            "Predicted outcome distribution with uncertainty",
            "Shows the full simplex-constrained future distribution and component uncertainty.",
        )

    if family == "classification" and isinstance(result.get("future_probabilities"), dict):
        probabilities = result["future_probabilities"]
        labels = list(probabilities)
        values = [float(probabilities[label]) for label in labels]
        axis.bar(labels, values)
        axis.set_ylim(0.0, 1.0)
        axis.set_ylabel("Predicted probability")
        return (
            "class_probabilities",
            "Future difficulty classification probabilities",
            "Shows both the predicted class and the confidence distribution across all classes.",
        )

    if family == "exploratory_analysis" and solver_method == "member_lifecycle_states" and result.get("state_profiles"):
        profiles = list(result["state_profiles"])
        labels = [str(item["state"]) for item in profiles]
        shares = [float(item["share"]) for item in profiles]
        axis.bar(labels, shares)
        axis.set_ylim(0.0, 1.0)
        axis.set_ylabel("Member share")
        return (
            "member_lifecycle_state_shares",
            "Member lifecycle-state composition",
            "Shows how retained members are distributed across the data-derived lifecycle states for the registered observation window.",
        )

    if family == "exploratory_analysis" and solver_method == "market_basket_association" and result.get("top_rules"):
        rules = list(result["top_rules"])[:8]
        labels = [f"{item['antecedent']} → {item['consequent']}" for item in reversed(rules)]
        lifts = [float(item["lift"]) for item in reversed(rules)]
        axis.barh(labels, lifts)
        axis.axvline(1.0, linewidth=1)
        axis.set_xlabel("Lift")
        return (
            "market_basket_rule_lift",
            "Strongest observed product-association rules",
            "Ranks the strongest retained basket rules by lift while support and confidence remain available in the evidence table.",
        )

    if family == "exploratory_analysis" and isinstance(result.get("profiles"), list) and result["profiles"]:
        profiles = list(result["profiles"])
        member_profile = solver_method == "member_group_profile"
        columns = list(result.get("profile_columns") or list(profiles[0].get("values", {})))
        matrix = np.asarray(
            [[float(item["values"][column]) for column in columns] for item in profiles],
            dtype=float,
        )
        low = np.min(matrix, axis=0)
        high = np.max(matrix, axis=0)
        span = np.where(np.abs(high - low) > 1e-12, high - low, 1.0)
        normalized = (matrix - low) / span
        image = axis.imshow(normalized, aspect="auto", vmin=0.0, vmax=1.0)
        axis.set_yticks(range(len(profiles)))
        axis.set_yticklabels([str(item["entity"]) for item in profiles])
        axis.set_xticks(range(len(columns)))
        axis.set_xticklabels([column.replace("_", " ") for column in columns], rotation=40, ha="right")
        axis.set_xlabel("Profile dimensions (column-wise normalized for display)")
        axis.figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04)
        if member_profile:
            return (
                "member_group_profile_heatmap",
                "Member and non-member consumption profile comparison",
                "Compares the two customer groups on the same observed consumption dimensions after column-wise normalization for display.",
            )
        return (
            "panel_profile_heatmap",
            "Comparable multi-state energy profile at the reference year",
            "Shows relative cross-state position on each registered profile dimension without mixing incompatible raw units.",
        )

    if family == "exploratory_analysis":
        discoveries = result.get("discoveries") or {}
        correlation_columns = [str(value) for value in discoveries.get("correlation_columns", [])]
        correlation_matrix = discoveries.get("spearman_correlation_matrix")
        if correlation_columns and isinstance(correlation_matrix, list):
            matrix = np.asarray(correlation_matrix, dtype=float)
            if matrix.ndim == 2 and matrix.shape[0] == matrix.shape[1] == len(correlation_columns) and len(correlation_columns) >= 3:
                # Choose a readable subset from the strongest observed relationships
                # rather than hard-coding problem-specific variables. The full matrix
                # remains in the execution artifact.
                selected: list[str] = []
                for item in discoveries.get("strongest_associations", []):
                    for key in ("left", "right"):
                        value = str(item.get(key) or "")
                        if value and value not in selected:
                            selected.append(value)
                    if len(selected) >= 12:
                        break
                for value in correlation_columns:
                    if len(selected) >= 12:
                        break
                    if value not in selected:
                        selected.append(value)
                indices = [correlation_columns.index(value) for value in selected]
                view = matrix[np.ix_(indices, indices)]
                template = get_chart_template("heatmap")
                image = axis.imshow(view, aspect="auto", vmin=-1.0, vmax=1.0, cmap=str(template.get("cmap") or "RdBu_r"))
                axis.set_xticks(range(len(selected)))
                axis.set_xticklabels(selected, rotation=45, ha="right")
                axis.set_yticks(range(len(selected)))
                axis.set_yticklabels(selected)
                if bool(template.get("annot", True)) and len(selected) <= 9:
                    for row in range(len(selected)):
                        for column in range(len(selected)):
                            axis.text(column, row, f"{view[row, column]:.2f}", ha="center", va="center", fontsize=6.2)
                axis.figure.colorbar(image, ax=axis, fraction=0.046, pad=0.04, label="Spearman correlation")
                return (
                    "correlation_heatmap",
                    "Spearman correlation structure among the most connected sales series",
                    "Shows the signed pairwise association structure for variables appearing in the strongest observed relationships; the full matrix remains in the execution evidence.",
                )
        associations = list(discoveries.get("strongest_associations", []))[:8]
        if associations:
            labels = [f"{item['left']} / {item['right']}" for item in reversed(associations)]
            values = [float(item["spearman_r"]) for item in reversed(associations)]
            axis.barh(labels, values)
            axis.axvline(0.0, linewidth=1)
            axis.set_xlabel("Spearman rank correlation")
            return (
                "association_ranking",
                "Strongest exploratory associations",
                "Ranks the strongest discovered monotone associations without presenting them as causal effects.",
            )

    if family == "ranking" and solver_method == "rfm_member_value" and result.get("ranking"):
        ranking = sorted(result["ranking"], key=lambda item: int(item.get("rank", 999)))[:10]
        labels = [str(item["entity"]) for item in reversed(ranking)]
        scores = [float(item["score"]) for item in reversed(ranking)]
        axis.barh(labels, scores)
        axis.set_xlabel("Member value score")
        return (
            "member_value_top_ranking",
            "Highest-scoring members under the registered value representation",
            "Shows the top member-value scores; ranking stability is evaluated separately by leave-one-dimension-out retention.",
        )

    if family == "ranking" and isinstance(result.get("ranking"), list) and result["ranking"]:
        ranking = sorted(result["ranking"], key=lambda item: int(item.get("rank", 999)), reverse=True)
        labels = [str(item["entity"]) for item in ranking]
        scores = [float(item["score"]) for item in ranking]
        axis.barh(labels, scores)
        axis.set_xlabel("TOPSIS closeness score")
        return (
            "mcdm_ranking",
            "Multi-criteria energy-profile ranking",
            "Shows the accepted entity ordering and TOPSIS closeness scores; criterion-deletion stability is reported separately in the result table.",
        )

    if family == "optimization" and solver_method == "retail_category_pricing_replenishment" and result.get("strategy"):
        strategy = list(result["strategy"])
        dates = sorted({str(item["date"]) for item in strategy})
        entities = sorted({str(item["entity"]) for item in strategy})
        for entity in entities:
            by_date = {str(item["date"]): float(item["replenishment_quantity"]) for item in strategy if str(item["entity"]) == entity}
            axis.plot(dates, [by_date.get(date, np.nan) for date in dates], marker="o", label=entity)
        axis.set_ylabel("Replenishment quantity (kg)")
        axis.tick_params(axis="x", rotation=35)
        axis.legend(ncol=2, fontsize="small")
        return (
            "retail_category_replenishment_plan",
            "Category replenishment plan for the future week",
            "Shows the executed seven-day replenishment decisions for every registered vegetable category; pricing decisions and validation remain in the evidence table.",
        )

    if family == "optimization" and solver_method == "retail_item_pricing_replenishment" and result.get("strategy"):
        strategy = sorted(result["strategy"], key=lambda item: float(item["replenishment_quantity"]))[-15:]
        labels = [str(item.get("item_name") or item.get("entity")) for item in strategy]
        values = [float(item["replenishment_quantity"]) for item in strategy]
        axis.barh(labels, values)
        axis.axvline(float(result.get("protocol", {}).get("minimum_display_quantity", 2.5)), linewidth=1)
        axis.set_xlabel("Replenishment quantity (kg)")
        return (
            "retail_item_replenishment_plan",
            "Largest item-level replenishment decisions for July 1",
            "Shows the largest replenishment quantities among the executed 27-33 item assortment; the complete item strategy is retained in the evidence table/artifact.",
        )

    if family == "optimization" and isinstance(result.get("solution"), dict) and result["solution"]:
        items = list(result["solution"].items())
        solution_keys = {str(name) for name, _value in items}
        labels = [str(name).replace("target_", "").replace("_", " ") for name, _value in items]
        values = [float(value) for _name, value in items]
        axis.barh(list(reversed(labels)), list(reversed(values)))
        if {"station_x", "shared_junction_y", "urban_boundary_crossing_y"}.issubset(solution_keys):
            axis.set_xlabel("Optimized geometric coordinate")
            return (
                "route_layout_geometry",
                "Optimal route-layout decision coordinates",
                "Shows the optimized station, shared-junction, and boundary-crossing coordinates that define the accepted route geometry.",
            )
        if solution_keys and all(name.startswith("target_") for name in solution_keys):
            axis.set_xlabel("Optimized target value")
            return (
                "optimization_targets",
                "Optimized decision target levels",
                "Shows the accepted target decision variables rather than only the optimizer objective value.",
            )
        axis.set_xlabel("Optimized decision-variable value")
        return (
            "optimization_solution",
            "Optimized decision-variable values",
            "Shows the accepted decision-variable values using labels derived from the executed result schema.",
        )

    axis.bar([item.metric for item in records], [item.value for item in records])
    axis.tick_params(axis="x", rotation=30)
    return (
        "metric_summary_fallback",
        f"{family} accepted result summary",
        "Fallback evidence summary used only when the executed family has no richer semantic plot schema yet.",
    )


def _result_type(family: str) -> str:
    return {
        "forecasting": "FORECAST",
        "classification": "CLASSIFICATION",
        "optimization": "OPTIMUM",
        "simulation": "SIMULATION",
        "ranking": "RANKING",
        "explanatory_inference": "EXPLANATORY",
        "distribution_forecasting": "DISTRIBUTION_FORECAST",
        "exploratory_analysis": "EXPLORATORY",
    }[family]


def _numeric_rows(family: str, result: dict[str, Any]) -> list[tuple[str, float, str, dict[str, Any]]]:
    rows: list[tuple[str, float, str, dict[str, Any]]] = []
    metrics = result.get("metrics")
    if isinstance(metrics, dict):
        for metric, value in metrics.items():
            if isinstance(value, (int, float)):
                direction = "MINIMIZE" if metric in {"rmse", "mae", "raw_simplex_error", "projected_simplex_error"} else "DESCRIPTIVE"
                rows.append((str(metric), float(value), direction, {}))
    if family == "forecasting" and isinstance(result.get("forecast"), dict):
        forecast = result["forecast"]
        rows.extend(
            [
                ("future_point", float(forecast["point"]), "DESCRIPTIVE", {"future": True}),
                ("future_interval_lower", float(forecast["interval"][0]), "DESCRIPTIVE", {"future": True}),
                ("future_interval_upper", float(forecast["interval"][1]), "DESCRIPTIVE", {"future": True}),
            ]
        )
    if family == "forecasting" and isinstance(result.get("trend_grid"), list):
        for item in result["trend_grid"]:
            metadata = {"entity": str(item["entity"]), "target": str(item["target"]), "trend": True}
            rows.extend(
                [
                    (f"annual_slope_{item['entity']}_{item['target']}", float(item["annual_slope"]), "DESCRIPTIVE", metadata),
                    (f"observed_change_{item['entity']}_{item['target']}", float(item["observed_change"]), "DESCRIPTIVE", metadata),
                ]
            )
    if family == "forecasting" and isinstance(result.get("forecast_grid"), list):
        for item in result["forecast_grid"]:
            metadata = {
                "future": True,
                "entity": str(item["entity"]),
                "target": str(item["target"]),
                "future_time": str(item["future_time"]),
            }
            metric_base = f"future_{item['entity']}_{item['target']}_{str(item['future_time'])[:4]}"
            rows.extend(
                [
                    (metric_base, float(item["point"]), "DESCRIPTIVE", metadata),
                    (metric_base + "_lower", float(item["interval"][0]), "DESCRIPTIVE", metadata),
                    (metric_base + "_upper", float(item["interval"][1]), "DESCRIPTIVE", metadata),
                ]
            )
    if family == "distribution_forecasting" and isinstance(result.get("future_distribution"), dict):
        rows.extend(
            (f"future_{column}", float(value), "DESCRIPTIVE", {"future": True, "component": column})
            for column, value in result["future_distribution"].items()
        )
    if family == "explanatory_inference" and result.get("effects") and str(result.get("solver_method") or "").lower() != "activation_promotion_association":
        lead = result["effects"][0]
        rows.append(
            (
                "leading_standardized_effect",
                float(lead["standardized_coefficient"]),
                "DESCRIPTIVE",
                {"feature": lead["feature"], "direction": lead.get("direction", "")},
            )
        )
    if family == "exploratory_analysis" and isinstance(result.get("profiles"), list):
        for item in result["profiles"]:
            for column, value in item.get("values", {}).items():
                rows.append(
                    (
                        f"profile_{item['entity']}_{column}",
                        float(value),
                        "DESCRIPTIVE",
                        {"entity": str(item["entity"]), "profile_dimension": str(column)},
                    )
                )
    if family == "exploratory_analysis" and str(result.get("solver_method") or "").lower() == "member_lifecycle_states":
        for item in list(result.get("state_profiles") or [])[:8]:
            rows.append(
                (
                    f"state_share_{item['state']}",
                    float(item["share"]),
                    "DESCRIPTIVE",
                    {"state": str(item["state"]), "state_count": int(item["count"])},
                )
            )
    if family == "exploratory_analysis" and str(result.get("solver_method") or "").lower() == "market_basket_association":
        top_rules = list(result.get("top_rules") or [])
        if top_rules:
            lead = top_rules[0]
            rows.extend(
                [
                    ("top_rule_support", float(lead["support"]), "DESCRIPTIVE", {"antecedent": lead["antecedent"], "consequent": lead["consequent"]}),
                    ("top_rule_confidence", float(lead["confidence"]), "DESCRIPTIVE", {"antecedent": lead["antecedent"], "consequent": lead["consequent"]}),
                    ("top_rule_lift", float(lead["lift"]), "DESCRIPTIVE", {"antecedent": lead["antecedent"], "consequent": lead["consequent"]}),
                ]
            )
    if family == "exploratory_analysis":
        associations = result.get("discoveries", {}).get("strongest_associations", [])
        if associations:
            lead = associations[0]
            rows.append(
                (
                    "strongest_spearman_r",
                    float(lead["spearman_r"]),
                    "DESCRIPTIVE",
                    {"left": lead["left"], "right": lead["right"]},
                )
            )
    if family == "optimization" and "objective_value" in result:
        rows.append(("objective_value", float(result["objective_value"]), "DESCRIPTIVE", {}))
        if isinstance(result.get("solution"), dict):
            rows.extend(
                (
                    f"solution_{name}",
                    float(value),
                    "DESCRIPTIVE",
                    {"decision_variable": str(name)},
                )
                for name, value in result["solution"].items()
            )
    if family == "ranking" and isinstance(result.get("ranking"), list) and str(result.get("solver_method") or "").lower() != "rfm_member_value":
        for item in result["ranking"]:
            rows.append(
                (
                    f"rank_score_{item['entity']}",
                    float(item["score"]),
                    "DESCRIPTIVE",
                    {"entity": str(item["entity"]), "rank": int(item["rank"])},
                )
            )
    if family == "simulation" and isinstance(result.get("scenarios"), dict):
        for scenario, values in result["scenarios"].items():
            rows.append((f"{scenario}_mean", float(values["mean"]), "DESCRIPTIVE", {"scenario": scenario}))

    # A solver may expose a value both in its generic metrics dictionary and in
    # a family-specific result schema. Keep one paper-facing row per metric so
    # renderer tables do not repeat the same objective/error value.
    deduplicated: list[tuple[str, float, str, dict[str, Any]]] = []
    seen_metrics: set[str] = set()
    for row in rows:
        metric = row[0]
        if metric in seen_metrics:
            continue
        seen_metrics.add(metric)
        deduplicated.append(row)
    return deduplicated

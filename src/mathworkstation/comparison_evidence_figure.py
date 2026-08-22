from __future__ import annotations

from pathlib import Path
from typing import Any

import matplotlib.pyplot as plt

from .io_utils import read_json
from .plot_style import finalize_publication_figure, get_publication_figsize, publication_context
from .figure_color_director import FigureColorDirector


class ComparisonEvidenceFigureService:
    """Turn accepted alternative-comparison evidence into paper figures.

    The service never runs a new model. It only visualizes ACTIVE
    ``subproblem_alternative_comparison`` artifacts that are already part of the
    accepted NarrativeGraph evidence lineage. This makes recent-corpus pressure
    for comparison/robustness figures evidence-safe instead of quota-driven.
    """

    def __init__(self, cases: Any, artifacts: Any, figures: Any) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.figures = figures
        self.color_director = FigureColorDirector()

    def ensure(self, case_id: str, graph: Any, *, profile_id: str) -> list[dict[str, Any]]:
        outputs: list[dict[str, Any]] = []
        root = self.cases.case_root(case_id)
        for node in graph.nodes:
            if getattr(node, "role", "") != "RESEARCH" or getattr(node, "alternative_comparison", None) is None:
                continue
            comparison_artifact = self._comparison_artifact(case_id, list(getattr(node, "source_artifact_ids", [])))
            if comparison_artifact is None:
                continue
            comparison_id = str(comparison_artifact["artifact_id"])
            payload = read_json(root / comparison_artifact["path"])
            specs = comparison_figure_specs(payload)
            if not specs:
                continue
            existing = {
                str((item.get("parameters") or {}).get("semantic_kind") or "")
                for item in self.figures.list_figures(case_id)
                if item.get("status") == "FINAL"
                and str((item.get("parameters") or {}).get("subproblem_id") or "") == str(node.subproblem_id)
                and comparison_id in item.get("source_artifact_ids", [])
            }
            for spec in specs:
                semantic_kind = str(spec["semantic_kind"])
                if semantic_kind in existing:
                    continue
                outputs.append(
                    self._render(
                        case_id,
                        str(node.subproblem_id),
                        str(node.task_family),
                        comparison_id,
                        spec,
                        profile_id=profile_id,
                    )
                )
        return outputs

    def _comparison_artifact(self, case_id: str, source_ids: list[str]) -> dict[str, Any] | None:
        for artifact_id in reversed(source_ids):
            try:
                artifact = self.artifacts.get(case_id, artifact_id)
            except KeyError:
                continue
            if artifact.get("status") == "ACTIVE" and artifact.get("artifact_type") == "subproblem_alternative_comparison":
                return artifact
        return None

    def _render(
        self,
        case_id: str,
        subproblem_id: str,
        task_family: str,
        comparison_artifact_id: str,
        spec: dict[str, Any],
        *,
        profile_id: str,
    ) -> dict[str, Any]:
        root = self.cases.case_root(case_id)
        directory = root / "figures" / "research_state" / "comparison"
        directory.mkdir(parents=True, exist_ok=True)
        semantic_kind = str(spec["semantic_kind"])
        png_path = directory / f"{subproblem_id}-{semantic_kind}.png"
        svg_path = png_path.with_suffix(".svg")
        profile = profile_id if profile_id in {"MCM_C", "CUMCM_C", "SCI_CLEAN"} else "SCI_CLEAN"
        with publication_context(profile):
            figure, axis = plt.subplots(figsize=get_publication_figsize(profile, "wide"))
            render_comparison_figure(axis, spec)
            color_selection = self.color_director.apply(
                axis,
                semantic_kind,
                identity=f"{case_id}:{subproblem_id}:{semantic_kind}",
            )
            finalize_publication_figure(
                figure,
                axis,
                chart_type=str(spec.get("chart_type") or "comparison"),
                title=str(spec["title"]),
                caption_first=True,
            )
            figure.savefig(png_path, dpi=600, bbox_inches="tight", facecolor="white")
            figure.savefig(svg_path, format="svg", bbox_inches="tight", facecolor="white")
            plt.close(figure)
        vector_artifact = self.artifacts.register_existing(
            case_id,
            svg_path.relative_to(root).as_posix(),
            "scientific_data_figure_vector",
            "comparison_evidence_figure",
            upstream=[comparison_artifact_id],
            paper_eligible=False,
        )
        return self.figures.register(
            case_id,
            png_path.relative_to(root).as_posix(),
            str(spec["title"]),
            [comparison_artifact_id, vector_artifact["artifact_id"]],
            "mathworkstation.comparison_evidence_figure:ComparisonEvidenceFigureService",
            {
                "subproblem_id": subproblem_id,
                "task_family": task_family,
                "semantic_kind": semantic_kind,
                "purpose": str(spec["purpose"]),
                "publication_profile": profile,
                "dpi": 600,
                "vector_source": True,
                "svg_artifact_id": vector_artifact["artifact_id"],
                "paper_role": "supplementary_evidence",
                "evidence_kind": "accepted_alternative_comparison",
                "caption_first": True,
                "palette_family": color_selection["family"],
                "palette_mode": color_selection["mode"],
            },
            None,
            status="FINAL",
        )


def comparison_figure_specs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Build plotting specs only from persisted comparison evidence."""

    specs: list[dict[str, Any]] = []
    accepted = payload.get("accepted") or {}
    alternatives = [item for item in payload.get("alternatives", []) if isinstance(item, dict)]
    primary_metric = str(payload.get("primary_metric") or accepted.get("metric") or "metric")
    direction = str(payload.get("metric_direction") or "").upper()
    runs = [accepted, *alternatives]
    comparable = [
        item
        for item in runs
        if item.get("method") and isinstance(item.get("value"), (int, float))
    ]
    if len(comparable) >= 2:
        specs.append(
            {
                "semantic_kind": "alternative_model_metric_comparison",
                "chart_type": "bar",
                "title": f"Executed alternative-model comparison on {primary_metric}",
                "purpose": (
                    "Compares the accepted method with explicitly executed, semantically compatible alternatives "
                    "using the same registered primary metric and validation protocol."
                ),
                "labels": [str(item["method"]) for item in comparable],
                "values": [float(item["value"]) for item in comparable],
                "ylabel": primary_metric,
                "direction": direction,
                "best_method": str(payload.get("best_method") or ""),
            }
        )

    stress_runs = [item for item in payload.get("stress_runs", []) if isinstance(item, dict)]
    series: list[dict[str, Any]] = []
    x_values: set[float] = set()
    for run in stress_runs:
        metric_by_test_size = run.get("metric_by_test_size") or {}
        if not isinstance(metric_by_test_size, dict) or len(metric_by_test_size) < 2:
            continue
        points: list[tuple[float, float]] = []
        for raw_x, raw_y in metric_by_test_size.items():
            try:
                x = float(raw_x)
                y = float(raw_y)
            except (TypeError, ValueError):
                continue
            points.append((x, y))
            x_values.add(x)
        if len(points) >= 2:
            points.sort()
            series.append(
                {
                    "method": str(run.get("method") or "method"),
                    "x": [point[0] for point in points],
                    "y": [point[1] for point in points],
                    "is_accepted": bool(run.get("is_accepted")),
                    "robustly_better": bool(run.get("robustly_better")),
                }
            )
    if len(series) >= 2 and len(x_values) >= 2:
        specs.append(
            {
                "semantic_kind": "alternative_model_stress_comparison",
                "chart_type": "line",
                "title": f"Model robustness across validation test sizes ({primary_metric})",
                "purpose": (
                    "Shows the already-executed stress comparison across registered validation test sizes, "
                    "so model choice is not justified by one split alone."
                ),
                "series": series,
                "xlabel": "Validation test fraction",
                "ylabel": primary_metric,
                "direction": direction,
                "robust_best_method": str(payload.get("robust_best_method") or ""),
            }
        )
    return specs


def render_comparison_figure(axis: Any, spec: dict[str, Any]) -> None:
    chart_type = str(spec.get("chart_type") or "")
    if chart_type == "bar":
        labels = list(spec.get("labels") or [])
        values = [float(value) for value in spec.get("values") or []]
        positions = list(range(len(labels)))
        axis.bar(positions, values)
        axis.set_xticks(positions)
        axis.set_xticklabels(labels, rotation=25, ha="right")
        axis.set_ylabel(str(spec.get("ylabel") or ""))
        best = str(spec.get("best_method") or "")
        if best and best in labels:
            index = labels.index(best)
            axis.annotate("best", (index, values[index]), xytext=(0, 7), textcoords="offset points", ha="center")
        return
    if chart_type == "line":
        for series in spec.get("series") or []:
            label = str(series.get("method") or "method")
            if series.get("is_accepted"):
                label += " (accepted)"
            axis.plot(series.get("x") or [], series.get("y") or [], marker="o", label=label)
        axis.set_xlabel(str(spec.get("xlabel") or ""))
        axis.set_ylabel(str(spec.get("ylabel") or ""))
        axis.legend()
        return
    raise ValueError(f"UNSUPPORTED_COMPARISON_FIGURE:{chart_type}")

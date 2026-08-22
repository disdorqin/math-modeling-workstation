from __future__ import annotations

from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss, recall_score
from sklearn.model_selection import train_test_split

from .io_utils import atomic_write_json, now_iso
from .retail_pricing import choose_simplest_supported_variant


ValidationGate = Literal["PASS", "REVIEW", "FAIL"]
ValidationSeverity = Literal["INFO", "REVIEW", "BLOCK"]


class ValidationProtocol(BaseModel):
    model_config = ConfigDict(extra="forbid")

    protocol_id: str
    family: str
    name: str
    split_requirement: str
    required_metrics: list[str] = Field(default_factory=list)
    invariants: list[str] = Field(default_factory=list)
    robustness_checks: list[str] = Field(default_factory=list)


class ValidationFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    severity: ValidationSeverity
    code: str
    detail: str


class ValidationAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str | None = None
    subproblem_id: str | None = None
    protocol_id: str
    family: str
    gate: ValidationGate
    findings: list[ValidationFinding] = Field(default_factory=list)
    metrics: dict[str, Any] = Field(default_factory=dict)
    generated_at: str


class ValidationProtocolRegistry:
    """Single source of truth for task-appropriate validation semantics."""

    def resolve(self, family: str, plan: dict[str, Any]) -> ValidationProtocol:
        if family == "forecasting":
            method = str(plan.get("solver_method") or "").lower()
            if method in {"panel_trend", "panel_trend_characterization", "panel_linear_trend"}:
                return ValidationProtocol(
                    protocol_id="forecasting.panel-trend-characterization.v1",
                    family=family,
                    name="Entity-wise historical trend characterization with temporal holdout",
                    split_requirement="same temporal holdout fraction applied independently within each entity",
                    required_metrics=["rmse", "mae"],
                    invariants=["time unique within entity", "no cross-entity leakage", "trend summary emitted for every entity-target series"],
                    robustness_checks=["holdout error reported", "trend direction and magnitude derived only from observed history"],
                )
            if method in {"panel_holt", "panel_holt_exponential_smoothing", "panel_forecast"}:
                return ValidationProtocol(
                    protocol_id="forecasting.panel-temporal-uncertainty.v1",
                    family=family,
                    name="Grouped temporal forecast validation with entity-wise uncertainty guard",
                    split_requirement="same temporal holdout fraction applied independently within each entity",
                    required_metrics=["rmse", "mae"],
                    invariants=["time unique within entity", "no cross-entity leakage", "leakage_check=PASS"],
                    robustness_checks=["future interval present for every entity-target-horizon forecast", "interval bounds ordered"],
                )
            return ValidationProtocol(
                protocol_id="forecasting.temporal-uncertainty.v1",
                family=family,
                name="Temporal forecast validation with leakage and uncertainty guard",
                split_requirement="temporal holdout / rolling origin only",
                required_metrics=["rmse", "mae"],
                invariants=["time ordered", "no duplicate timestamps", "leakage_check=PASS"],
                robustness_checks=["future interval present when requested", "interval bounds ordered"],
            )
        if family == "classification":
            return ValidationProtocol(
                protocol_id="classification.stratified-calibration.v1",
                family=family,
                name="Stratified classification validation with class-wise and calibration checks",
                split_requirement="stratified holdout unless a temporal classification protocol is explicitly registered",
                required_metrics=["accuracy", "macro_f1", "balanced_accuracy"],
                invariants=["confusion matrix present", "at least two classes"],
                robustness_checks=["per-class recall", "multiclass log loss", "confidence calibration error"],
            )
        if family == "explanatory_inference":
            method = str(plan.get("solver_method") or "").lower().replace("-", "_").replace(" ", "_")
            if method in {"activation_promotion_association", "member_activation_rate", "promotion_activation_bootstrap"}:
                return ValidationProtocol(
                    protocol_id="inference.activation-promotion-bootstrap.v1",
                    family=family,
                    name="Member activation-rate association with temporal transitions and bootstrap uncertainty",
                    split_requirement="state transitions must be formed from ordered non-overlapping time windows",
                    required_metrics=[
                        "transition_count",
                        "activation_rate",
                        "promotion_activation_rate",
                        "nonpromotion_activation_rate",
                        "promotion_rate_difference",
                    ],
                    invariants=[
                        "activation rates lie in [0,1]",
                        "promotion and non-promotion groups are both observed",
                        "associational_not_causal guard",
                    ],
                    robustness_checks=["bootstrap CI for promotion rate difference", "minimum transition count"],
                )
            return ValidationProtocol(
                protocol_id="inference.bootstrap-effects.v1",
                family=family,
                name="Association/effect validation with bootstrap intervals",
                split_requirement="temporal holdout when time is declared; otherwise deterministic holdout",
                required_metrics=["rmse", "mae", "r2"],
                invariants=["associational_not_causal guard", "bootstrap CI for every effect"],
                robustness_checks=["effect sign/interval stability", "feature specification caveat"],
            )
        if family == "distribution_forecasting":
            return ValidationProtocol(
                protocol_id="distribution.temporal-simplex.v1",
                family=family,
                name="Temporal multi-output distribution validation",
                split_requirement="temporal holdout",
                required_metrics=["mae", "rmse", "projected_simplex_error"],
                invariants=["non-negative projected distribution", "components sum to configured total"],
                robustness_checks=["future component uncertainty when future prediction requested"],
            )
        if family == "exploratory_analysis" and str(plan.get("solver_method", "")).lower() in {"member_group_profile", "member consumption profile", "member_nonmember_consumption_comparison"}:
            return ValidationProtocol(
                protocol_id="exploration.member-group-profile.v1",
                family=family,
                name="Member versus non-member consumption-profile completeness check",
                split_requirement="not applicable; both groups are summarized on the same transaction schema and observation period",
                required_metrics=["entity_count", "profile_dimension_count", "row_count"],
                invariants=["exactly two comparison groups", "shared profile dimensions", "non-negative retained transaction amounts"],
                robustness_checks=["group transaction counts reported", "sales-share accounting"],
            )
        if family == "exploratory_analysis" and str(plan.get("solver_method", "")).lower() in {"member_lifecycle_states", "lifecycle_state_segmentation", "rfm_lifecycle_clustering"}:
            return ValidationProtocol(
                protocol_id="exploration.member-lifecycle-stability.v1",
                family=family,
                name="Lifecycle-state segmentation with separation and seed-stability checks",
                split_requirement="unsupervised member-level fit on a fixed observation window",
                required_metrics=["member_count", "state_count", "silhouette", "seed_adjusted_rand"],
                invariants=["at least two lifecycle states", "every retained member receives exactly one state"],
                robustness_checks=["silhouette separation", "adjusted Rand agreement under a second seed"],
            )
        if family == "exploratory_analysis" and str(plan.get("solver_method", "")).lower() in {"market_basket_association", "association_rules", "pairwise_basket_lift"}:
            return ValidationProtocol(
                protocol_id="exploration.market-basket-association.v1",
                family=family,
                name="Market-basket association validation with support, confidence, and lift semantics",
                split_requirement="transaction baskets are deduplicated before pair counting",
                required_metrics=["transaction_count", "unique_item_count", "rule_count", "max_lift"],
                invariants=["support and confidence lie in [0,1]", "lift is non-negative", "rules are supported by observed baskets"],
                robustness_checks=["minimum support count enforced", "large-basket filtering is reported"],
            )
        if family == "exploratory_analysis" and str(plan.get("solver_method", "")).lower() in {"panel_profile", "panel_profile_summary", "group_profile_summary"}:
            return ValidationProtocol(
                protocol_id="exploration.panel-profile-summary.v1",
                family=family,
                name="Panel profile completeness and comparability validation",
                split_requirement="not applicable; compare entities at a common registered reference time",
                required_metrics=["entity_count", "profile_dimension_count"],
                invariants=["one profile row per entity at reference time", "same profile dimensions for all entities"],
                robustness_checks=["history span reported", "no missing reference-time profile values"],
            )
        if family == "exploratory_analysis" and str(plan.get("solver_method", "")).lower() in {"kmeans", "k-means", "dbscan"}:
            return ValidationProtocol(
                protocol_id="exploration.clustering-stability.v1",
                family=family,
                name="Clustering validity and stability checks",
                split_requirement="unsupervised full-sample fit with explicit stability diagnostics",
                required_metrics=[],
                invariants=["cluster count reported", "noise count reported for density clustering"],
                robustness_checks=["silhouette when at least two clusters", "cluster-size audit"],
            )
        if family == "exploratory_analysis":
            return ValidationProtocol(
                protocol_id="exploration.discovery-bootstrap.v1",
                family=family,
                name="Exploratory discovery with bootstrap stability confirmation",
                split_requirement="exploration may use full sample; confirm leading pattern by resampling",
                required_metrics=[],
                invariants=["exploratory findings are hypothesis-generating, not confirmatory"],
                robustness_checks=["bootstrap sign stability for strongest association", "outlier/change-pattern audit"],
            )
        if family == "optimization":
            method = str(plan.get("solver_method", "bounded_grid")).lower()
            if method in {"linear_programming", "lp", "milp", "integer_programming", "mixed_integer_programming"}:
                suffix = "exact-linear"
            elif method in {"pipeline_layout_continuous", "pipeline layout continuous"}:
                suffix = "continuous-geometry"
            elif method in {"retail_category_pricing_replenishment", "retail_item_pricing_replenishment", "demand_aware_pricing_replenishment"}:
                suffix = "retail-pricing-replenishment"
            else:
                suffix = "bounded-grid"
            return ValidationProtocol(
                protocol_id=f"optimization.{suffix}.v1",
                family=family,
                name="Optimization feasibility and solver-status validation",
                split_requirement="not applicable",
                required_metrics=[],
                invariants=["all constraints satisfied", "variable bounds satisfied"],
                robustness_checks=["solver termination status", "scenario/RHS sensitivity required before strong policy claims"],
            )
        if family == "simulation":
            return ValidationProtocol(
                protocol_id="simulation.replication-uncertainty.v1",
                family=family,
                name="Seeded replication and uncertainty validation",
                split_requirement="not applicable",
                required_metrics=[],
                invariants=["replications >= 2", "seed recorded", "uncertainty interval reported"],
                robustness_checks=["scenario comparison", "replication/seed sensitivity"],
            )
        if family == "ranking":
            method = str(plan.get("solver_method") or plan.get("protocol") or "").lower()
            if method in {"rfm_member_value", "rfm member value", "rfmt member value", "rfms member value", "member value scoring"}:
                return ValidationProtocol(
                    protocol_id="ranking.rfm-member-value-stability.v1",
                    family=family,
                    name="Member-value scoring with explicit representation, normalized weights, and top-segment stability",
                    split_requirement="not applicable; scoring uses the fixed admissible observation window",
                    required_metrics=["member_count", "score_dimension_count", "top_decile_stability", "median_score", "top_decile_threshold"],
                    invariants=["weights sum to one", "recency direction is cost while value dimensions are benefit", "one score per retained member"],
                    robustness_checks=["leave-one-dimension-out top-decile retention"],
                )
            if method in {"entropy_topsis", "entropy-topsis", "topsis", "mcdm"}:
                return ValidationProtocol(
                    protocol_id="ranking.entropy-topsis-stability.v1",
                    family=family,
                    name="Multi-criteria TOPSIS weight and rank-stability validation",
                    split_requirement="not applicable; criterion directions and entity semantics must be explicit",
                    required_metrics=["winner_retention_rate", "mean_spearman"],
                    invariants=["weights sum to one", "all criteria have benefit/cost direction", "one row per entity"],
                    robustness_checks=["leave-one-criterion-out winner retention", "rank correlation under criterion deletion"],
                )
            return ValidationProtocol(
                protocol_id="ranking.protocol-stability.v1",
                family=family,
                name="Ranking protocol and stability validation",
                split_requirement="pairwise or listwise protocol must be explicit",
                required_metrics=["mrr", "ndcg_at_k", "pairwise_accuracy"],
                invariants=["query/item/relevance/score semantics fixed"],
                robustness_checks=["rank stability / weight sensitivity before strong ordering claims"],
            )
        raise ValueError(f"VALIDATION_PROTOCOL_UNAVAILABLE:{family}")


class ValidationRunner:
    def __init__(self, registry: ValidationProtocolRegistry | None = None) -> None:
        self.registry = registry or ValidationProtocolRegistry()

    def assess(
        self,
        family: str,
        plan: dict[str, Any],
        result: dict[str, Any],
        diagnostics: dict[str, Any],
        frame: pd.DataFrame | None = None,
        *,
        case_id: str | None = None,
        subproblem_id: str | None = None,
    ) -> ValidationAssessment:
        protocol = self.registry.resolve(family, plan)
        findings: list[ValidationFinding] = []
        metrics: dict[str, Any] = {}
        self._required_metrics(protocol, result, findings)
        checker = getattr(self, f"_check_{family}")
        checker(plan, result, diagnostics, frame, findings, metrics)
        gate: ValidationGate
        if any(item.severity == "BLOCK" for item in findings):
            gate = "FAIL"
        elif any(item.severity == "REVIEW" for item in findings):
            gate = "REVIEW"
        else:
            gate = "PASS"
        return ValidationAssessment(
            case_id=case_id,
            subproblem_id=subproblem_id,
            protocol_id=protocol.protocol_id,
            family=family,
            gate=gate,
            findings=findings,
            metrics=metrics,
            generated_at=now_iso(),
        )

    def persist(
        self,
        cases: Any,
        artifacts: Any,
        case_id: str,
        subproblem_id: str,
        assessment: ValidationAssessment,
        source_artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        root = cases.case_root(case_id)
        path = root / "results" / "validation" / subproblem_id / "assessment.json"
        atomic_write_json(path, assessment.model_dump(mode="json"))
        artifact = artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "validation_assessment",
            "validation_protocol",
            upstream=list(source_artifact_ids or []),
            paper_eligible=False,
        )
        return {"assessment": assessment, "artifact": artifact}

    def _required_metrics(
        self,
        protocol: ValidationProtocol,
        result: dict[str, Any],
        findings: list[ValidationFinding],
    ) -> None:
        metrics = result.get("metrics", {})
        for metric in protocol.required_metrics:
            if metric not in metrics:
                findings.append(
                    ValidationFinding(
                        severity="BLOCK",
                        code="VALIDATION_METRIC_MISSING",
                        detail=f"{protocol.protocol_id} requires metric {metric}.",
                    )
                )

    def _check_forecasting(self, plan, result, diagnostics, frame, findings, metrics) -> None:
        split = str(result.get("protocol", {}).get("split", ""))
        method = str(plan.get("solver_method") or "").lower()
        panel = method in {
            "panel_holt",
            "panel_holt_exponential_smoothing",
            "panel_forecast",
            "panel_trend",
            "panel_trend_characterization",
            "panel_linear_trend",
        }
        panel_trend = method in {"panel_trend", "panel_trend_characterization", "panel_linear_trend"}
        allowed_splits = {"panel_temporal_holdout"} if panel else {"temporal", "temporal_holdout", "rolling_origin"}
        if split not in allowed_splits:
            findings.append(_block("FORECAST_SPLIT_NOT_TEMPORAL", f"unexpected split={split}"))
        if result.get("leakage_check") != "PASS":
            findings.append(_block("FORECAST_LEAKAGE_GUARD_FAILED", "leakage_check is not PASS"))
        if frame is not None and plan.get("time_column") in frame.columns:
            timestamps = pd.to_datetime(frame[plan["time_column"]], errors="coerce")
            if timestamps.isna().any():
                findings.append(_block("FORECAST_TIME_INDEX_INVALID", "timestamps contain NaT"))
            elif panel:
                entity_column = str(plan.get("group_column") or "")
                if not entity_column or entity_column not in frame.columns:
                    findings.append(_block("FORECAST_GROUP_COLUMN_INVALID", "panel forecast requires a valid group_column"))
                elif frame[[entity_column, plan["time_column"]]].duplicated().any():
                    findings.append(_block("FORECAST_TIME_INDEX_INVALID", "timestamps duplicate within an entity"))
            elif timestamps.duplicated().any():
                findings.append(_block("FORECAST_TIME_INDEX_INVALID", "timestamps contain duplicates"))
        if panel_trend:
            trends = result.get("trend_grid")
            if not isinstance(trends, list) or not trends:
                findings.append(_block("FORECAST_PANEL_TREND_MISSING", "panel trend characterization requires entity-target trend outputs"))
            else:
                metrics["panel_trend_count"] = len(trends)
            return
        if panel:
            grid = result.get("forecast_grid")
            if not isinstance(grid, list) or not grid:
                findings.append(_block("FORECAST_PANEL_GRID_MISSING", "panel forecast requires entity-target-horizon outputs"))
                return
            invalid = 0
            widths: list[float] = []
            for item in grid:
                interval = item.get("interval") if isinstance(item, dict) else None
                if not isinstance(interval, list) or len(interval) != 2:
                    invalid += 1
                    continue
                lower, upper = map(float, interval)
                point = float(item.get("point", np.nan))
                if lower > upper or not lower <= point <= upper:
                    invalid += 1
                else:
                    widths.append(upper - lower)
            metrics["panel_forecast_count"] = len(grid)
            metrics["mean_interval_width"] = float(np.mean(widths)) if widths else 0.0
            if invalid:
                findings.append(_block("FORECAST_PANEL_INTERVAL_INVALID", f"invalid interval count={invalid}"))
            return
        if plan.get("future_time") is not None:
            forecast = result.get("forecast") or {}
            interval = forecast.get("interval")
            if not isinstance(interval, list) or len(interval) != 2:
                findings.append(_block("FORECAST_INTERVAL_MISSING", "future forecast requires a two-sided interval"))
            else:
                lower, upper = map(float, interval)
                point = float(forecast.get("point", np.nan))
                metrics["interval_width"] = upper - lower
                metrics["point_inside_interval"] = bool(lower <= point <= upper)
                if lower > upper or not lower <= point <= upper:
                    findings.append(_block("FORECAST_INTERVAL_INVALID", "point forecast is not inside ordered interval"))

    def _check_classification(self, plan, result, diagnostics, frame, findings, metrics) -> None:
        if str(result.get("protocol", {}).get("split", "")) != "stratified_holdout":
            findings.append(_block("CLASSIFICATION_SPLIT_NOT_STRATIFIED", "classification baseline must use stratified holdout"))
        if not result.get("confusion_matrix"):
            findings.append(_block("CLASSIFICATION_CONFUSION_MISSING", "confusion matrix is required"))
        stored_probabilities = result.get("holdout_probabilities")
        stored_actual = result.get("holdout_actual")
        probability_labels = result.get("probability_labels")
        if stored_probabilities is not None and stored_actual is not None and probability_labels:
            probabilities = np.asarray(stored_probabilities, dtype=float)
            actual = np.asarray([str(value) for value in stored_actual])
            labels = np.asarray([str(value) for value in probability_labels])
            if probabilities.ndim != 2 or probabilities.shape[0] != len(actual) or probabilities.shape[1] != len(labels):
                findings.append(_block("CLASSIFICATION_PROBABILITY_SHAPE_INVALID", "stored holdout probabilities do not match labels/actual rows"))
                return
            predicted = labels[np.argmax(probabilities, axis=1)]
            recalls = recall_score(actual, predicted, labels=labels, average=None, zero_division=0)
            metrics["per_class_recall"] = {
                str(label): float(value) for label, value in zip(labels, recalls, strict=True)
            }
            metrics["log_loss"] = float(log_loss(actual, probabilities, labels=labels))
            metrics["calibration_ece"] = _confidence_ece(actual, predicted, probabilities)
            metrics["probability_source"] = "executed_solver_holdout"
            if metrics["calibration_ece"] > 0.20:
                findings.append(_review("CLASSIFICATION_CALIBRATION_WEAK", f"ECE={metrics['calibration_ece']:.3f}"))
            return
        if frame is None:
            findings.append(_review("CLASSIFICATION_CALIBRATION_NOT_RECHECKED", "frame unavailable for independent probability validation"))
            return
        target = str(plan.get("target_column") or "")
        features = [str(value) for value in plan.get("feature_columns", [])]
        if not target or not features:
            findings.append(_block("CLASSIFICATION_VALIDATION_SCHEMA_MISSING", "target/features unavailable"))
            return
        data = frame[[*features, target]].dropna().reset_index(drop=True)
        seed = int(plan.get("random_seed", 42))
        test_rows = max(1, int(round(len(data) * float(plan.get("test_size", 0.2)))))
        indices = np.arange(len(data))
        stratify = data[target] if data[target].value_counts().min() >= 2 and test_rows >= data[target].nunique() else None
        train_idx, test_idx = train_test_split(indices, test_size=test_rows, random_state=seed, stratify=stratify)
        encoded = pd.get_dummies(data[features], drop_first=False, dtype=float)
        model = LogisticRegression(max_iter=2000, random_state=seed)
        model.fit(encoded.iloc[train_idx], data[target].iloc[train_idx])
        probabilities = model.predict_proba(encoded.iloc[test_idx])
        predicted = model.classes_[np.argmax(probabilities, axis=1)]
        actual = data[target].iloc[test_idx].to_numpy()
        recalls = recall_score(actual, predicted, labels=model.classes_, average=None, zero_division=0)
        metrics["per_class_recall"] = {str(label): float(value) for label, value in zip(model.classes_, recalls, strict=True)}
        metrics["log_loss"] = float(log_loss(actual, probabilities, labels=model.classes_))
        metrics["calibration_ece"] = _confidence_ece(actual, predicted, probabilities)
        if metrics["calibration_ece"] > 0.20:
            findings.append(_review("CLASSIFICATION_CALIBRATION_WEAK", f"ECE={metrics['calibration_ece']:.3f}"))

    def _check_explanatory_inference(self, plan, result, diagnostics, frame, findings, metrics) -> None:
        method = str(result.get("solver_method", plan.get("solver_method", ""))).lower()
        split = str(result.get("protocol", {}).get("split", ""))
        if method == "activation_promotion_association":
            if split != "temporal_state_transitions":
                findings.append(_block("ACTIVATION_TRANSITION_PROTOCOL_INVALID", f"split={split}"))
            if result.get("interpretation_guard") != "associational_not_causal":
                findings.append(_block("INFERENCE_CAUSALITY_GUARD_MISSING", "promotion association may not be described as causal"))
            values = result.get("metrics", {})
            transition_count = int(values.get("transition_count", 0))
            metrics["transition_count"] = transition_count
            for key in ("activation_rate", "promotion_activation_rate", "nonpromotion_activation_rate"):
                value = float(values.get(key, np.nan))
                metrics[key] = value
                if not np.isfinite(value) or not 0.0 <= value <= 1.0:
                    findings.append(_block("ACTIVATION_RATE_INVALID", f"{key}={value}"))
            effects = result.get("effects", [])
            if not effects or len(effects[0].get("bootstrap_ci_95", [])) != 2:
                findings.append(_block("ACTIVATION_BOOTSTRAP_CI_MISSING", "promotion rate difference requires a two-sided bootstrap CI"))
            runs = int(result.get("protocol", {}).get("bootstrap_runs", 0))
            metrics["bootstrap_runs"] = runs
            metrics["promotion_rate_difference"] = float(values.get("promotion_rate_difference", np.nan))
            if transition_count < 20:
                findings.append(_review("ACTIVATION_TRANSITIONS_LOW", f"transition_count={transition_count}"))
            if runs < 100:
                findings.append(_review("INFERENCE_BOOTSTRAP_RUNS_LOW", f"bootstrap_runs={runs}"))
            return
        if plan.get("split_strategy") == "temporal" and split != "temporal_holdout":
            findings.append(_block("INFERENCE_TEMPORAL_SPLIT_MISMATCH", f"split={split}"))
        if result.get("interpretation_guard") != "associational_not_causal":
            findings.append(_block("INFERENCE_CAUSALITY_GUARD_MISSING", "effect estimates may not be described as causal"))
        effects = result.get("effects", [])
        if not effects or any(len(item.get("bootstrap_ci_95", [])) != 2 for item in effects):
            findings.append(_block("INFERENCE_BOOTSTRAP_CI_MISSING", "every effect requires a bootstrap CI"))
        runs = int(result.get("protocol", {}).get("bootstrap_runs", 0))
        metrics["bootstrap_runs"] = runs
        metrics["stable_effect_count"] = sum(bool(item.get("interval_excludes_zero")) for item in effects)
        if runs < 100:
            findings.append(_review("INFERENCE_BOOTSTRAP_RUNS_LOW", f"bootstrap_runs={runs}"))

    def _check_distribution_forecasting(self, plan, result, diagnostics, frame, findings, metrics) -> None:
        if str(result.get("protocol", {}).get("split", "")) != "temporal_holdout":
            findings.append(_block("DISTRIBUTION_SPLIT_NOT_TEMPORAL", "distribution forecast must use temporal holdout"))
        simplex_error = float(result.get("metrics", {}).get("projected_simplex_error", np.inf))
        metrics["projected_simplex_error"] = simplex_error
        if simplex_error > 1e-8:
            findings.append(_block("DISTRIBUTION_SIMPLEX_FAILED", f"projected simplex error={simplex_error}"))
        future = result.get("future_distribution")
        if plan.get("future_features") is not None:
            if not isinstance(future, dict) or not future:
                findings.append(_block("DISTRIBUTION_FUTURE_MISSING", "future distribution required"))
            else:
                total = float(result.get("protocol", {}).get("distribution_total", 100.0))
                observed_total = float(sum(float(value) for value in future.values()))
                metrics["future_distribution_total"] = observed_total
                if abs(observed_total - total) > 1e-6 or any(float(value) < -1e-10 for value in future.values()):
                    findings.append(_block("DISTRIBUTION_FUTURE_SIMPLEX_FAILED", f"sum={observed_total}, expected={total}"))
            uncertainty = result.get("future_uncertainty_95")
            if not isinstance(uncertainty, dict) or not uncertainty:
                findings.append(_block("DISTRIBUTION_UNCERTAINTY_MISSING", "future component uncertainty required"))

    def _check_exploratory_analysis(self, plan, result, diagnostics, frame, findings, metrics) -> None:
        method = str(result.get("solver_method", plan.get("solver_method", ""))).lower()
        if method == "member_group_profile":
            profiles = list(result.get("profiles") or [])
            values = result.get("metrics", {})
            entity_count = int(values.get("entity_count", 0))
            dimension_count = int(values.get("profile_dimension_count", 0))
            metrics.update({
                "entity_count": entity_count,
                "profile_dimension_count": dimension_count,
                "row_count": int(values.get("row_count", 0)),
            })
            if entity_count != 2 or len(profiles) != 2:
                findings.append(_block("MEMBER_PROFILE_GROUP_COUNT_INVALID", f"groups={len(profiles)}"))
            if dimension_count < 3 or any(len(item.get("values", {})) != dimension_count for item in profiles):
                findings.append(_block("MEMBER_PROFILE_DIMENSION_MISMATCH", f"dimensions={dimension_count}"))
            shares = [float(item.get("values", {}).get("sales_share", np.nan)) for item in profiles]
            if len(shares) == 2 and (not all(np.isfinite(shares)) or abs(sum(shares) - 1.0) > 1e-6):
                findings.append(_block("MEMBER_PROFILE_SALES_SHARE_INVALID", f"sales_share_sum={sum(shares):.6g}"))
            return
        if method == "member_lifecycle_states":
            profiles = list(result.get("state_profiles") or [])
            assignments = list(result.get("member_states") or [])
            values = result.get("metrics", {})
            member_count = int(values.get("member_count", 0))
            state_count = int(values.get("state_count", 0))
            silhouette = float(values.get("silhouette", np.nan))
            seed_ari = float(values.get("seed_adjusted_rand", np.nan))
            metrics.update({
                "member_count": member_count,
                "state_count": state_count,
                "silhouette": silhouette,
                "seed_adjusted_rand": seed_ari,
            })
            if state_count < 2 or len(profiles) != state_count:
                findings.append(_block("LIFECYCLE_STATE_COUNT_INVALID", f"states={state_count}"))
            if len(assignments) != member_count:
                findings.append(_block("LIFECYCLE_ASSIGNMENT_COVERAGE_INVALID", f"assignments={len(assignments)}, members={member_count}"))
            if not np.isfinite(silhouette) or silhouette <= 0:
                findings.append(_review("LIFECYCLE_SEPARATION_WEAK", f"silhouette={silhouette:.3f}"))
            if not np.isfinite(seed_ari) or seed_ari < 0.8:
                findings.append(_review("LIFECYCLE_SEED_STABILITY_WEAK", f"adjusted_rand={seed_ari:.3f}"))
            return
        if method == "market_basket_association":
            rules = list(result.get("top_rules") or [])
            values = result.get("metrics", {})
            transaction_count = int(values.get("transaction_count", 0))
            rule_count = int(values.get("rule_count", 0))
            max_lift = float(values.get("max_lift", 0.0))
            metrics.update({
                "transaction_count": transaction_count,
                "unique_item_count": int(values.get("unique_item_count", 0)),
                "rule_count": rule_count,
                "max_lift": max_lift,
                "skipped_large_baskets": int(values.get("skipped_large_baskets", 0)),
            })
            if transaction_count < 10:
                findings.append(_block("MARKET_BASKET_TRANSACTIONS_INSUFFICIENT", f"transactions={transaction_count}"))
            if rule_count < 1 or not rules:
                findings.append(_review("MARKET_BASKET_NO_RULE", "no rule meets the registered support/confidence threshold"))
            for rule in rules:
                support = float(rule.get("support", np.nan))
                confidence = float(rule.get("confidence", np.nan))
                lift = float(rule.get("lift", np.nan))
                if not (np.isfinite(support) and 0 <= support <= 1 and np.isfinite(confidence) and 0 <= confidence <= 1 and np.isfinite(lift) and lift >= 0):
                    findings.append(_block("MARKET_BASKET_RULE_METRIC_INVALID", str(rule)))
                    break
            return
        if method in {"panel_profile", "panel_profile_summary", "group_profile_summary"}:
            profiles = result.get("profiles") or []
            expected_entities = int((result.get("metrics") or {}).get("entity_count", 0))
            expected_dimensions = int((result.get("metrics") or {}).get("profile_dimension_count", 0))
            metrics["entity_count"] = expected_entities
            metrics["profile_dimension_count"] = expected_dimensions
            if expected_entities < 2 or len(profiles) != expected_entities:
                findings.append(_block("PANEL_PROFILE_ENTITY_COVERAGE_INVALID", f"entities={len(profiles)}, expected={expected_entities}"))
            if expected_dimensions < 2:
                findings.append(_block("PANEL_PROFILE_DIMENSIONS_INSUFFICIENT", f"dimensions={expected_dimensions}"))
            if any(len((item or {}).get("values", {})) != expected_dimensions for item in profiles):
                findings.append(_block("PANEL_PROFILE_DIMENSION_MISMATCH", "entities do not share the same complete profile schema"))
            return
        if method in {"kmeans", "dbscan"}:
            cluster_count = int(result.get("cluster_count", 0))
            metrics["cluster_count"] = cluster_count
            metrics["silhouette"] = result.get("silhouette")
            if cluster_count < 1:
                findings.append(_block("CLUSTERING_NO_CLUSTER", "no non-noise cluster found"))
            elif cluster_count < 2:
                findings.append(_review("CLUSTERING_SINGLE_CLUSTER", "only one cluster found; separation is not established"))
            return
        discoveries = result.get("discoveries", {})
        associations = discoveries.get("strongest_associations", [])
        if not associations:
            findings.append(_review("EXPLORATION_NO_ASSOCIATION", "no finite leading association to confirm"))
            return
        if frame is None:
            findings.append(_review("EXPLORATION_STABILITY_NOT_RECHECKED", "frame unavailable for bootstrap confirmation"))
            return
        lead = associations[0]
        left, right = str(lead["left"]), str(lead["right"])
        if left not in frame.columns or right not in frame.columns:
            findings.append(_block("EXPLORATION_LEAD_COLUMNS_MISSING", f"{left},{right}"))
            return
        pair = frame[[left, right]].apply(pd.to_numeric, errors="coerce").dropna().reset_index(drop=True)
        runs = int(plan.get("validation_bootstrap_runs", 100))
        if len(pair) < 10 or runs < 20:
            findings.append(_review("EXPLORATION_BOOTSTRAP_INSUFFICIENT", f"rows={len(pair)}, runs={runs}"))
            return
        seed = int(plan.get("random_seed", 42))
        rng = np.random.default_rng(seed)
        original = float(pair.corr(method="spearman").iloc[0, 1])
        signs = []
        magnitudes = []
        for _ in range(runs):
            indices = rng.integers(0, len(pair), size=len(pair))
            sample = pair.iloc[indices]
            value = float(sample.corr(method="spearman").iloc[0, 1])
            if np.isfinite(value):
                signs.append(np.sign(value) == np.sign(original))
                magnitudes.append(abs(value))
        stability = float(np.mean(signs)) if signs else 0.0
        metrics["leading_association_sign_stability"] = stability
        metrics["leading_association_bootstrap_median_abs_r"] = float(np.median(magnitudes)) if magnitudes else 0.0
        metrics["validation_bootstrap_runs"] = runs
        if stability < 0.8:
            findings.append(_review("EXPLORATION_ASSOCIATION_UNSTABLE", f"sign stability={stability:.3f}"))

    def _check_optimization(self, plan, result, diagnostics, frame, findings, metrics) -> None:
        if result.get("constraint_status") != "PASS":
            findings.append(_block("OPTIMIZATION_CONSTRAINTS_FAILED", "reported solution violates constraints"))
        method = str(result.get("solver_method", plan.get("solver_method", "bounded_grid"))).lower()
        metrics["solver_method"] = method
        if method in {"linear_programming", "milp"} and int(result.get("solver_status", -1)) != 0:
            findings.append(_block("OPTIMIZATION_SOLVER_STATUS_FAILED", f"solver_status={result.get('solver_status')}"))
        if method in {"linear_programming", "milp"}:
            findings.append(_review("OPTIMIZATION_SENSITIVITY_PENDING", "strong decision claims should include RHS/objective sensitivity in a later validation pass"))
        if method == "pipeline_layout_continuous":
            if int(result.get("solver_status", -1)) != 0:
                findings.append(_block("PIPELINE_OPTIMIZATION_SOLVER_STATUS_FAILED", f"solver_status={result.get('solver_status')}"))
            runs = result.get("sensitivity_runs", [])
            metrics["sensitivity_runs"] = len(runs) if isinstance(runs, list) else 0
            if not isinstance(runs, list) or len(runs) < 2:
                findings.append(_review("PIPELINE_SURCHARGE_SENSITIVITY_MISSING", "continuous pipeline layout requires surcharge sensitivity before accepting the route recommendation"))
        if method in {"retail_category_pricing_replenishment", "retail_item_pricing_replenishment"}:
            if int(result.get("solver_status", -1)) != 0:
                findings.append(_block("RETAIL_OPTIMIZATION_SOLVER_STATUS_FAILED", f"solver_status={result.get('solver_status')}"))
            strategy = result.get("strategy")
            if not isinstance(strategy, list) or not strategy:
                findings.append(_block("RETAIL_STRATEGY_MISSING", "pricing/replenishment optimizer must emit an auditable strategy grid"))
                return
            metrics["strategy_rows"] = len(strategy)
            if method == "retail_category_pricing_replenishment":
                relationships = result.get("price_demand_relationship")
                if not isinstance(relationships, list) or not relationships:
                    findings.append(_block("RETAIL_DEMAND_VALIDATION_MISSING", "category pricing requires chronological demand-response validation"))
                else:
                    invalid = [item for item in relationships if not np.isfinite(float(item.get("validation_rmse", np.nan)))]
                    if invalid:
                        findings.append(_block("RETAIL_DEMAND_VALIDATION_INVALID", f"non-finite validation RMSE for {len(invalid)} entities"))
                    allowed_variants = {"simple_markup", "linear_markup", "quadratic_markup"}
                    invalid_variants = [
                        item for item in relationships
                        if str(item.get("feature_variant") or "") not in allowed_variants
                    ]
                    if invalid_variants:
                        findings.append(_block("RETAIL_DEMAND_VARIANT_INVALID", f"invalid feature variant for {len(invalid_variants)} entities"))
                    threshold = max(
                        0.0,
                        float(
                            plan.get(
                                "complexity_upgrade_min_relative_improvement",
                                plan.get("quadratic_markup_min_relative_improvement", 0.01),
                            )
                        ),
                    )
                    selection_mismatches = []
                    protocol = result.get("protocol") or {}
                    protocol_variants = protocol.get("feature_variants_selected") or {}
                    candidate_order = [
                        str(value)
                        for value in protocol.get(
                            "candidate_feature_order",
                            ["simple_markup", "linear_markup", "quadratic_markup"],
                        )
                    ]
                    protocol_mismatches = []
                    for item in relationships:
                        entity = str(item.get("entity") or "")
                        variant = str(item.get("feature_variant") or "")
                        rmse_map = {
                            str(key): float(value)
                            for key, value in (item.get("candidate_validation_rmse") or {}).items()
                            if isinstance(value, (int, float)) and np.isfinite(float(value))
                        }
                        if not rmse_map:
                            legacy = {
                                "linear_markup": float(item.get("linear_validation_rmse", np.nan)),
                                "quadratic_markup": float(item.get("quadratic_validation_rmse", np.nan)),
                            }
                            rmse_map = {key: value for key, value in legacy.items() if np.isfinite(value)}
                        order = [candidate for candidate in candidate_order if candidate in rmse_map]
                        if not order:
                            selection_mismatches.append(entity or "<unknown>")
                            continue
                        expected_variant = choose_simplest_supported_variant(
                            rmse_map,
                            order,
                            min_relative_improvement=threshold,
                        )
                        if variant != expected_variant:
                            selection_mismatches.append(entity or "<unknown>")
                        if str(protocol_variants.get(entity) or "") != variant:
                            protocol_mismatches.append(entity or "<unknown>")
                    if selection_mismatches:
                        findings.append(_block("RETAIL_DEMAND_VARIANT_SELECTION_MISMATCH", f"holdout selection rule mismatch for {len(selection_mismatches)} entities"))
                    if protocol_mismatches:
                        findings.append(_block("RETAIL_DEMAND_VARIANT_PROTOCOL_MISMATCH", f"protocol/result variant mismatch for {len(protocol_mismatches)} entities"))
                    metrics["demand_relationships"] = len(relationships)
                    metrics["simple_selected_count"] = sum(
                        str(item.get("feature_variant") or "") == "simple_markup" for item in relationships
                    )
                    metrics["quadratic_selected_count"] = sum(
                        str(item.get("feature_variant") or "") == "quadratic_markup" for item in relationships
                    )
                runs = result.get("sensitivity_runs", [])
                metrics["sensitivity_runs"] = len(runs) if isinstance(runs, list) else 0
                if not isinstance(runs, list) or len(runs) < 2:
                    findings.append(_review("RETAIL_WHOLESALE_COST_SENSITIVITY_MISSING", "pricing policy should be stress-tested against wholesale-cost uncertainty"))
            else:
                selected = int(result.get("selected_item_count", 0))
                min_items = int(plan.get("min_items", 27))
                max_items = int(plan.get("max_items", 33))
                minimum_order = float(plan.get("minimum_order", 2.5))
                metrics["selected_item_count"] = selected
                if not min_items <= selected <= max_items:
                    findings.append(_block("RETAIL_ITEM_COUNT_CONSTRAINT_FAILED", f"selected={selected}, allowed=[{min_items},{max_items}]"))
                below_minimum = [item for item in strategy if float(item.get("replenishment_quantity", 0.0)) < minimum_order - 1e-9]
                if below_minimum:
                    findings.append(_block("RETAIL_MINIMUM_DISPLAY_CONSTRAINT_FAILED", f"items below {minimum_order:g} kg={len(below_minimum)}"))

    def _check_simulation(self, plan, result, diagnostics, frame, findings, metrics) -> None:
        protocol = result.get("protocol", {})
        replications = int(protocol.get("replications", 0))
        metrics["replications"] = replications
        if replications < 2:
            findings.append(_block("SIMULATION_REPLICATIONS_INVALID", f"replications={replications}"))
        scenarios = result.get("scenarios", {})
        if not scenarios:
            findings.append(_block("SIMULATION_SCENARIOS_MISSING", "no scenario outputs"))
            return
        for name, values in scenarios.items():
            if any(key not in values for key in ("mean", "std", "p05", "p95")):
                findings.append(_block("SIMULATION_UNCERTAINTY_MISSING", f"scenario={name}"))

    def _check_ranking(self, plan, result, diagnostics, frame, findings, metrics) -> None:
        method = str(result.get("protocol", {}).get("method") or "").lower()
        if method == "rfm_member_value":
            weights = {str(key): float(value) for key, value in (result.get("weights") or {}).items()}
            ranking = list(result.get("ranking") or [])
            values = result.get("metrics", {})
            stability = float(values.get("top_decile_stability", np.nan))
            metrics.update({
                "member_count": int(values.get("member_count", 0)),
                "score_dimension_count": int(values.get("score_dimension_count", 0)),
                "top_decile_stability": stability,
                "median_score": float(values.get("median_score", np.nan)),
                "top_decile_threshold": float(values.get("top_decile_threshold", np.nan)),
            })
            if not weights or abs(sum(weights.values()) - 1.0) > 1e-6:
                findings.append(_block("RFM_WEIGHT_NORMALIZATION_FAILED", f"weight_sum={sum(weights.values()):.6g}"))
            if len(ranking) < 10 or len(ranking) != metrics["member_count"]:
                findings.append(_block("RFM_MEMBER_COVERAGE_INVALID", f"ranking={len(ranking)}, member_count={metrics['member_count']}"))
            if not np.isfinite(stability) or stability < 0.7:
                findings.append(_review("RFM_TOP_SEGMENT_UNSTABLE", f"top_decile_stability={stability:.3f}"))
            return
        if method == "entropy_topsis":
            weights = result.get("weights", {})
            ranking = result.get("ranking", [])
            winner_retention = float(result.get("metrics", {}).get("winner_retention_rate", 0.0))
            mean_spearman = float(result.get("metrics", {}).get("mean_spearman", 0.0))
            metrics["winner_retention_rate"] = winner_retention
            metrics["mean_spearman"] = mean_spearman
            metrics["criterion_count"] = len(result.get("criteria", []))
            if not weights or abs(sum(float(value) for value in weights.values()) - 1.0) > 1e-6:
                findings.append(_block("MCDM_WEIGHT_NORMALIZATION_FAILED", "entropy weights must sum to one"))
            if len(ranking) < 2:
                findings.append(_block("MCDM_RANKING_INSUFFICIENT", "at least two entities are required"))
            if winner_retention < 0.5:
                findings.append(_review("MCDM_WINNER_UNSTABLE", f"leave-one-criterion winner retention={winner_retention:.1%}"))
            if mean_spearman < 0.7:
                findings.append(_review("MCDM_RANK_ORDER_UNSTABLE", f"mean leave-one-criterion Spearman={mean_spearman:.3f}"))
            return
        if method not in {"pairwise", "listwise"}:
            findings.append(_block("RANKING_PROTOCOL_INVALID", "pairwise/listwise protocol required"))
        if int(result.get("queries", 0)) < 1:
            findings.append(_block("RANKING_QUERY_COUNT_INVALID", "no query groups evaluated"))


def _confidence_ece(actual: np.ndarray, predicted: np.ndarray, probabilities: np.ndarray, bins: int = 5) -> float:
    confidence = probabilities.max(axis=1)
    correct = (predicted == actual).astype(float)
    edges = np.linspace(0.0, 1.0, bins + 1)
    ece = 0.0
    for index in range(bins):
        lower, upper = edges[index], edges[index + 1]
        mask = (confidence >= lower) & (confidence <= upper if index == bins - 1 else confidence < upper)
        if not np.any(mask):
            continue
        ece += float(np.mean(mask)) * abs(float(np.mean(correct[mask])) - float(np.mean(confidence[mask])))
    return float(ece)


def _block(code: str, detail: str) -> ValidationFinding:
    return ValidationFinding(severity="BLOCK", code=code, detail=detail)


def _review(code: str, detail: str) -> ValidationFinding:
    return ValidationFinding(severity="REVIEW", code=code, detail=detail)

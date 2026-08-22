from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error


@dataclass(frozen=True)
class DemandFit:
    entity: str
    model: Ridge
    feature_variant: str
    origin: pd.Timestamp
    scale_days: float
    markup_low: float
    markup_high: float
    validation_rmse: float
    validation_mae: float
    candidate_validation_rmse: dict[str, float]
    candidate_validation_mae: dict[str, float]
    simple_validation_rmse: float
    linear_validation_rmse: float
    quadratic_validation_rmse: float
    train_rows: int
    test_rows: int
    pricing_identified: bool


def solve_retail_pricing_replenishment(frame: pd.DataFrame, plan: dict[str, Any]) -> dict[str, Any]:
    """Evidence-safe retail pricing/replenishment baseline.

    The input must already be a daily entity panel with observed sales quantity,
    quantity-weighted sale price, observed/estimated wholesale cost and loss rate.
    The solver learns an *associational* demand response to the observed markup,
    validates it on the final chronological holdout, and searches only inside the
    historically supported markup range.  It does not claim causal price elasticity.

    ``mode=category`` optimizes future category price/replenishment decisions.
    ``mode=item`` converts category demand targets into a constrained item assortment
    using only items observed in the registered recent availability window.
    """

    mode = str(plan.get("mode") or "category").lower()
    if mode == "category":
        return _solve_category(frame, plan)
    if mode == "item":
        return _solve_item(frame, plan)
    raise ValueError(f"RETAIL_PRICING_MODE_UNSUPPORTED:{mode}")


def validate_retail_plan(frame: pd.DataFrame | None, plan: dict[str, Any]) -> list[str]:
    if frame is None:
        return ["TASK_DATA_REQUIRED"]
    required_plan = (
        "mode",
        "date_column",
        "entity_column",
        "quantity_column",
        "sale_price_column",
        "wholesale_cost_column",
        "loss_rate_column",
    )
    errors = [f"{name.upper()}_REQUIRED" for name in required_plan if not plan.get(name)]
    columns = [str(plan.get(name) or "") for name in required_plan[1:]]
    errors.extend(f"COLUMN_MISSING:{name}" for name in columns if name and name not in frame.columns)
    mode = str(plan.get("mode") or "").lower()
    if mode == "category" and not plan.get("future_dates"):
        errors.append("FUTURE_DATES_REQUIRED")
    if mode == "item":
        category_column = str(plan.get("category_column") or "")
        if not category_column:
            errors.append("CATEGORY_COLUMN_REQUIRED")
        elif category_column not in frame.columns:
            errors.append("CATEGORY_COLUMN_MISSING")
        if not plan.get("category_targets"):
            errors.append("CATEGORY_TARGETS_REQUIRED")
        count = int(plan.get("selection_count", 30))
        if not int(plan.get("min_items", 27)) <= count <= int(plan.get("max_items", 33)):
            errors.append("SELECTION_COUNT_OUTSIDE_ALLOWED_RANGE")
    return list(dict.fromkeys(errors))


def _solve_category(frame: pd.DataFrame, plan: dict[str, Any]) -> dict[str, Any]:
    data = _clean_panel(frame, plan)
    entity_column = str(plan["entity_column"])
    date_column = str(plan["date_column"])
    cost_column = str(plan["wholesale_cost_column"])
    loss_column = str(plan["loss_rate_column"])
    future_dates = [pd.Timestamp(value) for value in plan["future_dates"]]
    if any(date <= data[date_column].max() for date in future_dates):
        raise ValueError("RETAIL_FUTURE_DATE_MUST_FOLLOW_OBSERVATIONS")

    strategies: list[dict[str, Any]] = []
    relationships: list[dict[str, Any]] = []
    fit_by_entity: dict[str, DemandFit] = {}
    recent_days = int(plan.get("recent_cost_days", 14))
    grid_points = max(5, int(plan.get("markup_grid_points", 21)))

    for entity, group in data.groupby(entity_column, sort=True):
        entity_name = str(entity)
        group = group.sort_values(date_column).reset_index(drop=True)
        fit = _fit_demand(group, plan, entity_name)
        fit_by_entity[entity_name] = fit
        recent_cutoff = group[date_column].max() - pd.Timedelta(days=max(1, recent_days - 1))
        recent = group[group[date_column] >= recent_cutoff]
        if recent.empty:
            recent = group.tail(max(1, recent_days))
        cost = _weighted_recent(recent, cost_column, str(plan["quantity_column"]))
        loss = float(np.clip(np.nanmedian(pd.to_numeric(recent[loss_column], errors="coerce")), 0.0, 0.95))
        markups = _markup_grid(fit, grid_points)
        for future_date in future_dates:
            choices = []
            for markup in markups:
                demand = _predict_demand(fit, float(markup), future_date)
                order = demand / max(1.0 - loss, 1e-6)
                price = cost * (1.0 + float(markup))
                profit = demand * price - order * cost
                choices.append((profit, markup, demand, order, price))
            profit, markup, demand, order, price = max(choices, key=lambda item: item[0])
            strategies.append(
                {
                    "entity": entity_name,
                    "date": future_date.date().isoformat(),
                    "demand_forecast": float(demand),
                    "replenishment_quantity": float(order),
                    "sale_price": float(price),
                    "wholesale_cost_forecast": float(cost),
                    "markup_rate": float(markup),
                    "loss_rate": float(loss),
                    "expected_profit": float(profit),
                }
            )
        relationships.append(
            {
                "entity": entity_name,
                "feature_variant": fit.feature_variant,
                "markup_response_coefficient": float(fit.model.coef_[0]),
                "markup_quadratic_coefficient": (
                    float(fit.model.coef_[1]) if fit.feature_variant == "quadratic_markup" else 0.0
                ),
                "validation_rmse": fit.validation_rmse,
                "validation_mae": fit.validation_mae,
                "candidate_validation_rmse": dict(fit.candidate_validation_rmse),
                "candidate_validation_mae": dict(fit.candidate_validation_mae),
                "simple_validation_rmse": fit.simple_validation_rmse,
                "linear_validation_rmse": fit.linear_validation_rmse,
                "quadratic_validation_rmse": fit.quadratic_validation_rmse,
                "train_rows": fit.train_rows,
                "test_rows": fit.test_rows,
                "historical_markup_range": [fit.markup_low, fit.markup_high],
                "pricing_identified": fit.pricing_identified,
                "interpretation_guard": "associational_not_causal",
            }
        )

    if not strategies:
        raise ValueError("RETAIL_CATEGORY_STRATEGY_EMPTY")
    total_profit = float(sum(item["expected_profit"] for item in strategies))
    total_demand = float(sum(item["demand_forecast"] for item in strategies))
    total_order = float(sum(item["replenishment_quantity"] for item in strategies))
    validation_rmse = float(np.mean([item["validation_rmse"] for item in relationships]))
    validation_mae = float(np.mean([item["validation_mae"] for item in relationships]))
    sensitivity_runs = _category_cost_sensitivity(strategies)
    return {
        "family": "optimization",
        "solver_method": "retail_category_pricing_replenishment",
        "protocol": {
            "method": "chronological_simple_to_richer_markup_ridge_plus_historical_range_grid",
            "candidate_feature_order": ["simple_markup", "linear_markup", "quadratic_markup"],
            "complexity_upgrade_min_relative_improvement": float(
                plan.get(
                    "complexity_upgrade_min_relative_improvement",
                    plan.get("quadratic_markup_min_relative_improvement", 0.01),
                )
            ),
            "future_dates": [item.date().isoformat() for item in future_dates],
            "price_search_support": "historical_markup_range_only",
            "demand_interpretation": "associational_not_causal",
            "feature_variants_selected": {
                entity: fit.feature_variant for entity, fit in fit_by_entity.items()
            },
        },
        "constraint_status": "PASS",
        "solver_status": 0,
        "objective_value": total_profit,
        "strategy": strategies,
        "price_demand_relationship": relationships,
        "metrics": {
            "expected_profit_total": total_profit,
            "expected_demand_total": total_demand,
            "replenishment_total": total_order,
            "demand_validation_rmse_mean": validation_rmse,
            "demand_validation_mae_mean": validation_mae,
            "entity_count": float(len(fit_by_entity)),
        },
        "sensitivity_runs": sensitivity_runs,
    }


def _solve_item(frame: pd.DataFrame, plan: dict[str, Any]) -> dict[str, Any]:
    data = _clean_panel(frame, plan)
    date_column = str(plan["date_column"])
    entity_column = str(plan["entity_column"])
    category_column = str(plan["category_column"])
    quantity_column = str(plan["quantity_column"])
    sale_price_column = str(plan["sale_price_column"])
    cost_column = str(plan["wholesale_cost_column"])
    loss_column = str(plan["loss_rate_column"])
    future_date = pd.Timestamp(plan.get("future_date") or plan.get("future_dates", [None])[0])
    if pd.isna(future_date):
        raise ValueError("RETAIL_ITEM_FUTURE_DATE_REQUIRED")
    if future_date <= data[date_column].max():
        raise ValueError("RETAIL_FUTURE_DATE_MUST_FOLLOW_OBSERVATIONS")

    availability_days = max(1, int(plan.get("availability_days", 7)))
    latest = data[date_column].max()
    cutoff = latest - pd.Timedelta(days=availability_days - 1)
    recent = data[data[date_column] >= cutoff].copy()
    sold_recently = set(recent.loc[recent[quantity_column] > 0, entity_column].astype(str))
    candidates = data[data[entity_column].astype(str).isin(sold_recently)].copy()
    if candidates.empty:
        raise ValueError("RETAIL_ITEM_RECENT_AVAILABILITY_EMPTY")

    summaries: list[dict[str, Any]] = []
    for entity, history in candidates.groupby(entity_column, sort=True):
        history = history.sort_values(date_column)
        recent_entity = history[history[date_column] >= cutoff]
        if recent_entity.empty:
            continue
        category = str(recent_entity[category_column].dropna().iloc[-1])
        avg_sales = float(recent_entity.set_index(date_column)[quantity_column].reindex(pd.date_range(cutoff, latest, freq="D"), fill_value=0.0).mean())
        cost = _weighted_recent(recent_entity, cost_column, quantity_column)
        sale_price = _weighted_recent(recent_entity, sale_price_column, quantity_column)
        loss = float(np.clip(np.nanmedian(pd.to_numeric(recent_entity[loss_column], errors="coerce")), 0.0, 0.95))
        unit_margin_after_loss = sale_price - cost / max(1.0 - loss, 1e-6)
        summaries.append(
            {
                "entity": str(entity),
                "category": category,
                "recent_daily_sales": avg_sales,
                "recent_sale_price": sale_price,
                "wholesale_cost_forecast": cost,
                "loss_rate": loss,
                "selection_score": avg_sales * unit_margin_after_loss,
            }
        )
    if not summaries:
        raise ValueError("RETAIL_ITEM_SUMMARY_EMPTY")

    targets = _normalize_category_targets(plan["category_targets"])
    selection_count = int(plan.get("selection_count", 30))
    minimum_order = float(plan.get("minimum_order", 2.5))
    min_items = int(plan.get("min_items", 27))
    max_items = int(plan.get("max_items", 33))
    available_by_category: dict[str, list[dict[str, Any]]] = {}
    for item in summaries:
        if item["category"] in targets:
            available_by_category.setdefault(item["category"], []).append(item)
    if not available_by_category:
        raise ValueError("RETAIL_ITEM_TARGET_CATEGORIES_UNAVAILABLE")
    selection_count = max(min_items, min(max_items, selection_count, sum(len(v) for v in available_by_category.values())))
    quotas = _category_quotas(targets, {key: len(value) for key, value in available_by_category.items()}, selection_count)

    selected: list[dict[str, Any]] = []
    for category, quota in quotas.items():
        ranked = sorted(
            available_by_category.get(category, []),
            key=lambda item: (float(item["selection_score"]), float(item["recent_daily_sales"]), item["entity"]),
            reverse=True,
        )
        selected.extend(ranked[:quota])
    # Fill any quota shortfall with the strongest remaining recently available items.
    selected_ids = {item["entity"] for item in selected}
    if len(selected) < selection_count:
        remaining = sorted(
            [item for item in summaries if item["entity"] not in selected_ids and item["category"] in targets],
            key=lambda item: (float(item["selection_score"]), float(item["recent_daily_sales"]), item["entity"]),
            reverse=True,
        )
        selected.extend(remaining[: selection_count - len(selected)])

    strategies: list[dict[str, Any]] = []
    for category, target in targets.items():
        category_items = [item for item in selected if item["category"] == category]
        if not category_items:
            continue
        weights = np.asarray([max(0.0, float(item["recent_daily_sales"])) for item in category_items], dtype=float)
        if float(weights.sum()) <= 1e-12:
            weights = np.ones(len(category_items), dtype=float)
        weights /= weights.sum()
        demand_target = float(target["demand_forecast"])
        markup = float(target["markup_rate"])
        for item, share in zip(category_items, weights):
            expected_sales = demand_target * float(share)
            loss = float(item["loss_rate"])
            order = max(minimum_order, expected_sales / max(1.0 - loss, 1e-6))
            price = float(item["wholesale_cost_forecast"]) * (1.0 + markup)
            expected_profit = expected_sales * price - order * float(item["wholesale_cost_forecast"])
            strategies.append(
                {
                    **item,
                    "date": future_date.date().isoformat(),
                    "category_demand_target": demand_target,
                    "allocation_share": float(share),
                    "expected_sales": float(expected_sales),
                    "replenishment_quantity": float(order),
                    "sale_price": float(price),
                    "markup_rate": markup,
                    "expected_profit": float(expected_profit),
                }
            )

    selected_count = len(strategies)
    covered_categories = {item["category"] for item in strategies}
    required_categories = {key for key, value in targets.items() if float(value["demand_forecast"]) > 0}
    constraints_ok = (
        min_items <= selected_count <= max_items
        and all(float(item["replenishment_quantity"]) >= minimum_order - 1e-9 for item in strategies)
        and required_categories <= covered_categories
    )
    total_profit = float(sum(item["expected_profit"] for item in strategies))
    return {
        "family": "optimization",
        "solver_method": "retail_item_pricing_replenishment",
        "protocol": {
            "method": "recent_availability_profit_screen_plus_category_demand_allocation",
            "availability_window_days": availability_days,
            "selection_count_requested": int(plan.get("selection_count", 30)),
            "minimum_display_quantity": minimum_order,
            "pricing_basis": "category_optimal_markup_applied_to_item_wholesale_cost",
        },
        "constraint_status": "PASS" if constraints_ok else "FAIL",
        "solver_status": 0 if constraints_ok else 1,
        "objective_value": total_profit,
        "selected_item_count": selected_count,
        "strategy": strategies,
        "category_quotas": quotas,
        "metrics": {
            "expected_profit_total": total_profit,
            "selected_item_count": float(selected_count),
            "category_coverage_count": float(len(covered_categories)),
            "minimum_order_quantity": min(float(item["replenishment_quantity"]) for item in strategies) if strategies else 0.0,
        },
    }


def _clean_panel(frame: pd.DataFrame, plan: dict[str, Any]) -> pd.DataFrame:
    columns = [
        str(plan["date_column"]),
        str(plan["entity_column"]),
        str(plan["quantity_column"]),
        str(plan["sale_price_column"]),
        str(plan["wholesale_cost_column"]),
        str(plan["loss_rate_column"]),
    ]
    category = str(plan.get("category_column") or "")
    if category:
        columns.append(category)
    data = frame[columns].copy()
    date_column = str(plan["date_column"])
    data[date_column] = pd.to_datetime(data[date_column], errors="raise")
    for column in (str(plan["quantity_column"]), str(plan["sale_price_column"]), str(plan["wholesale_cost_column"]), str(plan["loss_rate_column"])):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data = data.dropna(subset=columns[:6])
    data = data[(data[str(plan["quantity_column"])] >= 0) & (data[str(plan["sale_price_column"])] > 0) & (data[str(plan["wholesale_cost_column"])] > 0)]
    loss_column = str(plan["loss_rate_column"])
    if float(data[loss_column].median()) > 1.0:
        data[loss_column] = data[loss_column] / 100.0
    data[loss_column] = data[loss_column].clip(0.0, 0.95)
    if data.empty:
        raise ValueError("RETAIL_DAILY_PANEL_EMPTY")
    return data.sort_values([str(plan["entity_column"]), date_column]).reset_index(drop=True)


def _fit_demand(group: pd.DataFrame, plan: dict[str, Any], entity: str) -> DemandFit:
    date_column = str(plan["date_column"])
    quantity_column = str(plan["quantity_column"])
    price_column = str(plan["sale_price_column"])
    cost_column = str(plan["wholesale_cost_column"])
    values = group.copy()
    values["__markup"] = values[price_column] / values[cost_column] - 1.0
    values = values.replace([np.inf, -np.inf], np.nan).dropna(subset=["__markup", quantity_column])
    values = values[values[quantity_column] >= 0].sort_values(date_column).reset_index(drop=True)
    if len(values) < int(plan.get("minimum_demand_rows", 45)):
        raise ValueError(f"RETAIL_DEMAND_ROWS_INSUFFICIENT:{entity}:{len(values)}")
    test_rows = max(7, int(round(len(values) * float(plan.get("test_size", 0.2)))))
    test_rows = min(test_rows, max(7, len(values) // 3))
    split = len(values) - test_rows
    if split < 30:
        raise ValueError(f"RETAIL_DEMAND_TRAIN_ROWS_INSUFFICIENT:{entity}:{split}")
    origin = values[date_column].iloc[0]
    scale_days = max(1.0, float((values[date_column].iloc[-1] - origin).days))
    markups = values["__markup"].to_numpy(dtype=float)
    y = np.log1p(values[quantity_column].to_numpy(dtype=float))
    actual = values[quantity_column].to_numpy(dtype=float)[split:]
    alpha = float(plan.get("demand_ridge_alpha", 1.0))
    candidate_predictions: dict[str, np.ndarray] = {}
    candidate_rmse: dict[str, float] = {}
    candidate_mae: dict[str, float] = {}
    candidate_design: dict[str, np.ndarray] = {}
    supported_variants = ("simple_markup", "linear_markup", "quadratic_markup")
    requested_variants = [str(value) for value in plan.get("demand_feature_variants", supported_variants)]
    candidate_variants = [value for value in requested_variants if value in supported_variants]
    if not candidate_variants:
        raise ValueError("RETAIL_DEMAND_FEATURE_VARIANTS_EMPTY")
    for variant in candidate_variants:
        design = _demand_features(
            values[date_column],
            markups,
            origin,
            scale_days,
            variant=variant,
        )
        validation_model = Ridge(alpha=alpha).fit(design[:split], y[:split])
        predicted = np.maximum(0.0, np.expm1(validation_model.predict(design[split:])))
        candidate_design[variant] = design
        candidate_predictions[variant] = predicted
        candidate_rmse[variant] = float(np.sqrt(mean_squared_error(actual, predicted)))
        candidate_mae[variant] = float(mean_absolute_error(actual, predicted))

    improvement = max(
        0.0,
        float(
            plan.get(
                "complexity_upgrade_min_relative_improvement",
                plan.get("quadratic_markup_min_relative_improvement", 0.01),
            )
        ),
    )
    selected_variant = choose_simplest_supported_variant(
        candidate_rmse,
        candidate_variants,
        min_relative_improvement=improvement,
    )
    simple_rmse = candidate_rmse.get("simple_markup", candidate_rmse[selected_variant])
    linear_rmse = candidate_rmse.get("linear_markup", candidate_rmse[selected_variant])
    quadratic_rmse = candidate_rmse.get("quadratic_markup", candidate_rmse[selected_variant])
    selected_design = candidate_design[selected_variant]
    full_model = Ridge(alpha=alpha).fit(selected_design, y)
    selected_predicted = candidate_predictions[selected_variant]
    low = float(np.quantile(markups, 0.10))
    high = float(np.quantile(markups, 0.90))
    pricing_identified = bool(np.isfinite(low) and np.isfinite(high) and high - low >= 0.03)
    if not pricing_identified:
        center = float(np.median(markups))
        low = high = center
    return DemandFit(
        entity=entity,
        model=full_model,
        feature_variant=selected_variant,
        origin=origin,
        scale_days=scale_days,
        markup_low=low,
        markup_high=high,
        validation_rmse=candidate_rmse[selected_variant],
        validation_mae=candidate_mae[selected_variant],
        candidate_validation_rmse=dict(candidate_rmse),
        candidate_validation_mae=dict(candidate_mae),
        simple_validation_rmse=simple_rmse,
        linear_validation_rmse=linear_rmse,
        quadratic_validation_rmse=quadratic_rmse,
        train_rows=int(split),
        test_rows=int(test_rows),
        pricing_identified=pricing_identified,
    )


def choose_simplest_supported_variant(
    candidate_rmse: dict[str, float],
    candidate_variants: list[str] | tuple[str, ...],
    *,
    min_relative_improvement: float,
) -> str:
    """Upgrade model complexity only when holdout error improves materially.

    ``candidate_variants`` is ordered from simpler to richer by the caller.  The
    function does not know model names or assign prestige ranks: it only asks
    whether the next registered candidate clears the same relative-improvement
    burden of proof.  This keeps the rule reusable when the candidate family is
    changed by configuration or an upstream modeling agent.
    """

    variants = [str(value) for value in candidate_variants if str(value) in candidate_rmse]
    if not variants:
        raise ValueError("RETAIL_DEMAND_VARIANT_METRICS_EMPTY")
    threshold = max(0.0, float(min_relative_improvement))
    selected = variants[0]
    for variant in variants[1:]:
        current = float(candidate_rmse[selected])
        challenger = float(candidate_rmse[variant])
        if challenger < current * max(0.0, 1.0 - threshold):
            selected = variant
    return selected


def _demand_features(
    dates: pd.Series | pd.DatetimeIndex,
    markups: np.ndarray,
    origin: pd.Timestamp,
    scale_days: float,
    *,
    variant: str = "linear_markup",
) -> np.ndarray:
    index = pd.DatetimeIndex(pd.to_datetime(dates))
    elapsed = (index - origin).days.to_numpy(dtype=float) / max(scale_days, 1.0)
    weekday = index.dayofweek.to_numpy(dtype=float)
    day_of_year = index.dayofyear.to_numpy(dtype=float)
    markup = np.asarray(markups, dtype=float)
    columns: list[np.ndarray] = [markup]
    if variant == "simple_markup":
        return np.column_stack(columns)
    if variant == "quadratic_markup":
        columns.append(markup ** 2)
    elif variant != "linear_markup":
        raise ValueError(f"RETAIL_DEMAND_FEATURE_VARIANT_UNSUPPORTED:{variant}")
    columns.extend(
        [
            np.sin(2.0 * np.pi * weekday / 7.0),
            np.cos(2.0 * np.pi * weekday / 7.0),
            np.sin(2.0 * np.pi * day_of_year / 365.25),
            np.cos(2.0 * np.pi * day_of_year / 365.25),
            elapsed,
        ]
    )
    return np.column_stack(columns)


def _predict_demand(fit: DemandFit, markup: float, date: pd.Timestamp) -> float:
    x = _demand_features(
        pd.DatetimeIndex([date]),
        np.asarray([markup]),
        fit.origin,
        fit.scale_days,
        variant=fit.feature_variant,
    )
    return float(max(0.0, np.expm1(fit.model.predict(x)[0])))


def _markup_grid(fit: DemandFit, points: int) -> np.ndarray:
    if abs(fit.markup_high - fit.markup_low) < 1e-12:
        return np.asarray([fit.markup_low], dtype=float)
    return np.linspace(fit.markup_low, fit.markup_high, points)


def _weighted_recent(frame: pd.DataFrame, value_column: str, weight_column: str) -> float:
    values = pd.to_numeric(frame[value_column], errors="coerce").to_numpy(dtype=float)
    weights = np.maximum(0.0, pd.to_numeric(frame[weight_column], errors="coerce").to_numpy(dtype=float))
    finite = np.isfinite(values) & np.isfinite(weights)
    values = values[finite]
    weights = weights[finite]
    if not len(values):
        raise ValueError(f"RETAIL_RECENT_VALUE_MISSING:{value_column}")
    if float(weights.sum()) <= 1e-12:
        return float(np.median(values))
    return float(np.average(values, weights=weights))


def _category_cost_sensitivity(strategy: list[dict[str, Any]]) -> list[dict[str, Any]]:
    runs = []
    for factor in (0.9, 1.1):
        total = 0.0
        for item in strategy:
            cost = float(item["wholesale_cost_forecast"]) * factor
            demand = float(item["demand_forecast"])
            order = demand / max(1.0 - float(item["loss_rate"]), 1e-6)
            price = cost * (1.0 + float(item["markup_rate"]))
            total += demand * price - order * cost
        runs.append({"wholesale_cost_factor": factor, "objective_value": float(total)})
    return runs


def _normalize_category_targets(value: Any) -> dict[str, dict[str, float]]:
    if not isinstance(value, dict):
        raise ValueError("CATEGORY_TARGETS_INVALID")
    targets: dict[str, dict[str, float]] = {}
    for category, payload in value.items():
        if not isinstance(payload, dict):
            continue
        demand = payload.get("demand_forecast")
        markup = payload.get("markup_rate")
        if isinstance(demand, (int, float)) and isinstance(markup, (int, float)):
            targets[str(category)] = {"demand_forecast": float(demand), "markup_rate": float(markup)}
    if not targets:
        raise ValueError("CATEGORY_TARGETS_EMPTY")
    return targets


def _category_quotas(
    targets: dict[str, dict[str, float]],
    available_counts: dict[str, int],
    total: int,
) -> dict[str, int]:
    categories = [key for key in sorted(targets) if available_counts.get(key, 0) > 0]
    if not categories:
        raise ValueError("CATEGORY_QUOTA_NO_AVAILABLE_CATEGORIES")
    if total < len(categories):
        raise ValueError("SELECTION_COUNT_BELOW_CATEGORY_COUNT")
    demand = np.asarray([max(0.0, float(targets[key]["demand_forecast"])) for key in categories], dtype=float)
    if float(demand.sum()) <= 1e-12:
        demand = np.ones(len(categories), dtype=float)
    raw = demand / demand.sum() * total
    quota = {key: 1 for key in categories}
    remaining = total - len(categories)
    priorities = sorted(
        range(len(categories)),
        key=lambda index: (raw[index] - 1.0, demand[index]),
        reverse=True,
    )
    while remaining > 0:
        progressed = False
        for index in priorities:
            key = categories[index]
            if quota[key] >= available_counts[key]:
                continue
            quota[key] += 1
            remaining -= 1
            progressed = True
            if remaining == 0:
                break
        if not progressed:
            break
    return quota

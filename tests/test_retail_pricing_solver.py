from __future__ import annotations

import numpy as np
import pandas as pd

from mathworkstation.paper_model_equations import equations_for_method
from mathworkstation.retail_pricing import choose_simplest_supported_variant, solve_retail_pricing_replenishment
from mathworkstation.solver_engine import SolverRegistry
from mathworkstation.validation_protocol import ValidationRunner


def _category_panel(days: int = 140) -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2023-01-01", periods=days, freq="D")
    for category_index, category in enumerate(("叶菜", "菌菇")):
        base_cost = 4.0 + category_index
        for index, date in enumerate(dates):
            markup = 0.25 + 0.08 * np.sin(index / 11.0 + category_index)
            cost = base_cost * (1.0 + 0.03 * np.sin(index / 17.0))
            price = cost * (1.0 + markup)
            quantity = max(
                1.0,
                42.0
                + 8.0 * np.sin(2 * np.pi * date.dayofweek / 7.0)
                - 18.0 * markup
                + 0.025 * index,
            )
            rows.append(
                {
                    "date": date,
                    "category": category,
                    "quantity": quantity,
                    "sale_price": price,
                    "wholesale_cost": cost,
                    "loss_rate": 0.08 + category_index * 0.02,
                }
            )
    return pd.DataFrame(rows)


def _category_plan() -> dict:
    return {
        "solver_method": "retail_category_pricing_replenishment",
        "mode": "category",
        "date_column": "date",
        "entity_column": "category",
        "quantity_column": "quantity",
        "sale_price_column": "sale_price",
        "wholesale_cost_column": "wholesale_cost",
        "loss_rate_column": "loss_rate",
        "future_dates": ["2023-05-21", "2023-05-22"],
        "test_size": 0.2,
        "minimum_demand_rows": 60,
        "markup_grid_points": 15,
    }


def _item_panel() -> pd.DataFrame:
    rows = []
    dates = pd.date_range("2023-06-24", "2023-06-30", freq="D")
    categories = ("叶菜", "菌菇", "辣椒")
    for category_index, category in enumerate(categories):
        for item_index in range(12):
            item_code = f"{category_index}-{item_index:02d}"
            for day_index, date in enumerate(dates):
                quantity = 1.5 + 0.3 * item_index + 0.1 * day_index
                cost = 3.0 + 0.15 * item_index + category_index
                rows.append(
                    {
                        "date": date,
                        "item_code": item_code,
                        "category": category,
                        "quantity": quantity,
                        "sale_price": cost * 1.45,
                        "wholesale_cost": cost,
                        "loss_rate": 0.06 + 0.01 * category_index,
                    }
                )
    return pd.DataFrame(rows)


def test_category_retail_solver_is_temporal_support_bounded_and_sensitive() -> None:
    frame = _category_panel()
    plan = _category_plan()
    result = solve_retail_pricing_replenishment(frame, plan)

    assert result["constraint_status"] == "PASS"
    assert result["solver_status"] == 0
    assert len(result["strategy"]) == 4
    assert len(result["price_demand_relationship"]) == 2
    assert len(result["sensitivity_runs"]) == 2
    assert result["metrics"]["demand_validation_rmse_mean"] >= 0
    for relationship in result["price_demand_relationship"]:
        assert relationship["test_rows"] >= 7
        assert relationship["feature_variant"] in {"simple_markup", "linear_markup", "quadratic_markup"}
        assert relationship["simple_validation_rmse"] >= 0
        assert relationship["linear_validation_rmse"] >= 0
        assert relationship["quadratic_validation_rmse"] >= 0
        low, high = relationship["historical_markup_range"]
        assert low <= high
        selected = [
            item["markup_rate"]
            for item in result["strategy"]
            if item["entity"] == relationship["entity"]
        ]
        assert selected
        assert all(low - 1e-12 <= value <= high + 1e-12 for value in selected)

    registry = SolverRegistry()
    assert registry.resolve("optimization", plan).name == "gold.retail_pricing_replenishment"
    assessment = ValidationRunner().assess("optimization", plan, result, registry.resolve("optimization", plan).diagnose("optimization", plan, result), frame)
    assert assessment.gate == "PASS"


def test_simple_model_priority_upgrades_only_after_material_holdout_gain() -> None:
    rmse = {"simple": 10.0, "richer": 9.95, "richest": 8.5}
    selected = choose_simplest_supported_variant(
        rmse,
        ["simple", "richer", "richest"],
        min_relative_improvement=0.01,
    )
    assert selected == "richest"

    near_tie = {"simple": 10.0, "richer": 9.95}
    assert choose_simplest_supported_variant(
        near_tie,
        ["simple", "richer"],
        min_relative_improvement=0.01,
    ) == "simple"


def test_category_retail_solver_selects_quadratic_markup_only_when_holdout_supports_it() -> None:
    dates = pd.date_range("2023-01-01", periods=180, freq="D")
    rows = []
    for index, date in enumerate(dates):
        markup = 0.08 + 0.62 * (index / (len(dates) - 1))
        cost = 4.0
        log_demand = 4.6 + 2.8 * markup - 5.2 * markup ** 2 + 0.10 * np.sin(2 * np.pi * date.dayofweek / 7.0)
        quantity = max(0.1, float(np.expm1(log_demand)))
        rows.append(
            {
                "date": date,
                "category": "非线性品类",
                "quantity": quantity,
                "sale_price": cost * (1.0 + markup),
                "wholesale_cost": cost,
                "loss_rate": 0.08,
            }
        )
    plan = {
        **_category_plan(),
        "future_dates": ["2023-07-01"],
        "demand_ridge_alpha": 0.01,
        "quadratic_markup_min_relative_improvement": 0.01,
    }
    result = solve_retail_pricing_replenishment(pd.DataFrame(rows), plan)
    relationship = result["price_demand_relationship"][0]
    assert relationship["feature_variant"] == "quadratic_markup"
    assert relationship["quadratic_validation_rmse"] < relationship["linear_validation_rmse"] * 0.99
    assert result["protocol"]["feature_variants_selected"]["非线性品类"] == "quadratic_markup"


def test_category_retail_validation_blocks_variant_selection_or_protocol_drift() -> None:
    frame = _category_panel()
    plan = _category_plan()
    result = solve_retail_pricing_replenishment(frame, plan)
    relationship = result["price_demand_relationship"][0]
    relationship["feature_variant"] = (
        "quadratic_markup" if relationship["feature_variant"] == "linear_markup" else "linear_markup"
    )
    plugin = SolverRegistry().resolve("optimization", plan)
    assessment = ValidationRunner().assess(
        "optimization",
        plan,
        result,
        plugin.diagnose("optimization", plan, result),
        frame,
    )
    assert assessment.gate == "FAIL"
    codes = {item.code for item in assessment.findings}
    assert "RETAIL_DEMAND_VARIANT_SELECTION_MISMATCH" in codes
    assert "RETAIL_DEMAND_VARIANT_PROTOCOL_MISMATCH" in codes


def test_retail_category_equation_matches_registered_relative_improvement_rule() -> None:
    equations = equations_for_method("retail_category_pricing_replenishment")
    selection = next(item for item in equations if item.label == "Ridge estimation and candidate selection")
    assert r"(1-\delta)" in selection.latex
    assert r"\text{otherwise}" in selection.latex
    assert "登记阈值" in selection.explanation_zh


def test_item_retail_solver_enforces_assortment_and_minimum_display() -> None:
    frame = _item_panel()
    plan = {
        "solver_method": "retail_item_pricing_replenishment",
        "mode": "item",
        "date_column": "date",
        "entity_column": "item_code",
        "category_column": "category",
        "quantity_column": "quantity",
        "sale_price_column": "sale_price",
        "wholesale_cost_column": "wholesale_cost",
        "loss_rate_column": "loss_rate",
        "future_date": "2023-07-01",
        "availability_days": 7,
        "selection_count": 30,
        "min_items": 27,
        "max_items": 33,
        "minimum_order": 2.5,
        "category_targets": {
            "叶菜": {"demand_forecast": 80.0, "markup_rate": 0.45},
            "菌菇": {"demand_forecast": 55.0, "markup_rate": 0.50},
            "辣椒": {"demand_forecast": 65.0, "markup_rate": 0.48},
        },
    }
    result = solve_retail_pricing_replenishment(frame, plan)

    assert result["constraint_status"] == "PASS"
    assert result["selected_item_count"] == 30
    assert set(result["category_quotas"]) == {"叶菜", "菌菇", "辣椒"}
    assert set(item["category"] for item in result["strategy"]) == {"叶菜", "菌菇", "辣椒"}
    assert min(item["replenishment_quantity"] for item in result["strategy"]) >= 2.5

    plugin = SolverRegistry().resolve("optimization", plan)
    assessment = ValidationRunner().assess("optimization", plan, result, plugin.diagnose("optimization", plan, result), frame)
    assert assessment.gate == "PASS"


def test_item_validation_blocks_a_broken_minimum_display_constraint() -> None:
    frame = _item_panel()
    plan = {
        "solver_method": "retail_item_pricing_replenishment",
        "mode": "item",
        "date_column": "date",
        "entity_column": "item_code",
        "category_column": "category",
        "quantity_column": "quantity",
        "sale_price_column": "sale_price",
        "wholesale_cost_column": "wholesale_cost",
        "loss_rate_column": "loss_rate",
        "future_date": "2023-07-01",
        "selection_count": 30,
        "min_items": 27,
        "max_items": 33,
        "minimum_order": 2.5,
        "category_targets": {"叶菜": {"demand_forecast": 20.0, "markup_rate": 0.4}},
    }
    result = {
        "solver_method": "retail_item_pricing_replenishment",
        "constraint_status": "PASS",
        "solver_status": 0,
        "selected_item_count": 30,
        "strategy": [
            {"replenishment_quantity": 1.0},
            *[{"replenishment_quantity": 2.5} for _ in range(29)],
        ],
        "metrics": {},
    }
    assessment = ValidationRunner().assess(
        "optimization",
        plan,
        result,
        {"status": "PASS"},
        frame,
    )
    assert assessment.gate == "FAIL"
    assert any(item.code == "RETAIL_MINIMUM_DISPLAY_CONSTRAINT_FAILED" for item in assessment.findings)

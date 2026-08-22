from __future__ import annotations

import numpy as np
import pandas as pd

from mathworkstation.solver_engine import SolverRegistry
from mathworkstation.validation_protocol import ValidationRunner


def _transaction_frame() -> pd.DataFrame:
    """Synthetic contract fixture only; never used as CUMCM 2018 official evidence."""

    rows: list[dict] = []
    origin = pd.Timestamp("2017-01-01")
    receipt = 0

    # Three clearly separated member-behaviour regimes for lifecycle/RFM tests.
    for member_index in range(90):
        member_id = f"M{member_index:03d}"
        regime = member_index // 30
        if regime == 0:  # active: many recent purchases, higher spend
            windows = [2, 3, 4, 5]
            tx_per_window = 4
            base_amount = 240.0
        elif regime == 1:  # dormant: moderate frequency/spend
            windows = [0, 2, 4]
            tx_per_window = 2
            base_amount = 120.0
        else:  # lost: old and sparse
            windows = [0, 1]
            tx_per_window = 1
            base_amount = 45.0
        for window in windows:
            for local_tx in range(tx_per_window):
                receipt += 1
                timestamp = origin + pd.Timedelta(days=window * 30 + local_tx + member_index % 5)
                promotion = 1 if (window % 2 == 0 and member_index % 3 == 0) else 0
                # Strong A-B co-purchase plus a lower-frequency C item.
                products = ["A", "B"]
                if receipt % 3 == 0:
                    products.append("C")
                for product_index, product_id in enumerate(products):
                    rows.append(
                        {
                            "member_id": member_id,
                            "is_member": True,
                            "transaction_id": f"R{receipt:06d}",
                            "timestamp": timestamp,
                            "amount": base_amount / len(products) + product_index,
                            "quantity": 1,
                            "product_id": product_id,
                            "promotion_flag": promotion,
                        }
                    )

    # Non-member receipts for the group-comparison contract.
    for index in range(140):
        receipt += 1
        timestamp = origin + pd.Timedelta(days=index % 180)
        products = ["A"] if index % 3 else ["A", "D"]
        for product_index, product_id in enumerate(products):
            rows.append(
                {
                    "member_id": f"N{index:03d}",
                    "is_member": False,
                    "transaction_id": f"R{receipt:06d}",
                    "timestamp": timestamp,
                    "amount": 35.0 / len(products) + product_index,
                    "quantity": 1,
                    "product_id": product_id,
                    "promotion_flag": 0,
                }
            )
    return pd.DataFrame(rows)


def _activation_frame() -> pd.DataFrame:
    """Synthetic temporal fixture with a known positive promotion association."""

    rows: list[dict] = []
    origin = pd.Timestamp("2017-01-01")
    receipt = 0
    for member_index in range(60):
        member_id = f"A{member_index:03d}"
        promoted = member_index < 30
        for window in range(6):
            if promoted:
                # Even windows are inactive+promotion; the next window becomes active.
                tx_count = 1 if window % 2 == 0 else 3
                promotion = 1 if window % 2 == 0 else 0
            else:
                tx_count = 1
                promotion = 0
            for local_tx in range(tx_count):
                receipt += 1
                rows.append(
                    {
                        "member_id": member_id,
                        "transaction_id": f"A{receipt:06d}",
                        "timestamp": origin + pd.Timedelta(days=window * 30 + local_tx),
                        "promotion_flag": promotion,
                        "amount": 50.0,
                    }
                )
    return pd.DataFrame(rows)


def _solve_and_validate(family: str, plan: dict, frame: pd.DataFrame):
    registry = SolverRegistry()
    plugin = registry.resolve(family, plan)
    errors = plugin.validate_inputs(family, plan, frame)
    assert not errors, errors
    result = plugin.solve(family, plan, frame)
    diagnostics = plugin.diagnose(family, plan, result)
    assert diagnostics["status"] == "PASS"
    assessment = ValidationRunner().assess(family, plan, result, diagnostics, frame)
    return plugin, result, assessment


def test_member_group_profile_is_solver_and_validation_ready() -> None:
    frame = _transaction_frame()
    plan = {
        "solver_method": "member_group_profile",
        "member_flag_column": "is_member",
        "member_value": True,
        "transaction_column": "transaction_id",
        "amount_column": "amount",
        "quantity_column": "quantity",
    }
    plugin, result, assessment = _solve_and_validate("exploratory_analysis", plan, frame)

    assert plugin.name == "gold.member_group_profile"
    assert assessment.gate == "PASS"
    assert result["metrics"]["entity_count"] == 2
    assert {item["entity"] for item in result["profiles"]} == {"member", "non_member"}
    assert np.isclose(sum(item["values"]["sales_share"] for item in result["profiles"]), 1.0)


def test_rfm_member_value_scoring_is_bounded_and_stability_checked() -> None:
    frame = _transaction_frame().query("is_member == True").copy()
    plan = {
        "solver_method": "rfm_member_value",
        "member_column": "member_id",
        "time_column": "timestamp",
        "transaction_column": "transaction_id",
        "amount_column": "amount",
        "reference_time": "2017-07-01",
        "score_dimensions": ["recency_days", "frequency", "monetary", "max_basket"],
    }
    plugin, result, assessment = _solve_and_validate("ranking", plan, frame)

    assert plugin.name == "gold.rfm_member_value"
    assert assessment.gate == "PASS"
    assert result["metrics"]["member_count"] == 90
    assert np.isclose(sum(result["weights"].values()), 1.0)
    assert 0.0 <= result["metrics"]["top_decile_stability"] <= 1.0
    scores = [item["score"] for item in result["ranking"]]
    assert min(scores) >= 0.0 and max(scores) <= 100.0


def test_member_lifecycle_states_have_separation_and_seed_stability() -> None:
    frame = _transaction_frame().query("is_member == True").copy()
    plan = {
        "solver_method": "member_lifecycle_states",
        "member_column": "member_id",
        "time_column": "timestamp",
        "transaction_column": "transaction_id",
        "amount_column": "amount",
        "reference_time": "2017-07-01",
        "n_states": 3,
        "random_seed": 2018,
    }
    plugin, result, assessment = _solve_and_validate("exploratory_analysis", plan, frame)

    assert plugin.name == "gold.member_lifecycle_states"
    assert assessment.gate == "PASS"
    assert result["metrics"]["state_count"] == 3
    assert len(result["member_states"]) == 90
    assert result["metrics"]["silhouette"] > 0.2
    assert result["metrics"]["seed_adjusted_rand"] >= 0.8
    assert {item["state"] for item in result["state_profiles"]} == {"active", "dormant", "lost"}


def test_activation_promotion_association_keeps_causal_guard_and_bootstrap_interval() -> None:
    frame = _activation_frame()
    plan = {
        "solver_method": "activation_promotion_association",
        "member_column": "member_id",
        "time_column": "timestamp",
        "transaction_column": "transaction_id",
        "promotion_column": "promotion_flag",
        "window_days": 30,
        "inactive_max_transactions": 1,
        "active_min_transactions": 2,
        "bootstrap_runs": 300,
        "random_seed": 2018,
    }
    plugin, result, assessment = _solve_and_validate("explanatory_inference", plan, frame)

    assert plugin.name == "gold.activation_promotion_association"
    assert assessment.gate == "PASS"
    assert result["interpretation_guard"] == "associational_not_causal"
    assert result["metrics"]["promotion_rate_difference"] > 0.5
    lower, upper = result["effects"][0]["bootstrap_ci_95"]
    assert lower > 0 and upper > 0


def test_market_basket_association_exposes_support_confidence_and_lift() -> None:
    frame = _transaction_frame().query("is_member == True").copy()
    plan = {
        "solver_method": "market_basket_association",
        "transaction_column": "transaction_id",
        "item_column": "product_id",
        "min_support": 0.05,
        "min_confidence": 0.5,
        "top_k": 10,
    }
    plugin, result, assessment = _solve_and_validate("exploratory_analysis", plan, frame)

    assert plugin.name == "gold.market_basket_association"
    assert assessment.gate == "PASS"
    assert result["metrics"]["rule_count"] >= 2
    assert result["top_rules"]
    assert all(0.0 <= rule["support"] <= 1.0 for rule in result["top_rules"])
    assert all(0.0 <= rule["confidence"] <= 1.0 for rule in result["top_rules"])
    assert all(rule["lift"] >= 0.0 for rule in result["top_rules"])

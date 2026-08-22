from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


ENERGY_STATES = ("AZ", "CA", "NM", "TX")
CORE_MSN_CODES = ("RETCB", "REPRB", "TETCB", "TEPRB", "TETPB", "TPOPP")
PROFILE_COLUMNS = (
    "renewable_consumption_share",
    "renewable_production_share",
    "renewable_consumption_per_capita_mmbtu",
    "total_energy_per_capita_mmbtu",
)
FORECAST_PROFILE_COLUMNS = (
    "renewable_consumption_share",
    "renewable_production_share",
)


def prepare_energy_2018_research(
    seseds: pd.DataFrame,
    *,
    states: tuple[str, ...] = ENERGY_STATES,
) -> tuple[pd.DataFrame, dict[str, dict[str, Any]]]:
    """Build a complete four-state profile panel from the official 2018 SEDS sheet.

    Only six directly documented SEDS series are used. Derived quantities keep
    their unit semantics explicit; no external climate/economic facts are added.
    """

    required = {"MSN", "StateCode", "Year", "Data"}
    missing = sorted(required - set(seseds.columns))
    if missing:
        raise ValueError("ENERGY_2018_COLUMNS_MISSING:" + ",".join(missing))
    raw = seseds.copy()
    raw["StateCode"] = raw["StateCode"].astype(str).str.upper()
    raw["MSN"] = raw["MSN"].astype(str).str.upper()
    raw["Year"] = pd.to_numeric(raw["Year"], errors="raise").astype(int)
    raw["Data"] = pd.to_numeric(raw["Data"], errors="coerce")
    raw = raw[
        raw["StateCode"].isin(states)
        & raw["MSN"].isin(CORE_MSN_CODES)
        & raw["Year"].between(1960, 2009)
    ].copy()
    observed_states = tuple(sorted(raw["StateCode"].dropna().unique()))
    if observed_states != tuple(sorted(states)):
        raise ValueError(
            "ENERGY_2018_STATE_COVERAGE_MISSING:"
            + ",".join(sorted(set(states) - set(observed_states)))
        )
    panel = raw.pivot_table(
        index=["StateCode", "Year"],
        columns="MSN",
        values="Data",
        aggfunc="first",
    ).reset_index()
    missing_codes = [code for code in CORE_MSN_CODES if code not in panel.columns]
    if missing_codes:
        raise ValueError("ENERGY_2018_CORE_SERIES_MISSING:" + ",".join(missing_codes))
    expected_rows = len(states) * 50
    if len(panel) != expected_rows:
        raise ValueError(f"ENERGY_2018_PANEL_ROWS_INVALID:{len(panel)}!={expected_rows}")
    if panel[list(CORE_MSN_CODES)].isna().any().any():
        raise ValueError("ENERGY_2018_CORE_SERIES_HAS_MISSING_VALUES")
    if (panel[["TETCB", "TEPRB", "TPOPP"]] <= 0).any().any():
        raise ValueError("ENERGY_2018_DENOMINATOR_NONPOSITIVE")

    panel["Date"] = pd.to_datetime(panel["Year"].astype(str) + "-01-01")
    panel["renewable_consumption_share"] = panel["RETCB"] / panel["TETCB"]
    panel["renewable_production_share"] = panel["REPRB"] / panel["TEPRB"]
    # Billion Btu / thousand residents = million Btu per resident.
    panel["renewable_consumption_per_capita_mmbtu"] = panel["RETCB"] / panel["TPOPP"]
    panel["total_energy_per_capita_mmbtu"] = panel["TETPB"]
    panel = panel.sort_values(["StateCode", "Year"]).reset_index(drop=True)

    plans: dict[str, dict[str, Any]] = {
        "I-A": {
            "solver_method": "panel_profile_summary",
            "group_column": "StateCode",
            "time_column": "Date",
            "profile_columns": list(PROFILE_COLUMNS),
            "reference_time": "2009-01-01",
        },
        "I-B": {
            "solver_method": "panel_trend_characterization",
            "group_column": "StateCode",
            "time_column": "Date",
            "target_columns": [
                "renewable_consumption_share",
                "renewable_production_share",
                "total_energy_per_capita_mmbtu",
            ],
            "test_size": 0.2,
        },
        "I-C": {
            "solver_method": "entropy_topsis",
            "entity_column": "StateCode",
            "criteria": [
                {"column": "renewable_consumption_share", "direction": "benefit"},
                {"column": "renewable_production_share", "direction": "benefit"},
                {"column": "renewable_consumption_per_capita_mmbtu", "direction": "benefit"},
                {"column": "total_energy_per_capita_mmbtu", "direction": "cost"},
            ],
        },
        "I-D": {
            "solver_method": "panel_holt",
            "group_column": "StateCode",
            "time_column": "Date",
            "target_columns": list(FORECAST_PROFILE_COLUMNS),
            "target_transforms": {
                "renewable_consumption_share": "logit_01",
                "renewable_production_share": "logit_01",
            },
            "future_times": ["2025-01-01", "2050-01-01"],
            "test_size": 0.2,
            "bootstrap_runs": 400,
            "random_seed": 2018,
        },
    }
    return panel, plans


def energy_2009_decision_frame(panel: pd.DataFrame) -> pd.DataFrame:
    required = {"StateCode", "Year", *PROFILE_COLUMNS}
    missing = sorted(required - set(panel.columns))
    if missing:
        raise ValueError("ENERGY_PROFILE_COLUMNS_MISSING:" + ",".join(missing))
    frame = panel[pd.to_numeric(panel["Year"], errors="raise").astype(int) == 2009][
        ["StateCode", *PROFILE_COLUMNS]
    ].copy()
    if sorted(frame["StateCode"].astype(str)) != sorted(ENERGY_STATES):
        raise ValueError("ENERGY_2009_STATE_COVERAGE_INCOMPLETE")
    return frame.reset_index(drop=True)


def build_energy_compact_target_plan(
    panel: pd.DataFrame,
    forecast_result: dict[str, Any],
) -> dict[str, Any]:
    """Create historically bounded stretch targets for 2025 and 2050.

    The lower bound for each state-year target is its no-policy panel forecast.
    The raw upper bound adds no more renewable-consumption-share improvement
    than that state has actually achieved over an equally long historical
    window. The 2050 envelope is then made non-decreasing relative to the 2025
    envelope, because a compact should not define a weaker long-run stretch
    ceiling than an already accepted nearer-term goal. This is a transparent
    feasibility envelope, not a claim about policy cost.
    """

    grid = list(forecast_result.get("forecast_grid") or [])
    consumption = [
        item for item in grid
        if str(item.get("target")) == "renewable_consumption_share"
    ]
    by_key = {
        (str(item["entity"]), int(str(item["future_time"])[:4])): float(item["point"])
        for item in consumption
    }
    expected = {(state, year) for state in ENERGY_STATES for year in (2025, 2050)}
    if set(by_key) != expected:
        raise ValueError("ENERGY_TARGET_FORECAST_GRID_INCOMPLETE")

    variables: list[dict[str, Any]] = []
    objective: dict[str, float] = {}
    feasibility: dict[str, dict[str, float]] = {}
    for state in ENERGY_STATES:
        history = panel[panel["StateCode"].astype(str) == state].sort_values("Year")
        years = history["Year"].to_numpy(dtype=int)
        shares = history["renewable_consumption_share"].to_numpy(dtype=float)
        previous_upper = 0.0
        for year in (2025, 2050):
            horizon = year - 2009
            improvements = []
            for index, start_year in enumerate(years):
                target_year = start_year + horizon
                matches = np.where(years == target_year)[0]
                if len(matches):
                    improvements.append(float(shares[matches[0]] - shares[index]))
            max_observed_uplift = max([0.0, *improvements])
            baseline = float(np.clip(by_key[(state, year)], 0.0, 1.0))
            raw_upper = float(np.clip(baseline + max_observed_uplift, baseline, 1.0))
            upper = float(max(raw_upper, previous_upper, baseline))
            previous_upper = upper
            name = f"target_{state}_{year}"
            variables.append(
                {"name": name, "lower": baseline, "upper": upper, "type": "continuous"}
            )
            objective[name] = 1.0 / len(expected)
            feasibility[name] = {
                "no_policy_forecast": baseline,
                "max_historical_same_horizon_uplift": max_observed_uplift,
                "raw_same_horizon_upper_bound": raw_upper,
                "upper_bound": upper,
                "non_decreasing_envelope": True,
            }
    return {
        "solver_method": "linear_programming",
        "variables": variables,
        "objective": {"sense": "max", "coefficients": objective},
        "constraints": [],
        "target_semantics": "maximize mean renewable-consumption share within no-policy lower bounds and historically observed same-horizon uplift limits",
        "feasibility_envelope": feasibility,
    }

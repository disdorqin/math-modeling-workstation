"""Unified time-series analysis toolkit for MCM C problems.

This module provides a reusable, dependency-light set of time-series analysis
routines (trend decomposition, autocorrelation, stationarity, change-point
detection, sliding-window statistics and a composite report) that can be
plugged into any problem that has an ordered time axis.  It was created to
satisfy task tc299a729: bring time-series grounding to the 2023 (Wordle daily
reports) and 2018 (Texas energy, yearly) papers.

It deliberately does NOT depend on the O-award momentum module; it is a
standalone complement.  The only external dependencies are numpy / pandas /
scipy / statsmodels (already present in the environment).  In particular it
uses ``statsmodels.stats.diagnostic.acorr_ljungbox`` because
``scipy.stats.acorr_ljungbox`` is not available in this environment (this is
the same root cause behind opencode's taedfb374 Ljung-Box failure).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from statsmodels.stats.diagnostic import acorr_ljungbox
from statsmodels.stats.stattools import durbin_watson
from statsmodels.tsa.stattools import adfuller


@dataclass
class TrendDecomposition:
    """Period decomposition of a series into fitted trend + residual."""

    method: str
    series_name: str
    fitted_trend: List[float]
    detrended: List[float]  # series - trend (residual around trend)
    n_points: int
    residual_std: float
    coefficient_of_variation: float  # relative variability of residuals


@dataclass
class AutocorrelationResult:
    """Autocorrelation / serial-correlation diagnostics."""

    series_name: str
    lags: List[int]
    acf: List[float]
    lb_stat: float
    lb_pvalue: float
    lb_lags: int
    durbin_watson: float
    has_serial_correlation: bool
    interpretation: str


@dataclass
class StationarityResult:
    """Augmented Dickey-Fuller stationarity test."""

    series_name: str
    adf_stat: float
    pvalue: float
    n_lags: int
    is_stationary: bool
    interpretation: str


@dataclass
class ChangePointResult:
    """Change-point / structural-break detection via rolling means."""

    series_name: str
    window: int
    change_points: List[int]
    segment_means: List[float]
    max_relative_jump: float
    interpretation: str


@dataclass
class SlideStatsResult:
    """Sliding-window descriptive statistics over time."""

    series_name: str
    window: int
    rolling_mean_mean: float
    rolling_std_mean: float
    overall_mean: float
    overall_std: float
    min_value: float
    max_value: float
    trend_slope: float  # OLS slope per step, normalized by mean


@dataclass
class SeriesReport:
    """Complete composite time-series report for a single series."""

    series_name: str
    n_points: int
    frequency: str
    trend: TrendDecomposition
    autocorrelation: AutocorrelationResult
    stationarity: StationarityResult
    change_points: ChangePointResult
    sliding: SlideStatsResult
    summary: str



# ── reusable building blocks ─────────────────────────────────────────────


def _as_float_list(series: pd.Series) -> List[float]:
    return [float(x) for x in series.dropna().astype(float)]


def decompose_trend(series: pd.Series, name: str, method: str = "rolling", window: int = 7) -> TrendDecomposition:
    """Fit a deterministic trend and return trend + residual decomposition.

    ``method="rolling"`` uses a centered/rolling mean as the trend (robust and
    dependency-free); ``method="poly"`` uses a degree-1 global linear trend.
    """
    s = series.dropna().astype(float)
    n = len(s)
    if n == 0:
        raise ValueError("empty series for trend decomposition")
    if method == "poly":
        x = np.arange(n, dtype=float)
        b, a = np.polyfit(x, s.to_numpy(), 1)
        fitted = a + b * x
    else:  # rolling
        w = max(3, min(window, n))
        fitted = s.rolling(window=w, center=True, min_periods=1).mean().to_numpy()
    detrended = s.to_numpy() - fitted
    residual_std = float(np.std(detrended))
    mean = float(np.mean(s.to_numpy()))
    cv = float(residual_std / mean) if mean != 0 else 0.0
    return TrendDecomposition(
        method=method,
        series_name=name,
        fitted_trend=[float(x) for x in fitted],
        detrended=[float(x) for x in detrended],
        n_points=n,
        residual_std=residual_std,
        coefficient_of_variation=cv,
    )


def autocorrelation(series: pd.Series, name: str, lags: int = 10) -> AutocorrelationResult:
    """Serial-correlation diagnostics: ACF + Ljung-Box + Durbin-Watson.

    Uses ``statsmodels.stats.diagnostic.acorr_ljungbox`` so the analysis works
    even when ``scipy.stats.acorr_ljungbox`` is unavailable.
    """
    s = series.dropna().astype(float)
    n = len(s)
    if n < 3:
        raise ValueError("too few points for autocorrelation")
    lags = max(1, min(lags, n - 1))
    centered = s.to_numpy() - np.mean(s.to_numpy())
    var = float(np.dot(centered, centered))
    acf = []
    for k in range(1, lags + 1):
        if var <= 0:
            acf.append(0.0)
            continue
        c = float(np.dot(centered[:-k], centered[k:]) / var)
        acf.append(c)
    lb = acorr_ljungbox(s, lags=[lags], return_df=True)
    lb_stat = float(lb["lb_stat"].iloc[-1])
    lb_pvalue = float(lb["lb_pvalue"].iloc[-1])
    try:
        dw = float(durbin_watson(s))
    except Exception:
        dw = float("nan")
    has_scc = lb_pvalue < 0.05
    interp = (
        f"Ljung-Box Q({lags}) = {lb_stat:.2f}, p = {lb_pvalue:.4f}, DW = "
        f"{dw:.2f}. "
        + (
            "Reject independence: significant serial correlation (trend/seasonality)."
            if has_scc
            else "No significant serial correlation detected."
        )
    )
    return AutocorrelationResult(
        series_name=name,
        lags=list(range(1, lags + 1)),
        acf=acf,
        lb_stat=lb_stat,
        lb_pvalue=lb_pvalue,
        lb_lags=lags,
        durbin_watson=dw,
        has_serial_correlation=has_scc,
        interpretation=interp,
    )


def stationarity(series: pd.Series, name: str, maxlag: Optional[int] = None) -> StationarityResult:
    """Augmented Dickey-Fuller test (statsmodels)."""
    s = series.dropna().astype(float)
    if len(s) < 4:
        raise ValueError("too few points for ADF")
    adf, pv, usedlag, _, _, _ = adfuller(s, maxlag=maxlag, autolag="AIC")
    is_st = float(pv) < 0.05
    interp = (
        f"ADF = {float(adf):.3f}, p = {float(pv):.4f}. "
        f"{'Series is stationary (reject unit root).' if is_st else 'Series has a unit root / non-stationary (consistent with a trend).'}"
    )
    return StationarityResult(
        series_name=name,
        adf_stat=float(adf),
        pvalue=float(pv),
        n_lags=int(usedlag),
        is_stationary=is_st,
        interpretation=interp,
    )


def change_points(series: pd.Series, name: str, window: int = 5) -> ChangePointResult:
    """Detect structural breaks by comparing local rolling means.

    A point i is flagged when the mean of the preceding `window` observations
    differs from the following `window` by more than one rolling std.
    """
    s = series.dropna().astype(float)
    n = len(s)
    if n < 2 * window + 2:
        raise ValueError("series too short for change-point detection")
    arr = s.to_numpy()
    std = float(np.std(arr))
    cps = []
    for i in range(window, n - window):
        left = np.mean(arr[i - window : i])
        right = np.mean(arr[i : i + window])
        if std > 0 and abs(left - right) > std:
            cps.append(i)
    bounds = [0] + cps + [n]
    seg_means = [float(np.mean(arr[bounds[j] : bounds[j + 1]])) for j in range(len(bounds) - 1)]
    overall = float(np.mean(arr))
    max_jump = 0.0
    significant = []
    for j in range(len(seg_means) - 1):
        if overall != 0:
            jump = abs(seg_means[j + 1] - seg_means[j]) / overall
            max_jump = max(max_jump, jump)
            if jump >= 0.05:
                significant.append(cps[j] if j < len(cps) else None)
    significant = [c for c in significant if c is not None]
    interp = (
        f"Detected {len(significant)} significant structural breaks; "
        f"max relative segment jump = {max_jump:.1%}."
    )
    return ChangePointResult(
        series_name=name,
        window=window,
        change_points=significant,
        segment_means=seg_means,
        max_relative_jump=max_jump,
        interpretation=interp,
    )


def sliding_stats(series: pd.Series, name: str, window: int = 7) -> SlideStatsResult:
    """Rolling descriptive statistics + normalized OLS trend slope."""
    s = series.dropna().astype(float)
    n = len(s)
    if n < 3:
        raise ValueError("series too short for sliding stats")
    w = max(2, min(window, n // 2))
    roll = s.rolling(window=w, min_periods=1)
    mean = float(np.mean(s))
    trend_slope = 0.0
    if len(s) > 1:
        x = np.arange(len(s), dtype=float)
        b, _ = np.polyfit(x, s.to_numpy(), 1)
        trend_slope = float(b / mean) if mean != 0 else float(b)
    return SlideStatsResult(
        series_name=name,
        window=w,
        rolling_mean_mean=float(np.mean(roll.mean())),
        rolling_std_mean=float(np.mean(roll.std())),
        overall_mean=mean,
        overall_std=float(np.std(s)),
        min_value=float(np.min(s)),
        max_value=float(np.max(s)),
        trend_slope=trend_slope,
    )



def analyze_series(
    series: pd.Series,
    name: str,
    frequency: str = "daily",
    lags: int = 10,
    window: int = 7,
    trend_method: str = "rolling",
) -> SeriesReport:
    """Run the full composite analysis for a single ordered series.

    Args:
        series: pandas Series with a clean numeric index (ordered).
        name: human-readable series name.
        frequency: data cadence label ("daily", "yearly", ...).
        lags: number of Ljung-Box lags.
        window: sliding window / trend window / change-point window.
        trend_method: "rolling" or "poly".

    Returns:
        SeriesReport aggregating all diagnostics.
    """
    trend = decompose_trend(series, name, method=trend_method, window=window)
    ac = autocorrelation(series, name, lags=lags)
    st = stationarity(series, name)
    cp = change_points(series, name, window=window)
    sw = sliding_stats(series, name, window=window)
    summary = (
        f"{name} ({frequency}, n={len(series)}): "
        f"{'serial correlation present' if ac.has_serial_correlation else 'no serial correlation'}, "
        f"{'non-stationary (trend)' if not st.is_stationary else 'stationary'}, "
        f"ADF p={st.pvalue:.3f}, LB p={ac.lb_pvalue:.3f}, "
        f"trend slope (normalized) = {sw.trend_slope:+.3f}/step, "
        f"{len(cp.change_points)} breaks. {cp.interpretation}"
    )
    return SeriesReport(
        series_name=name,
        n_points=len(series),
        frequency=frequency,
        trend=trend,
        autocorrelation=ac,
        stationarity=st,
        change_points=cp,
        sliding=sw,
        summary=summary,
    )


def to_json_dict(report: SeriesReport) -> Dict[str, Any]:
    """Serialize a SeriesReport into a JSON-friendly dict (no numpy types)."""

    def _clean(v: Any) -> Any:
        if isinstance(v, (np.integer,)):
            return int(v)
        if isinstance(v, (np.floating,)):
            return float(v)
        if isinstance(v, np.ndarray):
            return [_clean(x) for x in v.tolist()]
        if isinstance(v, list):
            return [_clean(x) for x in v]
        if isinstance(v, dict):
            return {k: _clean(x) for k, x in v.items()}
        return v

    return _clean(asdict(report))


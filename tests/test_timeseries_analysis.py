"""Tests for the unified time-series analysis module (task tc299a729)."""

import numpy as np
import pandas as pd
import pytest

from mathworkstation.timeseries_analysis import (
    analyze_series,
    autocorrelation,
    change_points,
    decompose_trend,
    sliding_stats,
    stationarity,
    to_json_dict,
)


@pytest.fixture
def trending_series():
    """A clean upward-trending series with mild noise (non-stationary, trending)."""
    rng = np.random.default_rng(7)
    x = np.arange(80, dtype=float)
    y = 10.0 + 0.3 * x + rng.normal(0, 1.5, size=80)
    return pd.Series(y)


@pytest.fixture
def random_series():
    """A stationary white-noise series."""
    rng = np.random.default_rng(11)
    return pd.Series(rng.normal(0, 1.0, size=200))


def test_decompose_trend_shapes(trending_series):
    td = decompose_trend(trending_series, "trend", method="rolling", window=7)
    assert td.n_points == 80
    assert len(td.fitted_trend) == 80
    assert len(td.detrended) == 80
    assert td.series_name == "trend"
    # detrended should be much smaller than original spread
    original_std = float(np.std(trending_series))
    assert td.residual_std < original_std


def test_decompose_trend_poly_preserves_slope(trending_series):
    td = decompose_trend(trending_series, "t", method="poly", window=7)
    # slope ~ 0.3 -> fitted trend endpoints reflect it
    assert td.fitted_trend[-1] > td.fitted_trend[0]


def test_autocorrelation_white_noise(random_series):
    ac = autocorrelation(random_series, "wn", lags=10)
    assert ac.lb_lags == 10
    assert len(ac.acf) == 10
    # white noise: should NOT reject independence
    assert ac.has_serial_correlation is False


def test_autocorrelation_trend_has_serial_corr(trending_series):
    ac = autocorrelation(trending_series, "trend", lags=10)
    assert ac.has_serial_correlation is True


def test_stationarity_trending_series_has_unit_root(trending_series):
    st = stationarity(trending_series, "trend")
    assert st.is_stationary is False  # trending => ADF can't reject unit root


def test_stationarity_white_noise_is_stationary(random_series):
    st = stationarity(random_series, "wn")
    assert st.is_stationary is True


def test_change_points_runs(trending_series):
    cp = change_points(trending_series, "trend", window=5)
    assert isinstance(cp.change_points, list)
    assert cp.window == 5
    assert len(cp.segment_means) >= 1


def test_sliding_stats(trending_series):
    sw = sliding_stats(trending_series, "trend", window=7)
    assert sw.overall_mean > 0
    assert sw.max_value >= sw.min_value
    assert sw.trend_slope > 0  # upward series -> positive normalized slope


def test_analyze_series_composite(trending_series):
    report = analyze_series(trending_series, "synth", frequency="daily", lags=8, window=7)
    assert report.n_points == 80
    assert report.frequency == "daily"
    assert len(report.summary) > 0
    assert report.autocorrelation.has_serial_correlation is True
    assert report.stationarity.is_stationary is False


def test_to_json_dict_clean_types(trending_series):
    report = analyze_series(trending_series, "synth", lags=6, window=5)
    d = to_json_dict(report)
    import json
    roundtripped = json.loads(json.dumps(d))  # must serialize
    assert roundtripped["series_name"] == "synth"
    assert isinstance(roundtripped["autocorrelation"]["lb_pvalue"], float)
    assert isinstance(roundtripped["n_points"], int)

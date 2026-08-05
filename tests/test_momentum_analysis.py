"""Tests for momentum analysis module."""

import numpy as np
import pandas as pd
import pytest

from mathworkstation.momentum_analysis import (
    define_momentum,
    compute_naive_binomial_expected,
    compute_momentum_residual,
    sliding_window_momentum,
    ljung_box_test,
    runs_test,
    server_advantage_weighting,
    predict_momentum_shifts,
    full_momentum_analysis,
    format_report_markdown,
)


@pytest.fixture
def sample_tennis_data():
    """Create sample tennis match data."""
    np.random.seed(42)
    n_points = 500
    
    # Simulate match with some momentum effects
    server = np.random.choice([1, 2], size=n_points, p=[0.5, 0.5])
    
    # Base win probability (server advantage)
    p1_win_prob = np.where(server == 1, 0.65, 0.35)
    
    # Add momentum effect (consecutive wins)
    momentum = np.zeros(n_points)
    for i in range(1, n_points):
        if np.random.random() < 0.1:  # 10% chance of momentum shift
            momentum[i] = momentum[i - 1] * 0.5 + np.random.choice([-1, 1]) * 0.3
        else:
            momentum[i] = momentum[i - 1] * 0.8
    
    # Adjust probabilities based on momentum
    p1_win_prob = np.clip(p1_win_prob + momentum * 0.2, 0.1, 0.9)
    
    # Generate point winners
    point_victor = np.where(np.random.random(n_points) < p1_win_prob, 1, 2)
    
    return pd.DataFrame({
        "server": server,
        "point_victor": point_victor,
        "elapsed_time": np.arange(n_points),
        "p1_score": np.random.choice(["0", "15", "30", "40"], size=n_points),
        "p2_score": np.random.choice(["0", "15", "30", "40"], size=n_points),
    })


def test_define_momentum():
    """Test momentum definition."""
    # Test default (residual method)
    defn = define_momentum()
    assert defn.method == "residual"
    assert defn.window_size == 5
    assert defn.momentum_threshold == 0.3
    assert "residual" in defn.description.lower()
    
    # Test consecutive points method
    defn2 = define_momentum(method="consecutive_points", window_size=10)
    assert defn2.method == "consecutive_points"
    assert defn2.window_size == 10
    assert "consecutive" in defn2.description.lower()
    
    # Test score differential method
    defn3 = define_momentum(method="score_differential", momentum_threshold=0.5)
    assert defn3.method == "score_differential"
    assert defn3.momentum_threshold == 0.5


def test_compute_naive_binomial_expected(sample_tennis_data):
    """Test Naive Binomial Model expected probability computation."""
    expected = compute_naive_binomial_expected(sample_tennis_data)
    
    # Check output shape
    assert len(expected) == len(sample_tennis_data)
    
    # Check all values are between 0 and 1
    assert (expected >= 0).all()
    assert (expected <= 1).all()
    
    # Check server 1 has different expected than server 2
    server1_expected = expected[sample_tennis_data["server"] == 1].mean()
    server2_expected = expected[sample_tennis_data["server"] == 2].mean()
    assert server1_expected != server2_expected


def test_compute_momentum_residual(sample_tennis_data):
    """Test momentum residual computation."""
    momentum = compute_momentum_residual(sample_tennis_data)
    
    # Check output shape
    assert len(momentum) == len(sample_tennis_data)
    
    # Check momentum is centered around 0
    assert abs(momentum.mean()) < 0.2  # Should be close to 0
    
    # Check momentum values are reasonable
    assert momentum.min() >= -1.0
    assert momentum.max() <= 1.0


def test_sliding_window_momentum(sample_tennis_data):
    """Test sliding window momentum analysis."""
    result = sliding_window_momentum(sample_tennis_data, window_size=5)
    
    # Check output
    assert result.window_size == 5
    assert len(result.momentum_series) == len(sample_tennis_data)
    assert isinstance(result.momentum_shifts, list)
    assert result.shift_frequency >= 0
    assert result.avg_momentum_duration > 0


def test_ljung_box_test(sample_tennis_data):
    """Test Ljung-Box Q Test."""
    result = ljung_box_test(sample_tennis_data)
    
    # Check output structure
    assert result.test_name == "Ljung-Box Q Test"
    assert result.statistic >= 0
    assert 0 <= result.p_value <= 1
    assert "momentum" in result.null_hypothesis.lower()
    assert isinstance(result.reject_null, bool)
    assert len(result.interpretation) > 0


def test_runs_test(sample_tennis_data):
    """Test Runs Test for randomness."""
    result = runs_test(sample_tennis_data)
    
    # Check output structure
    assert result.test_name == "Runs Test"
    assert 0 <= result.p_value <= 1
    assert "momentum" in result.null_hypothesis.lower()
    assert bool(result.reject_null) in [True, False]
    assert len(result.interpretation) > 0


def test_server_advantage_weighting(sample_tennis_data):
    """Test server advantage weighting."""
    momentum = compute_momentum_residual(sample_tennis_data)
    result = server_advantage_weighting(
        sample_tennis_data, momentum=momentum
    )
    
    # Check output
    assert 0 <= result.server_win_rate <= 1
    assert 0 <= result.returner_advantage <= 1
    assert abs(result.server_win_rate + result.returner_advantage - 1.0) < 0.01


def test_predict_momentum_shifts(sample_tennis_data):
    """Test momentum shift prediction."""
    result = predict_momentum_shifts(
        sample_tennis_data,
        window_size=5,
        shift_threshold=0.2,
    )
    
    # Check output
    assert "momentum_series" in result
    assert "shifts" in result
    assert "phases" in result
    assert "predicted_next_shift" in result
    assert len(result["momentum_series"]) == len(sample_tennis_data)


def test_full_momentum_analysis(sample_tennis_data):
    """Test complete momentum analysis."""
    report = full_momentum_analysis(sample_tennis_data)
    
    # Check report structure
    assert report.momentum_definition is not None
    assert len(report.hypothesis_tests) == 2  # Ljung-Box and Runs
    assert report.sliding_window is not None
    assert report.server_weight is not None
    assert isinstance(report.momentum_exists, bool)
    assert 0 <= report.confidence_level <= 1
    assert len(report.summary) > 0


def test_format_report_markdown(sample_tennis_data):
    """Test Markdown report formatting."""
    report = full_momentum_analysis(sample_tennis_data)
    markdown = format_report_markdown(report)
    
    # Check Markdown content
    assert "## Momentum Analysis Report" in markdown
    assert "### Momentum Definition" in markdown
    assert "### Hypothesis Tests" in markdown
    assert "### Sliding Window Analysis" in markdown
    assert "### Server Advantage" in markdown
    assert "### Conclusion" in markdown


def test_momentum_with_missing_columns():
    """Test momentum analysis with missing columns."""
    df = pd.DataFrame({
        "server": [1, 2, 1, 2],
        "point_victor": [1, 1, 2, 2],
    })
    
    # Should handle gracefully
    expected = compute_naive_binomial_expected(df)
    assert len(expected) == 4
    
    momentum = compute_momentum_residual(df)
    assert len(momentum) == 4
    
    result = ljung_box_test(df)
    assert result.test_name == "Ljung-Box Q Test"


def test_momentum_with_insufficient_data():
    """Test momentum analysis with insufficient data."""
    df = pd.DataFrame({
        "server": [1, 2],
        "point_victor": [1, 2],
    })
    
    # Should handle gracefully
    result = ljung_box_test(df)
    assert "Insufficient" in result.interpretation
    
    result2 = runs_test(df)
    assert "Insufficient" in result2.interpretation

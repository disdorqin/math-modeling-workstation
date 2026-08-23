"""Momentum analysis for tennis matches — O-award method implementation.

This module implements key methods from the O-award paper:
1. Momentum definition (residual effect from Naive Binomial Model)
2. Hypothesis testing (Ljung-Box Q Test, Runs Test)
3. Sliding window analysis (continuous N-point state changes)
4. Server advantage weighting

Reference: Team 2401298 MCM/ICM 2024 C题 O-award paper.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
from scipy import stats


@dataclass
class MomentumDefinition:
    """Operational definition of momentum in tennis."""
    method: str  # "residual", "consecutive_points", "score_differential"
    window_size: int = 5  # sliding window size (points)
    momentum_threshold: float = 0.3  # threshold to declare momentum shift
    description: str = ""


@dataclass
class HypothesisTestResult:
    """Result of hypothesis test for momentum existence."""
    test_name: str  # "Ljung-Box", "Runs Test"
    statistic: float
    p_value: float
    null_hypothesis: str  # "momentum does not exist (swings are random)"
    reject_null: bool  # True if we reject null hypothesis
    interpretation: str


@dataclass
class SlidingWindowResult:
    """Result of sliding window momentum analysis."""
    window_size: int
    momentum_series: List[float]  # momentum values over time
    momentum_shifts: List[int]  # indices where momentum shifts
    shift_frequency: float  # average shifts per match
    avg_momentum_duration: float  # average duration of momentum phase


@dataclass
class ServerWeightResult:
    """Result of server advantage weighting."""
    server_win_rate: float  # overall server win rate
    returner_advantage: float  # returner advantage (1 - server_win_rate)
    server_momentum_effect: float  # server advantage on momentum
    returner_momentum_effect: float  # returner advantage on momentum


@dataclass
class MomentumAnalysisReport:
    """Complete momentum analysis report."""
    momentum_definition: MomentumDefinition
    hypothesis_tests: List[HypothesisTestResult]
    sliding_window: SlidingWindowResult
    server_weight: ServerWeightResult
    momentum_exists: bool  # overall conclusion
    confidence_level: float  # confidence in conclusion (0-1)
    summary: str


def define_momentum(
    method: str = "residual",
    window_size: int = 5,
    momentum_threshold: float = 0.3,
) -> MomentumDefinition:
    """Define momentum operationally.
    
    Args:
        method: "residual" (O-award method), "consecutive_points", or "score_differential"
        window_size: number of consecutive points for sliding window
        momentum_threshold: threshold to declare momentum shift (0-1)
    
    Returns:
        MomentumDefinition with operational definition
    """
    descriptions = {
        "residual": (
            "Momentum is defined as the residual effect of actual points won "
            "minus expected points from a Naive Binomial Model. Positive residuals "
            "indicate player 1 momentum, negative residuals indicate player 2 momentum."
        ),
        "consecutive_points": (
            "Momentum is defined as consecutive points won by one player. "
            "A momentum phase is identified when a player wins N consecutive points "
            "exceeding the expected binomial probability."
        ),
        "score_differential": (
            "Momentum is defined as the rate of change in score differential. "
            "Rapid changes in point differential indicate momentum shifts."
        ),
    }
    
    return MomentumDefinition(
        method=method,
        window_size=window_size,
        momentum_threshold=momentum_threshold,
        description=descriptions.get(method, "Custom momentum definition."),
    )


def compute_naive_binomial_expected(
    df: pd.DataFrame,
    player_col: str = "server",
    winner_col: str = "point_victor",
) -> pd.Series:
    """Compute expected points from Naive Binomial Model.
    
    The Naive Binomial Model assumes:
    - P(player 1 wins point | server = 1) = M1
    - P(player 1 wins point | server = 2) = M2
    where M1, M2 are estimated from the data.
    
    Args:
        df: DataFrame with match data
        player_col: column identifying the server (1 or 2)
        winner_col: column identifying point winner (1 or 2)
    
    Returns:
        Series of expected probabilities for player 1 winning each point
    """
    if player_col not in df.columns or winner_col not in df.columns:
        return pd.Series(0.5, index=df.index)
    
    # Estimate M1 (P(player 1 wins | server = 1))
    server1_mask = df[player_col] == 1
    if server1_mask.sum() > 0:
        m1 = (df.loc[server1_mask, winner_col] == 1).mean()
    else:
        m1 = 0.5
    
    # Estimate M2 (P(player 1 wins | server = 2))
    server2_mask = df[player_col] == 2
    if server2_mask.sum() > 0:
        m2 = (df.loc[server2_mask, winner_col] == 1).mean()
    else:
        m2 = 0.5
    
    # Expected probability for each point
    expected = pd.Series(0.5, index=df.index)
    expected[server1_mask] = m1
    expected[server2_mask] = m2
    
    return expected


def compute_momentum_residual(
    df: pd.DataFrame,
    player_col: str = "server",
    winner_col: str = "point_victor",
) -> pd.Series:
    """Compute momentum as residual effect (O-award method).
    
    Momentum = Actual points won - Expected points from Naive Binomial Model.
    Positive momentum = player 1 momentum, Negative = player 2 momentum.
    
    Args:
        df: DataFrame with match data
        player_col: column identifying the server
        winner_col: column identifying point winner
    
    Returns:
        Series of momentum residuals
    """
    # Actual outcome (1 if player 1 wins, 0 if player 2 wins)
    actual = (df[winner_col] == 1).astype(float)
    
    # Expected from Naive Binomial Model
    expected = compute_naive_binomial_expected(df, player_col, winner_col)
    
    # Momentum residual
    momentum = actual - expected
    
    return momentum


def sliding_window_momentum(
    df: pd.DataFrame,
    window_size: int = 5,
    player_col: str = "server",
    winner_col: str = "point_victor",
) -> SlidingWindowResult:
    """Perform sliding window momentum analysis.
    
    Computes rolling momentum score and identifies momentum shifts.
    
    Args:
        df: DataFrame with match data
        window_size: number of consecutive points in window
        player_col: column identifying the server
        winner_col: column identifying point winner
    
    Returns:
        SlidingWindowResult with momentum series and shift detection
    """
    momentum = compute_momentum_residual(df, player_col, winner_col)
    
    # Rolling momentum (average over window)
    rolling_momentum = momentum.rolling(window=window_size, min_periods=1).mean()
    
    # Identify momentum shifts (sign changes)
    momentum_series = rolling_momentum.tolist()
    shifts = []
    for i in range(1, len(momentum_series)):
        if (momentum_series[i] > 0 and momentum_series[i - 1] <= 0) or \
           (momentum_series[i] < 0 and momentum_series[i - 1] >= 0):
            shifts.append(i)
    
    # Calculate shift frequency and average duration
    shift_frequency = len(shifts) / max(1, len(df))
    
    if len(shifts) > 1:
        durations = [shifts[i + 1] - shifts[i] for i in range(len(shifts) - 1)]
        avg_duration = sum(durations) / len(durations)
    else:
        avg_duration = float(len(df))
    
    return SlidingWindowResult(
        window_size=window_size,
        momentum_series=momentum_series,
        momentum_shifts=shifts,
        shift_frequency=shift_frequency,
        avg_momentum_duration=avg_duration,
    )


def ljung_box_test(
    df: pd.DataFrame,
    winner_col: str = "point_victor",
    lags: int = 10,
) -> HypothesisTestResult:
    """Perform Ljung-Box Q Test for momentum existence.
    
    Null hypothesis: Momentum does not exist (swings are random).
    If p-value < 0.05, we reject null hypothesis and conclude momentum exists.
    
    Args:
        df: DataFrame with match data
        winner_col: column identifying point winner
        lags: number of lags for the test
    
    Returns:
        HypothesisTestResult with test statistics
    """
    # Convert to binary series (1 if player 1 wins, 0 if player 2 wins)
    if winner_col not in df.columns:
        return HypothesisTestResult(
            test_name="Ljung-Box Q Test",
            statistic=0.0,
            p_value=1.0,
            null_hypothesis="momentum does not exist (swings are random)",
            reject_null=False,
            interpretation="Cannot perform test: winner column not found.",
        )
    
    series = (df[winner_col] == 1).astype(float)
    
    # Remove any NaN values
    series = series.dropna()
    
    if len(series) < lags + 1:
        return HypothesisTestResult(
            test_name="Ljung-Box Q Test",
            statistic=0.0,
            p_value=1.0,
            null_hypothesis="momentum does not exist (swings are random)",
            reject_null=False,
            interpretation="Insufficient data for Ljung-Box test.",
        )
    
    # Perform Ljung-Box test
    try:
        lb_result = stats.acorr_ljungbox(series, lags=lags, return_df=True)
        statistic = float(lb_result["lb_stat"].iloc[-1])
        p_value = float(lb_result["lb_pvalue"].iloc[-1])
    except Exception as e:
        return HypothesisTestResult(
            test_name="Ljung-Box Q Test",
            statistic=0.0,
            p_value=1.0,
            null_hypothesis="momentum does not exist (swings are random)",
            reject_null=False,
            interpretation=f"Test failed: {str(e)}",
        )
    
    reject_null = p_value < 0.05
    
    if reject_null:
        interpretation = (
            f"Ljung-Box Q = {statistic:.2f}, p = {p_value:.4f} < 0.05. "
            "Reject null hypothesis: momentum effects exist in match swings."
        )
    else:
        interpretation = (
            f"Ljung-Box Q = {statistic:.2f}, p = {p_value:.4f} >= 0.05. "
            "Fail to reject null hypothesis: swings appear random."
        )
    
    return HypothesisTestResult(
        test_name="Ljung-Box Q Test",
        statistic=statistic,
        p_value=p_value,
        null_hypothesis="momentum does not exist (swings are random)",
        reject_null=reject_null,
        interpretation=interpretation,
    )


def runs_test(
    df: pd.DataFrame,
    winner_col: str = "point_victor",
) -> HypothesisTestResult:
    """Perform Runs Test for randomness.
    
    Null hypothesis: Momentum does not exist (swings are random).
    A "run" is a consecutive sequence of same outcomes.
    
    Args:
        df: DataFrame with match data
        winner_col: column identifying point winner
    
    Returns:
        HypothesisTestResult with test statistics
    """
    if winner_col not in df.columns:
        return HypothesisTestResult(
            test_name="Runs Test",
            statistic=0.0,
            p_value=1.0,
            null_hypothesis="momentum does not exist (swings are random)",
            reject_null=False,
            interpretation="Cannot perform test: winner column not found.",
        )
    
    series = (df[winner_col] == 1).astype(int)
    series = series.dropna()
    
    if len(series) < 10:
        return HypothesisTestResult(
            test_name="Runs Test",
            statistic=0.0,
            p_value=1.0,
            null_hypothesis="momentum does not exist (swings are random)",
            reject_null=False,
            interpretation="Insufficient data for Runs test.",
        )
    
    # Count runs
    runs = 1
    for i in range(1, len(series)):
        if series.iloc[i] != series.iloc[i - 1]:
            runs += 1
    
    # Calculate expected runs and variance
    n1 = (series == 1).sum()
    n0 = (series == 0).sum()
    n = n1 + n0
    
    if n1 == 0 or n0 == 0:
        return HypothesisTestResult(
            test_name="Runs Test",
            statistic=0.0,
            p_value=1.0,
            null_hypothesis="momentum does not exist (swings are random)",
            reject_null=False,
            interpretation="Only one outcome observed, cannot perform runs test.",
        )
    
    expected_runs = (2 * n1 * n0) / n + 1
    variance_runs = (2 * n1 * n0 * (2 * n1 * n0 - n)) / (n ** 2 * (n - 1))
    
    if variance_runs <= 0:
        return HypothesisTestResult(
            test_name="Runs Test",
            statistic=0.0,
            p_value=1.0,
            null_hypothesis="momentum does not exist (swings are random)",
            reject_null=False,
            interpretation="Variance too small for z-test.",
        )
    
    # Z-statistic
    z = (runs - expected_runs) / math.sqrt(variance_runs)
    p_value = 2 * (1 - stats.norm.cdf(abs(z)))
    
    reject_null = p_value < 0.05
    
    if reject_null:
        interpretation = (
            f"Runs = {runs}, Z = {z:.2f}, p = {p_value:.4f} < 0.05. "
            "Reject null hypothesis: pattern is not random."
        )
    else:
        interpretation = (
            f"Runs = {runs}, Z = {z:.2f}, p = {p_value:.4f} >= 0.05. "
            "Fail to reject null hypothesis: swings appear random."
        )
    
    return HypothesisTestResult(
        test_name="Runs Test",
        statistic=z,
        p_value=p_value,
        null_hypothesis="momentum does not exist (swings are random)",
        reject_null=reject_null,
        interpretation=interpretation,
    )


def server_advantage_weighting(
    df: pd.DataFrame,
    player_col: str = "server",
    winner_col: str = "point_victor",
    momentum: Optional[pd.Series] = None,
) -> ServerWeightResult:
    """Analyze server advantage and its effect on momentum.
    
    Args:
        df: DataFrame with match data
        player_col: column identifying the server
        winner_col: column identifying point winner
        momentum: pre-computed momentum series (optional)
    
    Returns:
        ServerWeightResult with server advantage analysis
    """
    if player_col not in df.columns or winner_col not in df.columns:
        return ServerWeightResult(
            server_win_rate=0.5,
            returner_advantage=0.5,
            server_momentum_effect=0.0,
            returner_momentum_effect=0.0,
        )
    
    # Server win rate
    server_wins = (df[player_col] == df[winner_col]).sum()
    total_points = len(df)
    server_win_rate = server_wins / total_points if total_points > 0 else 0.5
    
    # Server advantage
    returner_advantage = 1.0 - server_win_rate
    
    # Server momentum effect
    if momentum is not None and len(momentum) == len(df):
        server_momentum = momentum[df[player_col] == 1].mean()
        returner_momentum = momentum[df[player_col] == 2].mean()
    else:
        server_momentum = 0.0
        returner_momentum = 0.0
    
    return ServerWeightResult(
        server_win_rate=server_win_rate,
        returner_advantage=returner_advantage,
        server_momentum_effect=server_momentum,
        returner_momentum_effect=returner_momentum,
    )


def predict_momentum_shifts(
    df: pd.DataFrame,
    window_size: int = 5,
    shift_threshold: float = 0.3,
    player_col: str = "server",
    winner_col: str = "point_victor",
) -> Dict[str, Any]:
    """Predict when momentum shifts occur.
    
    Uses sliding window analysis to identify momentum phases and predict shifts.
    
    Args:
        df: DataFrame with match data
        window_size: sliding window size
        shift_threshold: threshold for momentum shift detection
        player_col: column identifying the server
        winner_col: column identifying point winner
    
    Returns:
        Dictionary with shift predictions and analysis
    """
    # Compute sliding window momentum
    sw_result = sliding_window_momentum(df, window_size, player_col, winner_col)
    
    # Identify momentum phases
    phases = []
    current_phase = None
    phase_start = 0
    
    for i, momentum_val in enumerate(sw_result.momentum_series):
        if momentum_val > shift_threshold:
            new_phase = "player1"
        elif momentum_val < -shift_threshold:
            new_phase = "player2"
        else:
            new_phase = "neutral"
        
        if current_phase != new_phase:
            if current_phase is not None:
                phases.append({
                    "phase": current_phase,
                    "start": phase_start,
                    "end": i,
                    "duration": i - phase_start,
                })
            current_phase = new_phase
            phase_start = i
    
    # Add final phase
    if current_phase is not None:
        phases.append({
            "phase": current_phase,
            "start": phase_start,
            "end": len(sw_result.momentum_series),
            "duration": len(sw_result.momentum_series) - phase_start,
        })
    
    # Predict next shift based on average duration
    if len(sw_result.momentum_shifts) > 1:
        avg_duration = sw_result.avg_momentum_duration
        last_shift = sw_result.momentum_shifts[-1] if sw_result.momentum_shifts else 0
        predicted_next_shift = last_shift + int(avg_duration)
    else:
        predicted_next_shift = len(df)  # Cannot predict
    
    return {
        "momentum_series": sw_result.momentum_series,
        "shifts": sw_result.momentum_shifts,
        "phases": phases,
        "predicted_next_shift": predicted_next_shift,
        "shift_frequency": sw_result.shift_frequency,
        "avg_phase_duration": sw_result.avg_momentum_duration,
    }


def full_momentum_analysis(
    df: pd.DataFrame,
    player_col: str = "server",
    winner_col: str = "point_victor",
    window_size: int = 5,
    momentum_threshold: float = 0.3,
) -> MomentumAnalysisReport:
    """Perform complete momentum analysis.
    
    Args:
        df: DataFrame with match data
        player_col: column identifying the server
        winner_col: column identifying point winner
        window_size: sliding window size
        momentum_threshold: threshold for momentum shift detection
    
    Returns:
        MomentumAnalysisReport with complete analysis
    """
    # 1. Define momentum
    momentum_def = define_momentum(
        method="residual",
        window_size=window_size,
        momentum_threshold=momentum_threshold,
    )
    
    # 2. Hypothesis tests
    lb_test = ljung_box_test(df, winner_col)
    runs_test_result = runs_test(df, winner_col)
    
    # 3. Sliding window analysis
    sw_result = sliding_window_momentum(df, window_size, player_col, winner_col)
    
    # 4. Server advantage
    momentum = compute_momentum_residual(df, player_col, winner_col)
    server_weight = server_advantage_weighting(df, player_col, winner_col, momentum)
    
    # 5. Overall conclusion
    # Momentum exists if at least one test rejects null hypothesis OR
    # there are significant momentum shifts
    momentum_exists = (
        lb_test.reject_null or
        runs_test_result.reject_null or
        sw_result.shift_frequency > 0.1  # More than 10% shifts
    )
    
    # Confidence level
    reject_count = sum([
        lb_test.reject_null,
        runs_test_result.reject_null,
        sw_result.shift_frequency > 0.1,
    ])
    confidence_level = reject_count / 3.0
    
    # Summary
    summary_parts = [
        f"Momentum analysis using {momentum_def.method} method.",
        f"Ljung-Box test: p={lb_test.p_value:.4f} ({'reject' if lb_test.reject_null else 'fail to reject'} null).",
        f"Runs test: p={runs_test_result.p_value:.4f} ({'reject' if runs_test_result.reject_null else 'fail to reject'} null).",
        f"Sliding window (size={window_size}): {len(sw_result.momentum_shifts)} shifts detected.",
        f"Server win rate: {server_weight.server_win_rate:.2%}.",
    ]
    
    if momentum_exists:
        summary_parts.append(
            f"CONCLUSION: Momentum effects exist (confidence: {confidence_level:.0%})."
        )
    else:
        summary_parts.append(
            f"CONCLUSION: No significant momentum effects detected (confidence: {confidence_level:.0%})."
        )
    
    return MomentumAnalysisReport(
        momentum_definition=momentum_def,
        hypothesis_tests=[lb_test, runs_test_result],
        sliding_window=sw_result,
        server_weight=server_weight,
        momentum_exists=momentum_exists,
        confidence_level=confidence_level,
        summary=" ".join(summary_parts),
    )


def format_report_markdown(report: MomentumAnalysisReport) -> str:
    """Format momentum analysis report as Markdown.
    
    Args:
        report: MomentumAnalysisReport to format
    
    Returns:
        Markdown formatted report
    """
    lines = []
    
    lines.append("## Momentum Analysis Report\n")
    
    # Definition
    lines.append("### Momentum Definition\n")
    lines.append(f"**Method:** {report.momentum_definition.method}\n")
    lines.append(f"**Window Size:** {report.momentum_definition.window_size} points\n")
    lines.append(f"**Threshold:** {report.momentum_definition.momentum_threshold}\n")
    lines.append(f"**Description:** {report.momentum_definition.description}\n")
    
    # Hypothesis Tests
    lines.append("### Hypothesis Tests\n")
    for test in report.hypothesis_tests:
        lines.append(f"#### {test.test_name}\n")
        lines.append(f"- **Null Hypothesis:** {test.null_hypothesis}\n")
        lines.append(f"- **Statistic:** {test.statistic:.4f}\n")
        lines.append(f"- **P-value:** {test.p_value:.4f}\n")
        lines.append(f"- **Reject Null:** {'Yes' if test.reject_null else 'No'}\n")
        lines.append(f"- **Interpretation:** {test.interpretation}\n")
    
    # Sliding Window
    lines.append("### Sliding Window Analysis\n")
    lines.append(f"- **Window Size:** {report.sliding_window.window_size} points\n")
    lines.append(f"- **Momentum Shifts Detected:** {len(report.sliding_window.momentum_shifts)}\n")
    lines.append(f"- **Shift Frequency:** {report.sliding_window.shift_frequency:.4f} shifts/point\n")
    lines.append(f"- **Average Phase Duration:** {report.sliding_window.avg_momentum_duration:.1f} points\n")
    
    # Server Advantage
    lines.append("### Server Advantage\n")
    lines.append(f"- **Server Win Rate:** {report.server_weight.server_win_rate:.2%}\n")
    lines.append(f"- **Returner Advantage:** {report.server_weight.returner_advantage:.2%}\n")
    lines.append(f"- **Server Momentum Effect:** {report.server_weight.server_momentum_effect:.4f}\n")
    lines.append(f"- **Returner Momentum Effect:** {report.server_weight.returner_momentum_effect:.4f}\n")
    
    # Conclusion
    lines.append("### Conclusion\n")
    lines.append(f"**Momentum Exists:** {'Yes' if report.momentum_exists else 'No'}\n")
    lines.append(f"**Confidence Level:** {report.confidence_level:.0%}\n")
    lines.append(f"\n**Summary:** {report.summary}\n")
    
    return "\n".join(lines)

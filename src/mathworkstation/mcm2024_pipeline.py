from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.calibration import calibration_curve
from sklearn.metrics import (
    balanced_accuracy_score,
    brier_score_loss,
    f1_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import GroupKFold
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from statsmodels.stats.diagnostic import acorr_ljungbox

from .figure_color_director import FigureColorDirector
from .momentum_analysis import runs_test
from .plot_style import finalize_publication_axis, finalize_publication_figure, get_publication_figsize, publication_context


FINAL_MATCH_ID = "2023-wimbledon-1701"
FLOW_WINDOW = 7
SWING_HORIZON = 5
STATE_DEADBAND = 0.03
FEATURES = [
    "momentum",
    "abs_momentum",
    "slope3",
    "toward_zero",
    "server_direction",
    "point_diff",
    "game_diff",
    "set_diff",
    "unforced_error_diff7",
    "winner_diff7",
    "ace_diff7",
    "distance_diff7",
    "rally_count",
    "speed_mph",
    "break_point_diff",
]
FEATURE_LABELS = {
    "momentum": "current flow score",
    "abs_momentum": "distance from neutral flow",
    "slope3": "3-point flow slope",
    "toward_zero": "speed of return toward neutral",
    "server_direction": "server identity",
    "point_diff": "normalized point-score gap",
    "game_diff": "game-score gap",
    "set_diff": "set-score gap",
    "unforced_error_diff7": "recent unforced-error differential",
    "winner_diff7": "recent winner-shot differential",
    "ace_diff7": "recent ace differential",
    "distance_diff7": "recent distance-run differential",
    "rally_count": "current rally length",
    "speed_mph": "serve speed",
    "break_point_diff": "break-point pressure differential",
}


@dataclass(frozen=True)
class PredictionSummary:
    model: str
    auc: float
    balanced_accuracy: float
    f1: float


@dataclass(frozen=True)
class MCM2024Analysis:
    server_point_win_rate: float
    n_points: int
    n_matches: int
    final_players: tuple[str, str]
    final_points: int
    final_server_point_win_rate: float
    final_set_points: list[tuple[int, int, int]]
    ljung_reject_count: int
    runs_reject_count: int
    permutation_reject_count: int
    final_ljung_p: float
    final_runs_p: float
    final_permutation_p: float
    rf_summary: PredictionSummary
    logit_summary: PredictionSummary
    final_holdout_auc: float
    final_holdout_balanced_accuracy: float
    final_holdout_logit_auc: float
    final_holdout_logit_balanced_accuracy: float
    brier_score: float
    calibration_points: list[tuple[float, float]]
    logit_coefficients: list[tuple[str, float]]
    state_transition_matrix: list[list[float]]
    feature_importance: list[tuple[str, float]]
    per_match_auc: list[tuple[str, float]]
    sensitivity_auc: list[tuple[int, float]]
    prediction_rows: int
    swing_rate: float
    prepared: pd.DataFrame
    cv_predictions: pd.DataFrame
    final_holdout: pd.DataFrame
    null_tests: pd.DataFrame


def load_wimbledon(path: str | Path) -> pd.DataFrame:
    frame = pd.read_csv(path)
    required = {
        "match_id",
        "player1",
        "player2",
        "server",
        "point_victor",
        "set_no",
        "game_no",
        "point_no",
        "p1_sets",
        "p2_sets",
        "p1_games",
        "p2_games",
        "p1_points_won",
        "p2_points_won",
        "p1_unf_err",
        "p2_unf_err",
        "p1_winner",
        "p2_winner",
        "p1_ace",
        "p2_ace",
        "p1_distance_run",
        "p2_distance_run",
        "rally_count",
        "speed_mph",
        "p1_break_pt",
        "p2_break_pt",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError("MCM2024_DATA_COLUMNS_MISSING:" + ",".join(missing))
    return frame


def analyze_wimbledon(
    frame: pd.DataFrame,
    *,
    random_state: int = 42,
    n_permutations: int = 250,
) -> MCM2024Analysis:
    data = frame.copy()
    n_matches = int(data["match_id"].nunique())
    if n_matches < 5:
        raise ValueError("MCM2024_REQUIRES_AT_LEAST_FIVE_MATCHES")

    server_rate = float((data["server"] == data["point_victor"]).mean())
    prepared = _prepare_features(data, server_rate=server_rate, flow_window=FLOW_WINDOW)
    modeling = prepared.dropna(subset=[*FEATURES, "swing_within_horizon"]).copy()
    y = modeling["swing_within_horizon"].astype(int).to_numpy()
    groups = modeling["match_id"].astype(str).to_numpy()
    X = modeling[FEATURES]

    rf = _random_forest(random_state)
    logit = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=2500, class_weight="balanced", random_state=random_state),
    )
    rf_prob, rf_fold = _group_cv_predict(rf, X, y, groups)
    logit_prob, _ = _group_cv_predict(logit, X, y, groups)
    rf_summary = _prediction_summary("Random Forest swing-hazard model", y, rf_prob)
    logit_summary = _prediction_summary("Logistic swing-hazard model", y, logit_prob)

    cv_predictions = modeling[["match_id", "point_no", "momentum", "swing_within_horizon"]].copy()
    cv_predictions["rf_probability"] = rf_prob
    cv_predictions["logit_probability"] = logit_prob
    cv_predictions["fold"] = rf_fold

    rf.fit(X, y)
    importances = sorted(
        ((FEATURE_LABELS[name], float(value)) for name, value in zip(FEATURES, rf.feature_importances_)),
        key=lambda item: item[1],
        reverse=True,
    )

    standardized_logit = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=2500, class_weight="balanced", random_state=random_state),
    )
    standardized_logit.fit(X, y)
    logit_estimator = standardized_logit.named_steps["logisticregression"]
    logit_coefficients = sorted(
        ((FEATURE_LABELS[name], float(value)) for name, value in zip(FEATURES, logit_estimator.coef_[0])),
        key=lambda item: abs(item[1]),
        reverse=True,
    )
    prob_true, prob_pred = calibration_curve(y, logit_prob, n_bins=8, strategy="quantile")
    calibration_points = [(float(px), float(py)) for px, py in zip(prob_pred, prob_true)]
    brier = float(brier_score_loss(y, logit_prob))

    state_transition_matrix = _state_transition_matrix(prepared)

    per_match_auc: list[tuple[str, float]] = []
    for match_id, group in cv_predictions.groupby("match_id"):
        truth = group["swing_within_horizon"].astype(int).to_numpy()
        if np.unique(truth).size < 2:
            continue
        per_match_auc.append((str(match_id), float(roc_auc_score(truth, group["rf_probability"]))))
    per_match_auc.sort(key=lambda item: item[1])

    final_train = modeling[modeling["match_id"] != FINAL_MATCH_ID]
    final_test = modeling[modeling["match_id"] == FINAL_MATCH_ID].copy()
    final_model = _random_forest(random_state)
    final_model.fit(final_train[FEATURES], final_train["swing_within_horizon"].astype(int))
    final_test["swing_risk"] = final_model.predict_proba(final_test[FEATURES])[:, 1]
    final_logit = make_pipeline(
        StandardScaler(),
        LogisticRegression(max_iter=2500, class_weight="balanced", random_state=random_state),
    )
    final_logit.fit(final_train[FEATURES], final_train["swing_within_horizon"].astype(int))
    final_test["swing_risk_logit"] = final_logit.predict_proba(final_test[FEATURES])[:, 1]
    final_truth = final_test["swing_within_horizon"].astype(int).to_numpy()
    final_holdout_auc = float(roc_auc_score(final_truth, final_test["swing_risk"])) if np.unique(final_truth).size > 1 else 0.5
    final_holdout_balanced = float(balanced_accuracy_score(final_truth, final_test["swing_risk"] >= 0.5))
    final_holdout_logit_auc = float(roc_auc_score(final_truth, final_test["swing_risk_logit"])) if np.unique(final_truth).size > 1 else 0.5
    final_holdout_logit_balanced = float(balanced_accuracy_score(final_truth, final_test["swing_risk_logit"] >= 0.5))

    null_tests = _null_tests(data, server_rate, random_state=random_state, n_permutations=n_permutations)
    final_null = null_tests[null_tests["match_id"] == FINAL_MATCH_ID].iloc[0]

    final_match = prepared[prepared["match_id"] == FINAL_MATCH_ID]
    players = (str(final_match["player1"].iloc[0]), str(final_match["player2"].iloc[0]))
    set_points: list[tuple[int, int, int]] = []
    for set_no, group in final_match.groupby("set_no", sort=True):
        set_points.append(
            (
                int(set_no),
                int((group["point_victor"] == 1).sum()),
                int((group["point_victor"] == 2).sum()),
            )
        )

    sensitivity = []
    for window in (5, 7, 9, 11):
        candidate = _prepare_features(data, server_rate=server_rate, flow_window=window)
        candidate = candidate.dropna(subset=[*FEATURES, "swing_within_horizon"])
        cy = candidate["swing_within_horizon"].astype(int).to_numpy()
        cp, _ = _group_cv_predict(
            RandomForestClassifier(
                n_estimators=140,
                min_samples_leaf=8,
                max_depth=8,
                class_weight="balanced",
                random_state=random_state,
                n_jobs=-1,
            ),
            candidate[FEATURES],
            cy,
            candidate["match_id"].astype(str).to_numpy(),
        )
        sensitivity.append((window, float(roc_auc_score(cy, cp))))

    return MCM2024Analysis(
        server_point_win_rate=server_rate,
        n_points=int(len(data)),
        n_matches=n_matches,
        final_players=players,
        final_points=int(len(final_match)),
        final_server_point_win_rate=float((final_match["server"] == final_match["point_victor"]).mean()),
        final_set_points=set_points,
        ljung_reject_count=int((null_tests["ljung_p"] < 0.05).sum()),
        runs_reject_count=int((null_tests["runs_p"] < 0.05).sum()),
        permutation_reject_count=int((null_tests["permutation_p"] < 0.05).sum()),
        final_ljung_p=float(final_null["ljung_p"]),
        final_runs_p=float(final_null["runs_p"]),
        final_permutation_p=float(final_null["permutation_p"]),
        rf_summary=rf_summary,
        logit_summary=logit_summary,
        final_holdout_auc=final_holdout_auc,
        final_holdout_balanced_accuracy=final_holdout_balanced,
        final_holdout_logit_auc=final_holdout_logit_auc,
        final_holdout_logit_balanced_accuracy=final_holdout_logit_balanced,
        brier_score=brier,
        calibration_points=calibration_points,
        logit_coefficients=logit_coefficients,
        state_transition_matrix=state_transition_matrix,
        feature_importance=importances,
        per_match_auc=per_match_auc,
        sensitivity_auc=sensitivity,
        prediction_rows=int(len(modeling)),
        swing_rate=float(y.mean()),
        prepared=prepared,
        cv_predictions=cv_predictions,
        final_holdout=final_test,
        null_tests=null_tests,
    )


def render_figures(
    analysis: MCM2024Analysis,
    output_dir: str | Path,
    *,
    profile: str = "MCM_C",
) -> list[dict[str, Any]]:
    directory = Path(output_dir)
    directory.mkdir(parents=True, exist_ok=True)
    color = FigureColorDirector()
    outputs: list[dict[str, Any]] = []

    final = analysis.prepared[analysis.prepared["match_id"] == FINAL_MATCH_ID].reset_index(drop=True)
    x = np.arange(1, len(final) + 1)
    with publication_context(profile):
        fig, ax = plt.subplots(figsize=get_publication_figsize(profile, "wide"))
        ax.plot(x, final["momentum"], linewidth=1.6, label="serve-adjusted flow score")
        ax.axhline(0.0, linewidth=1.0, linestyle="--")
        ax.fill_between(x, 0, final["momentum"], where=final["momentum"] >= 0, alpha=0.16)
        ax.fill_between(x, 0, final["momentum"], where=final["momentum"] < 0, alpha=0.16)
        boundaries = final.groupby("set_no", sort=True).size().cumsum().iloc[:-1].to_numpy()
        for boundary in boundaries:
            ax.axvline(float(boundary), linewidth=0.8, linestyle=":", alpha=0.65)
        ax.set_xlabel("Point sequence")
        ax.set_ylabel("Flow score $M_t$")
        ax.set_title("2023 Wimbledon Final: Serve-adjusted Match Flow")
        color.apply(ax, "panel_trend_characterization", identity="mcm2024:final-flow")
        finalize_publication_axis(ax, chart_type="line", caption_first=True)
        outputs.append(_save_figure(fig, directory, "final-match-flow", "panel_trend_characterization", "primary"))
        plt.close(fig)

    with publication_context(profile):
        fig, ax = plt.subplots(figsize=get_publication_figsize(profile, "wide"))
        ordered = analysis.null_tests.sort_values("permutation_p").reset_index(drop=True)
        xx = np.arange(1, len(ordered) + 1)
        ax.plot(xx, ordered["ljung_p"], marker="o", markersize=3, linewidth=1.0, label="Ljung-Box on residuals")
        ax.plot(xx, ordered["permutation_p"], marker="s", markersize=3, linewidth=1.0, label="server-only permutation")
        ax.axhline(0.05, linestyle="--", linewidth=1.0, label="5% significance")
        ax.set_xlabel("Matches ordered by permutation p-value")
        ax.set_ylabel("p-value")
        ax.set_ylim(0, 1.03)
        ax.set_title("Momentum Persistence Tests Across 31 Matches")
        ax.legend(fontsize=8, frameon=False)
        color.apply(ax, "comparison_evidence", identity="mcm2024:null-tests")
        finalize_publication_axis(ax, chart_type="line", caption_first=True)
        outputs.append(_save_figure(fig, directory, "null-test-comparison", "comparison_evidence", "primary"))
        plt.close(fig)

    with publication_context(profile):
        fig, ax = plt.subplots(figsize=get_publication_figsize(profile, "wide"))
        matrix = np.asarray(analysis.state_transition_matrix, dtype=float)
        image = ax.imshow(matrix, cmap="RdBu_r", vmin=0.0, vmax=1.0, aspect="auto")
        labels = ["P2 flow", "Neutral", "P1 flow"]
        ax.set_xticks(range(3), labels=labels)
        ax.set_yticks(range(3), labels=labels)
        ax.set_xlabel("Next flow state")
        ax.set_ylabel("Current flow state")
        ax.set_title("Serve-adjusted Flow-state Transition Probabilities")
        for row in range(3):
            for col in range(3):
                ax.text(col, row, f"{matrix[row, col]:.2f}", ha="center", va="center", fontsize=9)
        fig.colorbar(image, ax=ax, fraction=0.045, pad=0.04, label="Transition probability")
        finalize_publication_axis(ax, chart_type="heatmap", caption_first=True)
        outputs.append(_save_figure(fig, directory, "flow-state-transition", "probabilistic_state_transition", "primary"))
        plt.close(fig)

    truth = analysis.cv_predictions["swing_within_horizon"].astype(int).to_numpy()
    with publication_context(profile):
        fig, ax = plt.subplots(figsize=get_publication_figsize(profile, "wide"))
        for label, column in (("Random Forest", "rf_probability"), ("Logistic regression", "logit_probability")):
            fpr, tpr, _ = roc_curve(truth, analysis.cv_predictions[column])
            auc = roc_auc_score(truth, analysis.cv_predictions[column])
            ax.plot(fpr, tpr, linewidth=1.6, label=f"{label} (AUC={auc:.3f})")
        ax.plot([0, 1], [0, 1], linestyle="--", linewidth=1.0, label="chance")
        ax.set_xlabel("False-positive rate")
        ax.set_ylabel("True-positive rate")
        ax.set_title("Five-point Swing-Hazard Prediction: Grouped Cross-validation")
        ax.legend(fontsize=8, frameon=False, loc="lower right")
        color.apply(ax, "model_comparison", identity="mcm2024:roc")
        finalize_publication_axis(ax, chart_type="line", caption_first=True)
        outputs.append(_save_figure(fig, directory, "swing-prediction-roc", "probability_validation_roc", "primary"))
        plt.close(fig)

    with publication_context(profile):
        fig, ax = plt.subplots(figsize=get_publication_figsize(profile, "wide"))
        calibration = np.asarray(analysis.calibration_points, dtype=float)
        ax.plot([0, 1], [0, 1], linestyle="--", linewidth=1.0, label="ideal calibration")
        if calibration.size:
            ax.plot(calibration[:, 0], calibration[:, 1], marker="o", linewidth=1.5, label=f"logistic hazard (Brier={analysis.brier_score:.3f})")
        ax.set_xlabel("Mean predicted swing probability")
        ax.set_ylabel("Observed swing frequency")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.set_title("Calibration of the Probabilistic Swing-Hazard Layer")
        ax.legend(fontsize=8, frameon=False)
        color.apply(ax, "comparison_evidence", identity="mcm2024:calibration")
        finalize_publication_axis(ax, chart_type="line", caption_first=True)
        outputs.append(_save_figure(fig, directory, "swing-calibration", "probability_validation_calibration", "primary"))
        plt.close(fig)

    with publication_context(profile):
        fig, ax = plt.subplots(figsize=get_publication_figsize(profile, "wide"))
        top = analysis.feature_importance[:10][::-1]
        labels = [item[0] for item in top]
        values = [item[1] for item in top]
        ax.barh(labels, values)
        ax.set_xlabel("Random Forest importance")
        ax.set_title("Most Informative Indicators of an Approaching Flow Reversal")
        color.apply(ax, "feature_importance", identity="mcm2024:importance")
        finalize_publication_axis(ax, chart_type="bar", caption_first=True)
        outputs.append(_save_figure(fig, directory, "swing-feature-importance", "feature_importance", "primary"))
        plt.close(fig)

    with publication_context(profile):
        fig, axes = plt.subplots(2, 1, figsize=get_publication_figsize(profile, "wide"), sharex=True)
        hold = analysis.final_holdout.reset_index(drop=True)
        xx = np.arange(1, len(hold) + 1)
        axes[0].plot(xx, hold["momentum"], linewidth=1.4)
        axes[0].axhline(0, linestyle="--", linewidth=0.9)
        axes[0].set_ylabel("Flow score")
        axes[0].set_title("Final held out from training")
        axes[1].plot(xx, hold["swing_risk"], linewidth=1.4)
        axes[1].axhline(0.5, linestyle="--", linewidth=0.9)
        axes[1].set_ylabel("Predicted swing risk")
        axes[1].set_xlabel("Eligible point sequence")
        for axis in axes:
            color.apply(axis, "panel_forecast_intervals", identity="mcm2024:final-holdout")
            finalize_publication_axis(axis, chart_type="line", caption_first=True)
        fig.tight_layout(pad=0.8)
        outputs.append(_save_figure(fig, directory, "final-holdout-swing-risk", "panel_forecast_intervals", "primary"))
        plt.close(fig)

    with publication_context(profile):
        fig, ax = plt.subplots(figsize=get_publication_figsize(profile, "wide"))
        aucs = np.array([value for _, value in analysis.per_match_auc], dtype=float)
        ax.scatter(np.arange(1, len(aucs) + 1), np.sort(aucs), s=18)
        ax.axhline(0.5, linestyle="--", linewidth=1.0, label="chance")
        ax.axhline(float(np.median(aucs)), linestyle=":", linewidth=1.0, label=f"median={np.median(aucs):.3f}")
        ax.set_xlabel("Held-out matches ordered by AUC")
        ax.set_ylabel("Match-level AUC")
        ax.set_ylim(0, 1.02)
        ax.set_title("Generalization Across Held-out Wimbledon Matches")
        ax.legend(fontsize=8, frameon=False)
        color.apply(ax, "comparison_evidence", identity="mcm2024:generalization")
        finalize_publication_axis(ax, chart_type="scatter", caption_first=True)
        outputs.append(_save_figure(fig, directory, "match-generalization", "generalization_distribution", "supplementary_evidence"))
        plt.close(fig)

    with publication_context(profile):
        fig, ax = plt.subplots(figsize=get_publication_figsize(profile, "wide"))
        windows = [item[0] for item in analysis.sensitivity_auc]
        aucs = [item[1] for item in analysis.sensitivity_auc]
        ax.plot(windows, aucs, marker="o", linewidth=1.5)
        ax.axhline(0.5, linestyle="--", linewidth=1.0, label="chance")
        ax.set_xlabel("Flow window (points)")
        ax.set_ylabel("Grouped-CV AUC")
        ax.set_title("Sensitivity to the Flow Aggregation Window")
        ax.set_xticks(windows)
        ax.legend(fontsize=8, frameon=False)
        color.apply(ax, "parameter_sensitivity_curve", identity="mcm2024:flow-window-sensitivity")
        finalize_publication_axis(ax, chart_type="line", caption_first=True)
        outputs.append(_save_figure(fig, directory, "flow-window-sensitivity", "parameter_sensitivity_curve", "supplementary_evidence"))
        plt.close(fig)

    return outputs


def _prepare_features(frame: pd.DataFrame, *, server_rate: float, flow_window: int) -> pd.DataFrame:
    data = frame.copy()
    data["p1_point_win"] = (data["point_victor"] == 1).astype(int)
    data["expected_p1"] = np.where(data["server"].eq(1), server_rate, 1.0 - server_rate)
    data["residual"] = data["p1_point_win"] - data["expected_p1"]
    groups = []
    for _, group in data.groupby("match_id", sort=False):
        g = group.copy().reset_index(drop=True)
        g["momentum"] = g["residual"].rolling(flow_window, min_periods=3).mean()
        g["slope3"] = g["momentum"] - g["momentum"].shift(3)
        g["abs_momentum"] = g["momentum"].abs()
        g["toward_zero"] = -(g["momentum"] * g["slope3"])
        state = np.where(g["momentum"] > STATE_DEADBAND, 1, np.where(g["momentum"] < -STATE_DEADBAND, -1, 0))
        g["flow_state"] = state
        target: list[float] = []
        for index in range(len(g)):
            current = int(state[index])
            future = state[index + 1 : min(len(g), index + SWING_HORIZON + 1)]
            if index + SWING_HORIZON >= len(g) or current == 0:
                target.append(np.nan)
            else:
                target.append(float(any(int(value) == -current for value in future)))
        g["swing_within_horizon"] = target
        g["server_direction"] = np.where(g["server"].eq(1), 1, -1)
        g["point_diff"] = (g["p1_points_won"] - g["p2_points_won"]) / np.maximum(1, g["point_no"])
        g["game_diff"] = g["p1_games"] - g["p2_games"]
        g["set_diff"] = g["p1_sets"] - g["p2_sets"]
        g["unforced_error_diff7"] = (g["p1_unf_err"] - g["p2_unf_err"]).rolling(7, min_periods=1).sum()
        g["winner_diff7"] = (g["p1_winner"] - g["p2_winner"]).rolling(7, min_periods=1).sum()
        g["ace_diff7"] = (g["p1_ace"] - g["p2_ace"]).rolling(7, min_periods=1).sum()
        g["distance_diff7"] = (g["p1_distance_run"] - g["p2_distance_run"]).rolling(7, min_periods=1).mean()
        g["break_point_diff"] = g["p1_break_pt"] - g["p2_break_pt"]
        groups.append(g)
    return pd.concat(groups, ignore_index=True)


def _state_transition_matrix(prepared: pd.DataFrame) -> list[list[float]]:
    """Estimate a smoothed three-state Markov transition matrix.

    States are -1 (player 2 flow), 0 (neutral), +1 (player 1 flow).  Jeffreys
    pseudo-counts keep rows well-defined without pretending that the transition
    model is more certain than the finite match sample supports.
    """
    order = (-1, 0, 1)
    index = {state: idx for idx, state in enumerate(order)}
    counts = np.full((3, 3), 0.5, dtype=float)
    for _, group in prepared.groupby("match_id", sort=False):
        states = group["flow_state"].dropna().astype(int).to_numpy()
        for left, right in zip(states[:-1], states[1:]):
            if int(left) in index and int(right) in index:
                counts[index[int(left)], index[int(right)]] += 1.0
    probs = counts / counts.sum(axis=1, keepdims=True)
    return probs.tolist()


def _random_forest(random_state: int) -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=300,
        min_samples_leaf=8,
        max_depth=8,
        class_weight="balanced",
        random_state=random_state,
        n_jobs=-1,
    )


def _group_cv_predict(model: Any, X: pd.DataFrame, y: np.ndarray, groups: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    cv = GroupKFold(5)
    probabilities = np.zeros(len(y), dtype=float)
    folds = np.full(len(y), -1, dtype=int)
    for fold, (train_index, test_index) in enumerate(cv.split(X, y, groups), start=1):
        model.fit(X.iloc[train_index], y[train_index])
        probabilities[test_index] = model.predict_proba(X.iloc[test_index])[:, 1]
        folds[test_index] = fold
    return probabilities, folds


def _prediction_summary(name: str, y: np.ndarray, probability: np.ndarray) -> PredictionSummary:
    prediction = probability >= 0.5
    return PredictionSummary(
        model=name,
        auc=float(roc_auc_score(y, probability)),
        balanced_accuracy=float(balanced_accuracy_score(y, prediction)),
        f1=float(f1_score(y, prediction)),
    )


def _null_tests(
    frame: pd.DataFrame,
    server_rate: float,
    *,
    random_state: int,
    n_permutations: int,
) -> pd.DataFrame:
    rng = np.random.default_rng(random_state)
    rows: list[dict[str, Any]] = []
    for match_id, group in frame.groupby("match_id", sort=False):
        g = group.reset_index(drop=True)
        expected = np.where(g["server"].eq(1), server_rate, 1.0 - server_rate)
        actual = (g["point_victor"] == 1).astype(float).to_numpy()
        residual = actual - expected
        rolling = pd.Series(residual).rolling(FLOW_WINDOW, min_periods=3).mean().to_numpy()
        observed = float(np.nanmax(np.abs(rolling)))
        null_stats = []
        for _ in range(n_permutations):
            simulated = rng.binomial(1, expected)
            simulated_residual = simulated - expected
            simulated_flow = pd.Series(simulated_residual).rolling(FLOW_WINDOW, min_periods=3).mean().to_numpy()
            null_stats.append(float(np.nanmax(np.abs(simulated_flow))))
        permutation_p = float((1 + sum(value >= observed for value in null_stats)) / (n_permutations + 1))
        ljung_p = float(acorr_ljungbox(pd.Series(residual), lags=[min(10, max(1, len(residual) - 1))], return_df=True)["lb_pvalue"].iloc[0])
        runs_p = float(runs_test(g, winner_col="point_victor").p_value)
        rows.append(
            {
                "match_id": str(match_id),
                "points": int(len(g)),
                "max_abs_flow": observed,
                "ljung_p": ljung_p,
                "runs_p": runs_p,
                "permutation_p": permutation_p,
            }
        )
    return pd.DataFrame(rows)


def _save_figure(fig: Any, directory: Path, stem: str, semantic_kind: str, paper_role: str) -> dict[str, Any]:
    png = directory / f"{stem}.png"
    svg = directory / f"{stem}.svg"
    fig.savefig(png, dpi=600, bbox_inches="tight", facecolor="white")
    fig.savefig(svg, format="svg", bbox_inches="tight", facecolor="white")
    return {
        "title": stem.replace("-", " ").title(),
        "path": png,
        "svg_path": svg,
        "semantic_kind": semantic_kind,
        "paper_role": paper_role,
    }

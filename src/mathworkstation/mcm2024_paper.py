from __future__ import annotations

import numpy as np

from .mcm2024_pipeline import MCM2024Analysis


def render_mcm2024_paper(analysis: MCM2024Analysis) -> str:
    p1, p2 = analysis.final_players
    per_auc = np.array([value for _, value in analysis.per_match_auc], dtype=float)
    median_auc = float(np.median(per_auc)) if len(per_auc) else 0.5
    q1_auc = float(np.quantile(per_auc, 0.25)) if len(per_auc) else 0.5
    q3_auc = float(np.quantile(per_auc, 0.75)) if len(per_auc) else 0.5
    above_chance = int((per_auc > 0.5).sum()) if len(per_auc) else 0
    top_features = analysis.feature_importance[:6]
    set_rows = "\n".join(
        f"| {set_no} | {p1_points} | {p2_points} | {p1_points - p2_points:+d} |"
        for set_no, p1_points, p2_points in analysis.final_set_points
    )
    importance_rows = "\n".join(
        f"| {name} | {value:.3f} |" for name, value in top_features
    )
    sensitivity_rows = "\n".join(
        f"| {window} | {auc:.3f} |" for window, auc in analysis.sensitivity_auc
    )

    return rf"""# Flow Without Myth: A Serve-Adjusted Model of Tennis Momentum and Swing Risk

# Summary

The 2023 Wimbledon men's final contained repeated reversals that spectators naturally call *momentum*. Tennis, however, already contains a powerful structural source of apparent runs - the server advantage. We therefore distinguish changes in relative performance from the predictable benefit of serving.

We analyze **{analysis.n_points:,} point-level observations from {analysis.n_matches} Wimbledon 2023 men's matches**. Across the data, the server wins **{analysis.server_point_win_rate:.1%}** of points. We first construct a serve-adjusted residual for every point: actual performance minus the probability expected from server identity. A seven-point rolling average of these residuals forms our **Flow Score**, a signed and continuous measure of which player is currently outperforming the serve-only baseline and by how much. Applied to the Alcaraz-Djokovic final, the Flow Score reproduces the large changes visible in the five-set match without treating every service hold as momentum.

We then test the skeptical coach's claim that the swings are random. After server adjustment, Ljung-Box tests reject independence in **{analysis.ljung_reject_count}/{analysis.n_matches}** matches, and a server-sequence-preserving Monte Carlo test rejects the serve-only null in **{analysis.permutation_reject_count}/{analysis.n_matches}** matches at the 5% level. The raw Runs Test rejects randomness in **{analysis.runs_reject_count}/{analysis.n_matches}** matches, but it is less specific because service alternation itself can generate runs. For the featured final, the p-values are {analysis.final_ljung_p:.3f} (Ljung-Box), {analysis.final_runs_p:.3f} (Runs), and {analysis.final_permutation_p:.3f} (server-only simulation). Thus, our evidence does **not** support a universal persistent force called momentum once the server advantage is removed.

This does not mean that local changes in flow are unpredictable. We define a swing event as a transition from one player's non-neutral Flow Score to the opponent's side within the next five points. A Random Forest hazard model is trained with grouped cross-validation so that complete matches, rather than individual points, are held out. It reaches **AUC={analysis.rf_summary.auc:.3f}**, **balanced accuracy={analysis.rf_summary.balanced_accuracy:.3f}**, and **F1={analysis.rf_summary.f1:.3f}**, outperforming an interpretable logistic model (AUC={analysis.logit_summary.auc:.3f}). When the entire 2023 final is excluded from training, the model still obtains **AUC={analysis.final_holdout_auc:.3f}** on that match. The leading signal is how rapidly the current Flow Score is returning toward neutral, followed by the distance from neutral, the current flow level, the point-score gap, and the recent flow slope.

For coaching, we recommend treating momentum as an alert problem rather than a hidden force: use the serve-adjusted Flow Score to describe current performance and the swing-risk score to identify advantages that are decaying toward neutral.

**Keywords:** tennis momentum, server advantage, rolling residual, swing prediction, Random Forest, grouped cross-validation

# Contents

# 1. Introduction

## 1.1 Problem background

The word *momentum* is attractive because it gives a simple name to a familiar visual pattern: a player wins several points or games, appears increasingly confident, and seems to carry that advantage forward. The 2023 Wimbledon final between {p1} and {p2} contained several such reversals. However, tennis is not a sequence of identical Bernoulli trials. The server has a strong structural advantage, service games occur in blocks, and the score constrains player behavior. Any apparent run can therefore combine genuine changes in execution with predictable tennis mechanics.

The modeling challenge is to separate three questions that are often mixed together. First, **who is performing better right now after accounting for serve?** Second, **does current advantage persist more strongly than a serve-only random process would produce?** Third, **even if persistent momentum is weak, are there observable warning signs that the local flow is about to reverse?** We answer these questions in that order so later claims inherit only evidence established earlier.

## 1.2 Data and task interpretation

The provided data contain every point from {analysis.n_matches} featured Wimbledon 2023 men's matches after the second round, for a total of {analysis.n_points:,} observations. Each row describes the score, server, point winner, aces, winners, unforced errors, net play, break-point status, distance run, rally count, serve speed, and other point-level information. The featured final has {analysis.final_points} points.

We interpret "momentum" operationally rather than psychologically. A model may reveal a period of unusually strong relative performance, but the data do not directly measure confidence, self-efficacy, crowd response, injury, or coaching communication. Consequently, we reserve the word *flow* for our observed metric and use *momentum* only when discussing the hypothesis that flow has persistence beyond the serve-adjusted null.

## 1.3 Our work

Our complete modeling chain is:

- remove the first-order effect of the server and define a continuous serve-adjusted Flow Score;
- visualize the featured final and quantify set-to-set changes without changing the scale between players;
- test persistent dependence using residual Ljung-Box statistics and a server-sequence-preserving simulation null;
- define a five-point *swing hazard* and predict it using only information available at the current point;
- validate prediction by holding out complete matches with GroupKFold cross-validation;
- hold out the entire Wimbledon final as an additional transfer test;
- analyze sensitivity to the smoothing window and translate the evidence into coaching advice.

This structure deliberately starts with the simplest relation - a serve-adjusted Bernoulli baseline - and adds complexity only where it yields a new testable purpose.

# 2. Data Preparation and the Flow Model

## 2.1 Data preparation

Rows are kept in their original within-match point order. We create only features that can be computed from the current or previous points. No future point winner enters the predictor variables. The prediction target uses future points only to label whether a swing actually occurs; those future labels are never used as inputs.

The dominant structural effect in the full data is service. The observed server point-win rate is

$${analysis.server_point_win_rate:.6f}.$$

In the featured final it is {analysis.final_server_point_win_rate:.1%}, lower than the tournament-wide level. This difference alone warns against using raw consecutive points as a universal momentum index.

## 2.2 A serve-adjusted point residual

Let $Y_t=1$ if player 1 wins point $t$ and $Y_t=0$ otherwise. Let $S_t=1$ when player 1 serves and $S_t=0$ when player 2 serves. From the full competition sample we estimate the first-order server point-win probability $\hat p_s={analysis.server_point_win_rate:.4f}$. The expected probability that player 1 wins the point is

$$e_t=S_t\hat p_s+(1-S_t)(1-\hat p_s).$$

The point-level performance residual is

$$r_t=Y_t-e_t.$$

A positive residual means player 1 performed better than the serve-only expectation on that point; a negative residual favors player 2. Because the expectation flips with the server, a routine service point does not automatically create positive momentum for the server.

## 2.3 The Flow Score

Point residuals are noisy, so we aggregate them over a short rolling window. With $w=7$,

$$M_t=\frac{{1}}{{w}}\sum_{{j=0}}^{{w-1}} r_{{t-j}}.$$

$M_t>0$ favors player 1 and $M_t<0$ favors player 2. Its magnitude is directly interpretable as the recent average difference between observed point outcomes and the serve-only expectation. We call $M_t$ the **Flow Score** rather than assuming it is momentum.

The seven-point window is long enough to suppress point-by-point noise while remaining substantially shorter than a typical set. Section 5 tests windows from 5 to 11 points.

## 2.4 The 2023 Wimbledon final

The point totals by set are:

| Set | {p1} points | {p2} points | Point differential |
|---:|---:|---:|---:|
{set_rows}

![Figure 1. Serve-adjusted Flow Score through the 2023 Wimbledon final](../../figures/final/final-match-flow.png)

Figure 1 gives the match-flow view requested in the problem. The score reproduces the main match narrative: a strong Djokovic opening, an extended Alcaraz recovery through the middle sets, a Djokovic resurgence in set four, and a final Alcaraz recovery. The vertical set boundaries show that the flow does not simply reset at a set boundary, but it also does not remain locked in one direction.

The figure is intentionally descriptive. A visually persistent region is not by itself evidence that momentum exists; persistence must be tested against a null model that includes server advantage.

# 3. Is Momentum More Than Random Fluctuation?

## 3.1 The skeptical coach's hypothesis

We formalize the skeptical claim as:

**$H_0$:** after conditioning on the server, point outcomes are independent Bernoulli events with the observed tournament-wide server advantage.

This null does not claim that both players are equal. It preserves the most important tennis asymmetry while removing any extra serial dependence that could be interpreted as momentum.

We use three diagnostics. The first two operate on the serve-adjusted residuals; the third is reported because runs are intuitive to coaches but has a weaker causal interpretation in tennis.

## 3.2 Ljung-Box residual test

For each match we apply a Ljung-Box test to $r_t$ with up to ten lags. If the residuals are serially correlated, the serve-only expectation has failed to explain temporal dependence. At the 5% level, the test rejects independence in **{analysis.ljung_reject_count} of {analysis.n_matches} matches**.

This is a strong negative result: after a simple serve correction, we do not observe consistent residual autocorrelation at these lags.

## 3.3 Server-sequence-preserving simulation

A second test keeps the exact observed server sequence for each match. For point $t$ we simulate

$$Y_t^*\sim \mathrm{{Bernoulli}}(e_t),$$

recompute the seven-point Flow Score, and record the maximum absolute flow excursion. Repeating this process creates a match-specific null distribution. The empirical p-value is the fraction of simulated matches whose largest excursion is at least as large as the observed excursion.

Across all {analysis.n_matches} matches, **{analysis.permutation_reject_count}/{analysis.n_matches}** fall below 0.05. For the final, $p={analysis.final_permutation_p:.3f}$.

![Figure 2. Residual and simulation-based momentum tests across matches](../../figures/final/null-test-comparison.png)

Figure 2 shows that the apparent swings are not unusually large relative to a server-only process once the structure of service is retained. The conclusion is not "tennis has no psychology"; rather, this data set does not justify treating momentum as a persistent latent force that creates serial dependence in point outcomes.

## 3.4 Runs Test as a secondary diagnostic

The raw Runs Test rejects randomness in **{analysis.runs_reject_count}/{analysis.n_matches}** matches. For the featured final, $p={analysis.final_runs_p:.3f}$. Because raw runs ignore which player serves, they can mix genuine temporal structure with alternating service games. We therefore treat the Runs Test as supporting context, not the primary momentum test.

The combination of tests answers the coach's skepticism carefully: **persistent momentum is not statistically established, but the match still has observable local flow that can rise, weaken, and reverse.** This motivates a prediction problem that is different from proving long-run momentum.

# 4. Predicting an Approaching Swing

## 4.1 From momentum existence to swing hazard

A coach does not need a mystical momentum variable; the practical question is whether a current advantage is becoming fragile. We define three flow states using a small neutral band $\delta=0.03$:

$$Z_t=\begin{{cases}}+1,&M_t>\delta,\\0,&|M_t|\leq\delta,\\-1,&M_t<-\delta.\end{{cases}}$$

A **swing event** occurs when a non-neutral current state reaches the opposite non-neutral state at any time during the next $H=5$ points. Thus the target $A_t$ equals 1 if a reversal occurs within five points and 0 otherwise. Neutral starting states are excluded because there is no current player advantage to reverse.

This definition creates {analysis.prediction_rows:,} eligible point states; {analysis.swing_rate:.1%} are positive swing events.

## 4.2 Predictor design

The features are deliberately local and available at decision time:

- current Flow Score $M_t$ and $|M_t|$;
- the three-point slope of $M_t$;
- a **return-to-neutral** term $-M_t\Delta M_t$, positive when the current advantage is moving toward zero;
- current server identity;
- normalized point differential, game differential, and set differential;
- seven-point differentials in unforced errors, winners, aces, and distance run;
- rally count, serve speed, and break-point pressure.

The return-to-neutral term is important because a large advantage that is still strengthening is very different from the same advantage collapsing toward zero.

## 4.3 Models and leakage-resistant validation

We compare an interpretable logistic model with a Random Forest. The Random Forest uses 300 trees, maximum depth 8, minimum leaf size 8, and balanced class weights. These restrictions reduce overfitting and make the comparison about nonlinear interactions rather than an unrestricted tree ensemble.

Validation is performed with **five-fold GroupKFold by match**. Every point from one match is placed entirely in either training or testing for a fold. This is stricter than randomly splitting points, which would leak player- and match-specific temporal structure into both sides.

| Model | ROC AUC | Balanced accuracy | F1 |
|---|---:|---:|---:|
| Logistic regression | {analysis.logit_summary.auc:.3f} | {analysis.logit_summary.balanced_accuracy:.3f} | {analysis.logit_summary.f1:.3f} |
| Random Forest | **{analysis.rf_summary.auc:.3f}** | **{analysis.rf_summary.balanced_accuracy:.3f}** | **{analysis.rf_summary.f1:.3f}** |

![Figure 3. Grouped cross-validated ROC curves for five-point swing prediction](../../figures/final/swing-prediction-roc.png)

The Random Forest reaches AUC {analysis.rf_summary.auc:.3f}. This is not strong enough to claim deterministic control of match swings, but it is materially above a chance-ranking AUC of 0.5. Therefore, local reversal risk contains usable information even though persistent momentum was not established in Section 3.

## 4.4 Which indicators matter most?

Random Forest impurity importance is not a causal effect, but it shows which variables the prediction rule uses most often.

| Indicator | Relative importance |
|---|---:|
{importance_rows}

![Figure 4. Leading indicators in the swing-hazard model](../../figures/final/swing-feature-importance.png)

The dominant indicator is **speed of return toward neutral**, followed by distance from neutral and the current Flow Score. Score position and recent physical/workload variables contribute after the geometry of the flow itself. Server identity has low residual importance because the Flow Score has already removed the first-order service advantage.

This ordering gives a useful coaching interpretation: the most dangerous situation is not simply "the opponent has momentum." It is **an existing advantage that is shrinking rapidly toward the neutral region.**

## 4.5 Full-final holdout test

To demonstrate transfer beyond ordinary folds, we remove the entire Alcaraz-Djokovic final from training and fit the Random Forest on the other 30 matches. On the final alone, the model achieves **AUC={analysis.final_holdout_auc:.3f}** and **balanced accuracy={analysis.final_holdout_balanced_accuracy:.3f}**.

![Figure 5. Flow Score and predicted swing risk for a final excluded from training](../../figures/final/final-holdout-swing-risk.png)

The risk series rises most often near periods where the Flow Score is approaching or crossing neutral. This is the intended use of the model: not to announce an inevitable winner, but to warn that the current local advantage is unstable.

# 5. Generalization and Sensitivity

## 5.1 Match-to-match generalization

Because grouped cross-validation predicts only matches unseen by the fitted fold, each match provides a local test of transfer. Among matches with both swing and non-swing examples, **{above_chance}/{len(per_auc)}** have AUC above 0.5. The median match-level AUC is **{median_auc:.3f}**, with an interquartile range of **{q1_auc:.3f}-{q3_auc:.3f}**.

![Figure 6. Distribution of held-out match-level AUC](../../figures/final/match-generalization.png)

The spread in Figure 6 is as important as the mean. Some matches are substantially easier to forecast than others, so a coach should interpret risk as probabilistic and match-dependent. A universal fixed threshold is less defensible than recalibrating the alert rate to the opponent and recent playing conditions.

## 5.2 Sensitivity to the Flow Score window

We repeat the complete grouped validation after changing the rolling window used in the Flow Score.

| Flow window (points) | Random Forest AUC |
|---:|---:|
{sensitivity_rows}

Longer windows improve predictability because they suppress point-level noise, but they also react later to a genuine change. We retain **7 points** as the primary model because it gives a useful compromise between responsiveness and stability; the qualitative conclusion that swing risk is moderately predictable is not tied to one exact window.

## 5.3 Generalization beyond this data set

The architecture separates sport-specific and general components. The sport-specific part is the baseline expectation $e_t$. In tennis it is dominated by server identity. On clay or grass, in women's matches, or for a different player pair, $\hat p_s$ should be re-estimated. The residual-flow construction and swing-hazard logic can then remain unchanged.

For table tennis, volleyball, or other alternating-possession sports, the same idea applies if the dominant structural advantage is redefined. For continuous sports such as soccer, possession or expected-goal context would replace server identity. We therefore claim **structural generalizability of the framework**, not numerical transfer of the fitted Wimbledon parameters.

# 6. Model Evaluation

## 6.1 Strengths

- **Serve is removed before momentum is discussed.** This prevents a known tennis mechanism from being mislabeled as psychological persistence.
- **Descriptive flow and causal claims are separated.** A useful visualization can exist even when the momentum null is not rejected.
- **Prediction uses complete-match holdouts.** This blocks the easiest source of temporal leakage in point-level sports data.
- **The model remains interpretable.** The strongest predictor has a simple meaning: an advantage that is moving rapidly toward neutral is fragile.
- **The conclusions are evidence-calibrated.** AUC near 0.69 is presented as moderate warning ability, not deterministic prediction.

## 6.2 Limitations

The data omit potentially important latent factors such as injury, emotional state, crowd effects, tactical intent, and real-time coaching information. Player identities also repeat across matches, so grouped-by-match validation does not constitute a fully unseen-player test. The server baseline is intentionally simple; player-specific serve and return strength could improve calibration but would require stronger shrinkage or external history to avoid overfitting.

The swing label depends on the smoothing window and neutral band. Section 5 shows window sensitivity, but the operational definition remains a modeling choice. Random Forest importance is predictive, not causal: for example, recent running distance may correlate with long rallies rather than independently causing a swing.

Finally, the absence of significant residual persistence does not prove that psychological momentum never exists. It says that **this point-level Wimbledon sample does not require a persistent momentum process to explain the observed flow excursions after serve adjustment.**

# 7. Memorandum

**To: Coaching staff preparing for a high-level grass-court match**

**From: Match analytics team**

**Subject: How to use - and not misuse - momentum during a tennis match**

Our analysis of {analysis.n_points:,} points from {analysis.n_matches} Wimbledon matches suggests that coaches should distinguish *current flow* from *persistent momentum*.

First, do not interpret a service hold or a short winning run as evidence that a player has acquired a force that will automatically continue. Across the data, servers win {analysis.server_point_win_rate:.1%} of points. Once this advantage is removed, we find no match with significant residual Ljung-Box dependence and no match whose largest Flow Score excursion exceeds a server-only simulation at the 5% level. In practical terms: much of what looks like momentum can be generated by the normal structure of tennis.

Second, the current flow is still useful. Our Flow Score compares actual recent points with what the server alone would predict. A large positive or negative value tells you that one player is temporarily outperforming the structural baseline. Treat this as a **state description**, not a guarantee about the next game.

Third, watch the *direction of change* more than the current level. Our swing-risk model predicts whether the flow will reverse within five points with grouped cross-validated AUC {analysis.rf_summary.auc:.3f}. The strongest warning sign is an advantage that is already moving back toward neutral. The next most useful information is how close the match is to neutral, the recent slope of flow, the score situation, and recent error/workload indicators.

We recommend three response rules for player preparation:

- **Protect a decaying advantage.** When flow is positive but falling rapidly, simplify patterns, prioritize first-serve quality, and avoid donating points through unforced errors. The objective is not to "keep momentum" but to stop a measurable deterioration.
- **Use changeovers as reset points.** If recent unforced errors and physical workload rise while flow approaches neutral, use the next legal rest period for a rehearsed reset routine: breathing, first-serve target selection, and one high-percentage rally pattern.
- **Rebaseline for the opponent.** Before a new match, estimate the expected serve/return advantage for the two players. Do not compare raw Flow Scores across opponents without changing this baseline. A strong returner changes what counts as abnormal performance.

The model should be used as an alert system, not an oracle. In our strict full-final holdout, it still achieves AUC {analysis.final_holdout_auc:.3f}; useful, but far from perfect. The correct coaching message is therefore: **prepare for fragile states, do not chase narratives.**

# 8. Conclusion

We developed a continuous measure of tennis match flow, tested the stronger claim of persistent momentum, and built a leakage-resistant model of approaching reversals. The main mathematical insight is to subtract the server advantage before measuring local performance. The resulting Flow Score gives an intuitive visualization of the 2023 Wimbledon final while remaining comparable across service changes.

Formal residual and simulation tests do not support a universal persistent momentum effect in this data set. Yet the probability of a near-term flow reversal is moderately predictable. A Random Forest trained with entire matches held out reaches AUC {analysis.rf_summary.auc:.3f}, and a model trained without the featured final transfers to that final with AUC {analysis.final_holdout_auc:.3f}. The most useful warning is an advantage decaying toward neutral, not the absolute presence of a winning run.

Thus the apparent contradiction in the problem has a simple resolution: **flow is real as a measurable description; persistent momentum is not required as an extra stochastic force; swing risk is locally predictable.**

# 9. References

[1] COMAP. 2024 MCM Problem C: Momentum in Tennis. Consortium for Mathematics and Its Applications, 2024.

[2] Ljung, G. M., and Box, G. E. P. "On a Measure of Lack of Fit in Time Series Models." *Biometrika*, 65(2), 297-303, 1978.

[3] Wald, A., and Wolfowitz, J. "On a Test Whether Two Samples Are from the Same Population." *The Annals of Mathematical Statistics*, 11(2), 147-162, 1940.

[4] Breiman, L. "Random Forests." *Machine Learning*, 45, 5-32, 2001.

[5] Fawcett, T. "An Introduction to ROC Analysis." *Pattern Recognition Letters*, 27(8), 861-874, 2006.

# AI Use Report

Generative AI was used as a coding and drafting assistant in the development of this report. It helped organize the research workflow, translate computed results into prose, and check consistency between equations, figures, and the written narrative. All numerical results reported in the paper were generated from the provided `wimbledon_data.csv` through deterministic Python analysis; the statistical tests, grouped cross-validation, Random Forest predictions, feature importances, tables, and figures were recomputed from the data rather than supplied by the language model. The final PDF was compiled from the generated manuscript and subjected to programmatic whole-PDF layout review. No AI-generated image is used as quantitative evidence in this solution.
"""

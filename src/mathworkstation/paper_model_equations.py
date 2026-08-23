from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelEquation:
    label: str
    latex: str
    explanation: str
    label_zh: str = ""
    explanation_zh: str = ""
    paper_priority: int = 50


def select_equations_for_paper(method: str, budget: int | None = None) -> list[ModelEquation]:
    """Select the smallest paper-facing equation set that still exposes the model.

    ``equations_for_method`` remains the complete executed-method registry.  This
    selector is the presentation layer: routine estimator or tuning equations may
    stay registered for auditability while the paper shows only the equations with
    the highest explanatory value.  Ties preserve registry order.
    """

    equations = equations_for_method(method)
    if budget is None or budget >= len(equations):
        return equations
    if budget <= 0:
        return []
    ranked = sorted(enumerate(equations), key=lambda item: (-item[1].paper_priority, item[0]))
    selected = {index for index, _equation in ranked[:budget]}
    return [equation for index, equation in enumerate(equations) if index in selected]


def equations_for_method(method: str) -> list[ModelEquation]:
    """Return equations only for solver methods the workstation actually runs.

    Unknown methods intentionally return an empty list. Paper generation must
    never fill an equation gap with a generic state-space/optimization template.
    """

    value = method.lower().replace("-", "_").replace(" ", "_")
    if "pipeline_layout_continuous" in value:
        return [
            ModelEquation(
                label="Continuous pipeline-layout cost",
                latex=(
                    r"L(x,y,z)=c_A\sqrt{x^2+(y-a)^2}+c_B\sqrt{(c-x)^2+(z-y)^2}"
                    r"+c_Sy+(c_B+c_U)\sqrt{(d-c)^2+(b-z)^2}"
                ),
                explanation="A=(0,a) and B=(d,b) are the two refineries, E=(x,y) is the shared junction, F=(c,z) is the urban-boundary crossing and G=(x,0) is the railway station. Segment costs are assigned according to the registered pipeline and urban-surcharge coefficients.",
            ),
            ModelEquation(
                label="Geometric feasibility bounds",
                latex=r"0\le x\le c,\qquad 0\le y\le a,\qquad 0\le z\le b",
                explanation="The shared junction stays in the admissible suburban rectangle, the boundary crossing lies on the urban boundary, and the station lies on the railway. The no-shared alternative is the boundary case y=0.",
            ),
        ]
    if "panel_holt_exponential_smoothing" in value:
        return [
            ModelEquation(
                label="Entity-wise transformed Holt state",
                latex=r"z_{e,t}=g(y_{e,t}),\qquad \ell_{e,t}=\alpha z_{e,t}+(1-\alpha)(\ell_{e,t-1}+\phi b_{e,t-1})",
                explanation="Each state/indicator series is modeled independently under the same chronological protocol; g is the registered identity, log, or logit transform for that target.",
            ),
            ModelEquation(
                label="Entity-wise damped trend",
                latex=r"b_{e,t}=\beta(\ell_{e,t}-\ell_{e,t-1})+(1-\beta)\phi b_{e,t-1}",
                explanation="The local trend is updated separately for each entity-target series, avoiding cross-state leakage.",
            ),
            ModelEquation(
                label="Panel future forecast",
                latex=r"\hat y_{e,t+h}=g^{-1}\!\left(\ell_{e,t}+\sum_{j=1}^{h}\phi^j b_{e,t}\right)",
                explanation="Forecasts are transformed back to the original profile scale; residual bootstrap intervals are formed from that series' temporal holdout errors.",
            ),
        ]
    if "panel_linear_trend_characterization" in value:
        return [
            ModelEquation(
                label="Entity-specific historical trend",
                latex=r"y_{e,t}=\beta_{0,e}+\beta_{1,e}t+\varepsilon_{e,t}",
                explanation="A separate least-squares trend is estimated for each state-profile series so the sign and annual magnitude of historical evolution remain comparable without pooling state levels.",
            ),
            ModelEquation(
                label="Least-squares trend estimate",
                latex=r"(\hat\beta_{0,e},\hat\beta_{1,e})=\arg\min_{\beta_0,\beta_1}\sum_{t\in\mathcal T_e}(y_{e,t}-\beta_0-\beta_1 t)^2",
                explanation="The accepted trend direction is derived from observed history; the same entity-wise temporal holdout rule evaluates predictive adequacy of the simple characterization.",
            ),
        ]
    if "entropy_topsis" in value:
        return [
            ModelEquation(
                label="Entropy-derived criterion weight",
                latex=r"e_j=-\frac{1}{\ln m}\sum_{i=1}^{m}p_{ij}\ln p_{ij},\qquad w_j=\frac{1-e_j}{\sum_k(1-e_k)}",
                explanation="After direction-aware normalization, criteria with greater cross-entity information dispersion receive larger objective weights.",
            ),
            ModelEquation(
                label="TOPSIS closeness score",
                latex=r"C_i=\frac{D_i^-}{D_i^++D_i^-},\qquad D_i^{\pm}=\left\|v_i-v^{\pm}\right\|_2",
                explanation="Each state's weighted profile is ranked by relative closeness to the ideal and distance from the anti-ideal profile.",
            ),
        ]
    if "linear_programming" in value:
        return [
            ModelEquation(
                label="Linear compact-target program",
                latex=r"\max_x\;c^\top x\qquad\text{s.t.}\qquad Ax\le b,\;A_{eq}x=b_{eq},\;\ell\le x\le u",
                explanation="The decision variables are the registered state-year target shares; their bounds encode the no-policy forecast lower envelope and the historically bounded stretch envelope.",
            )
        ]
    if "holt_exponential_smoothing" in value:
        return [
            ModelEquation(
                label="Damped Holt level update",
                latex=r"\ell_t=\alpha z_t+(1-\alpha)(\ell_{t-1}+\phi b_{t-1}),\qquad z_t=\log y_t",
                explanation="The observed report count is modeled on the log scale, with a recursively updated local level and damped trend.",
            ),
            ModelEquation(
                label="Damped Holt trend update",
                latex=r"b_t=\beta(\ell_t-\ell_{t-1})+(1-\beta)\phi b_{t-1}",
                explanation="The trend state is smoothed and damped so long-horizon forecasts do not extrapolate an unrestricted linear trend.",
            ),
            ModelEquation(
                label="h-step forecast",
                latex=r"\hat z_{t+h\mid t}=\ell_t+(\phi+\phi^2+\cdots+\phi^h)b_t,\qquad \hat y_{t+h\mid t}=\exp(\hat z_{t+h\mid t})",
                explanation="The final point forecast is transformed back to the report-count scale; interval uncertainty is added from temporal-holdout residual bootstrap.",
            ),
        ]
    if "ridge_time_trend" in value:
        return [
            ModelEquation(
                label="Ridge forecasting fit",
                latex=r"\hat{\beta}=\arg\min_{\beta}\left(\|y-X\beta\|_2^2+\alpha\|\beta\|_2^2\right)",
                explanation="The time trend and registered numeric predictors are fit with L2 regularization.",
            ),
            ModelEquation(
                label="Residual-bootstrap interval",
                latex=r"I_{0.95}=\left[\hat y+q_{0.025}(r^*),\;\hat y+q_{0.975}(r^*)\right]",
                explanation="The accepted future interval uses centered temporal-holdout residual resampling.",
            ),
        ]
    if "standardized_ridge_with_bootstrap" in value:
        return [
            ModelEquation(
                label="Standardized ridge effect model",
                latex=r"\hat{\beta}=\arg\min_{\beta}\left(\|y-Z\beta\|_2^2+\alpha\|\beta\|_2^2\right)",
                explanation="Z contains the registered standardized explanatory features.",
            ),
            ModelEquation(
                label="Bootstrap effect interval",
                latex=r"CI_{0.95}(\beta_j)=\left[q_{0.025}(\beta_j^*),\;q_{0.975}(\beta_j^*)\right]",
                explanation="Coefficient uncertainty is estimated by refitting the registered model on bootstrap samples.",
            ),
        ]
    if "multioutput_ridge_with_simplex_projection" in value:
        return [
            ModelEquation(
                label="Component ridge heads",
                latex=r"\hat{\beta}_j=\arg\min_{\beta_j}\left(\|y_j-X\beta_j\|_2^2+\alpha\|\beta_j\|_2^2\right)",
                explanation="One regularized head is fitted for each outcome component under the same temporal split.",
            ),
            ModelEquation(
                label="Simplex projection",
                latex=r"p_j=100\,\frac{\max(0,z_j)}{\sum_k\max(0,z_k)}",
                explanation="The raw component forecasts are constrained to be nonnegative and sum to 100 percent.",
            ),
        ]
    if "serve_adjusted_flow" in value:
        return [
            ModelEquation(
                label="Serve-conditioned baseline probability",
                latex=r"e_t=S_t\hat p_s+(1-S_t)(1-\hat p_s)",
                explanation="The baseline conditions each point on the observed server before any local flow effect is discussed.",
                paper_priority=100,
            ),
            ModelEquation(
                label="Serve-adjusted point residual",
                latex=r"r_t=Y_t-e_t",
                explanation="Subtracting the serve-conditioned expectation prevents routine service advantage from being mislabeled as momentum.",
                paper_priority=100,
            ),
            ModelEquation(
                label="Local flow state statistic",
                latex=r"M_t=\frac{1}{w}\sum_{j=0}^{w-1}r_{t-j}",
                explanation="A short rolling mean converts point residuals into a signed local performance state while preserving within-match order.",
                paper_priority=100,
            ),
            ModelEquation(
                label="Serve-conditioned null simulation",
                latex=r"Y_t^{*}\sim\operatorname{Bernoulli}(e_t)",
                explanation="The null preserves the observed server sequence and tests whether flow excursions exceed what the structural baseline alone can generate.",
                paper_priority=85,
            ),
        ]
    if "probabilistic_state_transition_logistic_hazard" in value:
        return [
            ModelEquation(
                label="Three-state flow representation",
                latex=r"Z_t=\begin{cases}+1,&M_t>\delta,\\0,&|M_t|\le\delta,\\-1,&M_t<-\delta,\end{cases}",
                explanation="The continuous flow statistic is mapped to positive, neutral, and negative operating states using a declared deadband.",
                paper_priority=100,
            ),
            ModelEquation(
                label="Smoothed state-transition probability",
                latex=r"\hat P_{ij}=\frac{N_{ij}+1/2}{\sum_k(N_{ik}+1/2)}",
                explanation="Jeffreys pseudo-counts regularize the empirical transition matrix without turning finite-state counts into zero-probability transitions.",
                paper_priority=90,
            ),
            ModelEquation(
                label="Probabilistic swing-hazard link",
                latex=r"\Pr(A_t=1\mid x_t)=\sigma(\beta_0+\beta^\top x_t),\qquad \sigma(u)=\frac{1}{1+e^{-u}}",
                explanation="The primary interpretable predictor estimates the probability of a near-term flow reversal from information available at the current point; nonlinear ensembles are used only as a robustness comparator.",
                paper_priority=100,
            ),
        ]
    if "logistic_regression" in value:
        return [
            ModelEquation(
                label="Multiclass logistic probability",
                latex=r"P(Y=c\mid x)=\frac{\exp(\eta_c)}{\sum_k\exp(\eta_k)},\qquad \eta_c=\beta_c^\top x+b_c",
                explanation="The registered features determine class probabilities under the executed logistic model.",
            )
        ]
    if "retail_category_pricing_replenishment" in value:
        return [
            ModelEquation(
                label="Category demand-response candidates",
                latex=(
                    r"\begin{aligned}"
                    r"\log(1+q_{c,t})={}&\beta_{0,c}+\beta_{1,c}m_{c,t}+I_{Q,c}\beta_{2,c}m_{c,t}^{2}\\"
                    r"&+I_{T,c}s_c(t)+\varepsilon_{c,t},\qquad I_{Q,c},I_{T,c}\in\{0,1\}."
                    r"\end{aligned}"
                ),
                explanation="The candidate chain starts from markup alone, then adds temporal controls and finally a quadratic markup term. Each increase in complexity is retained only when it materially reduces chronological holdout RMSE under the same protocol.",
                label_zh="品类需求响应候选模型",
                explanation_zh="候选链从“仅使用加价率”的简约响应开始，再依次允许时间校正项 $s_c(t)$ 与二次加价项。$I_{T,c}$ 和 $I_{Q,c}$ 表示该品类是否需要对应扩展；只有更复杂候选在同一时间留出集上带来实质性误差下降时才升级模型。",
                paper_priority=100,
            ),
            ModelEquation(
                label="Ridge estimation and candidate selection",
                latex=(
                    r"\begin{aligned}"
                    r"\hat\theta_{c,k}&=\arg\min_{\theta}\left\{\|z_c-X_{c,k}\theta\|_2^2+\alpha\|\theta\|_2^2\right\},"
                    r"\quad k\in\{S,L,Q\},\\"
                    r"k_c^{(0)}&=S,\qquad"
                    r"k_c^{(j)}=\begin{cases}"
                    r"k_j,&\operatorname{RMSE}_{k_j}<(1-\delta)\operatorname{RMSE}_{k_c^{(j-1)}},\\"
                    r"k_c^{(j-1)},&\text{otherwise},\end{cases}\quad (k_1,k_2)=(L,Q)."
                    r"\end{aligned}"
                ),
                explanation="All candidates use the same ridge penalty and chronological split. Starting from the simple markup-only response S, the route upgrades to the temporally adjusted linear model L and then the quadratic model Q only when the next candidate clears the registered relative holdout-RMSE improvement threshold δ.",
                label_zh="岭回归估计与逐级复杂度选择",
                explanation_zh="三个候选采用相同的岭惩罚与时间切分。模型从简约响应 $S$ 出发，依次考察时间校正线性模型 $L$ 和二次模型 $Q$；只有下一层候选的留出RMSE相对当前模型至少改善登记阈值 $\\delta$ 时才升级。该估计细节保留在方法登记中，正文可按公式预算省略。",
                paper_priority=25,
            ),
            ModelEquation(
                label="Loss-adjusted replenishment",
                latex=r"Q_{c,t}=\frac{\hat q_{c,t}}{1-\lambda_c}",
                explanation="Expected sellable demand is converted to purchase quantity using the registered category loss rate.",
                label_zh="损耗修正后的补货量",
                explanation_zh="根据品类历史损耗率将预计可销售需求换算为实际进货量，使补货决策显式考虑损耗。",
                paper_priority=90,
            ),
            ModelEquation(
                label="Expected profit under markup decision",
                latex=r"\Pi_{c,t}(m)=\hat q_{c,t}(m)\,w_{c,t}(1+m)-Q_{c,t}(m)\,w_{c,t}",
                explanation="The decision searches only the historically observed markup support and chooses the markup maximizing expected operating profit.",
                label_zh="品类定价—补货联合收益函数",
                explanation_zh="在历史实际出现过的加价率区间内搜索候选价格，对每个候选加价率同时计算需求、补货量和预期收益，并选择预期收益最大的方案。",
                paper_priority=100,
            ),
            ModelEquation(
                label="Historical-support optimization",
                latex=r"m^*_{c,t}=\arg\max_{m\in[m_c^{\min},m_c^{\max}]}\Pi_{c,t}(m)",
                explanation="Restricting the search to observed markup support avoids unsupported price extrapolation.",
                label_zh="历史价格支持域内的最优加价率",
                explanation_zh="最优加价率只在历史数据支持的区间内搜索，避免把需求模型外推到从未观测的价格区域。",
                paper_priority=80,
            ),
        ]
    if "retail_item_pricing_replenishment" in value:
        return [
            ModelEquation(
                label="Item selection score",
                latex=r"s_i=\bar q_i\left(p_i-\frac{w_i}{1-\lambda_i}\right)",
                explanation="Recently available items are screened by recent average sales multiplied by loss-adjusted unit margin.",
                label_zh="单品经营价值筛选指标",
                explanation_zh="对近期实际有售的单品，以近期日均销量乘以损耗修正后的单位毛利构造经营价值指标，用于在真实可售集合中筛选候选单品。",
                paper_priority=75,
            ),
            ModelEquation(
                label="Category-demand allocation",
                latex=r"\hat q_i=\hat Q_{c(i)}\frac{\bar q_i}{\sum_{j\in\mathcal I_{c(i)}}\bar q_j}",
                explanation="Each selected item's expected sales are allocated from the upstream category demand target according to its recent sales share.",
                label_zh="品类需求向单品的分配",
                explanation_zh="将问题2得到的品类需求预测作为上游约束，再按入选单品近期销量占比分配到单品层，保证问题3与问题2的数据链和决策链保持一致。",
                paper_priority=100,
            ),
            ModelEquation(
                label="Minimum-display replenishment",
                latex=r"Q_i=\max\left\{Q_{\min},\frac{\hat q_i}{1-\lambda_i}\right\},\qquad Q_{\min}=2.5\text{ kg}",
                explanation="The replenishment quantity respects the minimum display requirement and compensates for item loss.",
                label_zh="最小陈列量与损耗约束",
                explanation_zh="单品补货量同时满足题目规定的最小陈列量和损耗补偿要求，确保给出的方案在经营约束下可执行。",
                paper_priority=95,
            ),
            ModelEquation(
                label="Item-level expected profit",
                latex=r"\Pi_i=\hat q_i p_i-Q_i w_i,\qquad 27\le\sum_i x_i\le33",
                explanation="The accepted assortment keeps the requested number of displayed items, covers the required categories, and reports expected operating profit under the inherited category markup.",
                label_zh="单品组合收益与数量约束",
                explanation_zh="在单品数量保持27—33个并覆盖全部需求品类的条件下计算组合预期收益；售价继承问题2的品类最优加价率，因此上下游决策保持一致。",
                paper_priority=90,
            ),
        ]
    if "spearman_iqr_mean_shift_scan" in value:
        return [
            ModelEquation(
                label="Spearman association",
                latex=r"\rho_s=\operatorname{Corr}(\operatorname{rank}(X),\operatorname{rank}(Y))",
                explanation="Rank correlation is used for monotone association discovery; the validation layer separately checks bootstrap sign stability.",
                label_zh="Spearman 秩相关系数",
                explanation_zh="利用秩相关系数刻画不同销量序列之间的单调关联，并通过重抽样检查相关方向的稳定性，避免把一次样本相关直接当成稳定规律。",
                paper_priority=100,
            )
        ]
    return []

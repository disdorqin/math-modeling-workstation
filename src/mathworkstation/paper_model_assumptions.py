from __future__ import annotations


def assumptions_for_method(method: str, task_family: str, *, language: str = "en") -> list[str]:
    """Return explicit assumptions implied by an actually executed solver.

    These are method/validation scope assumptions, not domain facts. Unknown
    solver methods return an empty list so the paper engine cannot fill the
    assumptions section with generic competition boilerplate.
    """

    value = method.lower().replace("-", "_").replace(" ", "_")
    if language == "zh":
        return _assumptions_for_method_zh(value, task_family)
    if "pipeline_layout_continuous" in value:
        return [
            "The railway and urban boundary are represented by straight lines in the coordinate system registered by the problem statement.",
            "Pipeline construction cost is proportional to segment length within each registered cost region; unobserved safety, maintenance, mixing, and environmental costs are not silently added to the numerical objective.",
            "The shared junction, urban-boundary crossing, and railway station remain inside the registered geometric bounds; the no-shared alternative is represented by a zero shared-segment length.",
            "The accepted route is conditional on the registered unit-cost and urban-surcharge coefficients, so surcharge perturbation is reported before treating the route as robust.",
        ]
    if "panel_holt_exponential_smoothing" in value:
        return [
            "Each entity-target series follows its own chronological state evolution; observations from another state are not used as future information for that series.",
            "The registered transform for each target is appropriate for its support (for example, logit for a share constrained to [0,1]).",
            "Temporal-holdout residuals are treated as a local approximation to future forecast error for the reported entity-specific bootstrap intervals; structural policy changes remain outside the no-policy forecast.",
        ]
    if "panel_linear_trend_characterization" in value:
        return [
            "A first-order trend is used as a transparent characterization of historical direction and annual magnitude, not as a claim that the series is globally linear forever.",
            "Each entity's historical trend is estimated separately under the same time scale and profile definition, preserving cross-entity comparability without pooling entity levels.",
            "Temporal holdout error is used to check whether the simple characterization remains adequate near the end of the observed history.",
        ]
    if "entropy_topsis" in value:
        return [
            "All entities are evaluated on the same registered criterion definitions and reference time.",
            "Benefit/cost directions are fixed before scoring, and entropy weights are derived only from the observed cross-entity criterion matrix rather than assigned to force a preferred winner.",
            "The top-ranked conclusion is considered stronger only when the winner and ordering remain stable under the registered leave-one-criterion-out perturbations.",
        ]
    if "linear_programming" in value:
        return [
            "The objective coefficients and variable bounds represent the stated target-setting criterion and feasibility envelope; the optimizer does not infer causal policy effects absent from the data.",
            "No-policy forecasts form lower bounds and historically observed same-horizon improvements bound stretch targets; the resulting targets are feasible-envelope decisions rather than natural forecasts.",
            "The accepted optimum remains conditional on those bounds and requires sensitivity analysis before stronger policy claims are made.",
        ]
    if "holt_exponential_smoothing" in value:
        return [
            "The chronological order is meaningful, and the local level/trend states are updated only from observations available at each forecast origin.",
            "A damped additive trend on the registered log-transformed report counts is a locally adequate description of the stated forecast horizon; no seasonal component is asserted without evidence.",
            "Centered temporal-holdout residuals are sufficiently representative of near-future forecast error for the reported bootstrap prediction interval.",
        ]
    if "ridge_time_trend" in value or task_family == "forecasting":
        return [
            "The chronological order is meaningful, so validation and fitting must not use future target observations to predict earlier dates.",
            "The registered time trend and numeric predictors provide a locally adequate approximation for the stated forecast horizon; the model is not claimed to extrapolate indefinitely.",
            "Centered temporal-holdout residuals are sufficiently representative of near-future forecast error for the reported bootstrap prediction interval.",
        ]
    if "standardized_ridge_with_bootstrap" in value or task_family == "explanatory_inference":
        return [
            "Standardized linear effects are used as conditional associations under the registered feature specification, not as causal effects.",
            "The fitted effect directions are meaningful only within the observed feature range and the accepted regularized model specification.",
            "Bootstrap coefficient intervals quantify resampling stability of the fitted association; they do not remove omitted-variable or causal-identification limitations.",
        ]
    if "multioutput_ridge_with_simplex_projection" in value or task_family == "distribution_forecasting":
        return [
            "The response components form a composition: they are nonnegative and their total is fixed at 100 percent.",
            "A shared chronological split is appropriate for all response components, so component forecasts are evaluated on the same future-like holdout period.",
            "Simplex projection enforces structural validity after component prediction and must be retained when interpreting the reported future distribution.",
        ]
    if "serve_adjusted_flow" in value:
        return [
            "Server identity is treated as the dominant first-order structural baseline for point-winning probability; residual Flow is interpreted only after that baseline is removed.",
            "The rolling Flow Score is an observable local-performance statistic, not a direct measurement of confidence, psychology, injury, or a causal momentum force.",
            "The serve-conditioned simulation preserves the observed server sequence; rejecting or failing to reject this null is interpreted only as evidence about residual temporal persistence in the observed match sample.",
        ]
    if "probabilistic_state_transition_logistic_hazard" in value:
        return [
            "The three Flow states are an operational discretization of the accepted continuous Flow Score; the neutral deadband and forecast horizon are modeling choices whose sensitivity must be checked.",
            "All hazard predictors are available at the current point; future point outcomes are used only to label whether a reversal occurs and never enter the predictor vector.",
            "Complete matches are held out together so reported probability performance measures transfer across match contexts rather than across randomly mixed points from the same match.",
            "Transition probabilities and logistic coefficients are predictive conditional relationships, not causal tactical effects or proof of a psychological latent force.",
        ]
    if "logistic_regression" in value or task_family == "classification":
        return [
            "The registered labels correspond to the event/state defined by the executed solver and are suitable targets for probabilistic classification.",
            "Prediction uses exactly the feature schema available at the decision origin; target-defining future information is excluded from predictors.",
            "Predicted probabilities remain conditional on the observed training distribution and require out-of-sample calibration or grouped validation before interpretation.",
        ]
    if "spearman_iqr_mean_shift_scan" in value:
        return [
            "Spearman rank correlation is used to describe monotone association and is not interpreted as causal dependence.",
            "Outlier and mean-shift scans are exploratory diagnostics whose purpose is to generate prioritized patterns for follow-up, not to establish confirmatory hypotheses by themselves.",
            "A discovered pattern is considered more credible only when its direction or strength is stable under the registered resampling/validation check.",
        ]
    if task_family == "exploratory_analysis":
        return [
            "Exploratory statistics are treated as descriptive evidence and are not promoted to causal or mechanistic claims without a dedicated validation step.",
            "Ordering, grouping, and baseline adjustments follow the executed solver plan rather than being reconstructed from domain intuition during writing.",
            "Only patterns that remain compatible with the registered resampling, null, or stability checks are carried into downstream modeling.",
        ]
        return [
            "Spearman rank correlation is used to describe monotone association and is not interpreted as causal dependence.",
            "Outlier and mean-shift scans are exploratory diagnostics whose purpose is to generate prioritized patterns for follow-up, not to establish confirmatory hypotheses by themselves.",
            "A discovered pattern is considered more credible only when its direction or strength is stable under the registered resampling/validation check.",
        ]
    if task_family == "optimization":
        return [
            "The registered objective and constraints faithfully represent the decision problem over the stated feasible region.",
            "The reported solution is valid only for the registered parameter values and solver status; sensitivity analysis is required before broad policy claims.",
        ]
    if task_family == "simulation":
        return [
            "The registered random mechanisms and parameter distributions are scenario assumptions rather than observed facts unless explicitly tied to data evidence.",
            "Simulation conclusions are based on repeated replications and uncertainty summaries, not on any single random trajectory.",
        ]
    if task_family == "ranking":
        return [
            "The registered relevance/score definition is an acceptable representation of ranking quality for the stated decision context.",
            "Adjacent ranks should not be treated as substantively different when the registered stability analysis cannot distinguish them.",
        ]
    return []


def _assumptions_for_method_zh(value: str, task_family: str) -> list[str]:
    """Chinese paper-facing assumptions for CUMCM output.

    The statements mirror the scope of the executed solver. They intentionally
    avoid internal registry/protocol terminology and never add a new data fact.
    """

    if "retail_category_pricing_replenishment" in value:
        return [
            "在短期决策窗口内，历史实际出现过的成本加成率区间可作为定价搜索的可信支持域，区间外价格不作无证据外推。",
            "销量与成本加成率、周周期、年周期及时间趋势之间的关系用于预测而非因果解释；线性或二次响应形式由时间留出误差决定。",
            "历史损耗率用于把预计可销售需求换算为补货量；未来批发成本估计存在误差，因此需要通过成本扰动检验判断策略稳定性。",
        ]
    if "retail_item_pricing_replenishment" in value:
        return [
            "题目规定的近期实际可售记录用于界定7月1日候选单品集合，不把历史上已停止销售的单品重新加入决策。",
            "单品层需求继承问题2得到的品类需求，并按近期销量份额分配；该分配用于形成可执行方案，不解释为消费者偏好的因果机制。",
            "单品数量、品类覆盖和最低2.5 kg陈列量按题目要求作为硬约束，任何收益比较都只在满足这些约束的方案之间进行。",
        ]
    if "spearman_iqr_mean_shift_scan" in value or task_family == "exploratory_analysis":
        return [
            "Spearman秩相关仅刻画销量序列之间的单调关联，不将相关关系解释为因果作用。",
            "四分位距异常扫描和均值变化用于发现值得后续关注的结构，其结果属于探索性证据，不能单独替代确认性检验。",
            "只有在重抽样或已登记稳定性检验中方向和强度保持稳定的发现，才作为后续建模的主要依据。",
        ]
    if "pipeline_layout_continuous" in value:
        return [
            "铁路与城区边界按题目给定坐标关系表示为直线，管线节点均限制在题目允许的几何区域内。",
            "各区域铺设成本按单位长度计入目标函数；题目未给出的维护、安全和环境附加成本不擅自加入数值目标。",
            "最优路线依赖题目给定的单位成本和城区附加费用，因此需通过关键成本参数扰动检查结论稳定性。",
        ]
    if "entropy_topsis" in value:
        return [
            "所有评价对象采用相同指标定义与同一参考时点，正向、负向属性在计算权重前固定。",
            "熵权仅由观测指标矩阵的信息差异确定，不人为调整权重以得到预设排序。",
            "只有在删去单项指标等扰动下领先对象和主要排序保持稳定时，才将排序解释为稳健结论。",
        ]
    if "linear_programming" in value:
        return [
            "目标系数、变量上下界和约束均来自题意或已接受上游结果，优化器不额外推断未被数据支持的政策效应。",
            "所得最优值表示当前可行域与参数条件下的决策结果，而不是脱离约束条件的自然预测。",
            "关键边界或成本参数变化可能改变最优方案，因此强决策结论需同时参考敏感性分析。",
        ]
    if "panel_holt_exponential_smoothing" in value or "holt_exponential_smoothing" in value:
        return [
            "时间顺序具有实际意义，预测时仅使用预测起点之前能够获得的观测，不引入未来信息。",
            "局部水平与趋势用于描述题目给定预测期内的变化，不假定该趋势能够无限期保持。",
            "时间留出残差用于近似近期预测误差，其有效性仍受结构突变和政策变化等未观测因素限制。",
        ]
    if "panel_linear_trend_characterization" in value:
        return [
            "一阶趋势仅用于透明刻画历史方向和变化幅度，不假定序列长期严格线性。",
            "各对象在统一时间尺度和指标定义下分别估计趋势，以保证跨对象比较时不混合其水平差异。",
            "通过时间留出误差检查简单趋势在观测期末端附近是否仍具有足够的刻画能力。",
        ]
    if "standardized_ridge_with_bootstrap" in value or task_family == "explanatory_inference":
        return [
            "标准化回归系数表示给定特征集合下的条件关联，不解释为因果效应。",
            "效应方向仅在观测特征范围与当前正则化模型设定内解释，不作超出样本支持域的外推。",
            "Bootstrap区间用于衡量重抽样稳定性，不能消除遗漏变量和因果识别不足。",
        ]
    if "multioutput_ridge_with_simplex_projection" in value or task_family == "distribution_forecasting":
        return [
            "各响应分量构成非负且总和固定的组成数据，预测后仍需保持该结构约束。",
            "所有分量采用同一时间留出区间评价，使不同分量的预测误差具有可比性。",
            "单纯形投影是保证分布有效性的必要步骤，解释结果时不能忽略投影后的结构修正。",
        ]
    if "serve_adjusted_flow" in value:
        return [
            "先把发球方带来的结构性胜点优势作为基线扣除，再讨论局部比赛流向，避免把常规发球优势误写成动量。",
            "滚动Flow Score只表示可观测的局部相对表现，不直接等同于信心、心理状态、伤病或因果性的动量力量。",
            "随机基准保持真实发球顺序，检验结论只用于判断样本中的剩余时序持续性，不外推为普遍心理规律。",
        ]
    if "probabilistic_state_transition_logistic_hazard" in value:
        return [
            "三状态划分来自已接受的连续Flow Score，中性阈值与预测窗口属于模型设定，必须结合敏感性分析解释。",
            "所有风险预测特征在当前时点均可获得；未来胜负只用于定义反转标签，不进入特征向量。",
            "完整比赛作为分组整体留出，使概率验证反映跨比赛泛化，而不是同一比赛随机切点造成的信息混合。",
            "状态转移概率和Logistic系数表示条件预测关系，不解释为战术变量的因果效应。",
        ]
    if "logistic_regression" in value or task_family == "classification":
        return [
            "登记标签与实际求解器定义的事件或状态一致，并可作为概率分类目标。",
            "预测只使用决策时点能够获得的特征，定义标签所需的未来信息不得进入输入。",
            "概率结果仅在当前训练分布下解释，并需通过样本外分组验证或校准检验后使用。",
        ]
    if "ridge_time_trend" in value or task_family == "forecasting":
        return [
            "时间顺序不可打乱，训练与验证均不得使用未来目标值预测更早时点。",
            "时间趋势和实际登记解释变量只在题目给定预测窗口内作局部近似，不宣称能够无限外推。",
            "时间留出残差用于近似近期预测误差，并据此评价预测稳定性或构造区间。",
        ]
    if task_family == "optimization":
        return [
            "目标函数和约束能够表示题目要求的决策目标与可行边界，未登记的业务条件不在求解后补写。",
            "所得方案只对当前参数和可行域有效；关键参数变化可能改变最优决策，因此需结合敏感性结果解释。",
        ]
    if task_family == "simulation":
        return [
            "随机机制和参数分布属于已登记情景设定，除非有数据证据，否则不把它们表述为观测事实。",
            "仿真结论依据重复试验与不确定性汇总，而不是单条随机轨迹。",
        ]
    if task_family == "ranking":
        return [
            "评分指标能够表示题目所需的综合评价含义，所有对象在相同指标口径下比较。",
            "当稳定性分析无法区分相邻名次时，不把细小排序差异解释为实质差异。",
        ]
    return []

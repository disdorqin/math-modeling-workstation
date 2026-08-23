from __future__ import annotations

import re
from typing import Any


_METHOD_LABELS_EN = {
    "serve adjusted flow with ljung box and bootstrap null inference": "serve-adjusted Flow model with Ljung–Box and bootstrap null inference",
    "probabilistic state transition logistic hazard classification with calibration and random forest comparator": "calibrated state-transition logistic swing-hazard model with a Random Forest comparator",
    "probabilistic state transition logistic hazard with grouped resampling": "state-transition logistic swing-hazard model with grouped resampling",
}

_METHOD_LABELS_ZH = {
    "pipeline layout continuous": "连续几何管线布局优化模型",
    "pipeline layout continuous optimization": "连续几何管线布局优化模型",
    "pipeline geometry optimization": "连续几何管线布局优化模型",
    "geometric pipeline layout": "连续几何管线布局优化模型",
    "ridge time trend": "岭回归时间趋势模型",
    "holt exponential smoothing": "Holt 指数平滑预测模型",
    "popularity lifecycle": "分段指数生命周期模型",
    "multioutput ridge with simplex projection": "单纯形约束多输出岭回归模型",
    "logistic regression": "Logistic 回归分类模型",
    "entropy topsis": "熵权-TOPSIS 综合评价模型",
    "panel holt": "面板 Holt 趋势预测模型",
    "panel profile summary": "多对象指标画像模型",
    "panel trend characterization": "面板趋势刻画模型",
    "linear programming": "线性规划模型",
    "member group profile": "会员与非会员消费画像对比模型",
    "member consumption profile": "会员与非会员消费画像对比模型",
    "rfm member value": "RFM 会员价值评分模型",
    "rfmt member value": "RFMT 会员价值评分模型",
    "rfms member value": "RFMS 会员价值评分模型",
    "member value scoring": "会员价值综合评分模型",
    "member lifecycle states": "会员生命周期状态划分模型",
    "lifecycle state segmentation": "会员生命周期状态划分模型",
    "activation promotion association": "会员激活率与促销关联模型",
    "member activation rate": "会员激活率分析模型",
    "market basket association": "购物篮关联规则模型",
    "association rules": "购物篮关联规则模型",
    "spearman iqr mean shift scan": "Spearman秩相关—稳健异常扫描模型",
    "retail category pricing replenishment": "品类需求响应—定价补货联合优化模型",
    "retail item pricing replenishment": "单品组合—定价补货约束优化模型",
}

_METRIC_LABELS_ZH = {
    "objective_value": "目标函数值",
    "no_shared_objective_value": "不共享方案目标函数值",
    "shared_cost_advantage": "共享方案相对成本优势",
    "surcharge_sensitivity_max_relative_change": "附加费用扰动下目标值最大相对变化",
    "future_point": "预测值",
    "future_interval_lower": "预测区间下界",
    "future_interval_upper": "预测区间上界",
    "rmse": "均方根误差 RMSE",
    "mae": "平均绝对误差 MAE",
    "balanced_accuracy": "平衡准确率",
    "macro_f1": "宏平均 F1",
    "strongest_spearman_r": "最强 Spearman 相关系数",
    "top_decile_stability": "高价值会员前10%稳定保留率",
    "top_decile_threshold": "高价值会员前10%评分阈值",
    "activation_rate": "非活跃会员总体激活率",
    "promotion_activation_rate": "促销暴露会员激活率",
    "nonpromotion_activation_rate": "无促销暴露会员激活率",
    "promotion_rate_difference": "促销与非促销激活率差",
    "top_rule_support": "最强连带规则支持度",
    "top_rule_confidence": "最强连带规则置信度",
    "top_rule_lift": "最强连带规则提升度",
    "silhouette": "轮廓系数",
    "seed_adjusted_rand": "不同随机种子调整兰德一致性",
    "expected_profit_total": "预期总收益",
    "expected_demand_total": "预测总需求量",
    "replenishment_total": "总补货量",
    "demand_validation_rmse_mean": "需求预测平均RMSE",
    "demand_validation_mae_mean": "需求预测平均MAE",
    "entity_count": "建模品类数",
    "selected_item_count": "入选单品数",
    "category_coverage_count": "覆盖品类数",
    "minimum_order_quantity": "最小单品补货量",
}

_TOKEN_LABELS_ZH = {
    "station": "站点",
    "shared": "共享",
    "junction": "汇合点",
    "urban": "城区",
    "boundary": "边界",
    "crossing": "穿越点",
    "objective": "目标函数",
    "value": "值",
    "cost": "成本",
    "advantage": "优势",
    "sensitivity": "敏感性",
    "relative": "相对",
    "change": "变化",
    "solution": "决策变量",
    "target": "目标",
    "rank": "排序",
    "score": "得分",
    "profile": "画像指标",
    "future": "预测",
    "lower": "下界",
    "upper": "上界",
    "annual": "年度",
    "slope": "斜率",
    "observed": "观测",
}


_VALIDATION_LABELS_ZH = {
    "optimization continuous geometry sensitivity v1": "连续几何优化的约束可行性与敏感性检验",
    "forecasting temporal uncertainty v1": "时间留出与预测不确定性检验",
    "forecasting panel temporal uncertainty v1": "面板时间留出与预测不确定性检验",
    "ranking entropy topsis stability v1": "综合评价排序稳定性检验",
    "exploration panel profile summary v1": "多对象画像一致性检验",
    "forecasting panel trend characterization v1": "面板趋势刻画检验",
    "exploration discovery bootstrap v1": "Bootstrap重抽样稳定性检验",
    "optimization retail pricing replenishment": "时间留出预测、约束可行性与成本扰动检验",
    "optimization retail pricing replenishment v1": "时间留出预测、约束可行性与成本扰动检验",
}

_FIGURE_TITLES_ZH = {
    "research_workflow": "数据—分析—模型—验证—决策技术路线",
    "model_framework": "统一数学建模框架",
    "route_layout_geometry": "最优管线布局的关键坐标",
    "parameter_sensitivity_curve": "关键参数扰动下的目标函数变化",
    "scenario_cost_comparison": "共用与非共用方案的最优成本比较",
    "alternative_model_metric_comparison": "候选模型在统一指标下的实证比较",
    "alternative_model_stress_comparison": "不同验证规模下的模型稳健性比较",
    "retail_category_replenishment_plan": "未来一周各蔬菜品类补货策略",
    "retail_item_replenishment_plan": "7月1日主要单品补货决策",
    "retail_price_demand_relationship": "各蔬菜品类加价率与需求的关联响应",
    "retail_category_assortment_counts": "各蔬菜品类入选单品数量",
    "optimization_targets": "优化决策目标水平",
    "optimization_solution": "优化决策变量取值",
    "forecast_interval": "预测结果及不确定区间",
    "effect_intervals": "主要因素效应及不确定区间",
    "distribution_uncertainty": "预测分布及其不确定性",
    "class_probabilities": "分类结果与类别概率",
    "association_ranking": "主要变量关联强度排序",
    "exploratory_diagnostics_panel": "异常波动与阶段变化的稳健诊断",
    "panel_profile_heatmap": "多对象指标画像对比",
    "mcdm_ranking": "多指标综合评价结果",
    "member_group_profile_heatmap": "会员与非会员消费画像对比",
    "member_lifecycle_state_shares": "会员生命周期状态构成",
    "activation_rate_comparison": "促销暴露与会员激活率对比",
    "market_basket_rule_lift": "主要商品连带规则提升度",
    "member_value_top_ranking": "高价值会员综合评分结果",
}


class PaperHumanizationAdapter:
    """Translate internal research vocabulary into paper-facing academic prose.

    The adapter is deliberately document-only: it changes labels and fixed
    provenance phrases, never numerical values, equations, method selection,
    validation outcomes, or evidence identity.
    """

    @staticmethod
    def method_label(method: str, *, language: str = "en") -> str:
        normalized = _normalize(method)
        if language == "zh":
            return _METHOD_LABELS_ZH.get(normalized, _human_words(method))
        return _METHOD_LABELS_EN.get(normalized, _human_words(method))

    @staticmethod
    def validation_label(protocol: str, *, language: str = "en") -> str:
        normalized = _normalize(protocol)
        if language == "zh":
            return _VALIDATION_LABELS_ZH.get(normalized, _human_words(protocol).replace(".v1", ""))
        return _human_words(protocol).replace(".v1", "")

    @staticmethod
    def figure_title(figure: dict[str, Any], *, language: str = "en") -> str:
        title = str(figure.get("title") or "Result visualization")
        if language != "zh":
            return title
        semantic_kind = str((figure.get("parameters") or {}).get("semantic_kind") or "")
        return _FIGURE_TITLES_ZH.get(semantic_kind, title)

    @staticmethod
    def metric_label(metric: str, metadata: dict[str, Any] | None = None, *, language: str = "en") -> str:
        metadata = metadata or {}
        normalized = str(metric).strip().lower()
        if language != "zh":
            return _human_words(metric)
        if normalized in _METRIC_LABELS_ZH:
            return _METRIC_LABELS_ZH[normalized]
        if normalized.startswith("solution_"):
            variable = str(metadata.get("decision_variable") or normalized.removeprefix("solution_"))
            return "决策变量：" + PaperHumanizationAdapter._zh_tokens(variable)
        if normalized.startswith("rank_score_"):
            entity = str(metadata.get("entity") or normalized.removeprefix("rank_score_"))
            return f"{entity} 综合评价得分"
        if normalized.startswith("profile_"):
            entity = str(metadata.get("entity") or "对象")
            dimension = str(metadata.get("profile_dimension") or normalized)
            return f"{entity}：{PaperHumanizationAdapter._zh_tokens(dimension)}"
        if normalized.startswith("future_") and metadata.get("entity"):
            entity = str(metadata.get("entity"))
            target = PaperHumanizationAdapter._zh_tokens(str(metadata.get("target") or "目标"))
            future_time = str(metadata.get("future_time") or "")[:4]
            suffix = ""
            if normalized.endswith("_lower"):
                suffix = "下界"
            elif normalized.endswith("_upper"):
                suffix = "上界"
            return f"{entity} {future_time}年{target}预测{suffix}".strip()
        return PaperHumanizationAdapter._zh_tokens(normalized)

    @staticmethod
    def candidate_rationale(rationale: str, *, language: str = "en") -> str:
        text = str(rationale or "").strip()
        if language == "zh" and (
            "ProblemGraph" in text
            or "Modeling Brain" in text
            or "compatibility path" in text.lower()
            or "research envelope" in text.lower()
        ):
            return "该方案仅在研究阶段被登记为候选，当前没有形成同口径的实证对照，因此不补造性能差异。"
        return text

    @staticmethod
    def sanitize(text: str, *, language: str) -> str:
        """Remove fixed internal vocabulary without touching evidence-bearing content.

        Markdown link/image destinations are machine paths or URLs, not prose.
        Protect them before humanizing visible text so tokens such as ``SP1`` in
        ``subproblem-SP1-evidence.png`` can never be translated into a broken
        path.
        """

        text, protected_destinations = _protect_markdown_destinations(text)
        if language == "zh":
            replacements = (
                ("accepted Research State", "已验证研究结果"),
                ("Research State", "研究证据链"),
                ("SolverRegistry", "当前可执行方法库"),
                ("Solver execution", "实际求解过程"),
                ("Solver capability gap", "尚未补足的求解能力"),
                ("Solver evidence", "求解结果证据"),
                ("Solver", "求解方法"),
                ("登记模型下", "所建模型下"),
                ("登记模型", "所建模型"),
                ("登记策略", "所给策略"),
                ("登记约束", "模型约束"),
                ("已登记的", "所采用的"),
                ("已接受参数", "经检验的参数"),
                ("已接受结果", "经检验的结果"),
                ("已接受数值", "经检验的数值"),
                ("simple_markup", "简约加价响应"),
                ("linear_markup", "时间校正线性响应"),
                ("quadratic_markup", "时间校正二次响应"),
                ("retail_category_pricing_replenishment", "品类需求响应—定价补货联合优化模型"),
            )
            for old, new in replacements:
                text = text.replace(old, new)
            text = re.sub(r"validation gate\s*=\s*PASS", "检验结果通过", text, flags=re.IGNORECASE)
            text = re.sub(r"gate\s*为\s*\*\*PASS\*\*", "检验结果为 **通过**", text, flags=re.IGNORECASE)
            text = text.replace("protocol =", "检验协议：")
            text = re.sub(r"(?<![A-Za-z0-9_])SP(\d+)(?![A-Za-z0-9_])", r"问题\1", text)
            text = re.sub(
                r"Exploratory calculations are restricted to the registered numeric columns:\s*([^\n]+)",
                r"探索性分析仅使用实际登记并进入求解流程的数值字段：\1",
                text,
                flags=re.IGNORECASE,
            )
            return _restore_markdown_destinations(text, protected_destinations)
        replacements = (
            ("accepted Research State", "validated research evidence"),
            ("accepted research state", "validated research evidence"),
            ("Solver execution", "executed computational method"),
            ("Solver capability gap", "unresolved computational capability gap"),
            ("Solver evidence", "computational evidence"),
        )
        for old, new in replacements:
            text = text.replace(old, new)
        return _restore_markdown_destinations(text, protected_destinations)

    @staticmethod
    def _zh_tokens(value: str) -> str:
        tokens = re.split(r"[_\-\s]+", value.strip().lower())
        translated = [_TOKEN_LABELS_ZH.get(token, token) for token in tokens if token]
        return "".join(translated)


_MARKDOWN_DESTINATION_RE = re.compile(r"(!?\[[^\]]*\]\()([^\)]+)(\))")


def _protect_markdown_destinations(text: str) -> tuple[str, dict[str, str]]:
    protected: dict[str, str] = {}

    def replace(match: re.Match[str]) -> str:
        token = f"@@MATHWS_MD_DEST_{len(protected)}@@"
        protected[token] = match.group(2)
        return match.group(1) + token + match.group(3)

    return _MARKDOWN_DESTINATION_RE.sub(replace, text), protected


def _restore_markdown_destinations(text: str, protected: dict[str, str]) -> str:
    for token, destination in protected.items():
        text = text.replace(token, destination)
    return text


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("_", " ").replace("-", " ").replace(".", " ")).strip().lower()


def _human_words(value: str) -> str:
    return re.sub(r"\s+", " ", value.replace("_", " ").replace("-", " ")).strip()

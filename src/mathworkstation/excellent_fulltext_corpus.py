from __future__ import annotations

import re
from collections import Counter
from statistics import median
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .io_utils import now_iso
from .same_problem_benchmark import _METHOD_PATTERNS, _extract_abstract, _extract_references, profile_full_text


class FullTextDeepProfile(BaseModel):
    """Copyright-safe derived profile of one excellent full-text paper."""

    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    paper_id: str
    year: int
    competition: str
    problem: str
    award: str
    page_count: int
    language: str
    question_types: list[str] = Field(default_factory=list)
    model_sequence: list[str] = Field(default_factory=list)
    model_selection_rationales: list[str] = Field(default_factory=list)
    model_transition_patterns: list[str] = Field(default_factory=list)
    validation_types: list[str] = Field(default_factory=list)
    figure_purposes: dict[str, int] = Field(default_factory=dict)
    innovation_patterns: list[str] = Field(default_factory=list)
    abstract_structure: dict[str, Any] = Field(default_factory=dict)
    failure_patterns: list[str] = Field(default_factory=list)
    structural_profile: dict[str, Any] = Field(default_factory=dict)
    extraction_policy: str = "derived_signals_only_no_raw_reference_text"


class FullTextDeepCorpusProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    corpus_id: str
    competition: str
    problem: str
    year: int
    paper_count: int
    paper_ids: list[str]
    prevalence: dict[str, float]
    figure_purpose_prevalence: dict[str, float]
    median_abstract_tokens: float
    median_abstract_numeric_tokens: float
    median_abstract_method_count: float
    median_model_sequence_length: float
    median_figure_mentions: float
    median_table_mentions: float
    extraction_note: str
    generated_at: str


_QUESTION_TYPE_PATTERNS: dict[str, re.Pattern[str]] = {
    "mechanistic_modeling": re.compile(r"机理模型|物理模型|mechanistic|physical model|governing equation|热传导|光学效率|几何模型", re.I),
    "optimization": re.compile(r"优化|最优|最大化|最小化|optimization|maximi[sz]|minimi[sz]|objective function", re.I),
    "scheduling": re.compile(r"调度|scheduling|dispatch", re.I),
    "forecasting": re.compile(r"预测|forecast|prediction|未来(?:一周|两年|\d+年)", re.I),
    "statistical_analysis": re.compile(r"相关分析|分布规律|回归|聚类|统计分析|数据挖掘|correlation|regression|clustering|distribution|data mining", re.I),
    "classification_or_scoring": re.compile(r"分类|评级|评分|评价体系|会员画像|会员价值|购买力模型|classification|rating|scoring system|member profile|member value", re.I),
    "resource_allocation": re.compile(r"资源分配|额度分配|补货|配额|allocation|replenishment", re.I),
    "simulation": re.compile(r"仿真|模拟|monte[- ]?carlo|simulation", re.I),
    "uncertainty_or_stochastic": re.compile(r"不确定|随机|概率|故障率|uncertain|stochastic|probabilistic|fault", re.I),
    "spatial_or_layout_design": re.compile(r"布局|位置设计|镜场|路径|测线|layout|spatial|route design", re.I),
    "decision_strategy": re.compile(r"决策|策略|方案|decision|strategy|policy", re.I),
}

_SELECTION_RATIONALE_PATTERNS: dict[str, re.Pattern[str]] = {
    "physical_or_domain_mechanism": re.compile(r"机理|物理规律|光学|热传导|几何关系|domain mechanism|physical law", re.I),
    "data_characteristics": re.compile(r"数据特征|数据特点|时效性|季节性|周期性|非线性|相关性|data characteristics|seasonal|nonlinear", re.I),
    "constraint_structure": re.compile(r"约束条件|离散|整数|0\s*[-—]?\s*1|可行域|constraint|integer|binary", re.I),
    "accuracy_or_fit": re.compile(r"提高.*(?:精度|准确)|拟合.*(?:更好|较好)|误差.*(?:小|降低)|accuracy|better fit|reduce.*error", re.I),
    "computational_efficiency": re.compile(r"降低.*(?:计算量|复杂度|维度)|提高.*(?:计算效率|求解效率)|解空间|computational|complexity|search space", re.I),
    "robustness_or_uncertainty": re.compile(r"稳健|鲁棒|不确定|随机|robust|uncertain|stochastic", re.I),
    "interpretability_or_operability": re.compile(r"易于理解|可解释|直观|可操作|便于实施|interpretable|practical|implement", re.I),
}

_TRANSITION_PATTERNS: dict[str, re.Pattern[str]] = {
    "staged_question_progression": re.compile(r"针对问题[一二三四五六七八九十\d]+|for question\s+\d+", re.I),
    "refine_previous_model": re.compile(r"在(?:问题|模型|上述|前述).{0,60}基础上|基于(?:问题|模型|上述|前述).{0,60}(?:改进|进一步|扩展)|based on the previous|building on", re.I | re.S),
    "hybrid_or_combined_model": re.compile(r"组合模型|混合模型|结合.{0,40}(?:模型|算法)|hybrid|combine.{0,40}(?:model|method)", re.I | re.S),
    "switch_due_to_limitation": re.compile(r"(?:由于|鉴于).{0,80}(?:不足|局限|不适用|误差|复杂).{0,80}(?:采用|改用|引入)|because.{0,80}(?:limitation|poor|error).{0,80}(?:use|adopt)", re.I | re.S),
    "scenario_branching": re.compile(r"分情形|不同情形|不同场景|情况[一二三123]|scenario|case\s+\d+", re.I),
    "coarse_to_fine": re.compile(r"先.{0,80}再.{0,80}(?:优化|细化|求解)|粗略.{0,40}精细|coarse.{0,80}fine", re.I | re.S),
}

_VALIDATION_DEEP_PATTERNS: dict[str, re.Pattern[str]] = {
    "error_metrics": re.compile(r"RMSE|MSE|MAE|相对误差|绝对误差|均方误差|拟合优度|误差分析|error metric|relative error", re.I),
    "sensitivity_or_robustness": re.compile(r"灵敏度分析|敏感性分析|稳健性分析|扰动|sensitivity|robustness|stress test", re.I),
    "model_comparison": re.compile(r"模型.{0,30}(?:比较|对比)|(?:比较|对比).{0,30}模型|method comparison|compare.{0,30}model", re.I | re.S),
    "simulation_check": re.compile(r"仿真.{0,30}(?:验证|检验|测试)|模拟.{0,30}(?:验证|检验)|simulation.{0,30}(?:validation|test|check)", re.I | re.S),
    "external_or_real_data_check": re.compile(r"实际数据.{0,30}(?:验证|检验)|真实数据.{0,30}(?:验证|检验)|历史数据.{0,30}(?:验证|回测)|real data.{0,30}(?:validation|test)", re.I | re.S),
    "cross_validation_or_holdout": re.compile(r"交叉验证|训练集|测试集|验证集|留出法|cross[- ]?validation|holdout|test set", re.I),
    "parameter_search": re.compile(r"参数寻优|参数优化|参数标定|网格搜索|三分查找|遗传算法|模拟退火|粒子群|parameter search|grid search|tuning", re.I),
    "constraint_feasibility_check": re.compile(r"满足.{0,40}约束|可行性.{0,30}(?:检验|验证)|constraint.{0,30}(?:satisfied|feasible)|feasibility check", re.I | re.S),
    "uncertainty_interval": re.compile(r"置信区间|预测区间|概率分布|后验分布|confidence interval|prediction interval|posterior", re.I),
}

_FIGURE_PURPOSE_PATTERNS: dict[str, re.Pattern[str]] = {
    "workflow_or_framework": re.compile(r"流程|框架|技术路线|研究路线|workflow|framework|flowchart", re.I),
    "data_distribution": re.compile(r"分布|散点|箱线|直方|distribution|scatter|histogram|boxplot", re.I),
    "time_series_or_trend": re.compile(r"趋势|变化曲线|时间序列|随时间|trend|time series", re.I),
    "physical_or_geometric_mechanism": re.compile(r"示意图|结构图|几何|光路|反射|热传导|mechanism|geometry|schematic", re.I),
    "spatial_layout_or_route": re.compile(r"布局|位置|路径|路线|镜场|layout|route|spatial", re.I),
    "optimization_or_convergence": re.compile(r"收敛|适应度|目标函数|优化过程|参数寻优|convergence|fitness|objective", re.I),
    "result_comparison": re.compile(r"对比|比较|误差|comparison|versus|error", re.I),
    "decision_or_schedule": re.compile(r"调度|策略|方案|补货|定价|decision|schedule|strategy", re.I),
    "sensitivity_or_uncertainty": re.compile(r"敏感|灵敏|不确定|概率|sensitivity|uncertainty", re.I),
}

_INNOVATION_PATTERNS: dict[str, re.Pattern[str]] = {
    "domain_specific_construct": re.compile(r"构建.{0,50}(?:指标|指数|画像|评价体系)|定义.{0,40}(?:指标|指数)|custom (?:index|metric|profile)", re.I | re.S),
    "mechanistic_model": re.compile(r"机理模型|从机理.{0,30}建模|mechanistic model|physics-informed", re.I),
    "hybrid_model": re.compile(r"混合模型|组合模型|融合模型|hybrid model|ensemble", re.I),
    "algorithmic_improvement": re.compile(r"改进.{0,40}(?:算法|模型|方法)|优化.{0,30}算法|improved? (?:algorithm|model|method)", re.I | re.S),
    "adaptive_or_dynamic_strategy": re.compile(r"动态.{0,30}(?:策略|调度|决策|调整)|自适应|滚动优化|adaptive|dynamic strategy|rolling optimization", re.I | re.S),
    "constraint_aware_optimization": re.compile(r"以.{0,60}为目标函数.{0,100}约束|在.{0,50}约束.{0,50}(?:最大|最小|优化)|subject to.{0,80}(?:maximi|minimi)", re.I | re.S),
    "uncertainty_aware_strategy": re.compile(r"考虑.{0,50}(?:不确定|随机|故障|概率)|预案集|robust|stochastic|uncertainty-aware", re.I | re.S),
}

_FAILURE_PATTERNS: dict[str, re.Pattern[str]] = {
    "data_limitation": re.compile(r"数据.{0,30}(?:不足|缺失|有限|误差|噪声)|样本.{0,20}(?:少|不足)|limited data|missing data|data noise", re.I | re.S),
    "simplifying_assumption": re.compile(r"假设.{0,60}(?:理想|简化|忽略)|忽略.{0,50}(?:因素|影响)|simplif(?:y|ying) assumption|ignore.{0,40}(?:factor|effect)", re.I | re.S),
    "computational_cost": re.compile(r"计算量.{0,20}(?:大|高)|复杂度.{0,20}(?:高|大)|耗时|运行时间.{0,20}(?:长|高)|computational cost|time consuming", re.I | re.S),
    "generalization_limit": re.compile(r"普适性.{0,30}(?:不足|有限)|推广.{0,30}(?:有限|困难)|适用范围.{0,20}(?:有限|局限)|generaliz|limited applicability", re.I | re.S),
    "unmodeled_uncertainty": re.compile(r"(?:未考虑|忽略(?:了)?).{0,50}(?:随机|不确定|故障|波动|扰动)|不确定性.{0,20}(?:未|没有).{0,20}考虑|uncertainty.{0,30}not considered", re.I | re.S),
    "parameter_subjectivity": re.compile(r"主观.{0,30}(?:权重|参数|因素)|权重.{0,30}主观|subjective.{0,30}(?:weight|parameter)", re.I | re.S),
    "accuracy_limit": re.compile(r"精度.{0,20}(?:不高|有限|不足)|误差.{0,20}(?:较大|偏大)|accuracy.{0,20}(?:limited|low)|large error", re.I | re.S),
}


def deep_profile_full_text(
    text: str,
    *,
    paper_id: str,
    year: int,
    competition: str,
    problem: str,
    page_count: int,
    award: str,
) -> FullTextDeepProfile:
    body = _main_body(text)
    references = _extract_references(text)
    structural_text = body + ("\nReferences\n" + references if references else "")
    base = profile_full_text(
        structural_text,
        paper_id=paper_id,
        year=year,
        problem=problem,
        page_count=page_count,
        award=award,
    )
    language = _language(body)
    sequence = _methods_in_order(body)
    captions = _figure_captions(body)
    figure_purposes = Counter(_classify_caption(value) for value in captions)
    figure_purposes.pop("other", None)
    abstract = _extract_abstract_local(body)
    abstract_methods = _methods_in_order(abstract)
    return FullTextDeepProfile(
        paper_id=paper_id,
        year=year,
        competition=competition,
        problem=problem,
        award=award,
        page_count=page_count,
        language=language,
        question_types=_hits(body, _QUESTION_TYPE_PATTERNS),
        model_sequence=sequence,
        model_selection_rationales=_hits(body, _SELECTION_RATIONALE_PATTERNS),
        model_transition_patterns=_hits(body, _TRANSITION_PATTERNS),
        validation_types=_hits(body, _VALIDATION_DEEP_PATTERNS),
        figure_purposes=dict(sorted(figure_purposes.items())),
        innovation_patterns=_hits(body, _INNOVATION_PATTERNS),
        abstract_structure={
            "token_count": base.abstract_word_count,
            "numeric_token_count": base.abstract_numeric_tokens,
            "method_count": len(abstract_methods),
            "per_question_marker_count": len(
                re.findall(r"针对问题[一二三四五六七八九十\d]+|for question\s+\d+", abstract, flags=re.I)
            ),
            "has_quantified_results": base.abstract_numeric_tokens > 0,
            "has_validation_language": bool(
                re.search(r"验证|检验|误差|敏感|稳健|validation|error|sensitivity|robust", abstract, flags=re.I)
            ),
            "has_concluding_language": bool(
                re.search(r"最后|综上|结果表明|最终|finally|overall|we conclude", abstract, flags=re.I)
            ),
        },
        failure_patterns=_hits(body, _FAILURE_PATTERNS),
        structural_profile={
            "structure_signals": base.structure_signals,
            "domain_signals": base.domain_signals,
            "validation_signals": base.validation_signals,
            "figure_mentions": base.figure_mentions,
            "table_mentions": base.table_mentions,
            "reference_entries": base.reference_entries,
            "has_workflow_figure": base.has_workflow_figure,
        },
    )


def build_deep_corpus_profile(
    profiles: list[FullTextDeepProfile],
    *,
    corpus_id: str,
    extraction_note: str,
) -> FullTextDeepCorpusProfile:
    if len(profiles) < 3:
        raise ValueError("DEEP_FULLTEXT_CORPUS_REQUIRES_AT_LEAST_3_PAPERS")
    competitions = {item.competition for item in profiles}
    problems = {item.problem for item in profiles}
    years = {item.year for item in profiles}
    if len(competitions) != 1 or len(problems) != 1 or len(years) != 1:
        raise ValueError("DEEP_FULLTEXT_CORPUS_MUST_SHARE_COMPETITION_PROBLEM_YEAR")

    prevalence: dict[str, float] = {}
    list_fields = (
        "question_types",
        "model_selection_rationales",
        "model_transition_patterns",
        "validation_types",
        "innovation_patterns",
        "failure_patterns",
    )
    for field in list_fields:
        values = sorted({value for item in profiles for value in getattr(item, field)})
        for value in values:
            prevalence[f"{field}.{value}"] = round(
                sum(value in getattr(item, field) for item in profiles) / len(profiles), 6
            )

    abstract_flags = (
        "has_quantified_results",
        "has_validation_language",
        "has_concluding_language",
    )
    for flag in abstract_flags:
        prevalence[f"abstract_structure.{flag}"] = round(
            sum(bool(item.abstract_structure.get(flag)) for item in profiles) / len(profiles), 6
        )

    purpose_names = sorted({name for item in profiles for name in item.figure_purposes})
    purpose_prevalence = {
        name: round(sum(item.figure_purposes.get(name, 0) > 0 for item in profiles) / len(profiles), 6)
        for name in purpose_names
    }
    return FullTextDeepCorpusProfile(
        corpus_id=corpus_id,
        competition=next(iter(competitions)),
        problem=next(iter(problems)),
        year=next(iter(years)),
        paper_count=len(profiles),
        paper_ids=[item.paper_id for item in profiles],
        prevalence=dict(sorted(prevalence.items())),
        figure_purpose_prevalence=dict(sorted(purpose_prevalence.items())),
        median_abstract_tokens=float(median(int(item.abstract_structure["token_count"]) for item in profiles)),
        median_abstract_numeric_tokens=float(median(int(item.abstract_structure["numeric_token_count"]) for item in profiles)),
        median_abstract_method_count=float(median(int(item.abstract_structure["method_count"]) for item in profiles)),
        median_model_sequence_length=float(median(len(item.model_sequence) for item in profiles)),
        median_figure_mentions=float(median(int(item.structural_profile["figure_mentions"]) for item in profiles)),
        median_table_mentions=float(median(int(item.structural_profile["table_mentions"]) for item in profiles)),
        extraction_note=extraction_note,
        generated_at=now_iso(),
    )


def _main_body(text: str) -> str:
    """Exclude reference/appendix payload from research-story extraction."""

    normalized = text.replace("\r\n", "\n")
    stops = []
    for pattern in (
        r"(?im)^\s*(?:references|参考文献)\s*$",
        r"(?im)^\s*(?:[A-Z一二三四五六七八九十]+\s*)?(?:appendix|附录|附件清单)(?:\s*[:：].*)?\s*$",
    ):
        match = re.search(pattern, normalized)
        if match:
            stops.append(match.start())
    return normalized[: min(stops)] if stops else normalized


def _hits(text: str, patterns: dict[str, re.Pattern[str]]) -> list[str]:
    return [name for name, pattern in patterns.items() if pattern.search(text)]


def _methods_in_order(text: str) -> list[str]:
    found: list[tuple[int, str]] = []
    for name, pattern in _METHOD_PATTERNS:
        match = pattern.search(text)
        if match:
            found.append((match.start(), name))
    return [name for _position, name in sorted(found)]


def _language(text: str) -> str:
    chinese = len(re.findall(r"[\u4e00-\u9fff]", text))
    english = len(re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", text))
    if chinese > english * 2:
        return "zh"
    if english > chinese * 2:
        return "en"
    return "mixed"


def _figure_captions(text: str) -> list[str]:
    captions: list[str] = []
    for line in text.replace("\r\n", "\n").splitlines():
        value = " ".join(line.split())
        if re.match(r"(?i)^(?:图\s*\d+|figure\s+\d+)", value):
            captions.append(value[:180])
    return captions


def _classify_caption(caption: str) -> str:
    for name, pattern in _FIGURE_PURPOSE_PATTERNS.items():
        if pattern.search(caption):
            return name
    return "other"


def _extract_abstract_local(text: str) -> str:
    """Reuse the shared bilingual/MCM Summary-Sheet abstract parser."""

    return _extract_abstract(text)

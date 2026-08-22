from __future__ import annotations

import json
import math
import re
from pathlib import Path
from statistics import median
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .io_utils import atomic_write_json, now_iso, read_json


GapType = Literal["DOCUMENT", "RESEARCH", "EXTERNAL"]
GapSeverity = Literal["REVIEW", "BLOCK"]


_METHOD_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("ARIMA", re.compile(r"\barima\b", re.I)),
    ("BP neural network", re.compile(r"\b(?:bp|back[- ]?propagation)\s+(?:neural\s+)?network\b", re.I)),
    ("LSTM", re.compile(r"\blstm\b", re.I)),
    ("Prophet", re.compile(r"\bprophet\b", re.I)),
    ("SIR/differential equation", re.compile(r"\bSIR\b|differential equation|epidemiolog", re.I)),
    ("Gaussian regression", re.compile(r"gaussian regression", re.I)),
    ("Poisson process", re.compile(r"poisson process", re.I)),
    ("KNN", re.compile(r"\bK[- ]?(?:nearest\s+neighbors?|NN)\b|nearest neighbor", re.I)),
    ("GMM", re.compile(r"\bGMM\b|gaussian mixture", re.I)),
    ("K-means", re.compile(r"\bK[- ]?means(?:\+\+)?\b", re.I)),
    ("Random Forest", re.compile(r"random forest", re.I)),
    ("Lasso", re.compile(r"\blasso\b", re.I)),
    ("Bayesian/MCMC", re.compile(r"bayesian|markov chain monte[- ]?carlo|\bMCMC\b", re.I)),
    ("Bootstrap", re.compile(r"bootstrap", re.I)),
    ("Apriori", re.compile(r"apriori|association rule", re.I)),
    ("Linear regression", re.compile(r"(?:multiple |multi[- ]?objective |ordinary )?linear regression", re.I)),
    ("Ridge regression", re.compile(r"\bridge(?: regression)?\b|multi[- ]?output ridge|standardized ridge", re.I)),
    ("Logistic regression", re.compile(r"logistic regression|multiclass logistic", re.I)),
    ("Spearman analysis", re.compile(r"spearman", re.I)),
    ("Partial correlation", re.compile(r"partial correlation", re.I)),
    ("Genetic algorithm", re.compile(r"genetic algorithm", re.I)),
    ("Nelder-Mead", re.compile(r"nelder[- ]?mead", re.I)),
    ("Gradient descent", re.compile(r"gradient descent", re.I)),
    ("Player simulation", re.compile(r"player simulation|simulate(?:d|s|ing)? (?:the )?(?:strateg|behavio|player)|simulation algorithm", re.I)),
    ("Beta distribution", re.compile(r"beta distribution", re.I)),
    ("Entropy construct", re.compile(r"subset entropy|negentropy|entropy measure", re.I)),
    ("Gaussian process regression", re.compile(r"gaussian process regression|\bGPR\b", re.I)),
    ("ARMA", re.compile(r"\bARMA\b|auto[- ]?regressive.*moving average", re.I)),
    ("VAR", re.compile(r"vector autoregression|\bVAR model\b", re.I)),
    ("PCA", re.compile(r"principal component analysis|principle component analysis|\bPCA\b", re.I)),
    ("TOPSIS", re.compile(r"\bTOPSIS\b", re.I)),
    ("PROMETHEE", re.compile(r"\bPROMETHEE\b", re.I)),
    ("Entropy weighting", re.compile(r"entropy weight(?:ing)? method|entropy[- ]weighted", re.I)),
    ("Gray relational analysis", re.compile(r"gr[ae]y relational analysis", re.I)),
    ("New Keynesian/IS-LM", re.compile(r"new keynesian|\bIS[- ]?LM\b", re.I)),
    ("Game theory", re.compile(r"game theory", re.I)),
    ("Linear programming", re.compile(r"linear programming|simplex method", re.I)),
    ("Multidimensional scaling", re.compile(r"multi(?:ple)? dimensional scaling|\bMDS\b|多维尺度", re.I)),
    ("Heat equation/PDE", re.compile(r"heat (?:conduction|transfer) equation|partial differential equation|\bPDE\b|热传导方程|导热方程|偏微分方程", re.I)),
    ("Finite difference", re.compile(r"finite difference|有限差分", re.I)),
    ("Newton cooling", re.compile(r"newton(?:'s)? law of cooling|牛顿冷却", re.I)),
    ("Dynamic programming", re.compile(r"dynamic programming|动态规划", re.I)),
    ("0-1/integer programming", re.compile(r"0\s*[-—]?\s*1\s*(?:integer )?programming|integer programming|binary programming|0\s*[-—]?\s*1\s*规划|整数规划", re.I)),
    ("Nonlinear programming", re.compile(r"nonlinear programming|非线性规划", re.I)),
    ("Multiobjective optimization", re.compile(r"multi[- ]?objective optimization|多目标(?:规划|优化)", re.I)),
    ("Simulated annealing", re.compile(r"simulated annealing|模拟退火", re.I)),
    ("Particle swarm optimization", re.compile(r"particle swarm|\bPSO\b|粒子群", re.I)),
    ("Monte Carlo", re.compile(r"monte[- ]?carlo|蒙特卡洛", re.I)),
    ("Markov model", re.compile(r"markov|马尔可夫", re.I)),
    ("Queueing model", re.compile(r"queueing|queuing|排队论|排队模型", re.I)),
    ("Support vector machine", re.compile(r"support vector (?:machine|regression)|\bSVM\b|\bSVR\b|支持向量", re.I)),
    ("Decision tree", re.compile(r"decision tree|决策树", re.I)),
    ("XGBoost", re.compile(r"\bxgboost\b|极端梯度提升", re.I)),
    ("AHP", re.compile(r"analytic hierarchy process|\bAHP\b|层次分析法", re.I)),
    ("Fuzzy comprehensive evaluation", re.compile(r"fuzzy comprehensive evaluation|模糊综合评价", re.I)),
    ("Grey prediction", re.compile(r"grey prediction|gray prediction|GM\s*\(?1\s*,\s*1\)?|灰色预测", re.I)),
    ("Clustering", re.compile(r"cluster(?:ing)?|聚类分析|聚类模型", re.I)),
    ("Neural network", re.compile(r"neural network|神经网络", re.I)),
    ("Time series", re.compile(r"time[- ]?series|时间序列", re.I)),
    ("Fitting/least squares", re.compile(r"least squares?|curve fitting|最小二乘|曲线拟合", re.I)),
    ("Shortest path", re.compile(r"shortest path|最短路径|最短路", re.I)),
    ("Fermat point/geometric construction", re.compile(r"Fermat point|费尔马点|平面镜成像|光的反射|光的折射|反射折射", re.I)),
    ("RFM-family member value model", re.compile(r"\bRFM(?:T|S)?\b|recency[- ]frequency[- ]monetary|FMS\s*(?:购买力|purchase power)|会员.{0,30}(?:RFM|RFMS|RFMT)", re.I)),
    ("Member lifecycle state model", re.compile(r"会员.{0,40}(?:生命周期|消费状态|活跃状态)|(?:生命周期|时间窗口).{0,40}(?:会员|活跃|非活跃)|RF\s*(?:消费状态|状态评价)", re.I | re.S)),
)

_STRUCTURE_PATTERNS: dict[str, re.Pattern[str]] = {
    "literature_review": re.compile(r"(?im)^\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\.?)?\s*(?:literature review|文献综述|研究现状|国内外研究现状)\b"),
    "data_preprocessing": re.compile(r"(?im)^\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\.?)?\s*(?:(?:data (?:pre[- ]?processing|cleaning|processing)|preparation for modeling)|数据预处理|数据处理|数据清洗|数据整理)\b"),
    "assumptions": re.compile(r"(?im)^\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\.?)?\s*(?:(?:model )?assumptions?(?: and justifications?)?|模型假设|问题假设|基本假设)\b"),
    "notations": re.compile(r"(?im)^\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\.?)?\s*(?:notations?|符号说明|符号约定|符号表|变量说明)\b"),
    "problem_analysis": re.compile(r"(?im)^\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\.?)?\s*(?:problem analysis|问题分析)\b"),
    "model_establishment": re.compile(r"(?im)^\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\.?)?\s*(?:(?:establishment|building|construction) of (?:the )?model|模型(?:的)?(?:建立|构建)|建立模型|模型建立与求解)\b"),
    "model_solution": re.compile(r"(?im)^\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\.?)?\s*(?:(?:solving|solution) (?:of )?(?:the )?model|模型(?:的)?求解|求解模型|模型建立与求解)\b"),
    "uncertainty": re.compile(r"(?im)^\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\.?)?\s*(?:uncertainty|predict confidence|error analysis|不确定性(?:分析)?|误差分析)\b|confidence interval|prediction interval|置信区间|预测区间", re.I),
    "sensitivity": re.compile(r"(?im)^\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\.?)?\s*(?:sensitivity analysis|灵敏度分析|敏感性分析|稳健性分析)\b|sensitivity of", re.I),
    "strengths_weaknesses": re.compile(r"(?im)^\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\.?)?\s*(?:(?:model evaluation:?[\s-]*)?(?:strengths? and weaknesses?|strengths?, weaknesses?, and robustness|model evaluation(?: and improvement| and further discussion)?)|模型(?:的)?(?:优缺点|评价与推广|评价|改进)|优点与缺点|模型优缺点)\b"),
    "conclusion": re.compile(r"(?im)^\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\.?)?\s*(?:conclusions?|结论|总结|模型总结)\b"),
    "letter": re.compile(r"(?im)^\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\.?)?\s*letter(?: to the puzzle editor.*)?\b|dear (?:puzzle )?editor", re.I),
    "memo": re.compile(r"(?im)^\s*(?:#+\s*)?(?:\d+(?:\.\d+)*\.?)?\s*memo\b|^\s*to:\s*(?:the )?(?:group of )?governors\b|governors['’]? memo", re.I),
}

_DOMAIN_PATTERNS: dict[str, re.Pattern[str]] = {
    "word_feature_engineering": re.compile(r"word (?:attribute|feature)|repeated letters?|vowels?|consonants?|letter frequency|word frequency|commonness|familiarity", re.I),
    "wordle_mechanics": re.compile(r"(?is)(?=.*\bwordle\b)(?:.*(?:green tile|yellow tile|gray tile|grey tile|guess(?:es|ing)?|hard mode|six tries|solution word))", re.I),
    "custom_domain_construct": re.compile(
        r"subset entropy|negentropy|regularity|purity|word internal distance|degree of confusion|degree of association|"
        r"positional[_ ]letter[_ ]surprisal|letter[_ ]transition[_ ]surprisal|lexical[_ ]surprisal|transition[_ ]surprisal",
        re.I,
    ),
    "player_or_popularity_mechanism": re.compile(r"loyal players?|player behavior|player structure|life ?cycle|epidemiolog|viral spread|popularity relaxation|popularity lifecycle|SIR model", re.I),
    "external_word_resource": re.compile(r"wordbank|word bank|stanford graphbase|word frequency|frequency in english|dictionary|corpus", re.I),
    "distribution_constraint": re.compile(r"sum to 100|spherical coordinate|simplex|compositional|percentage distribution", re.I),
    "energy_profile_construct": re.compile(r"energy profile|comprehensive utilization performance|\bCUP\b|\bEROI\b|3E principle", re.I),
    "energy_multi_criteria_evaluation": re.compile(r"TOPSIS|PROMETHEE|principal component analysis|principle component analysis|\bPCA\b|entropy weight|evaluation system|overall score|comprehensive utilization performance|\bEROI\b", re.I),
    "energy_long_horizon_forecast": re.compile(r"energy profile.*(?:2025|2050)|(?:2025|2050).*energy profile|predict(?:ion|ing)?.*(?:2025|2050)", re.I),
    "energy_compact_targets_actions": re.compile(r"energy compact.*(?:target|goal|action)|(?:target|goal|action).*energy compact|renewable energy usage targets?|three actions", re.I),
    "reflow_mechanistic_thermal_model": re.compile(r"回焊炉|炉温曲线|热传导方程|导热方程|机理模型|reflow furnace|temperature profile", re.I),
    "reflow_process_constraints": re.compile(r"制程界限|峰值温度|温度上升斜率|温度下降斜率|超过\s*217|过炉速度|传送带.*速度", re.I),
    "reflow_curve_optimization": re.compile(r"炉温曲线.{0,120}(?:优化|最优|面积|对称)|(?:优化|最优).{0,120}炉温曲线|超过\s*217.{0,120}面积", re.I | re.S),
    "rgv_cnc_scheduling": re.compile(r"\bRGV\b|\bCNC\b|动态调度|调度策略|调度模型", re.I),
    "rgv_fault_robustness": re.compile(r"(?is)(?=.*(?:\bRGV\b|\bCNC\b))(?=.*(?:故障|故障率|随机故障|fault|repair))", re.I),
    "credit_risk_quantification": re.compile(r"信贷风险|信用风险|信誉评级|风险量化|risk assessment|credit risk", re.I),
    "credit_strategy_allocation": re.compile(r"信贷策略|贷款额度|贷款利率|信贷总额|客户流失率|贷款策略|credit allocation|lending strategy", re.I),
    "credit_shock_adjustment": re.compile(r"(?is)(?=.*(?:信贷|贷款|credit))(?=.*(?:突发因素|新冠|疫情|行业.{0,80}影响|信贷调整策略|shock|pandemic))", re.I),
    "heliostat_optical_efficiency_model": re.compile(r"(?is)(?=.*定日镜)(?=.*(?:光学效率|余弦效率|阴影遮挡效率|截断效率|DNI|输出热功率))", re.I),
    "heliostat_layout_optimization": re.compile(r"(?is)(?=.*定日镜)(?=.*(?:吸收塔|镜场))(?=.*(?:优化|最优|额定功率|单位镜面面积))", re.I),
    "vegetable_sales_relationship": re.compile(r"(?is)(?=.*蔬菜)(?=.*(?:销售量|销量))(?=.*(?:相关|分布规律|聚类))", re.I),
    "vegetable_demand_forecast": re.compile(r"(?is)(?=.*蔬菜)(?=.*(?:未来一周|日销售量|销量预测|需求预测|时间序列))", re.I),
    "vegetable_pricing_replenishment_optimization": re.compile(r"(?is)(?=.*蔬菜)(?=.*(?:补货|订购量))(?=.*(?:定价|价格))(?=.*(?:收益最大|利润最大|最大收益|优化))", re.I),
    "vegetable_additional_data": re.compile(r"(?is)(?=.*蔬菜)(?=.*(?:采集|补充|引入).{0,80}(?:数据|信息))", re.I),
    "rgv_single_dual_process": re.compile(r"(?is)(?=.*(?:\bRGV\b|\bCNC\b))(?=.*(?:单工序|双工序))", re.I),
    "rgv_output_efficiency_objective": re.compile(r"(?is)(?=.*(?:\bRGV\b|\bCNC\b))(?=.*(?:成料|产量|工作时长|加工效率))", re.I),
}

_VALIDATION_PATTERNS: dict[str, re.Pattern[str]] = {
    "cross_validation_or_holdout": re.compile(r"cross[- ]?validation|test set|training set|holdout|retrodict|交叉验证|训练集|测试集|验证集|留出法", re.I),
    "uncertainty_interval": re.compile(r"confidence interval|prediction interval|posterior distribution|uncertaint|置信区间|预测区间|后验分布|不确定性", re.I),
    "bootstrap": re.compile(r"bootstrap|自助法|自举法", re.I),
    "sensitivity": re.compile(r"sensitivity analysis|sensitivity of|added noise|parameter changes?|stress[- ]?test(?:ed|ing)?|holdout fractions?|灵敏度分析|敏感性分析|稳健性分析|扰动分析", re.I),
    "error_metrics": re.compile(r"\bRMSE\b|\bMSE\b|\bMAE\b|\bR\^?2\b|accuracy|absolute error|coefficient of variation|\bCOV\b|均方误差|均方根误差|平均绝对误差|绝对误差|相对误差|准确率|拟合优度", re.I),
    "parameter_tuning": re.compile(r"parameter tuning|select(?:ed|ing)? (?:the )?(?:optimal|best) .*?(?:parameter|k value|model)|grid search|genetic algorithm|gradient descent|参数优化|参数寻优|参数标定|网格搜索|遗传算法|梯度下降", re.I),
}


class FullTextPaperProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    paper_id: str
    year: int
    problem: str
    award: str = "O"
    page_count: int
    abstract_word_count: int
    abstract_numeric_tokens: int
    abstract_method_count: int
    detected_methods: list[str] = Field(default_factory=list)
    structure_signals: dict[str, bool] = Field(default_factory=dict)
    domain_signals: dict[str, bool] = Field(default_factory=dict)
    validation_signals: dict[str, bool] = Field(default_factory=dict)
    figure_mentions: int = 0
    table_mentions: int = 0
    reference_entries: int = 0
    has_workflow_figure: bool = False
    source_kind: str = "full_text_pdf"


class SameProblemCorpusProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    corpus_id: str
    year: int
    problem: str
    award: str
    paper_count: int
    paper_ids: list[str]
    prevalence: dict[str, float]
    median_page_count: float
    median_abstract_word_count: float
    median_abstract_numeric_tokens: float
    median_abstract_method_count: float
    median_method_count: float
    median_figure_mentions: float
    median_table_mentions: float
    median_reference_entries: float
    method_prevalence: dict[str, float]
    extraction_note: str
    generated_at: str


class SameProblemGap(BaseModel):
    model_config = ConfigDict(extra="forbid")

    defect_type: GapType
    severity: GapSeverity
    dimension: str
    message: str
    repair_phase: str
    subproblem_ids: list[str] = Field(default_factory=list)
    benchmark_prevalence: float | None = None
    benchmark_evidence: str = ""


class SameProblemAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str | None = None
    corpus_id: str
    gate: Literal["PASS", "REVIEW", "BLOCK"]
    gaps: list[SameProblemGap]
    document_gaps: int
    research_gaps: int
    checked_at: str


def profile_full_text(
    text: str,
    *,
    paper_id: str,
    year: int,
    problem: str,
    page_count: int,
    award: str = "O",
) -> FullTextPaperProfile:
    cleaned = _normalize_text(text)
    abstract = _extract_abstract(cleaned)
    methods = [name for name, pattern in _METHOD_PATTERNS if pattern.search(cleaned)]
    structure = {name: bool(pattern.search(cleaned)) for name, pattern in _STRUCTURE_PATTERNS.items()}
    domain = {name: bool(pattern.search(cleaned)) for name, pattern in _DOMAIN_PATTERNS.items()}
    validation = {name: bool(pattern.search(cleaned)) for name, pattern in _VALIDATION_PATTERNS.items()}
    figure_numbers = {
        int(value)
        for value in re.findall(r"(?i)(?:\bfigure\s+|图\s*)(\d+)\b", cleaned)
    }
    table_numbers = {
        int(value)
        for value in re.findall(r"(?i)(?:\btable\s+|表\s*)(\d+)\b", cleaned)
    }
    references = _extract_references(cleaned)
    ref_entries = len(re.findall(r"(?m)^\s*(?:\[\d+\]|\d+[.)、])\s*\S.+$", references))
    if ref_entries == 0 and references:
        # MCM papers often use compact bibliography formatting that pdftotext
        # does not preserve as one entry per line. Citation-number coverage is a
        # conservative lower-bound proxy and is used only for corpus medians.
        ref_entries = len({int(value) for value in re.findall(r"\[(\d+)\]", references)})
    return FullTextPaperProfile(
        paper_id=paper_id,
        year=year,
        problem=problem,
        award=award,
        page_count=int(page_count),
        abstract_word_count=_text_token_count(abstract),
        abstract_numeric_tokens=len(re.findall(r"(?<![A-Za-z])\d+(?:\.\d+)?%?", abstract)),
        abstract_method_count=sum(bool(pattern.search(abstract)) for _name, pattern in _METHOD_PATTERNS),
        detected_methods=methods,
        structure_signals=structure,
        domain_signals=domain,
        validation_signals=validation,
        figure_mentions=len(figure_numbers),
        table_mentions=len(table_numbers),
        reference_entries=ref_entries,
        has_workflow_figure=bool(
            re.search(
                r"(?is)(?:figure\s+\d+[^\n]{0,100}(?:flow\s*chart|flowchart|our work|workflow|model framework)|"
                r"图\s*\d+[^\n]{0,100}(?:流程图|流程|技术路线|模型框架|研究框架)|"
                r"!\[[^\]]*(?:flow|workflow|framework)[^\]]*\])",
                cleaned,
            )
        ),
    )


def build_corpus_profile(
    profiles: list[FullTextPaperProfile],
    *,
    corpus_id: str,
    extraction_note: str,
) -> SameProblemCorpusProfile:
    if len(profiles) < 3:
        raise ValueError("SAME_PROBLEM_CORPUS_REQUIRES_AT_LEAST_3_PAPERS")
    years = {item.year for item in profiles}
    problems = {item.problem for item in profiles}
    awards = {item.award for item in profiles}
    if len(years) != 1 or len(problems) != 1 or len(awards) != 1:
        raise ValueError("SAME_PROBLEM_CORPUS_MUST_SHARE_YEAR_PROBLEM_AWARD")

    boolean_keys: set[str] = {"has_workflow_figure"}
    for item in profiles:
        boolean_keys.update(f"structure.{key}" for key in item.structure_signals)
        boolean_keys.update(f"domain.{key}" for key in item.domain_signals)
        boolean_keys.update(f"validation.{key}" for key in item.validation_signals)

    prevalence: dict[str, float] = {}
    for key in sorted(boolean_keys):
        if key == "has_workflow_figure":
            hits = sum(item.has_workflow_figure for item in profiles)
        else:
            group, name = key.split(".", 1)
            hits = sum(bool(getattr(item, f"{group}_signals").get(name)) for item in profiles)
        prevalence[key] = round(hits / len(profiles), 6)

    method_names = sorted({method for item in profiles for method in item.detected_methods})
    method_prevalence = {
        method: round(sum(method in item.detected_methods for item in profiles) / len(profiles), 6)
        for method in method_names
    }
    return SameProblemCorpusProfile(
        corpus_id=corpus_id,
        year=next(iter(years)),
        problem=next(iter(problems)),
        award=next(iter(awards)),
        paper_count=len(profiles),
        paper_ids=[item.paper_id for item in profiles],
        prevalence=prevalence,
        median_page_count=float(median(item.page_count for item in profiles)),
        median_abstract_word_count=float(median(item.abstract_word_count for item in profiles)),
        median_abstract_numeric_tokens=float(median(item.abstract_numeric_tokens for item in profiles)),
        median_abstract_method_count=float(median(item.abstract_method_count for item in profiles)),
        median_method_count=float(median(len(item.detected_methods) for item in profiles)),
        median_figure_mentions=float(median(item.figure_mentions for item in profiles)),
        median_table_mentions=float(median(item.table_mentions for item in profiles)),
        median_reference_entries=float(median(item.reference_entries for item in profiles)),
        method_prevalence=method_prevalence,
        extraction_note=extraction_note,
        generated_at=now_iso(),
    )


class SameProblemBenchmarkRegistry:
    """Resolve optional same-problem full-text calibration assets by match terms.

    The registry only reads compact derived profile JSON files. Raw excellent
    PDFs remain outside the repository and are never a runtime dependency.
    """

    def __init__(self, config_dir: str | Path = "config/ref_models") -> None:
        self.config_dir = Path(config_dir)

    def resolve(self, query: str) -> tuple[SameProblemExcellentAssessor, dict[str, Any]] | None:
        lowered = query.lower()
        if not self.config_dir.is_dir():
            return None
        best: tuple[float, SameProblemExcellentAssessor, dict[str, Any]] | None = None
        for path in sorted(self.config_dir.glob("*_fulltext.json")):
            try:
                payload = read_json(path)
                terms = [str(value).strip().lower() for value in payload.get("match_terms", []) if str(value).strip()]
                corpus_payload = payload.get("corpus")
                if not terms or not isinstance(corpus_payload, dict):
                    continue
                hits = sum(term in lowered for term in terms)
                # One highly specific term (e.g. Wordle) is enough. More hits
                # win if multiple benchmark assets are ever applicable.
                if hits == 0:
                    continue
                score = hits / len(terms)
                assessor = SameProblemExcellentAssessor(SameProblemCorpusProfile.model_validate(corpus_payload))
                candidate = (score, assessor, {"path": path.as_posix(), "match_terms": terms, "hits": hits})
                if best is None or candidate[0] > best[0]:
                    best = candidate
            except (OSError, ValueError, TypeError):
                continue
        return (best[1], best[2]) if best is not None else None


class SameProblemExcellentAssessor:
    """Compare a current paper/Research State against a same-problem O-award corpus.

    The corpus is a calibration prior, not a recipe. Recurring *presentation*
    patterns become DOCUMENT reviews. Recurring modeling depth or domain-specific
    mechanisms become RESEARCH reviews and must route upstream; the writer is not
    allowed to imitate them in prose without new evidence.
    """

    def __init__(self, benchmark: SameProblemCorpusProfile, *, prevalence_threshold: float = 0.60) -> None:
        if not 0.5 <= prevalence_threshold <= 1.0:
            raise ValueError("prevalence_threshold must be in [0.5, 1.0]")
        self.benchmark = benchmark
        self.threshold = prevalence_threshold

    @classmethod
    def from_json(cls, path: str | Any, *, prevalence_threshold: float = 0.60) -> "SameProblemExcellentAssessor":
        payload = read_json(Path(path))
        corpus_payload = payload.get("corpus", payload) if isinstance(payload, dict) else payload
        return cls(
            SameProblemCorpusProfile.model_validate(corpus_payload),
            prevalence_threshold=prevalence_threshold,
        )

    def assess(
        self,
        paper_text: str,
        narrative: Any | None = None,
        *,
        case_id: str | None = None,
    ) -> SameProblemAssessment:
        current = profile_full_text(
            paper_text,
            paper_id="current-paper",
            year=self.benchmark.year,
            problem=self.benchmark.problem,
            page_count=max(1, math.ceil(len(paper_text) / 3500)),
            award="CURRENT",
        )
        gaps: list[SameProblemGap] = []

        # Presentation patterns: require recurrence across the same-problem O
        # corpus, never a single reference paper.
        gaps.extend(self._document_signal_gap(current, "structure.literature_review", "same_problem_literature_review", "The same-problem O-award corpus usually includes an explicit background/literature review that motivates the modeling choices.", "paper_introduction"))
        gaps.extend(self._document_signal_gap(current, "structure.data_preprocessing", "same_problem_data_preprocessing", "The O-award papers usually expose data cleaning/preprocessing as part of the paper narrative instead of hiding the transformed dataset behind the model section.", "paper_data"))
        gaps.extend(self._document_signal_gap(current, "has_workflow_figure", "same_problem_workflow_figure", "A workflow/model-framework figure is recurrent in the same-problem O-award papers and helps the judge see the multi-question strategy at a glance.", "paper_storyline"))
        gaps.extend(self._document_signal_gap(current, "structure.strengths_weaknesses", "same_problem_strengths_weaknesses", "The O-award corpus usually contains an explicit strengths/weaknesses or model-evaluation section; a limitations paragraph alone is a weaker competition narrative.", "paper_review"))
        if narrative is not None and any(getattr(node, "role", "") == "SYNTHESIS" for node in narrative.nodes):
            gaps.extend(self._document_signal_gap(current, "structure.letter", "same_problem_editor_letter", "A prompt-specific editor letter recurs in the same-problem O-award corpus and should be rendered as an actual letter rather than only an internal synthesis paragraph.", "paper_deliverable"))
            gaps.extend(self._document_signal_gap(current, "structure.memo", "same_problem_governors_memo", "A governors' memo recurs in the same-problem O-award corpus and should be rendered as an actual memo rather than only an internal synthesis paragraph.", "paper_deliverable"))

        if current.abstract_method_count + 1e-9 < max(2.0, self.benchmark.median_abstract_method_count * 0.65):
            gaps.append(
                SameProblemGap(
                    defect_type="DOCUMENT",
                    severity="REVIEW",
                    dimension="same_problem_abstract_method_density",
                    message=(
                        f"Current abstract exposes {current.abstract_method_count} detected method families; "
                        f"same-problem O-award median is {self.benchmark.median_abstract_method_count:.1f}. "
                        "Increase method/result specificity only from already accepted Research State."
                    ),
                    repair_phase="paper_abstract",
                    benchmark_evidence=f"median abstract method count={self.benchmark.median_abstract_method_count:.1f}",
                )
            )
        if current.abstract_numeric_tokens + 1e-9 < max(3.0, self.benchmark.median_abstract_numeric_tokens * 0.55):
            gaps.append(
                SameProblemGap(
                    defect_type="DOCUMENT",
                    severity="REVIEW",
                    dimension="same_problem_abstract_result_density",
                    message=(
                        f"Current abstract has {current.abstract_numeric_tokens} quantitative tokens versus "
                        f"same-problem O-award median {self.benchmark.median_abstract_numeric_tokens:.1f}. "
                        "Surface accepted answers/intervals/uncertainty more concretely; do not invent new values."
                    ),
                    repair_phase="paper_abstract",
                    benchmark_evidence=f"median abstract numeric tokens={self.benchmark.median_abstract_numeric_tokens:.1f}",
                )
            )

        # Research depth. These are intentionally reviews, not blocks: O-award
        # papers show several successful strategies, not one mandatory recipe.
        paper_domain = current.domain_signals
        if self._prevalent("domain.word_feature_engineering") and not paper_domain.get("word_feature_engineering"):
            gaps.append(
                self._research_gap(
                    "same_problem_word_feature_engineering",
                    "The same-problem O-award corpus consistently makes Wordle/word attributes an explicit reusable research object. The current Research State does not visibly expose a comparable feature-engineering backbone.",
                    "modeling_brain",
                    narrative,
                    families={"explanatory_inference", "distribution_forecasting", "classification", "exploratory_analysis"},
                    prevalence_key="domain.word_feature_engineering",
                )
            )
        if self._prevalent("domain.custom_domain_construct") and not paper_domain.get("custom_domain_construct"):
            gaps.append(
                self._research_gap(
                    "same_problem_custom_domain_construct",
                    "A majority of the calibration papers introduce a Wordle-specific construct or mechanism (for example a custom lexical/game feature), while the current paper remains dominated by generic solver vocabulary. Consider a domain-specific construct only if it can be derived and validated from admissible data.",
                    "modeling_brain",
                    narrative,
                    families={"explanatory_inference", "distribution_forecasting", "classification"},
                    prevalence_key="domain.custom_domain_construct",
                )
            )
        if self._prevalent("domain.player_or_popularity_mechanism") and not paper_domain.get("player_or_popularity_mechanism"):
            gaps.append(
                self._research_gap(
                    "same_problem_popularity_mechanism",
                    "Mechanistic explanations of Wordle popularity/player dynamics recur in the O-award calibration set. The current SP1 is primarily a statistical forecast; consider whether a mechanism-based alternative can explain the trajectory materially better before competition polish.",
                    "modeling_brain",
                    narrative,
                    families={"forecasting"},
                    prevalence_key="domain.player_or_popularity_mechanism",
                )
            )
        if self._prevalent("domain.energy_profile_construct") and not paper_domain.get("energy_profile_construct"):
            gaps.append(
                self._research_gap(
                    "same_problem_energy_profile_construct",
                    "The same-problem O-award corpus consistently turns the raw energy variables into an explicit, reusable state energy-profile construct. The current Research State does not visibly expose a comparable profile object.",
                    "modeling_brain",
                    narrative,
                    families={"exploratory_analysis", "ranking"},
                    prevalence_key="domain.energy_profile_construct",
                )
            )
        if self._prevalent("domain.energy_multi_criteria_evaluation") and not paper_domain.get("energy_multi_criteria_evaluation"):
            gaps.append(
                self._research_gap(
                    "same_problem_energy_evaluation_depth",
                    "Multi-criteria evaluation of the four states recurs in the O-award calibration set. The current Research State should expose explicit criteria, directions/weights, and ranking stability before claiming a best state.",
                    "modeling_brain",
                    narrative,
                    families={"ranking"},
                    prevalence_key="domain.energy_multi_criteria_evaluation",
                )
            )
        if self._prevalent("domain.energy_long_horizon_forecast") and not paper_domain.get("energy_long_horizon_forecast"):
            gaps.append(
                self._research_gap(
                    "same_problem_energy_forecast_depth",
                    "Long-horizon 2025/2050 energy-profile forecasting is a recurring research backbone in the same-problem O-award corpus, but the current paper does not visibly expose comparable state-level future forecasts.",
                    "modeling_brain",
                    narrative,
                    families={"forecasting"},
                    prevalence_key="domain.energy_long_horizon_forecast",
                )
            )
        if self._prevalent("domain.energy_compact_targets_actions") and not paper_domain.get("energy_compact_targets_actions"):
            gaps.append(
                self._research_gap(
                    "same_problem_compact_target_depth",
                    "The O-award corpus repeatedly translates prediction and evaluation into quantitative compact targets/actions. The current Research State should connect targets to accepted forecasts and explicit feasibility constraints rather than inventing policy numbers in prose.",
                    "modeling_brain",
                    narrative,
                    families={"optimization"},
                    prevalence_key="domain.energy_compact_targets_actions",
                )
            )
        if self._prevalent("validation.parameter_tuning") and not current.validation_signals.get("parameter_tuning"):
            gaps.append(
                self._research_gap(
                    "same_problem_model_selection_depth",
                    "Parameter selection/model comparison is recurrent in the same-problem O-award corpus, but the current paper does not show a comparable accepted head-to-head/tuning experiment. Run it only where the existing candidate set makes the comparison meaningful.",
                    "experiment",
                    narrative,
                    families={"forecasting", "distribution_forecasting", "classification"},
                    prevalence_key="validation.parameter_tuning",
                )
            )
        if self._prevalent("validation.uncertainty_interval") and not current.validation_signals.get("uncertainty_interval"):
            gaps.append(
                self._research_gap(
                    "same_problem_uncertainty_depth",
                    "Prediction uncertainty is recurrent in the same-problem O-award corpus, but the current paper does not expose interval/posterior uncertainty clearly enough.",
                    "validation",
                    narrative,
                    families={"forecasting", "distribution_forecasting"},
                    prevalence_key="validation.uncertainty_interval",
                )
            )
        if self._prevalent("validation.sensitivity") and not _narrative_has_sensitivity_evidence(narrative):
            gaps.append(
                self._research_gap(
                    "same_problem_sensitivity_depth",
                    "Sensitivity or stress analysis recurs in the same-problem O-award corpus, but the current paper does not expose an accepted perturbation/stability analysis. Add one only where the decision or forecast conclusion can be meaningfully stress-tested.",
                    "validation",
                    narrative,
                    families={"forecasting"},
                    prevalence_key="validation.sensitivity",
                )
            )

        # Reference richness is presentation/document depth, not permission to
        # invent citations. Only verified bibliography services may fix it.
        if self.benchmark.median_reference_entries >= 5 and current.reference_entries < min(5, self.benchmark.median_reference_entries * 0.6):
            gaps.append(
                SameProblemGap(
                    defect_type="DOCUMENT",
                    severity="REVIEW",
                    dimension="same_problem_reference_depth",
                    message=(
                        f"Current paper exposes {current.reference_entries} reference entries; same-problem O-award median is "
                        f"{self.benchmark.median_reference_entries:.1f}. Add only verified domain/method references."
                    ),
                    repair_phase="bibliography",
                    benchmark_evidence=f"median references={self.benchmark.median_reference_entries:.1f}",
                )
            )

        gaps = _dedupe_gaps(gaps)
        gate: Literal["PASS", "REVIEW", "BLOCK"] = (
            "BLOCK" if any(item.severity == "BLOCK" for item in gaps) else "REVIEW" if gaps else "PASS"
        )
        return SameProblemAssessment(
            case_id=case_id,
            corpus_id=self.benchmark.corpus_id,
            gate=gate,
            gaps=gaps,
            document_gaps=sum(item.defect_type == "DOCUMENT" for item in gaps),
            research_gaps=sum(item.defect_type == "RESEARCH" for item in gaps),
            checked_at=now_iso(),
        )

    def persist(
        self,
        cases: Any,
        artifacts: Any,
        case_id: str,
        assessment: SameProblemAssessment,
        *,
        source_artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        root = cases.case_root(case_id)
        path = root / "review" / "competition" / "same_problem_oaward_gap.json"
        atomic_write_json(path, assessment.model_dump(mode="json"))
        artifact = artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "same_problem_excellent_gap_assessment",
            "same_problem_benchmark",
            upstream=list(source_artifact_ids or []),
            paper_eligible=False,
        )
        return {"assessment": assessment, "artifact": artifact}

    def _prevalent(self, key: str) -> bool:
        return float(self.benchmark.prevalence.get(key, 0.0)) + 1e-9 >= self.threshold

    def _document_signal_gap(
        self,
        current: FullTextPaperProfile,
        key: str,
        dimension: str,
        message: str,
        repair_phase: str,
    ) -> list[SameProblemGap]:
        if not self._prevalent(key):
            return []
        if key == "has_workflow_figure":
            present = current.has_workflow_figure
        else:
            group, name = key.split(".", 1)
            present = bool(getattr(current, f"{group}_signals").get(name))
        if present:
            return []
        return [
            SameProblemGap(
                defect_type="DOCUMENT",
                severity="REVIEW",
                dimension=dimension,
                message=message,
                repair_phase=repair_phase,
                benchmark_prevalence=float(self.benchmark.prevalence.get(key, 0.0)),
                benchmark_evidence=f"{key} prevalence={self.benchmark.prevalence.get(key, 0.0):.0%}",
            )
        ]

    def _research_gap(
        self,
        dimension: str,
        message: str,
        repair_phase: str,
        narrative: Any | None,
        *,
        families: set[str],
        prevalence_key: str,
    ) -> SameProblemGap:
        subproblem_ids = []
        if narrative is not None:
            subproblem_ids = [
                str(node.subproblem_id)
                for node in narrative.nodes
                if getattr(node, "role", "") == "RESEARCH" and getattr(node, "task_family", "") in families
            ]
        return SameProblemGap(
            defect_type="RESEARCH",
            severity="REVIEW",
            dimension=dimension,
            message=message,
            repair_phase=repair_phase,
            subproblem_ids=subproblem_ids,
            benchmark_prevalence=float(self.benchmark.prevalence.get(prevalence_key, 0.0)),
            benchmark_evidence=f"{prevalence_key} prevalence={self.benchmark.prevalence.get(prevalence_key, 0.0):.0%}",
        )


def _narrative_has_sensitivity_evidence(narrative: Any | None) -> bool:
    """Require structured perturbation/stability evidence, not a prose keyword."""

    if narrative is None:
        return False
    stability_metrics = {
        "winner_retention_rate",
        "mean_spearman",
        "rank_stability",
        "sensitivity_score",
    }
    for node in getattr(narrative, "nodes", []):
        comparison = getattr(node, "alternative_comparison", None)
        if comparison is not None and getattr(comparison, "stress_runs", None):
            return True
        for result in getattr(node, "key_results", []):
            metric = str(getattr(result, "metric", "")).lower()
            if metric in stability_metrics or "sensitivity" in metric or "stability" in metric:
                return True
    return False


def load_profiles(path: str | Path) -> list[FullTextPaperProfile]:
    payload = read_json(Path(path))
    rows = payload.get("papers", payload) if isinstance(payload, dict) else payload
    if not isinstance(rows, list):
        raise ValueError("FULLTEXT_PROFILE_FILE_INVALID")
    return [FullTextPaperProfile.model_validate(item) for item in rows]


def dump_corpus_payload(profiles: list[FullTextPaperProfile], corpus: SameProblemCorpusProfile) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "papers": [item.model_dump(mode="json") for item in profiles],
        "corpus": corpus.model_dump(mode="json"),
    }


def _normalize_text(text: str) -> str:
    return text.replace("\x0c", "\n").replace("\u00ad", "").replace("\r\n", "\n")


def _extract_abstract(text: str) -> str:
    match = re.search(r"(?im)^\s*(?:#+\s*)?(?:summary|abstract|摘\s*要)\s*$", text)
    if match:
        rest = text[match.end():]
        stop = re.search(
            r"(?im)^\s*(?:#+\s*)?(?:keywords?|关\s*键\s*词|contents|目录|1\s+introduction|一[、.]?\s*问题|1\s*[、.]?\s*问题|team\s+#?).*$",
            rest,
        )
        return rest[: stop.start()] if stop else rest[:6000]
    # MCM summary sheets often omit a second standalone 'Summary' heading.
    # Remove the administrative header lines first; `Team Control Number` must
    # not be treated as an end-of-abstract marker because it precedes the title.
    sheet = re.search(r"(?i)summary sheet", text)
    if sheet:
        rest = text[sheet.end():]
        rest = re.sub(
            r"(?im)^\s*(?:for office use only|team control number|problem chosen|[TF]\d(?:\s+[TF]\d)*|\d{4,8}|[A-F])\s*$",
            "",
            rest,
        )
        stop = re.search(
            r"(?im)^\s*(?:keywords?|contents|1\s+introduction|team\s*#).*$",
            rest,
        )
        return rest[: stop.start()] if stop else rest[:6000]
    return text[:4000]


def _extract_references(text: str) -> str:
    matches = list(re.finditer(r"(?im)^\s*(?:#+\s*)?(?:references|参考文献)\s*$", text))
    if not matches:
        return ""
    rest = text[matches[-1].end():]
    stop = re.search(r"(?im)^\s*(?:#+\s*)?(?:[A-Z一二三四五六七八九十]+\s*)?(?:appendix|letter|附录|附件清单|致谢)(?:\s*[:：].*)?\s*$", rest)
    return rest[: stop.start()] if stop else rest


def _text_token_count(text: str) -> int:
    """Comparable rough abstract length for English and Chinese corpora."""

    english = re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", text)
    chinese = re.findall(r"[\u4e00-\u9fff]", text)
    return len(english) + len(chinese)


def _dedupe_gaps(gaps: list[SameProblemGap]) -> list[SameProblemGap]:
    result: list[SameProblemGap] = []
    seen: set[tuple[str, str]] = set()
    for item in gaps:
        key = (item.defect_type, item.dimension)
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result

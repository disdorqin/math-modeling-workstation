from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path
from statistics import median
from typing import Any, Iterable

from pydantic import BaseModel, ConfigDict, Field

from .excellent_pdf_text import extract_pdf_text, pdf_page_count
from .io_utils import atomic_write_json, now_iso, read_json


FINGERPRINT_CACHE_SCHEMA_VERSION = 5


class CorpusPaperSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    paper_id: str
    corpus_id: str
    competition: str
    year: int
    problem_letter: str
    award: str
    source_path: str
    title_hint: str
    file_size: int
    modified_ns: int
    source_fingerprint: str
    duplicate_group: str
    is_compilation: bool = False
    c_problem: bool = False
    style_weight: float = 0.0
    modeling_weight: float = 0.0


class CorpusPaperFingerprint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: CorpusPaperSource
    status: str
    backend: str | None = None
    error: str = ""
    page_count: int = 0
    text_characters: int = 0
    language: str = "unknown"
    abstract_units: int = 0
    abstract_numeric_tokens: int = 0
    abstract_method_count: int = 0
    model_sequence_length: int = 0
    figure_mentions: int = 0
    table_mentions: int = 0
    reference_entries: int = 0
    workflow_figure_signal: bool = False
    figure_purposes: dict[str, int] = Field(default_factory=dict)
    question_types: list[str] = Field(default_factory=list)
    model_selection_rationales: list[str] = Field(default_factory=list)
    model_transition_patterns: list[str] = Field(default_factory=list)
    validation_types: list[str] = Field(default_factory=list)
    innovation_patterns: list[str] = Field(default_factory=list)
    failure_patterns: list[str] = Field(default_factory=list)
    image_count: int = 0
    pages_with_images: int = 0
    image_area_ratio: float = 0.0
    text_area_ratio: float = 0.0
    landscape_page_ratio: float = 0.0
    scan_page_ratio: float = 0.0
    generated_at: str


class CorpusDistillationSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    source_root: str
    paper_count: int
    parsed_count: int
    visual_only_count: int = 0
    failed_count: int
    c_problem_count: int
    competition_counts: dict[str, int]
    year_counts: dict[str, int]
    c_year_counts: dict[str, int]
    parser_backends: dict[str, int]
    failure_codes: dict[str, int]
    weighted_style_prior: dict[str, float]
    weighted_layout_prior: dict[str, float] = Field(default_factory=dict)
    weighted_c_modeling_prior: dict[str, float]
    recent_style_prior: dict[str, float]
    recent_layout_prior: dict[str, float] = Field(default_factory=dict)
    pre_ai_style_prior: dict[str, float]
    era_change: dict[str, float]
    top_figure_purposes_recent: dict[str, float]
    top_validation_patterns_c: dict[str, float]
    fallback_queue: list[str]
    generated_at: str


@dataclass(frozen=True)
class _CorpusSpec:
    corpus_id: str
    competition: str
    path: Path
    award: str


_YEAR_RE = re.compile(r"(?:19|20)\d{2}")
_MCM_LETTER_RE = re.compile(r"^(?:[A-F])$", re.I)
_MCM_LETTER_VERBOSE_RE = re.compile(r"([A-F])\s*题", re.I)
_CUMCM_NAME_RE = re.compile(r"(?:19|20)\d{2}\s*([A-F])", re.I)
_CUMCM_CODE_RE = re.compile(r"(?:^|[^A-Za-z])([A-F])\s*\d{2,4}(?:[^0-9]|$)", re.I)
_COPY_SUFFIX_RE = re.compile(r"(?:\s*[（(]\s*\d+\s*[）)]|[_\-\s]*(?:copy|副本))$", re.I)

_SAFE_METHOD_KEYWORDS: dict[str, tuple[str, ...]] = {
    "linear_regression": ("linear regression", "线性回归"),
    "logistic_regression": ("logistic regression", "逻辑回归"),
    "polynomial_fit": ("polynomial", "多项式拟合", "曲线拟合"),
    "time_series": ("time series", "时间序列", "arima", "prophet", "holt-winters", "holt winters"),
    "random_forest": ("random forest", "随机森林"),
    "xgboost": ("xgboost", "gradient boosting", "梯度提升"),
    "neural_network": ("neural network", "神经网络", "lstm", "bp network", "bp神经网络"),
    "svm": ("support vector", "svm", "支持向量"),
    "kmeans": ("k-means", "kmeans", "k means", "k均值"),
    "hierarchical_clustering": ("hierarchical clustering", "系统聚类", "层次聚类"),
    "pca": ("principal component", "pca", "主成分"),
    "topsis": ("topsis", "逼近理想解"),
    "ahp": ("analytic hierarchy", "ahp", "层次分析"),
    "entropy_weight": ("entropy weight", "熵权"),
    "grey_relation": ("grey relation", "gray relation", "灰色关联"),
    "markov": ("markov", "马尔可夫"),
    "monte_carlo": ("monte carlo", "蒙特卡洛"),
    "genetic_algorithm": ("genetic algorithm", "遗传算法"),
    "particle_swarm": ("particle swarm", "粒子群"),
    "simulated_annealing": ("simulated annealing", "模拟退火"),
    "linear_programming": ("linear programming", "线性规划"),
    "integer_programming": ("integer programming", "整数规划", "0-1规划", "0-1 programming"),
    "dynamic_programming": ("dynamic programming", "动态规划"),
    "bayesian": ("bayesian", "贝叶斯", "mcmc"),
    "association_rules": ("apriori", "association rule", "关联规则", "fp-growth", "fp growth"),
}

_SAFE_SIGNAL_KEYWORDS: dict[str, dict[str, tuple[str, ...]]] = {
    "question_types": {
        "optimization": ("优化", "最优", "optimization", "minimize", "maximize"),
        "forecasting": ("预测", "forecast", "prediction"),
        "statistical_analysis": ("相关分析", "回归", "聚类", "统计分析", "correlation", "regression", "clustering"),
        "classification_or_scoring": ("分类", "评分", "评级", "classification", "scoring", "rating"),
        "simulation": ("仿真", "模拟", "simulation", "monte carlo"),
        "spatial_or_layout_design": ("布局", "路径", "空间", "layout", "route", "spatial"),
        "decision_strategy": ("决策", "策略", "方案", "decision", "strategy"),
    },
    "model_selection_rationales": {
        "data_characteristics": ("数据特征", "季节性", "周期性", "非线性", "相关性", "seasonal", "nonlinear", "correlation"),
        "constraint_structure": ("约束条件", "可行域", "整数", "constraint", "integer", "binary"),
        "accuracy_or_fit": ("提高精度", "误差更小", "拟合优度", "accuracy", "better fit", "reduce error"),
        "robustness_or_uncertainty": ("稳健", "鲁棒", "不确定", "robust", "uncertain"),
        "interpretability_or_operability": ("可解释", "直观", "可操作", "interpretable", "practical"),
    },
    "model_transition_patterns": {
        "staged_question_progression": ("针对问题", "for question", "question 1", "problem 1"),
        "refine_previous_model": ("在此基础上", "进一步", "改进模型", "building on", "previous model"),
        "hybrid_or_combined_model": ("组合模型", "混合模型", "融合模型", "hybrid", "ensemble"),
        "scenario_branching": ("分情形", "不同情形", "不同场景", "scenario", "case 1"),
    },
    "validation_types": {
        "error_metrics": ("rmse", "mse", "mae", "相对误差", "均方误差", "误差分析"),
        "sensitivity_or_robustness": ("灵敏度分析", "敏感性分析", "稳健性分析", "sensitivity", "robustness", "stress test"),
        "model_comparison": ("模型比较", "模型对比", "method comparison", "model comparison"),
        "cross_validation_or_holdout": ("交叉验证", "训练集", "测试集", "验证集", "cross-validation", "cross validation", "holdout", "test set"),
        "parameter_search": ("参数寻优", "参数优化", "网格搜索", "遗传算法", "粒子群", "grid search", "tuning"),
        "uncertainty_interval": ("置信区间", "预测区间", "后验分布", "confidence interval", "prediction interval", "posterior"),
    },
    "innovation_patterns": {
        "domain_specific_construct": ("构建指标", "构建指数", "评价体系", "custom index", "custom metric"),
        "hybrid_model": ("混合模型", "组合模型", "融合模型", "hybrid model", "ensemble"),
        "algorithmic_improvement": ("改进算法", "改进模型", "improved algorithm", "improved model"),
        "adaptive_or_dynamic_strategy": ("动态策略", "滚动优化", "自适应", "adaptive", "rolling optimization"),
    },
    "failure_patterns": {
        "data_limitation": ("数据不足", "数据缺失", "样本不足", "limited data", "missing data"),
        "simplifying_assumption": ("简化假设", "忽略因素", "simplifying assumption", "ignore factor"),
        "computational_cost": ("计算量大", "复杂度高", "耗时", "computational cost", "time consuming"),
        "generalization_limit": ("普适性不足", "适用范围有限", "limited applicability", "generalization"),
        "parameter_subjectivity": ("主观权重", "参数主观", "subjective weight", "subjective parameter"),
    },
}

_FIGURE_PURPOSE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "workflow_or_framework": ("流程", "框架", "技术路线", "workflow", "framework", "flowchart"),
    "data_distribution": ("分布", "散点", "箱线", "直方", "distribution", "scatter", "histogram", "boxplot"),
    "time_series_or_trend": ("趋势", "变化曲线", "时间序列", "trend", "time series"),
    "physical_or_geometric_mechanism": ("示意图", "结构图", "几何", "mechanism", "geometry", "schematic"),
    "spatial_layout_or_route": ("布局", "位置", "路径", "路线", "layout", "route", "spatial"),
    "optimization_or_convergence": ("收敛", "适应度", "目标函数", "优化过程", "convergence", "fitness", "objective"),
    "result_comparison": ("对比", "比较", "误差", "comparison", "versus", "error"),
    "decision_or_schedule": ("调度", "策略", "方案", "补货", "定价", "decision", "schedule", "strategy"),
    "sensitivity_or_uncertainty": ("敏感", "灵敏", "不确定", "概率", "sensitivity", "uncertainty"),
}


def recency_style_weight(year: int) -> float:
    """Return style/layout weight; recent AI-era papers dominate presentation priors."""

    if year >= 2024:
        return 1.25
    if year >= 2023:
        return 1.15
    if year >= 2020:
        return 0.82
    if year >= 2016:
        return 0.52
    if year >= 2010:
        return 0.34
    return 0.20


def modeling_logic_weight(year: int, *, c_problem: bool) -> float:
    """Classic C papers remain useful for modeling logic; non-C papers are style-only priors."""

    if not c_problem:
        return 0.0
    if year >= 2023:
        return 1.0
    if year >= 2016:
        return 0.92
    return 0.82


def scan_registered_excellent_papers(registry_path: str | Path) -> list[CorpusPaperSource]:
    registry_file = Path(registry_path)
    registry = read_json(registry_file)
    source_root = Path(str(registry["source_root"]))
    specs = []
    for asset in registry.get("assets", []):
        if asset.get("kind") != "excellent_paper_corpus":
            continue
        competition = str(asset.get("competition") or "")
        specs.append(
            _CorpusSpec(
                corpus_id=str(asset["asset_id"]),
                competition=("MCM" if competition.startswith("MCM") else "CUMCM"),
                path=source_root / str(asset["path"]),
                award=("O_AWARD" if competition.startswith("MCM") else "EXCELLENT"),
            )
        )

    discovered: list[CorpusPaperSource] = []
    for spec in specs:
        if not spec.path.is_dir():
            continue
        for pdf in sorted(spec.path.rglob("*.pdf")):
            relative = pdf.relative_to(spec.path)
            year = _infer_year(relative)
            letter = _infer_problem_letter(spec.competition, relative)
            stat = pdf.stat()
            normalized_title = _normalize_title(pdf.stem)
            duplicate_group = f"{spec.competition}:{year}:{letter}:{normalized_title}"
            fingerprint_material = f"{pdf.resolve()}|{stat.st_size}|{stat.st_mtime_ns}"
            source_fingerprint = hashlib.sha256(fingerprint_material.encode("utf-8")).hexdigest()[:20]
            paper_id = hashlib.sha256(str(pdf.resolve()).encode("utf-8")).hexdigest()[:16]
            is_compilation = _is_compilation(relative, pdf.stem)
            c_problem = letter == "C"
            style_weight = recency_style_weight(year)
            if c_problem:
                style_weight *= 1.0
            else:
                # Other problem letters can teach modern visual/paper style, but
                # must not overwhelm C-problem priors.
                style_weight *= 0.35
            if is_compilation:
                style_weight *= 0.15
            discovered.append(
                CorpusPaperSource(
                    paper_id=paper_id,
                    corpus_id=spec.corpus_id,
                    competition=spec.competition,
                    year=year,
                    problem_letter=letter,
                    award=spec.award,
                    source_path=str(pdf),
                    title_hint=pdf.stem,
                    file_size=int(stat.st_size),
                    modified_ns=int(stat.st_mtime_ns),
                    source_fingerprint=source_fingerprint,
                    duplicate_group=duplicate_group,
                    is_compilation=is_compilation,
                    c_problem=c_problem,
                    style_weight=round(style_weight, 6),
                    modeling_weight=round(modeling_logic_weight(year, c_problem=c_problem), 6),
                )
            )

    group_counts = Counter(item.duplicate_group for item in discovered)
    # Downweight duplicate title copies without deleting them. This keeps every
    # local paper visible while preventing copied PDFs from dominating priors.
    for item in discovered:
        count = max(1, group_counts[item.duplicate_group])
        item.style_weight = round(item.style_weight / count, 6)
        item.modeling_weight = round(item.modeling_weight / count, 6)
    return discovered


def fingerprint_paper(source: CorpusPaperSource) -> CorpusPaperFingerprint:
    path = Path(source.source_path)
    # Layout/page signals remain valuable even when a Chinese competition PDF
    # has no usable Unicode text layer.  Extract them first so the newest papers
    # can still teach the visual/layout student without contaminating text/model
    # priors with fabricated OCR.
    try:
        pages = pdf_page_count(path)
        layout = _layout_metrics(path)
    except Exception as exc:
        return CorpusPaperFingerprint(
            source=source,
            status="FALLBACK_REQUIRED",
            error=f"{type(exc).__name__}:{str(exc)[:240]}",
            generated_at=now_iso(),
        )

    if float(layout["scan_page_ratio"]) >= 0.8 and float(layout["text_area_ratio"]) <= 0.03:
        return CorpusPaperFingerprint(
            source=source,
            status="VISUAL_ONLY",
            backend="layout_scan",
            error="SCAN_DOMINANT_UNICODE_TEXT_SKIPPED",
            page_count=pages,
            image_count=int(layout["image_count"]),
            pages_with_images=int(layout["pages_with_images"]),
            image_area_ratio=float(layout["image_area_ratio"]),
            text_area_ratio=float(layout["text_area_ratio"]),
            landscape_page_ratio=float(layout["landscape_page_ratio"]),
            scan_page_ratio=float(layout["scan_page_ratio"]),
            generated_at=now_iso(),
        )

    try:
        text, backend = extract_pdf_text(path)
    except Exception as exc:
        return CorpusPaperFingerprint(
            source=source,
            status="VISUAL_ONLY",
            backend="layout_only",
            error=f"{type(exc).__name__}:{str(exc)[:240]}",
            page_count=pages,
            image_count=int(layout["image_count"]),
            pages_with_images=int(layout["pages_with_images"]),
            image_area_ratio=float(layout["image_area_ratio"]),
            text_area_ratio=float(layout["text_area_ratio"]),
            landscape_page_ratio=float(layout["landscape_page_ratio"]),
            scan_page_ratio=float(layout["scan_page_ratio"]),
            generated_at=now_iso(),
        )

    fast = _fast_text_profile(text)
    return CorpusPaperFingerprint(
        source=source,
        status="PARSED",
        backend=backend,
        page_count=pages,
        text_characters=len(text),
        language=str(fast["language"]),
        abstract_units=int(fast["abstract_units"]),
        abstract_numeric_tokens=int(fast["abstract_numeric_tokens"]),
        abstract_method_count=int(fast["abstract_method_count"]),
        model_sequence_length=int(fast["model_sequence_length"]),
        figure_mentions=int(fast["figure_mentions"]),
        table_mentions=int(fast["table_mentions"]),
        reference_entries=int(fast["reference_entries"]),
        workflow_figure_signal=bool(fast["workflow_figure_signal"]),
        figure_purposes=dict(fast["figure_purposes"]),
        question_types=list(fast["question_types"]),
        model_selection_rationales=list(fast["model_selection_rationales"]),
        model_transition_patterns=list(fast["model_transition_patterns"]),
        validation_types=list(fast["validation_types"]),
        innovation_patterns=list(fast["innovation_patterns"]),
        failure_patterns=list(fast["failure_patterns"]),
        image_count=int(layout["image_count"]),
        pages_with_images=int(layout["pages_with_images"]),
        image_area_ratio=float(layout["image_area_ratio"]),
        text_area_ratio=float(layout["text_area_ratio"]),
        landscape_page_ratio=float(layout["landscape_page_ratio"]),
        scan_page_ratio=float(layout["scan_page_ratio"]),
        generated_at=now_iso(),
    )


def distill_registered_corpus(
    registry_path: str | Path,
    *,
    workers: int | None = None,
    sources: list[CorpusPaperSource] | None = None,
) -> tuple[list[CorpusPaperFingerprint], CorpusDistillationSummary]:
    registry = read_json(Path(registry_path))
    selected = sources or scan_registered_excellent_papers(registry_path)
    fingerprints = _fingerprint_many(selected, workers=workers)
    summary = summarize_fingerprints(fingerprints, source_root=str(registry["source_root"]))
    return fingerprints, summary


def distill_registered_corpus_cached(
    registry_path: str | Path,
    cache_path: str | Path,
    *,
    workers: int | None = None,
    sources: list[CorpusPaperSource] | None = None,
    write_cache: bool = False,
) -> tuple[list[CorpusPaperFingerprint], CorpusDistillationSummary, dict[str, int]]:
    """Incrementally distill a corpus by reusing unchanged PDF fingerprints.

    Cache validity is tied to each source fingerprint (path metadata/size/mtime),
    so newly downloaded or replaced papers are the only files that need a fresh
    parse. Source weights are refreshed even for reused fingerprints because
    duplicate-group counts can change when the local corpus grows.
    """

    registry = read_json(Path(registry_path))
    selected = sources or scan_registered_excellent_papers(registry_path)
    cached = _load_fingerprint_cache(cache_path)
    reused: list[CorpusPaperFingerprint] = []
    pending: list[CorpusPaperSource] = []
    for source in selected:
        previous = cached.get(source.paper_id)
        if previous is not None and previous.source.source_fingerprint == source.source_fingerprint:
            reused.append(previous.model_copy(update={"source": source}))
        else:
            pending.append(source)

    fresh = _fingerprint_many(pending, workers=workers)
    fingerprints = [*reused, *fresh]
    fingerprints.sort(key=lambda item: (item.source.competition, item.source.year, item.source.problem_letter, item.source.paper_id))
    summary = summarize_fingerprints(fingerprints, source_root=str(registry["source_root"]))
    if write_cache:
        # A global cache must survive filtered/sharded training runs.  Preserve
        # fingerprints from earlier shards and replace only the currently
        # selected paper ids.  This makes year/competition shards true
        # checkpointed distillation rather than destructive partial snapshots.
        merged_cache = dict(cached)
        merged_cache.update({item.source.paper_id: item for item in fingerprints})
        _persist_fingerprint_cache(
            cache_path,
            sorted(
                merged_cache.values(),
                key=lambda item: (
                    item.source.competition,
                    item.source.year,
                    item.source.problem_letter,
                    item.source.paper_id,
                ),
            ),
        )
    stats = {"reused": len(reused), "parsed_fresh": len(fresh), "selected": len(selected)}
    return fingerprints, summary, stats


def _fingerprint_many(
    sources: list[CorpusPaperSource],
    *,
    workers: int | None = None,
) -> list[CorpusPaperFingerprint]:
    if not sources:
        return []
    worker_count = workers or min(8, max(2, (os.cpu_count() or 4) // 2))
    fingerprints: list[CorpusPaperFingerprint] = []
    with ThreadPoolExecutor(max_workers=worker_count) as pool:
        future_map = {pool.submit(fingerprint_paper, item): item for item in sources}
        for future in as_completed(future_map):
            fingerprints.append(future.result())
    fingerprints.sort(key=lambda item: (item.source.competition, item.source.year, item.source.problem_letter, item.source.paper_id))
    return fingerprints


def _load_fingerprint_cache(path: str | Path) -> dict[str, CorpusPaperFingerprint]:
    source = Path(path)
    if not source.is_file():
        return {}
    try:
        payload = read_json(source)
        if int(payload.get("schema_version", 0)) != FINGERPRINT_CACHE_SCHEMA_VERSION:
            return {}
        values = [CorpusPaperFingerprint.model_validate(item) for item in payload.get("fingerprints", [])]
        return {item.source.paper_id: item for item in values}
    except (OSError, ValueError, TypeError):
        return {}


def _persist_fingerprint_cache(path: str | Path, fingerprints: list[CorpusPaperFingerprint]) -> None:
    target = Path(path)
    atomic_write_json(
        target,
        {
            "schema_version": FINGERPRINT_CACHE_SCHEMA_VERSION,
            "generated_at": now_iso(),
            "fingerprints": [item.model_dump(mode="json") for item in fingerprints],
        },
    )


def summarize_fingerprints(
    fingerprints: Iterable[CorpusPaperFingerprint],
    *,
    source_root: str,
) -> CorpusDistillationSummary:
    items = list(fingerprints)
    parsed = [item for item in items if item.status == "PARSED"]
    visual_only = [item for item in items if item.status == "VISUAL_ONLY"]
    visual_available = [item for item in items if item.status in {"PARSED", "VISUAL_ONLY"}]
    failed = [item for item in items if item.status == "FALLBACK_REQUIRED"]
    competition_counts = Counter(item.source.competition for item in items)
    year_counts = Counter(str(item.source.year) for item in items if item.source.year)
    c_year_counts = Counter(str(item.source.year) for item in items if item.source.c_problem and item.source.year)
    parser_backends = Counter(str(item.backend) for item in parsed if item.backend)
    fallback_items = [*visual_only, *failed]
    failure_codes = Counter((item.error.split(":", 1)[0] if item.error else "UNKNOWN") for item in fallback_items)

    style = _weighted_prior(parsed, weight_name="style_weight")
    layout = _weighted_layout_prior(visual_available, weight_name="style_weight")
    c_parsed = [item for item in parsed if item.source.c_problem]
    modeling = _weighted_prior(c_parsed, weight_name="modeling_weight")
    recent = [item for item in parsed if item.source.year >= 2023]
    recent_visual = [item for item in visual_available if item.source.year >= 2023]
    pre_ai = [item for item in parsed if 2016 <= item.source.year <= 2020]
    recent_prior = _weighted_prior(recent, weight_name="style_weight")
    recent_layout = _weighted_layout_prior(recent_visual, weight_name="style_weight")
    pre_ai_prior = _weighted_prior(pre_ai, weight_name="style_weight")
    era_change = {
        key: round(recent_prior.get(key, 0.0) - pre_ai_prior.get(key, 0.0), 4)
        for key in sorted(set(recent_prior) & set(pre_ai_prior))
    }

    recent_purposes = _weighted_prevalence(recent, "figure_purposes", "style_weight")
    c_validation = _weighted_list_prevalence(c_parsed, "validation_types", "modeling_weight")
    fallback_queue = [item.source.source_path for item in fallback_items]
    return CorpusDistillationSummary(
        source_root=source_root,
        paper_count=len(items),
        parsed_count=len(parsed),
        visual_only_count=len(visual_only),
        failed_count=len(failed),
        c_problem_count=sum(item.source.c_problem for item in items),
        competition_counts=dict(sorted(competition_counts.items())),
        year_counts=dict(sorted(year_counts.items())),
        c_year_counts=dict(sorted(c_year_counts.items())),
        parser_backends=dict(sorted(parser_backends.items())),
        failure_codes=dict(sorted(failure_codes.items())),
        weighted_style_prior=style,
        weighted_layout_prior=layout,
        weighted_c_modeling_prior=modeling,
        recent_style_prior=recent_prior,
        recent_layout_prior=recent_layout,
        pre_ai_style_prior=pre_ai_prior,
        era_change=era_change,
        top_figure_purposes_recent=dict(list(recent_purposes.items())[:12]),
        top_validation_patterns_c=dict(list(c_validation.items())[:12]),
        fallback_queue=fallback_queue,
        generated_at=now_iso(),
    )


def teacher_packet(summary: CorpusDistillationSummary) -> dict[str, Any]:
    """Compact packet intended for GPT-level reasoning, not raw-PDF prompting."""

    return {
        "schema_version": 1,
        "objective": "distill excellent-paper priors without copying paper text or forcing algorithms",
        "coverage": {
            "papers": summary.paper_count,
            "parsed": summary.parsed_count,
            "visual_only": summary.visual_only_count,
            "fallback": summary.visual_only_count + summary.failed_count,
            "c_problem": summary.c_problem_count,
            "competition_counts": summary.competition_counts,
            "c_year_counts": summary.c_year_counts,
        },
        "style_prior_all": summary.weighted_style_prior,
        "layout_prior_all": summary.weighted_layout_prior,
        "style_prior_2023_plus": summary.recent_style_prior,
        "layout_prior_2023_plus": summary.recent_layout_prior,
        "style_prior_2016_2020": summary.pre_ai_style_prior,
        "ai_era_delta_recent_minus_pre_ai": summary.era_change,
        "recent_figure_purpose_prevalence": summary.top_figure_purposes_recent,
        "c_validation_prevalence": summary.top_validation_patterns_c,
        "safety_policy": [
            "learn distributions and argument patterns, not source wording",
            "C-problem modeling priors come only from C papers",
            "non-C papers may contribute style/layout priors at reduced weight",
            "recent papers dominate visual/writing style; classic papers retain modeling-logic value",
            "never add a model, figure, metric, or experiment solely to imitate corpus frequency",
        ],
    }


def _fast_text_profile(text: str) -> dict[str, Any]:
    normalized = text.replace("\r\n", "\n")
    lowered = normalized.lower()
    abstract = _fast_abstract(normalized)
    abstract_lower = abstract.lower()
    chinese = len(re.findall(r"[\u4e00-\u9fff]", abstract))
    english = len(re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", abstract))
    abstract_units = chinese + english
    abstract_numeric_tokens = len(re.findall(r"(?<![A-Za-z])[-+]?\d+(?:\.\d+)?%?", abstract))

    method_positions: list[tuple[int, str]] = []
    for name, keywords in _SAFE_METHOD_KEYWORDS.items():
        positions = [lowered.find(keyword.lower()) for keyword in keywords]
        positions = [value for value in positions if value >= 0]
        if positions:
            method_positions.append((min(positions), name))
    method_sequence = [name for _position, name in sorted(method_positions)]
    abstract_methods = sum(
        any(keyword.lower() in abstract_lower for keyword in keywords)
        for keywords in _SAFE_METHOD_KEYWORDS.values()
    )

    figure_captions: list[str] = []
    figure_mentions = 0
    table_mentions = 0
    reference_entries = 0
    for line in normalized.splitlines():
        compact = " ".join(line.split())
        if not compact:
            continue
        if re.search(r"(?i)(?:\bfig(?:ure)?\.?\s*\d+|图\s*\d+)", compact):
            figure_mentions += 1
            if re.match(r"(?i)^(?:fig(?:ure)?\.?\s*\d+|图\s*\d+)", compact):
                figure_captions.append(compact[:180])
        if re.search(r"(?i)(?:\btable\s*\d+|表\s*\d+)", compact):
            table_mentions += 1
        if re.match(r"^\s*(?:\[?\d+\]?\s*[.、)]|\(\d+\)\s+)", compact):
            reference_entries += 1

    figure_purposes: Counter[str] = Counter()
    for caption in figure_captions:
        low = caption.lower()
        for name, keywords in _FIGURE_PURPOSE_KEYWORDS.items():
            if any(keyword.lower() in low for keyword in keywords):
                figure_purposes[name] += 1
                break

    signal_values: dict[str, list[str]] = {}
    for field, groups in _SAFE_SIGNAL_KEYWORDS.items():
        signal_values[field] = [
            name
            for name, keywords in groups.items()
            if any(keyword.lower() in lowered for keyword in keywords)
        ]

    language = _fast_language(normalized)
    return {
        "language": language,
        "abstract_units": abstract_units,
        "abstract_numeric_tokens": abstract_numeric_tokens,
        "abstract_method_count": abstract_methods,
        "model_sequence_length": len(method_sequence),
        "figure_mentions": figure_mentions,
        "table_mentions": table_mentions,
        "reference_entries": reference_entries,
        "workflow_figure_signal": bool(figure_purposes.get("workflow_or_framework", 0)),
        "figure_purposes": dict(sorted(figure_purposes.items())),
        **signal_values,
    }


def _fast_abstract(text: str) -> str:
    normalized = text.replace("\r\n", "\n")
    candidates = []
    for marker in ("摘要", "summary", "abstract"):
        index = normalized.lower().find(marker.lower())
        if index >= 0:
            candidates.append((index, marker))
    if not candidates:
        return normalized[:2500]
    start, marker = min(candidates, key=lambda item: item[0])
    chunk = normalized[start + len(marker): start + len(marker) + 5000]
    lowered = chunk.lower()
    stops = []
    for token in ("关键词", "keywords", "key words", "1. introduction", "1 introduction", "问题重述", "problem restatement"):
        position = lowered.find(token.lower())
        if position > 80:
            stops.append(position)
    if stops:
        chunk = chunk[: min(stops)]
    return " ".join(chunk.split())[:3500]


def _fast_language(text: str) -> str:
    sample = text[:12000]
    chinese = len(re.findall(r"[\u4e00-\u9fff]", sample))
    english = len(re.findall(r"\b[A-Za-z][A-Za-z'-]*\b", sample))
    if chinese > english * 2:
        return "zh"
    if english > chinese * 2:
        return "en"
    return "mixed"


def _weighted_layout_prior(items: list[CorpusPaperFingerprint], *, weight_name: str) -> dict[str, float]:
    """Aggregate layout-only signals, including PDFs with unusable text layers."""

    if not items:
        return {}
    metrics = (
        "page_count",
        "image_count",
        "pages_with_images",
        "image_area_ratio",
        "text_area_ratio",
        "landscape_page_ratio",
        "scan_page_ratio",
    )
    values: dict[str, float] = {}
    for metric in metrics:
        pairs = [(float(getattr(item, metric)), float(getattr(item.source, weight_name))) for item in items]
        values[f"weighted_median_{metric}"] = round(_weighted_median(pairs), 4)
    values["effective_weight"] = round(sum(float(getattr(item.source, weight_name)) for item in items), 4)
    values["paper_count"] = float(len(items))
    return values


def _weighted_prior(items: list[CorpusPaperFingerprint], *, weight_name: str) -> dict[str, float]:
    if not items:
        return {}
    metrics = (
        "page_count",
        "abstract_units",
        "abstract_numeric_tokens",
        "abstract_method_count",
        "model_sequence_length",
        "figure_mentions",
        "table_mentions",
        "reference_entries",
        "image_count",
        "pages_with_images",
        "image_area_ratio",
        "text_area_ratio",
        "landscape_page_ratio",
        "scan_page_ratio",
    )
    values: dict[str, float] = {}
    for metric in metrics:
        pairs = [(float(getattr(item, metric)), float(getattr(item.source, weight_name))) for item in items]
        values[f"weighted_median_{metric}"] = round(_weighted_median(pairs), 4)
    pairs = [(1.0 if item.workflow_figure_signal else 0.0, float(getattr(item.source, weight_name))) for item in items]
    values["weighted_workflow_figure_prevalence"] = round(_weighted_mean(pairs), 4)
    values["effective_weight"] = round(sum(float(getattr(item.source, weight_name)) for item in items), 4)
    values["paper_count"] = float(len(items))
    return values


def _weighted_prevalence(items: list[CorpusPaperFingerprint], field: str, weight_name: str) -> dict[str, float]:
    names = sorted({name for item in items for name in getattr(item, field)})
    total = sum(float(getattr(item.source, weight_name)) for item in items)
    if total <= 0:
        return {}
    result = {}
    for name in names:
        support = sum(
            float(getattr(item.source, weight_name))
            for item in items
            if bool(getattr(item, field).get(name, 0))
        )
        result[name] = round(support / total, 4)
    return dict(sorted(result.items(), key=lambda pair: (-pair[1], pair[0])))


def _weighted_list_prevalence(items: list[CorpusPaperFingerprint], field: str, weight_name: str) -> dict[str, float]:
    names = sorted({name for item in items for name in getattr(item, field)})
    total = sum(float(getattr(item.source, weight_name)) for item in items)
    if total <= 0:
        return {}
    result = {}
    for name in names:
        support = sum(
            float(getattr(item.source, weight_name))
            for item in items
            if name in getattr(item, field)
        )
        result[name] = round(support / total, 4)
    return dict(sorted(result.items(), key=lambda pair: (-pair[1], pair[0])))


def _weighted_median(pairs: list[tuple[float, float]]) -> float:
    positive = sorted((value, weight) for value, weight in pairs if weight > 0 and math.isfinite(value))
    if not positive:
        return 0.0
    threshold = sum(weight for _value, weight in positive) / 2.0
    cumulative = 0.0
    for value, weight in positive:
        cumulative += weight
        if cumulative >= threshold:
            return value
    return positive[-1][0]


def _weighted_mean(pairs: list[tuple[float, float]]) -> float:
    denominator = sum(weight for _value, weight in pairs if weight > 0)
    if denominator <= 0:
        return 0.0
    return sum(value * weight for value, weight in pairs if weight > 0) / denominator


def _layout_metrics(path: Path) -> dict[str, float | int]:
    """Extract fast, corpus-scale layout signals without decoding image geometry.

    The full corpus is large enough that per-image bbox extraction becomes the
    dominant cost while adding little reliable signal: watermarks, scan tiles,
    and PDF internals make raw image area noisy.  The fast pass therefore keeps
    only cheap page/text/image-presence signals.  Precise image geometry belongs
    to the later representative-paper visual review, not the 1000+ paper pass.
    """

    try:
        import fitz  # type: ignore
    except Exception:
        return {
            "image_count": 0,
            "pages_with_images": 0,
            "image_area_ratio": 0.0,
            "text_area_ratio": 0.0,
            "landscape_page_ratio": 0.0,
            "scan_page_ratio": 0.0,
        }

    doc = fitz.open(path)
    page_stats: list[tuple[float, list[tuple[Any, ...]]]] = []
    semantic_xrefs: set[int] = set()
    total_text_area = 0.0
    total_page_area = 0.0
    landscape = 0

    for page in doc:
        rect = page.rect
        area = max(1.0, float(rect.width * rect.height))
        total_page_area += area
        landscape += int(rect.width > rect.height)
        try:
            blocks = page.get_text("blocks")
        except Exception:
            blocks = []
        page_text_area = 0.0
        for block in blocks:
            if len(block) >= 7 and int(block[6]) != 0:
                continue
            page_text_area += max(
                0.0,
                float(block[2] - block[0]) * float(block[3] - block[1]),
            )
        total_text_area += page_text_area
        try:
            images = list(page.get_images(full=False))
        except Exception:
            images = []
        page_stats.append((page_text_area / area, images))

    page_count = max(1, len(doc))
    # A native paper can contain an occasional full-image page.  Treat the PDF
    # as scan-dominant only when low-text image pages are the majority, while a
    # page with many raster tiles is a scan unconditionally.
    low_text_image_pages = sum(coverage <= 0.03 and bool(images) for coverage, images in page_stats)
    scan_dominant = low_text_image_pages / page_count >= 0.60
    scan_pages = 0
    pages_with_images = 0
    for coverage, images in page_stats:
        tiled_scan = coverage <= 0.03 and len(images) >= 20
        scan_page = tiled_scan or (scan_dominant and coverage <= 0.03 and bool(images))
        if scan_page:
            scan_pages += 1
            continue
        if images:
            pages_with_images += 1
            for image in images:
                if image:
                    try:
                        semantic_xrefs.add(int(image[0]))
                    except (TypeError, ValueError):
                        continue
    doc.close()
    return {
        "image_count": len(semantic_xrefs),
        "pages_with_images": pages_with_images,
        # Intentionally unavailable in the fast pass; exact image geometry is
        # sampled only in deep visual review and is never used as a hard gate.
        "image_area_ratio": 0.0,
        "text_area_ratio": round(min(1.0, total_text_area / max(1.0, total_page_area)), 6),
        "landscape_page_ratio": round(landscape / page_count, 6),
        "scan_page_ratio": round(scan_pages / page_count, 6),
    }


def _infer_year(relative: Path) -> int:
    """Infer the deepest *specific* year, ignoring collection-range folders.

    Corpus folders such as ``2013-2016美赛优秀论文集`` or ``2006-2025`` are
    containers, not paper years.  A deeper child such as ``2014美赛特等奖`` is
    the authoritative label.  Using the deepest single-year component prevents
    collection ranges from corrupting era-weighted distillation.
    """

    candidates: list[int] = []
    for part in relative.parts[:-1]:
        years = {int(value) for value in _YEAR_RE.findall(part)}
        if len(years) == 1:
            candidates.append(next(iter(years)))
    if candidates:
        return candidates[-1]
    # Filename fallback is intentionally strict: a team id such as 2300348 or
    # 2019567 is not a contest year.  Only a four-digit year followed by a
    # non-digit separator/letter is accepted.
    match = re.match(r"^((?:19|20)\d{2})(?=\D)", relative.name)
    return int(match.group(1)) if match else 0


def _infer_problem_letter(competition: str, relative: Path) -> str:
    if competition == "MCM":
        for part in relative.parts[:-1]:
            compact = re.sub(r"【.*?】", "", part).strip()
            if _MCM_LETTER_RE.fullmatch(compact):
                return compact.upper()
            match = _MCM_LETTER_VERBOSE_RE.search(compact)
            if match:
                return match.group(1).upper()
        stem = relative.stem.strip()
        match = re.match(r"([A-F])(?:\s|\d)", stem, flags=re.I)
        return match.group(1).upper() if match else "?"
    match = _CUMCM_NAME_RE.search(relative.name)
    if match:
        return match.group(1).upper()
    match = _CUMCM_CODE_RE.search(relative.stem)
    return match.group(1).upper() if match else "?"


def _normalize_title(stem: str) -> str:
    value = re.sub(r"【.*?】", "", stem)
    value = _COPY_SUFFIX_RE.sub("", value).lower()
    value = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", value)
    return value[:160]


def _is_compilation(relative: Path, stem: str) -> bool:
    text = (str(relative) + " " + stem).lower()
    return any(token in text for token in ("合辑", "合集", "论文集", "collection", "compilation")) and len(relative.parts) <= 2


def _json_default(value: Any) -> Any:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    raise TypeError(type(value).__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Batch-distill registered excellent-paper corpora")
    parser.add_argument("--registry", default="config/ref_models/local_knowledge_base_registry.json")
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--start", type=int, default=0, help="start offset after filtering")
    parser.add_argument("--limit", type=int, default=0, help="batch limit after filtering; 0 means all")
    parser.add_argument("--competition", choices=("MCM", "CUMCM"), default=None)
    parser.add_argument("--only-c", action="store_true")
    parser.add_argument("--year-min", type=int, default=0)
    parser.add_argument("--year-max", type=int, default=0)
    parser.add_argument("--summary-only", action="store_true", help="omit per-paper fingerprints from stdout")
    parser.add_argument("--compact", action="store_true", help="print only batch/cache counters for shard training")
    parser.add_argument("--cache", default="", help="optional fingerprint cache JSON for incremental distillation")
    parser.add_argument("--write-cache", action="store_true", help="persist refreshed fingerprints to --cache")
    args = parser.parse_args(argv)
    sources = scan_registered_excellent_papers(args.registry)
    if args.competition:
        sources = [item for item in sources if item.competition == args.competition]
    if args.only_c:
        sources = [item for item in sources if item.c_problem]
    if args.year_min:
        sources = [item for item in sources if item.year >= args.year_min]
    if args.year_max:
        sources = [item for item in sources if item.year <= args.year_max]
    if args.start > 0:
        sources = sources[args.start:]
    if args.limit > 0:
        sources = sources[: args.limit]
    cache_stats = None
    if args.cache:
        fingerprints, summary, cache_stats = distill_registered_corpus_cached(
            args.registry,
            args.cache,
            workers=(args.workers or None),
            sources=sources,
            write_cache=bool(args.write_cache),
        )
    else:
        fingerprints, summary = distill_registered_corpus(
            args.registry,
            workers=(args.workers or None),
            sources=sources,
        )
    payload = {"summary": summary, "teacher_packet": teacher_packet(summary)}
    if cache_stats is not None:
        payload["cache"] = cache_stats
    if not args.summary_only:
        payload["fingerprints"] = fingerprints
    if args.compact:
        compact = {
            "selected": summary.paper_count,
            "parsed": summary.parsed_count,
            "visual_only": summary.visual_only_count,
            "failed": summary.failed_count,
            "c_problem": summary.c_problem_count,
            "years": summary.year_counts,
            "competition_counts": summary.competition_counts,
            "cache": cache_stats,
        }
        print(json.dumps(compact, ensure_ascii=False, indent=2))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2, default=_json_default))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

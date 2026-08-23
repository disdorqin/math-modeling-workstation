from __future__ import annotations

from mathworkstation.excellent_fulltext_corpus import (
    build_deep_corpus_profile,
    deep_profile_full_text,
)


def test_deep_fulltext_profile_extracts_chinese_research_story_without_raw_text() -> None:
    text = """
摘要
针对问题一，我们根据物理机理建立热传导方程，并用有限差分法求解，结果相对误差为2.1%。
针对问题二，在问题一模型基础上，以面积最小为目标、工艺约束为条件建立优化模型，并用模拟退火进行参数寻优。
最后通过灵敏度分析验证方案稳健性。
关键词：热传导 优化 模拟退火
一、问题分析
图1 技术路线与模型框架
图2 温度变化曲线
由于直接搜索计算量较大，因此采用模拟退火降低搜索复杂度。
模型的不足是忽略了环境随机扰动，且计算量仍较大。
"""
    profile = deep_profile_full_text(
        text,
        paper_id="demo",
        year=2020,
        competition="CUMCM",
        problem="demo-reflow",
        page_count=20,
        award="excellent",
    )

    assert profile.language == "zh"
    assert "mechanistic_modeling" in profile.question_types
    assert "optimization" in profile.question_types
    assert "physical_or_domain_mechanism" in profile.model_selection_rationales
    assert "computational_efficiency" in profile.model_selection_rationales
    assert "refine_previous_model" in profile.model_transition_patterns
    assert "sensitivity_or_robustness" in profile.validation_types
    assert "parameter_search" in profile.validation_types
    assert profile.figure_purposes["workflow_or_framework"] == 1
    assert profile.figure_purposes["time_series_or_trend"] == 1
    assert profile.abstract_structure["per_question_marker_count"] == 2
    assert profile.abstract_structure["has_quantified_results"] is True
    assert "computational_cost" in profile.failure_patterns
    assert "unmodeled_uncertainty" in profile.failure_patterns
    assert "热传导" not in profile.model_dump_json() or profile.extraction_policy.startswith("derived_")


def test_deep_fulltext_profile_recognizes_classic_cumcm_geometric_path_methods() -> None:
    profile = deep_profile_full_text(
        """
摘要
我们针对输油管布置问题建立费用最小优化模型。问题一采用改进的最短路径模型；
进一步利用费尔马点、平面镜成像和光的折射构造几何最优路径，并用规划软件求解。
""",
        paper_id="cumcm-2010-c",
        year=2010,
        competition="CUMCM",
        problem="oil-pipeline",
        page_count=14,
        award="excellent",
    )

    assert "Shortest path" in profile.model_sequence
    assert "Fermat point/geometric construction" in profile.model_sequence
    assert "optimization" in profile.question_types


def test_deep_fulltext_profile_recognizes_cumcm_member_value_and_lifecycle_models() -> None:
    profile = deep_profile_full_text(
        """
摘要
针对会员画像问题，我们借鉴传统RFM方法建立RFMS会员价值模型，并进一步构建FMS购买力模型。
在前述结果基础上，采用滑动时间窗口建立会员生命周期和RF消费状态评价模型，研究活跃与非活跃状态转移。
""",
        paper_id="cumcm-2018-c",
        year=2018,
        competition="CUMCM",
        problem="member-profile",
        page_count=20,
        award="excellent",
    )

    assert "RFM-family member value model" in profile.model_sequence
    assert "Member lifecycle state model" in profile.model_sequence
    assert "classification_or_scoring" in profile.question_types


def test_deep_profile_extracts_mcm_summary_sheet_without_standalone_summary_heading() -> None:
    text = """
Mathematical Contest in Modeling (MCM/ICM) Summary Sheet
Team Control Number 2300000
Problem Chosen C
A Compact Energy Strategy
We construct an energy profile, fit an ARIMA forecast, and report a 95% prediction interval for 2050.
Keywords: energy profile, ARIMA
1 Introduction
The main body starts here.
"""
    profile = deep_profile_full_text(
        text,
        paper_id="mcm-summary",
        year=2018,
        competition="MCM",
        problem="energy",
        page_count=20,
        award="O",
    )

    assert profile.abstract_structure["token_count"] > 10
    assert profile.abstract_structure["numeric_token_count"] >= 2
    assert profile.abstract_structure["method_count"] >= 1
    assert profile.abstract_structure["has_quantified_results"] is True


def test_deep_corpus_aggregates_recurring_capabilities() -> None:
    profiles = []
    for index, extra in enumerate(("灵敏度分析", "敏感性分析", "稳健性分析"), start=1):
        profiles.append(
            deep_profile_full_text(
                f"""
摘要
针对问题一建立优化模型，结果为{index * 10}。最后进行{extra}。
关键词：优化
问题分析
图1 优化流程图
模型不足是计算量较大。
""",
                paper_id=f"p{index}",
                year=2023,
                competition="CUMCM",
                problem="demo",
                page_count=20 + index,
                award="excellent",
            )
        )

    corpus = build_deep_corpus_profile(
        profiles,
        corpus_id="demo-v1",
        extraction_note="derived only",
    )

    assert corpus.paper_count == 3
    assert corpus.prevalence["question_types.optimization"] == 1.0
    assert corpus.prevalence["validation_types.sensitivity_or_robustness"] == 1.0
    assert corpus.figure_purpose_prevalence["workflow_or_framework"] == 1.0
    assert corpus.median_abstract_numeric_tokens > 0

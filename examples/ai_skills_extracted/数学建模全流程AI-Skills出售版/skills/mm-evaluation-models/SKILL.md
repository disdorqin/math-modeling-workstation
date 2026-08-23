---
name: mm-evaluation-models
description: Build or explain comprehensive evaluation and ranking models such as TOPSIS, entropy weight, AHP, grey relational analysis, and PCA-based scoring. Use for multi-indicator evaluation, ranking, scoring, and selection tasks. Do not use when the problem is mainly forecasting or constrained optimization.
---

# 数学建模：评价模型

## Purpose

处理多指标评价、排序、打分和优选问题，提供模型流程、代码模板和结果解释框架。

## When to use

- 评价对象和指标已经明确。
- 需要 TOPSIS、熵权、AHP、灰色关联或 PCA 综合评价。
- 需要排序、评分或优选。

## When not to use

- 目标主要是预测连续数值。
- 问题核心是带约束的决策优化。
- 指标方向和数据来源完全不清楚。

## Required inputs

- 评价对象列表。
- 指标数据和指标方向。
- 是否已有主观权重。
- 结果解释需求。

## Workflow

1. 判断是否适合综合评价。
2. 明确评价对象、指标和指标方向。
3. 选择归一化方法和权重来源。
4. 计算综合得分并排序。
5. 做敏感性分析建议。
6. 输出论文表达模板和模型局限。

## Output format

```markdown
## 评价问题判断

## 指标体系

| 指标 | 含义 | 类型 | 方向 | 数据来源 |
|---|---|---|---|---|

## 推荐模型

## 计算流程

## 结果解释模板

## 敏感性分析建议

## 模型局限
```

## Quality checks

- 指标方向必须明确。
- 权重来源必须说明。
- 排名结论必须依赖可核验数据。
- 建议做权重扰动或指标剔除敏感性分析。

## Academic integrity boundaries

- 只能用于学习、训练、课程作业辅助、赛前准备、结构检查和结果复盘。
- 不代写完整参赛论文，不代替用户参赛，不承诺获奖或保奖。
- 不伪造数据、代码运行结果、图表、参考文献或实验结论。
- 正在进行的正式竞赛中，必须提醒用户遵守赛事规则、课程要求和学术诚信。
- 所有不确定结论、推断条件和未验证结果都必须标注“需要用户核验”。

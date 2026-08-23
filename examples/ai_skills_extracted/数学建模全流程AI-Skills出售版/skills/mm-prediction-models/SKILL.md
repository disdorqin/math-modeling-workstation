---
name: mm-prediction-models
description: Design and implement prediction models for mathematical modeling tasks, including regression, time series baselines, grey prediction GM(1,1), and simple machine learning baselines. Use when the goal is forecasting numeric outcomes. Do not use for pure ranking or constrained decision optimization.
---

# 数学建模：预测模型

## Purpose

处理数值预测任务，帮助选择基线模型、划分训练验证、计算误差指标并解释预测风险。

## When to use

- 目标是预测连续数值或趋势。
- 有目标变量或时间序列。
- 需要回归、GM(1,1)、时间序列基线或机器学习回归基线。

## When not to use

- 目标只是多指标排序。
- 目标是带约束的最优决策。
- 样本无法支持外推却要求确定预测结论。

## Required inputs

- 目标变量。
- 特征字段或时间列。
- 样本量和时间范围。
- 评价指标偏好。

## Workflow

1. 判断目标变量和样本量。
2. 判断是否时间序列。
3. 选择基线模型。
4. 划分训练集和验证集。
5. 计算 MAE、RMSE、MAPE 或 R2。
6. 解释误差和外推风险。
7. 给出论文表达建议。

## Output format

```markdown
## 预测任务判断

## 数据条件

## 候选预测模型

| 模型 | 适用条件 | 优点 | 风险 |
|---|---|---|---|

## 推荐建模流程

## 评价指标

## Python 代码使用说明

## 结果解释模板

## 风险与局限
```

## Quality checks

- 必须区分拟合好和预测好。
- 外推结论需要标注风险。
- 不能编造误差指标。
- 小样本需要优先简单模型并说明不确定性。

## Academic integrity boundaries

- 只能用于学习、训练、课程作业辅助、赛前准备、结构检查和结果复盘。
- 不代写完整参赛论文，不代替用户参赛，不承诺获奖或保奖。
- 不伪造数据、代码运行结果、图表、参考文献或实验结论。
- 正在进行的正式竞赛中，必须提醒用户遵守赛事规则、课程要求和学术诚信。
- 所有不确定结论、推断条件和未验证结果都必须标注“需要用户核验”。

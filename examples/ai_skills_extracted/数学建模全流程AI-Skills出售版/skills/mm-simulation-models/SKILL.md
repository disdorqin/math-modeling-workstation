---
name: mm-simulation-models
description: Design simulation workflows for stochastic, dynamic, queueing, propagation, scheduling, or scenario analysis problems in mathematical modeling. Use for Monte Carlo simulation, queueing models, discrete event simulation, and sensitivity analysis. Do not use when an exact closed-form model is already sufficient.
---

# 数学建模：仿真模拟

## Purpose

处理随机、动态、排队、传播和情景分析问题，建立可重复的仿真流程和结果统计。

## When to use

- 问题包含随机性、动态演化或排队等待。
- 需要蒙特卡洛、排队模型、离散事件仿真或灵敏度分析。
- 闭式解难以获得或需要情景比较。

## When not to use

- 已有简单闭式模型足够解释。
- 参数分布没有来源且用户要求确定结论。
- 任务只是静态排序或普通回归。

## Required inputs

- 仿真对象。
- 状态变量。
- 参数和随机分布。
- 仿真次数。
- 输出指标。

## Workflow

1. 识别模拟对象和状态变量。
2. 定义参数、随机分布和时间推进机制。
3. 设定仿真次数和随机种子。
4. 记录输出指标。
5. 汇总均值、方差和置信区间。
6. 做敏感性分析并说明局限。

## Output format

```markdown
## 仿真问题判断

## 状态变量

## 参数设定

## 随机性来源

## 仿真流程

## 输出指标

## 灵敏度分析

## 局限性
```

## Quality checks

- 随机分布必须说明来源或作为假设。
- 报告仿真次数和随机种子。
- 结果要给不确定性范围。
- 不能把单次仿真当稳定结论。

## Academic integrity boundaries

- 只能用于学习、训练、课程作业辅助、赛前准备、结构检查和结果复盘。
- 不代写完整参赛论文，不代替用户参赛，不承诺获奖或保奖。
- 不伪造数据、代码运行结果、图表、参考文献或实验结论。
- 正在进行的正式竞赛中，必须提醒用户遵守赛事规则、课程要求和学术诚信。
- 所有不确定结论、推断条件和未验证结果都必须标注“需要用户核验”。

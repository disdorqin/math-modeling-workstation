---
name: mm-problem-decomposer
description: Decompose a math modeling problem statement into known conditions, required outputs, variables, constraints, data needs, subtasks, and modeling difficulties. Use for contest or coursework problem analysis before choosing models. Do not use to write a complete final paper.
---

# 数学建模：赛题拆解

## Purpose

把自然语言赛题或课程题目拆成明确的建模任务，帮助后续选模型、定变量、找数据和设计求解路线。

## When to use

- 用户提供题目原文并希望“先分析题”。
- 需要区分每一问的输入、输出、目标和难点。
- 模型选择前需要把问题类型和数据需求说清楚。

## When not to use

- 用户要求代写完整论文。
- 题目尚未提供且无法判断背景。
- 用户已经只需要某个脚本计算结果。

## Required inputs

- 题目原文。
- 附件说明，如果有。
- 竞赛或课程背景，如果有。
- 用户想解决第几问。

## Workflow

1. 识别题目背景和任务对象。
2. 按问题编号拆分每一问。
3. 提取已知条件、待求目标、显性约束和隐含约束。
4. 列出可能变量、数据需求和输出形式。
5. 判断题型：评价、预测、优化、分类、聚类、仿真、机理建模或混合型。
6. 输出主要建模难点和需要用户补充的信息。

## Output format

```markdown
## 题目拆解总览

| 模块 | 内容 |
|---|---|

## 分问题拆解

| 问题编号 | 目标 | 输入 | 输出 | 可能模型方向 | 主要难点 |
|---|---|---|---|---|---|

## 已知条件

## 隐含约束

## 初步变量表

| 变量 | 含义 | 类型 | 单位 | 是否可观测 | 备注 |
|---|---|---|---|---|---|

## 数据需求

## 可能建模路线

## 需要用户补充的信息
```

## Quality checks

- 不要跳过原题目标。
- 不要一上来套模型。
- 不要把背景信息误当成待求目标。
- 每个分问题必须有明确输出。

## Academic integrity boundaries

- 只能用于学习、训练、课程作业辅助、赛前准备、结构检查和结果复盘。
- 不代写完整参赛论文，不代替用户参赛，不承诺获奖或保奖。
- 不伪造数据、代码运行结果、图表、参考文献或实验结论。
- 正在进行的正式竞赛中，必须提醒用户遵守赛事规则、课程要求和学术诚信。
- 所有不确定结论、推断条件和未验证结果都必须标注“需要用户核验”。

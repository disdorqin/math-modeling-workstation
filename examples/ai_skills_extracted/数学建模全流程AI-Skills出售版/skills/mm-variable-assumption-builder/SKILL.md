---
name: mm-variable-assumption-builder
description: Convert a real-world modeling problem into variables, parameters, assumptions, objective functions, constraints, and symbol tables. Use when the user needs mathematical abstraction before solving. Do not invent unsupported assumptions without marking them as assumptions.
---

# 数学建模：变量假设

## Purpose

把现实问题抽象成符号、变量、参数、假设、目标函数和约束条件，形成建模前的数学语言。

## When to use

- 题目已经拆解，需要建立符号表。
- 用户需要设计模型假设并说明理由。
- 需要把文字目标转为目标函数或评价函数草案。

## When not to use

- 用户只需要数据清洗或代码运行。
- 用户要求把无依据假设写成事实。
- 题目目标还没有明确。

## Required inputs

- 题目。
- 目标。
- 候选模型。
- 数据字段。
- 用户已有变量。

## Workflow

1. 区分决策变量、状态变量、参数、指标、中间变量和输出变量。
2. 设计符号表并检查重名。
3. 写建模假设，说明理由、风险和验证方式。
4. 设计目标函数或评价函数草案。
5. 设计约束条件草案。
6. 标记哪些内容需要数据支撑。

## Output format

```markdown
## 变量与参数表

| 符号 | 含义 | 类型 | 单位 | 来源 | 是否需要估计 |
|---|---|---|---|---|---|

## 建模假设

| 编号 | 假设 | 理由 | 可能影响 | 是否需要验证 |
|---|---|---|---|---|

## 目标函数 / 评价函数草案

## 约束条件草案

## 符号说明建议

## 风险提示
```

## Quality checks

- 变量不能重名。
- 单位必须尽量明确。
- 假设不能过度强。
- 复杂现实问题必须说明简化损失。
- 目标函数不能和题目目标脱节。

## Academic integrity boundaries

- 只能用于学习、训练、课程作业辅助、赛前准备、结构检查和结果复盘。
- 不代写完整参赛论文，不代替用户参赛，不承诺获奖或保奖。
- 不伪造数据、代码运行结果、图表、参考文献或实验结论。
- 正在进行的正式竞赛中，必须提醒用户遵守赛事规则、课程要求和学术诚信。
- 所有不确定结论、推断条件和未验证结果都必须标注“需要用户核验”。

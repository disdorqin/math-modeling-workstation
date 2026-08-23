---
name: mm-abstract-polisher
description: Improve or structure a mathematical modeling abstract by summarizing problem goals, models used, key numerical results, conclusions, and limitations. Use after the user provides model results or a draft abstract. Do not invent results, awards, data, or claims.
---

# 数学建模：摘要优化

## Purpose

优化数学建模摘要，使其包含问题、模型、关键结果、结论和局限，不写空泛套话。

## When to use

- 用户提供摘要草稿。
- 用户提供每问模型和关键结果，需要压缩成摘要。
- 需要检查摘要是否夸大或缺结果。

## When not to use

- 用户没有任何结果却要求写完整摘要。
- 用户要求编造数值、奖项或结论。
- 用户要求代写完整论文。

## Required inputs

- 论文主题。
- 每问使用的模型。
- 每问关键结果。
- 用户已有摘要草稿，如果有。

## Workflow

1. 检查摘要是否缺少结果。
2. 检查是否只写过程不写结论。
3. 检查是否夸大。
4. 按问题顺序重组。
5. 保留关键数值并标注需核验处。
6. 输出改写版本、修改理由和压缩版本。

## Output format

```markdown
## 摘要问题诊断

## 改写版摘要

## 修改理由

## 需要核验的数据

## 可进一步压缩版本

## 学术诚信提醒
```

## Quality checks

- 不能编造结果。
- 不能写获奖承诺。
- 摘要要按问题顺序呈现。
- 所有不确定数值标注需要用户核验。

## Academic integrity boundaries

- 只能用于学习、训练、课程作业辅助、赛前准备、结构检查和结果复盘。
- 不代写完整参赛论文，不代替用户参赛，不承诺获奖或保奖。
- 不伪造数据、代码运行结果、图表、参考文献或实验结论。
- 正在进行的正式竞赛中，必须提醒用户遵守赛事规则、课程要求和学术诚信。
- 所有不确定结论、推断条件和未验证结果都必须标注“需要用户核验”。

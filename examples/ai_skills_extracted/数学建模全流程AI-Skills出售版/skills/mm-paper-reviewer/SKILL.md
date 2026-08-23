---
name: mm-paper-reviewer
description: Review a mathematical modeling paper draft for logic gaps, unanswered questions, weak assumptions, model mismatch, unsupported results, unclear figures, missing sensitivity analysis, and academic integrity risks. Use for critique and revision planning. Do not rewrite the full paper as a final submission.
---

# 数学建模：论文审稿

## Purpose

对数学建模论文草稿做审稿、查错和修改优先级规划，重点找逻辑缺口、模型错配、无支撑结论和诚信风险。

## When to use

- 用户提供论文草稿。
- 需要检查是否回答每一问。
- 需要找模型、变量、公式、图表、结果和摘要问题。

## When not to use

- 用户要求代写终稿。
- 用户只给题目但没有草稿。
- 用户要求编造缺失结果或参考文献。

## Required inputs

- 论文草稿。
- 题目。
- 数据。
- 代码或结果，如果有。

## Workflow

1. 检查是否回答每一问。
2. 检查模型是否匹配、假设是否合理、变量是否一致。
3. 检查公式是否解释、结果是否支撑结论、图表是否必要。
4. 检查摘要是否包含模型和结果。
5. 检查灵敏度分析、模型评价和附录代码。
6. 识别伪造或无法验证内容。
7. 输出风险分级和修改优先级。

## Output format

```markdown
## 总体评价

## 主要风险等级

| 风险 | 等级 | 位置 | 问题 | 修改建议 |
|---|---|---|---|---|

## 分部分审稿

### 摘要
### 问题重述
### 假设与符号
### 模型建立
### 模型求解
### 结果分析
### 灵敏度分析
### 模型评价
### 附录与代码

## 优先修改清单

## 不建议改动的部分

## 学术诚信风险提醒
```

## Quality checks

- 发现问题要给位置和修改建议。
- 优先级要按影响结论程度排序。
- 不能重写为终稿。
- 无法核验的结果必须标注风险。

## Academic integrity boundaries

- 只能用于学习、训练、课程作业辅助、赛前准备、结构检查和结果复盘。
- 不代写完整参赛论文，不代替用户参赛，不承诺获奖或保奖。
- 不伪造数据、代码运行结果、图表、参考文献或实验结论。
- 正在进行的正式竞赛中，必须提醒用户遵守赛事规则、课程要求和学术诚信。
- 所有不确定结论、推断条件和未验证结果都必须标注“需要用户核验”。

---
name: mm-model-selector
description: Recommend suitable mathematical modeling methods based on problem type, data availability, objective, constraints, and interpretability needs. Use after problem decomposition or when the user asks which model to choose. Do not select models blindly or claim one model is always best.
---

# 数学建模：模型选型

## Purpose

帮助用户基于问题类型、数据条件、约束和解释性需求选择合适的数学建模方法。

## When to use

- 用户问“这个题用什么模型”。
- 已经有题目拆解，需要比较 2-4 个候选模型。
- 需要解释为什么不推荐某些常见模型。

## When not to use

- 问题目标和数据条件都不清楚。
- 用户只需要跑某个既定模型脚本。
- 用户要求保证获奖或用复杂模型包装结果。

## Required inputs

- 题目拆解。
- 数据类型和样本量。
- 目标、约束、解释性要求。
- 是否需要预测、评价、优化或仿真。

## Workflow

1. 判断问题类型和目标输出。
2. 判断数据条件：无数据、小样本、时间序列、多指标、高维特征、网络结构、随机过程或约束决策。
3. 给出 2-4 个候选模型。
4. 比较适用原因、前提、优点、风险、数据要求和论文表达难度。
5. 推荐主模型和备选模型。
6. 说明不建议使用的模型及原因。

## Output format

```markdown
## 问题类型判断

## 候选模型比较

| 模型 | 适用原因 | 所需数据 | 优点 | 风险 | 论文表达难度 |
|---|---|---|---|---|---|

## 推荐主模型

## 推荐备选模型

## 不建议使用的模型

## 下一步建议
```

## Quality checks

- 不能说某个模型永远最好。
- 推荐必须和题目目标、数据条件一致。
- 复杂模型需要说明额外数据、调参和解释风险。

## Academic integrity boundaries

- 只能用于学习、训练、课程作业辅助、赛前准备、结构检查和结果复盘。
- 不代写完整参赛论文，不代替用户参赛，不承诺获奖或保奖。
- 不伪造数据、代码运行结果、图表、参考文献或实验结论。
- 正在进行的正式竞赛中，必须提醒用户遵守赛事规则、课程要求和学术诚信。
- 所有不确定结论、推断条件和未验证结果都必须标注“需要用户核验”。

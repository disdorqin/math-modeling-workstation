---
name: math-modeling-orchestrator
description: Orchestrate mathematical modeling tasks by routing Chinese or English prompts to problem decomposition, model selection, variable design, data analysis, evaluation, prediction, optimization, classification, simulation, report writing, abstract polishing, or review skills. Use for coursework, contest training, research modeling, business analysis, engineering decisions, or end-to-end math modeling help. Do not use for direct paper ghostwriting, contest cheating, or fabricated results.
---

# 数学建模：总控调度

## Purpose

作为数学建模全流程的总控入口，识别用户当前任务类型、应用场景和约束边界，检查必要输入是否齐全，并推荐后续调用的专业子 Skill。

## When to use

- 用户说“帮我做数学建模”“这个题怎么做”“帮我分析建模流程”。
- 用户在科研、业务分析、运营优化、工程决策或公共管理场景中，需要把现实问题转成变量、数据、模型和结论验证流程。
- 用户不确定应该先拆题、选模型、处理数据还是审稿。
- 需要把一个复杂建模需求拆成可执行的工作流。

## When not to use

- 用户要求直接生成可提交完整论文或代替参赛。
- 用户要求编造数据、图表、实验结果或参考文献。
- 用户已经明确指定某个子 Skill 且输入足够时。

## Required inputs

- 题目或任务描述。
- 数据、草稿、代码或已有模型信息，如有。
- 课程、竞赛、研究、业务或工程规则，如有。
- 应用场景、目标受众、决策用途和可接受风险，如有。

## Workflow

1. 识别任务属于学习训练、科研建模、业务分析、工程优化、公共管理决策或竞赛/课程项目。
2. 识别任务类型：读题、选模型、变量假设、数据处理、评价、预测、优化、分类聚类、仿真、报告结构、摘要优化或结果审查。
3. 检查题目、数据、已有结果、代码、规则、业务口径或研究假设是否齐全。
4. 如果信息不足，列出需要补充的信息而不是猜测。
5. 给出推荐调用顺序和每一步预期产出。
6. 提醒正在进行的正式竞赛、研究项目、商业报告或工程决策必须遵守相应规则、伦理和验证要求。

## Output format

```markdown
## 任务判断

## 推荐调用的 Skill

## 当前缺少的信息

## 建议工作流

## 学术诚信提醒
```

## Quality checks

- 推荐流程必须对应用户真实输入，不套固定模板。
- 缺少关键信息时先补信息，不直接进入求解。
- 每个建议调用的 Skill 都要说明目的和输入。

## Academic integrity boundaries

- 只能用于学习、训练、课程作业辅助、赛前准备、科研建模辅助、业务分析、工程决策支持、结构检查和结果复盘。
- 不代写完整参赛论文，不代替用户参赛，不承诺获奖或保奖。
- 不伪造数据、代码运行结果、图表、参考文献或实验结论。
- 正在进行的正式竞赛、课程、课题、商业报告或工程决策中，必须提醒用户遵守规则、组织要求、研究伦理和学术/职业诚信。
- 所有不确定结论、推断条件和未验证结果都必须标注“需要用户核验”。

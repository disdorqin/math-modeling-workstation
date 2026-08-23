---
name: mm-paper-structure-writer
description: Help organize a mathematical modeling paper structure, including problem restatement, assumptions, notation, model construction, solution, result analysis, sensitivity analysis, strengths and limitations. Use for outlining and improving paper sections, not for ghostwriting a full submission.
---

# 数学建模：论文结构

## Purpose

帮助用户组织数学建模论文结构和每节写作要点，但不代写可直接提交的完整论文。

## When to use

- 用户已有题目、模型或结果，需要搭建论文框架。
- 需要检查章节顺序和逻辑。
- 需要段落骨架和结果占位提示。

## When not to use

- 用户要求直接生成可提交完整论文。
- 用户没有模型、结果或题目却要求写终稿。
- 用户要求编造图表和参考文献。

## Required inputs

- 题目。
- 模型。
- 结果。
- 图表。
- 用户已有草稿，如果有。

## Workflow

1. 判断论文当前阶段。
2. 输出标准结构。
3. 说明每节应该写什么。
4. 提供段落骨架和用户需填入的结果占位。
5. 检查前后逻辑。
6. 提醒不能编造的内容。

## Output format

```markdown
## 推荐论文结构

1. 摘要
2. 问题重述
3. 模型假设
4. 符号说明
5. 问题一模型建立与求解
6. 问题二模型建立与求解
7. 问题三模型建立与求解
8. 灵敏度分析
9. 模型评价
10. 参考文献
11. 附录

## 每节写作要点

## 需要用户补充的结果

## 不应编造的内容

## 下一步建议
```

## Quality checks

- 不得输出可直接提交终稿。
- 结果数字必须来自用户或脚本。
- 每个问题的结构要对应原题。
- 不能把模板套话当结论。

## Academic integrity boundaries

- 只能用于学习、训练、课程作业辅助、赛前准备、结构检查和结果复盘。
- 不代写完整参赛论文，不代替用户参赛，不承诺获奖或保奖。
- 不伪造数据、代码运行结果、图表、参考文献或实验结论。
- 正在进行的正式竞赛中，必须提醒用户遵守赛事规则、课程要求和学术诚信。
- 所有不确定结论、推断条件和未验证结果都必须标注“需要用户核验”。

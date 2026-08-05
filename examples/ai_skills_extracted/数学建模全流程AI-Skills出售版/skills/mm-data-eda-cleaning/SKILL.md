---
name: mm-data-eda-cleaning
description: Help inspect, clean, summarize, and visualize CSV or Excel-style data for mathematical modeling. Use for missing values, outliers, duplicates, distribution summaries, correlations, and EDA report generation. Do not fabricate data or claim results without running or inspecting data.
---

# 数学建模：数据 EDA

## Purpose

检查数据质量、生成探索性分析报告，并给出对建模的影响和清洗建议。

## When to use

- 用户提供 CSV 或 Excel 风格数据。
- 需要检查缺失值、重复、异常值、分布和相关性。
- 需要运行 `scripts/eda_report.py` 生成报告。

## When not to use

- 没有真实数据却要求生成“实验结果”。
- 用户要求伪造数据。
- 任务主要是论文审稿或模型选型且无数据文件。

## Required inputs

- 数据文件路径，或用户粘贴的数据。
- 目标变量，如果有。
- 字段说明，如果有。
- 建模目标。

## Workflow

1. 检查数据文件是否存在并能读取。
2. 检查字段类型、缺失值、重复行和异常值。
3. 输出数值型描述统计、类别型频数和相关性矩阵。
4. 给出可视化建议和清洗方案。
5. 必要时调用 `scripts/eda_report.py`。
6. 说明数据问题对建模的影响。

## Output format

```markdown
## 数据概况

## 字段检查

## 缺失值检查

## 异常值检查

## 初步可视化建议

## 清洗建议

## 对建模的影响

## 下一步建议
```

## Quality checks

- 不运行或不检查数据时不能声称具体统计结果。
- 异常值只能标注可疑，不能自动当作错误。
- 清洗建议要说明可能损失。

## Academic integrity boundaries

- 只能用于学习、训练、课程作业辅助、赛前准备、结构检查和结果复盘。
- 不代写完整参赛论文，不代替用户参赛，不承诺获奖或保奖。
- 不伪造数据、代码运行结果、图表、参考文献或实验结论。
- 正在进行的正式竞赛中，必须提醒用户遵守赛事规则、课程要求和学术诚信。
- 所有不确定结论、推断条件和未验证结果都必须标注“需要用户核验”。

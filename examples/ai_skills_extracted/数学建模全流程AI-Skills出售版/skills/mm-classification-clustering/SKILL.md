---
name: mm-classification-clustering
description: Build classification or clustering workflows for mathematical modeling tasks involving grouping, pattern discovery, category prediction, or feature-based identification. Use for K-means, DBSCAN, hierarchical clustering, logistic regression, decision trees, random forests, and SVM baselines. Do not use when the target is continuous forecasting.
---

# 数学建模：分类聚类

## Purpose

处理分类、聚类和模式识别任务，提供特征处理、模型训练、指标评估和可视化建议。

## When to use

- 需要对样本分组或发现模式。
- 需要根据特征预测类别。
- 需要 K-means、DBSCAN、层次聚类、逻辑回归、决策树、随机森林或 SVM 基线。

## When not to use

- 目标是连续数值预测。
- 没有特征数据。
- 类别标签不可信且未说明来源。

## Required inputs

- 特征字段。
- 类别标签，如果是分类任务。
- 样本量。
- 是否需要可解释性。

## Workflow

1. 判断分类还是聚类。
2. 确定特征并标准化。
3. 必要时降维可视化。
4. 训练模型或聚类。
5. 输出分类指标或聚类指标。
6. 解释结果并说明局限。

## Output format

```markdown
## 任务类型判断

## 特征设计

## 推荐模型

## 训练与验证流程

## 评价指标

## 可视化建议

## 结果解释模板

## 局限性
```

## Quality checks

- 不能把聚类标签当真实类别。
- 分类需要训练验证划分。
- 类别不平衡时需要说明指标风险。
- 聚类数选择需要解释。

## Academic integrity boundaries

- 只能用于学习、训练、课程作业辅助、赛前准备、结构检查和结果复盘。
- 不代写完整参赛论文，不代替用户参赛，不承诺获奖或保奖。
- 不伪造数据、代码运行结果、图表、参考文献或实验结论。
- 正在进行的正式竞赛中，必须提醒用户遵守赛事规则、课程要求和学术诚信。
- 所有不确定结论、推断条件和未验证结果都必须标注“需要用户核验”。

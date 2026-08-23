# C层精华模型卡片交付说明(t99126b84)

- 日期: 2026-08-06 · 执行者: opencode · 分支: m2-contest-grade-paper
- 任务: 把姜启源《数学模型》29章 + 高教社C题优秀论文提炼成中文精华卡片

---

## 1. 交付清单

| 交付物 | 路径 | 说明 |
|---|---|---|
| 32 张模型卡片 | `config/knowledge/cards/*.md` | 与 model-catalog 32 方法一一对应 |
| 卡片索引 | `config/knowledge/index.json` | {model_id, title, family, task_types, card_path, c_fit} |
| 校验测试 | `tests/test_knowledge_cards.py` | 9 项验收测试, 全过 |

## 2. 卡片覆盖(catalog 32 方法全覆盖)

回归族: linear / ridge / lasso / elastic_net / random_forest / gradient_boosting
分类族: logistic / svm
优化族: linear_programming / integer_programming / nonlinear_optimization / dynamic_programming
评价族: ahp / entropy_weight / topsis / entropy_topsis
预测族: gm11 / time_series_arima / exponential_smoothing / holt_winters / moving_average
聚类族: kmeans / dbscan
降维族: pca
模拟族: monte_carlo
排队族: mm1 / mmc
关联族: grey_relation
插值族: interpolation
随机过程族: markov_chain
图优化族: graph_network
微分方程族: ode_modeling

## 3. 论文佐证统计(真实读取 PDF 内容)

- **OCR/文本真实解析 14 篇高教社C题优秀论文 PDF**(PyMuPDF + rapidocr 中文 OCR):
  2010输油管布置 / 2011养老金模型 / 2015月上柳梢头 / 2016电池放电 / 2017颜色浓度 /
  2018会员画像 / 2020信贷决策 / 2022玻璃成分 / 2023蔬菜定价(C050/C126/C228/C235) /
  2024农作物种植 / 2025 NIPT
- **26 张卡片含真实高教社C题论文佐证**(远超 ≥5 要求), 每条标注 年份+题目+如何用+具体数字:
  - linear: 2016放电曲线二次回归(R²>99%) / 2018激活率拟合(R²=0.7419)
  - kmeans: 2018会员四类聚类 / 2023蔬菜热销分级(K-means++) / 2020企业风险聚类
  - linear_programming: 2010输油管最优(282.7万) / 2024农作物种植(LINGO)
  - monte_carlo: 2024四因素1000组随机模拟风险决策
  - markov_chain: 2018会员活跃状态转移矩阵(激活率7.46%)
  - grey_relation: 2022玻璃成分关联 / 2023蔬菜指标关联(>0.5)
  - dynamic_programming: 2025 NIPT时点优化(BMI分5段) / 2023蔬菜动态规划补充
  - ahp: 2017影响因子(0.414/0.586) …… 等
- 部分模型(ridge/lasso/elastic_net/dbscan/排队族/pca/指数平滑等)在 C 题获奖论文中未作为独立模型出现, 卡片注明「作为稳健性/对比方案」, 不虚构证据。

## 4. 校验结果

- `pytest tests/test_knowledge_cards.py` 9 项全过: 卡片数≥20 / 6字段齐全 / LaTeX公式 / index-catalog 对齐(32=32) / 佐证≥5 / 确定性知识无RAG标记
- 全量 `pytest tests/` 无回归(全部通过)

## 5. 设计对齐

- 遵循 `docs/knowledge-base-tiered-design-2026-08-06.md` 卡片字段格式:
  适用场景 / 核心公式 / 建模步骤 / C题适用性 / 论文佐证 / 易错点
- 卡片为**确定性知识**(md + json), 未引入 RAG, 后续可在 model_plan 阶段按关键词确定性注入。

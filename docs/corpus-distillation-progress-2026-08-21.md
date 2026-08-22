# 本地优秀论文批量蒸馏进展（2026-08-21）

本阶段目标不是逐题生成论文再人工对比，而是把本地优秀论文库作为训练语料，批量蒸馏成可供 Paper Engine、Abstract Quality、Visual Quality、Validation Prior 使用的结构化先验。

## 当前本地语料

- 本地优秀论文 PDF：396 篇
  - MCM/ICM 优秀论文：177 篇
  - CUMCM/高教社优秀论文：219 篇
- 自动识别 C 题优秀论文：85 篇
  - MCM C：56 篇
  - CUMCM C：29 篇
- C 题年份覆盖：2010、2012、2018、2019、2020、2021、2022、2023、2024、2025

## 已落地流水线

新增 `src/mathworkstation/corpus_distillation.py`，支持：

1. 批量扫描本地 excellent-paper corpus；
2. 自动识别比赛、年份、题号、奖项与重复组；
3. 近年风格权重与经典建模逻辑权重分离；
4. 非 C 论文只能贡献 style/layout prior，不能污染 C 题 modeling prior；
5. PyMuPDF -> PyPDF -> pdftotext 文本层 fallback；
6. Fast Distillation Pass：摘要、数值密度、方法链、图表引用、验证类型、模型递进、图用途、页级布局；
7. Teacher Packet：只保留版权安全的统计和结构信号，不复制论文原文；
8. shard/filter：按比赛、年份、C题、offset/limit 分片；
9. 增量 fingerprint cache：后续用户新增论文时只重解析新增/修改文件。

## 已完成的真实训练视图

### C 题全集

- 85 篇进入队列；
- 67 篇成功解析文本；
- 18 篇进入 fallback（主要是 CUMCM 扫描/不可映射文本层）；
- 失败论文没有被当成空文本参与 teacher prior。

67 篇可读 C 论文的时间加权信号：

- 模型链中位长度：约 4；
- Figure 引用中位数：约 24；
- Table 引用中位数：约 10；
- sensitivity/robustness prevalence：0.7568；
- uncertainty interval prevalence：0.6198；
- error metric prevalence：0.5861；
- holdout/cross-validation prevalence：0.4961。

### 现代 MCM-C 主 Teacher（2023–2025）

- 41 篇 C 题 O 奖；
- 41/41 成功解析；
- 2023：12；2024：11；2025：18。

现代时间加权中位信号：

- 页数：25；
- 摘要信息单位：453；
- 摘要数值 token：13；
- 摘要方法数：2；
- 模型链长度：5；
- Figure 引用：26；
- Table 引用：10；
- workflow/framework signal prevalence：0.1958。

现代 MCM-C 图用途 prevalence：

- data distribution：0.6813；
- time series / trend：0.4356；
- sensitivity / uncertainty：0.3936；
- result comparison：0.3187；
- physical/geometric mechanism：0.2208；
- workflow/framework：0.1958。

现代 MCM-C 验证 prevalence：

- sensitivity/robustness：0.9024；
- uncertainty interval：0.8293；
- error metrics：0.7317；
- holdout/cross-validation：0.7073；
- parameter search：0.3171；
- explicit model comparison：0.0488。

这个结果支持一个重要结论：优秀论文高频出现的是稳健性、不确定性和验证，而不是强制堆模型对比。Paper Engine 不应为了模仿优秀论文而虚构对照模型。

### 2024 MCM 全题型 Style Teacher

35/35 解析成功。视觉/写作通用信号允许贡献给 C 题 style prior，但不进入 C 题建模先验。

- workflow/framework prevalence：约 0.2474；
- sensitivity/uncertainty figure prevalence：约 0.5928；
- data distribution：约 0.5052。

11 篇 2024 MCM-C 中 sensitivity/robustness signal 为 1.0。

### CUMCM 近期 Teacher

2023–2025 本地 37 篇国赛优秀论文中：

- 14 篇存在可用 Unicode 文本层；
- 23 篇为扫描/字体映射型 PDF，需要后续 visual/OCR fallback；
- 2023 C 的 4 篇均成功解析。

当前 CUMCM-C text prior 暂时以 2023 深度 corpus 为主：

- abstract units：约 851.5；
- abstract numeric tokens：约 10；
- abstract method count：约 3.5；
- model sequence：约 6.5；
- figure mentions：约 13；
- table mentions：约 13。

2024/2025 CUMCM 扫描论文不能被伪装成已完成 text teacher；待 visual fallback 验证后再升级。

## 已接回工作站

新增：

`config/ref_models/modern_competition_paper_prior_v1.json`

并已经让 `PaperQualityBenchmarkService` 优先读取现代先验：

- MCM_C：2023–2025 41 篇现代 C 题 O 奖主 Teacher；
- CUMCM_C：2023 可读 C 题 + 已有深度 2023C profile；
- `reference_entries`、raw image count、image area ratio 当前不作为硬 Gate，因为批量解析存在数字列表误计数和整页背景图问题；
- bibliography truth 仍由 verified-reference subsystem 管理。

## 工业化增量机制

新增 `distill_registered_corpus_cached(...)`：

- 用 source fingerprint 判断 PDF 是否改变；
- 旧论文直接复用 fingerprint；
- 用户新增/替换论文才重新解析；
- 即使重复组数量变化，也会刷新权重；
- cache 建议存放在 `output/corpus_distillation/`（已被 gitignore 忽略）。

因此后续用户继续下载论文时，不需要再次从头吃完整个语料库。

## 当前已验证

- `tests/test_corpus_distillation.py`
- `tests/test_paper_quality_benchmark.py`
- `tests/test_cumcm_2010_research_gate.py`

最新组合：10/10 PASS。

CodeGraph 已同步，索引 up to date。

## 下一阶段优先级

1. 把 CUMCM 2024/2025 扫描论文接入视觉 fallback，不阻塞文本 teacher；
2. 将 Modern Prior 进一步供 Figure Planner / Abstract Student / Validation Planner 使用，而不仅是 PaperQualityBenchmark；
3. 对 2010C、2023C、Wordle 重新跑现代 teacher 校准后的 Golden Gate；
4. 用户新增论文后使用 incremental cache 只蒸馏新增文件；
5. 只有真实 corpus 反复暴露的能力缺口才新增通用功能。

## 后续最希望补充的论文

优先级从高到低：

1. 2024–2025 国赛 C 题一等奖/优秀论文，最好是原始可搜索文本 PDF；
2. 2023–2025 国赛中视觉排版特别优秀、流程图/结果图明显好的论文（题型不限，用于 Style Teacher）；
3. 2025 国赛 C 题更多不同解法；
4. 2024–2025 美赛 C 题其他高奖级论文，如果能获得 Finalist/Meritorious 作为负/中间样本更好；
5. 同一道题不同奖级的论文（O/F/M/H 等），用于学习“优秀论文和普通论文到底差在哪里”，比单纯增加更多 O 奖更有训练价值。

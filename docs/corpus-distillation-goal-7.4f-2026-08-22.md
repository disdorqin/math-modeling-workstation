# Goal 7.4F — Corpus Distillation & Prior Factory

日期：2026-08-22

本阶段把本地优秀数学建模论文库从“少量人工 benchmark”升级为可增量、分层、可路由的批量语料蒸馏系统。目标不是模仿某一篇论文或训练固定文风，而是从大量优秀论文中提取可泛化的结构、视觉、叙事与验证先验，并在新题中按赛制、年代、题型和任务族动态组合。

## 当前训练覆盖

已登记并完成 fingerprint 的优秀论文记录共 1018 篇：

- MCM/ICM：799 篇
- CUMCM：219 篇
- C 题记录：162 篇
- 2023–2025 近年论文：254 篇
- 全文结构化 PARSED：843 篇
- 扫描/无可靠 Unicode 文本层、仅进入视觉层 VISUAL_ONLY：175 篇
- 真失败 FALLBACK_REQUIRED：0 篇

注意：资料根目录总 PDF 数高于 1018，因为其中还包含赛题、课程资料、模型资料等。本阶段训练集合只使用 registry 中明确标记为 `excellent_paper_corpus` 的优秀论文资产，避免把题面或教程误当成优秀论文训练样本。

## 流水线

```text
Excellent Paper Corpora
        ↓
Registry Scan / year / competition / problem letter / duplicate group
        ↓
Fast Fingerprint
        ├─ text/abstract/method/result/validation signals
        ├─ figure/table role signals
        └─ cheap page/layout/scan signals
        ↓
Incremental Fingerprint Cache
        ↓
Prior Bank
        ├─ competition slices
        ├─ C-only slices
        ├─ modern/classic era slices
        ├─ task-family slices
        └─ student views
        ↓
PriorRouter
        ↓
Paper Engine + PaperQualityBenchmark
```

## 工业化机制

### 增量缓存

`output/corpus_training/fingerprint_cache.json`

缓存按 PDF 路径、文件大小、mtime 和 pipeline schema 校验。新增或替换论文只重新解析变化文件。分年份/比赛的 shard 写入同一全局 cache，不会覆盖旧 shard。

### 扫描件隔离

扫描型 PDF 不进行伪 OCR。若页面无可靠文本层，则标记为 `VISUAL_ONLY`。这类论文可以贡献页数、扫描比例、可用布局信息，但不会贡献摘要、模型链、方法选择或 C 题建模先验。

整页扫描 raster 和 tiled scan 已与论文内嵌科学图分离，避免把“一页扫描图”误记成“一张科研图”。

### 双权重

- `style_weight`：近年论文权重更高，用于视觉、摘要、版式和现代呈现。
- `modeling_weight`：只允许 C 题论文贡献，经典 C 题仍保留较高建模逻辑权重。

非 C 题可以贡献现代视觉/排版风格，但不能主导 C 题建模逻辑。

## Prior Bank

产物：

`config/ref_models/distilled_prior_bank_v1.json`

当前共 19 个 prior slices，并提供 5 个 student 视图：

- abstract
- figures
- layout
- validation
- narrative

核心切片包括：

- `competition:MCM:C`
- `competition:MCM:C:modern`
- `competition:MCM:modern`
- `competition:CUMCM:C`
- `competition:CUMCM:C:modern`
- `competition:CUMCM:modern`
- classic / transition / modern era
- C-only task-family slices

PriorRouter 在新题上动态组合赛制、C 题、现代视觉和任务族先验，不建立单一 `GlobalStyle`。

摘要 calibration 优先使用 C-modern；视觉可以使用同赛制全题型 modern。这样既保持 C 题核心，又利用其他题型学习现代视觉表达。

## 全量蒸馏得到的主要统计信号

基于当前 1018 篇语料：

### 全体可解析论文

- 摘要 information units 中位约 465
- 摘要 numeric tokens 中位约 12
- 模型链长度中位约 3
- figure textual mentions 中位约 22
- table textual mentions 中位约 9
- workflow/framework 信号约 16.2%

### 2023+ 可解析论文

- 摘要 information units 中位约 462
- 摘要 numeric tokens 中位约 13
- 方法数中位约 2
- 模型链长度中位约 4
- figure textual mentions 中位约 24
- workflow/framework 信号约 21.9%

### 2016–2020 对照组

- 模型链长度中位约 2
- figure textual mentions 中位约 19
- workflow/framework 信号约 9.6%

目前全库统计支持一个稳定趋势：近年优秀论文更倾向于更长的方法链、更高的图表引用密度和更强的 workflow/framework 表达，但这些频率只能用于 calibration，不能转化成“必须堆模型/堆图”的配额。

### 近年高频图表角色

按当前文本 caption/mention 规则，较常见的功能包括：

- data distribution
- sensitivity / uncertainty
- result comparison
- time-series / trend
- workflow / framework
- physical / geometric mechanism

图表角色只用于提醒 Figure Planner 检查“是否有证据值得画”，绝不因为 corpus 中常见就凭空补图。

### C 题验证先验

当前 C-only 语料中较稳定的验证信号包括：

- sensitivity / robustness
- error metrics
- uncertainty interval
- cross-validation / holdout
- parameter search

Prior Bank 的 universal rule 只要求在任务语义允许时检查合适的验证方式，不要求所有题强行拥有全部验证。

## Paper Engine 接入

`ResearchStatePaperService` 已加载 `PriorRouter`。生成论文时会基于：

- competition profile
- Research State 中实际 task families

生成并持久化：

`review/paper_prior_route.json`

该 route 是软先验和可审计元数据，不直接向正文注入 corpus 文本。

`PaperQualityBenchmarkService` 已优先读取：

`distilled_prior_bank_v1.json -> competition:<MCM|CUMCM>:C:modern`

若新 Prior Bank 不存在才回退到旧 `modern_competition_paper_prior_v1.json` 和早期人工 corpus benchmark。

因此 1018 篇训练结果已经真正进入论文成品质量校准，而不是仅作为离线统计。

## 回归测试

本阶段核心测试：

- corpus distillation / cache / VISUAL_ONLY / scan handling
- Prior Bank / PriorRouter / competition isolation / C-only modeling isolation
- PaperQualityBenchmark new-prior preference

集中测试：15/15 PASS。

真实 Paper Engine 回归：

- MCM 2018 Energy
- CUMCM 2010C
- MCM/CUMCM C paper profiles

9/9 PASS。

Wordle 三个关键门：3/3 PASS。

Energy 在新 1018-paper 现代成品校准下新增 `excellent_c_document_density_calibration=REVIEW`，但：

- Research State PASS
- Competition auditor 无 block
- 同题 O-award full-text benchmark PASS
- VisualQuality PASS
- readiness `internal_pass=True`

因此它被正确解释为 DOCUMENT 层的“现代成品仍可增强”，不是 Research FAIL。旧测试已更新为检查这种分层语义，而不是为了维持旧绿灯而放宽新 benchmark。

## 目前明确的边界

1. 175 篇扫描论文没有做 OCR，因此文本/模型先验不会使用它们。
2. `reference_entries` 的快速规则仍可能把编号列表算作参考文献，因此该指标不进入新硬 Gate；参考文献真实性继续由 VerifiedReference 子系统负责。
3. `figure_mentions` 是文本引用密度，不等同于唯一科学图数量。当前只作为保守的文档密度 calibration，不应理解为图数量配额。
4. Corpus 只蒸馏规律、分布和论证结构，不保存优秀论文段落供改写，也不因为算法出现频率高而推荐算法。

## 下一步

下一阶段不再继续扩 corpus 基础设施。建议直接进入：

1. 用新 Prior Bank 重审 CUMCM 2010C、Wordle、Energy 的最低 DOCUMENT gate；
2. 优先修真实摘要密度、图表论证链、表格和最终排版，而不是增加模型复杂度；
3. 选择一个 2024/2025 C 题做新 Golden Case，验证 modern prior 对未人工针对题目的泛化；
4. 用户以后新增论文时，只跑 incremental distillation，再重建 Prior Bank 和回归测试。

本阶段至此可以视为：**Corpus Training / Distillation 基础链路完成，进入“用训练结果改论文成品”的阶段。**

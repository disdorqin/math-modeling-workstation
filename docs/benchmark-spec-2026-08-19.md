# Competition Benchmark Specification — 2026-08-19

目的：打破“自己生成 -> 自己 rubric -> 自己 benchmark -> 自己证明优秀”的 self-validation loop，建立能真正检验数学建模能力的外部/真实赛题 benchmark。

## 1. Benchmark 层级

### L0 — Unit / Regression

用途：保证 schema、registry、router、solver adapter、paper gate 等代码行为不回归。

允许：synthetic fixture、FakeProvider、deterministic rubric。

禁止结论：不得用 L0 证明“比赛级能力提高”“接近国奖/O奖”。

### L1 — Historical Problem Functional Gate

使用真实历史赛题、真实题面、真实数据、完整 AutoPipeline/Research Round。

第一固定 Gate：2023 MCM Wordle。

验收重点不是最终得分，而是：

- 子问题识别是否完整；
- 每个子问题 task family 是否正确；
- 方法是否针对该子问题；
- validation 是否匹配任务；
- 证据与结论是否独立可追踪；
- deliverable node 是否区别于 modeling node；
- paper 是否来自 research state 而不是 generic template。

### L2 — Cross-Problem Historical Benchmark

至少 5 题：

- 3 道 CUMCM，覆盖至少评价/预测/优化/机制仿真中的三类；
- 2 道 MCM/ICM，覆盖与 CUMCM 不同的任务结构。

同一套代码、同一公开配置跑完整流程。不得针对每题手工写死答案。

### L3 — Excellent Paper Corpus Comparison

只有在真正读取/OCR/结构化抽取优秀论文全文后才可启用。

本地资料路径：`D:\作业\竞赛\大学生数学建模\美赛\备赛\资料`。

此前仅依据文件名/已知结构的 comparator 结论一律视为未验证，不作为 L3 证据。

抽取维度：

```text
Question type
Problem decomposition
Model sequence
Why this model
Model transition
Validation type
Sensitivity / uncertainty
Figure purpose
Innovation pattern
Abstract structure
References pattern
Failure / limitation pattern
```

### L4 — Blind Review / Human Competition Quality

至少采用一名不知道系统内部实现细节的 reviewer，或多 reviewer ensemble，对匿名化论文进行结构化评分。

评分必须区分：

- correctness
- modeling appropriateness
- mathematical depth
- validation rigor
- evidence credibility
- insight/innovation
- storyline
- writing/presentation
- contest compliance

系统内部 evaluator 只能作为辅助信号，不能作为唯一裁判。

## 2. 2023 MCM Wordle Gate v1

### SP1 — daily reported results

期望：识别时间趋势/结构突变/外推目标，使用时间感知验证；输出点预测+区间，并解释主要驱动因素/趋势。

失败条件：仍把 `Number in hard mode` 当 SP1 唯一目标；或使用 random split 作为唯一验证。

### SP2 — word attributes vs Hard Mode share

期望：构造 word-level attributes，做 effect/inference 或解释性建模；报告方向、效应、不确定性/显著性或稳健性。

失败条件：直接复用 SP1 best model + RMSE 作为答案。

### SP3 — future guess distribution

期望：输出 1,2,3,4,5,6,X 的分布，并满足和为约 100% 的结构约束；有 prediction uncertainty。

失败条件：只输出单一连续目标。

### SP4 — difficulty classification + EERIE

期望：明确 difficulty construct、类别/排序定义、word features、分类/有序模型、准确性评估，并对 EERIE 给出独立 evidence。

失败条件：复用 SP1 回归 RMSE。

### SP5 — interesting features

期望：EDA/discovery node，至少产生一个非平凡、可验证、与前四问不同的发现；不要求训练 supervised model。

### SP6 — editor letter

期望：`task_family = synthesis/deliverable`；依赖 SP1-SP5 accepted answers/evidence；不得创建 solver/model training experiment；信件内容只使用前面已接受结论。

## 3. Paper-level hard failures

任一出现则本轮 Competition Gate 不得 PASS：

- 内部 `claim-*` / `result-*` / `table-*` / `figure-*` ID 泄漏到最终用户论文；
- 题目无关单位/符号/公式模板污染；
- references 为空、虚构、或只有“方法论框架”而无真实文献；
- research defect 仅通过文字润色掩盖；
- 多个性质不同的 subproblem 共享同一 model/metric answer；
- 数据泄漏或验证协议与任务结构明显冲突；
- editor letter / policy memo / summary deliverable 被当作训练节点。

## 4. 对比原则

每次 Section Gate 都保存 before/after：

- ProblemGraph snapshot
- per-subproblem plan
- experiment/evidence lineage
- validation protocol
- final paper
- reviewer findings

比较必须回答：

1. before 的具体错误是什么；
2. after 是否消除了这个错误；
3. 是否引入新的退化；
4. 提升来自真实 research state 还是仅文字变化。

## 5. 禁止的 benchmark shortcut

- 只跑 synthetic fixture；
- FakeProvider 自己回答自己评分；
- 用项目自建 deterministic rubric 的 100/100 当比赛能力；
- 根据优秀论文文件名猜结构；
- 只比较关键词覆盖率；
- 只检查 PDF 能否生成；
- 只看测试数量；
- 为单个赛题硬编码题号/答案然后宣称通用能力提升。

## 6. Section 1 的最低通过标准

在 2023 Wordle 上，至少观察到：

```text
SP1 != SP2 != SP3 != SP4 != SP5
SP6 = synthesis/deliverable
```

且每个建模 SP 具有独立 task family / selected method / validation / evidence / answer。做到这一点后，Section 1 才算从“数据结构存在”进入“研究主线真实分叉”。

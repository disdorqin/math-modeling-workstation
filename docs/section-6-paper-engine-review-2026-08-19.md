# Section 6 Progress Review — Research-State Paper Engine

Last updated: 2026-08-20 01:20 +08:00

## Status

**Section 6 overall: INTERNAL GATE PASS.**

**Milestone 6.1 — Research-State Paper Architecture: PASS.**

**Milestone 6.2A — Same-problem O-award gap-driven refinement: PASS（Wordle 全文文本/结构/研究校准层）。**

**Milestone 6.2B — 2018 MCM C Energy cross-problem + same-problem O-award calibration: PASS.**

Section 6 的内部 Gate 已经从单题验证升级为两道 materially different MCM C 历史题验证。当前仍不等于 O/F 认证：blind/human review 与 PDF 视觉版式核验属于 Section 7 / 外部验证，不允许由内部代码自证。

本里程碑通过不等于“已经达到 CUMCM 国奖 / MCM-ICM O/F”。它只证明：论文可以从真实多子问题 Research State 生成，并且旧 Wordle 论文已经确认的 P0 污染能够被同一套新 Auditor 阻断/消除；同时优秀论文提炼稿暴露的结构性差距可以驱动 Paper Engine 修改。

## 原来具体有什么问题

旧 2023 MCM Wordle `paper/final.md` 的主要问题不是句子不好看，而是 Paper Engine 的来源错误：

```text
whole-problem ModelPlan / best model
-> generic section template
-> generic formula/unit/prose
-> paper
```

因此出现：

- SP1-SP6 同一模型/RMSE 叙事；
- editor letter 被当作模型训练节点；
- `A_t / B_t / x_t` 等无对应 solver 的公式；
- kWh/kW/CNY 等跨题单位污染；
- internal artifact/result/table/claim/figure ID 泄漏；
- References 使用占位/方法论元话语；
- 图只是指标展示，未承担具体论证任务；
- 结论更像实验报告，没有转成可执行建议。

## 当前真实主链

Section 6 已经实现并验证：

```text
ProblemGraph
-> ModelGraph
-> EvidenceGraph
-> NarrativeGraph
-> Research-State Paper
-> CompetitionPaperAuditor
-> Document defect -> paper repair
-> Research defect -> Section 5 exact subproblem repair
```

### ModelGraph

逐 subproblem 固化：

- task family
- selected method
- candidate methods
- experiment
- solver evidence
- validation protocol / gate / artifacts
- dependencies

SP6 是 DELIVERABLE，无 experiment。

### EvidenceGraph

逐 subproblem 固化 active：

- Answer
- Result
- Table
- FINAL Figure
- verified Claim（若存在）
- source artifacts
- synthesis dependency closure

### NarrativeGraph

只接受 ModelGraph + EvidenceGraph 已闭合的节点。它负责把研究状态转成 paper-facing narrative node，但 preview 不暴露内部 registry ids。

## 论文生成规则

### 1. Answer 必须先回答题目，再报告验证指标

修复 `SubproblemEngine._default_answer()`：

- forecasting：目标日期点预测 + 95% 区间 + temporal validation
- distribution forecast：目标分布 + validation
- classification：目标类别 + class probabilities + validation
- explanatory inference：主效应 + bootstrap CI + validation
- exploration：真实探索发现

不再把“RMSE=...”当成问题本身的答案。

### 2. 公式只能来自已执行 Solver

新增 method-specific equation schema，例如：

- ridge objective
- residual-bootstrap interval
- standardized ridge + coefficient bootstrap CI
- multi-output ridge + simplex projection
- multiclass logistic probability
- Spearman rank association

未知 solver 返回空公式列表；禁止 generic state-space 模板填空。

### 3. 假设只能来自 Solver/Validation 前提

逐问生成 method-specific assumptions：

- 时间预测禁止未来泄漏、外推范围有限、bootstrap residual representativeness
- inference 明确 associational-not-causal
- distribution 明确 nonnegative + sum-to-100 composition
- classification 明确标签与 feature schema 一致
- exploration 明确 hypothesis-generating 而非 causal/confirmatory

未知 solver 不生成通用假设。

### 4. 图必须回答一个研究问题

真实 Wordle 当前五张图分别为：

- SP1：future forecast + 95% interval
- SP2：standardized effects + bootstrap CI
- SP3：future distribution + component uncertainty
- SP4：class probability distribution
- SP5：strongest Spearman associations

五问全部命中 semantic plot schema，没有 metric-dashboard fallback。

### 5. 多方案比较不得伪造实验

优秀提炼稿 11/11 都反复出现“分情形/多方案对比”。当前系统不为满足这一模式而伪造 model-performance comparison。

NarrativeGraph 现在投影真实 ProblemGraph / ModelingBrain candidate considerations：

- selected
- PASS / NEEDS_SOLVER / REJECT / PLANNED
- source
- rationale

论文明确写：未执行 alternative 不赋予虚构性能指标。

### 6. 结论必须落到 practical recommendation

优秀提炼稿在 2010/2011/2018/2020/2023/2024 六年反复出现“结论落到业务/策略建议”。

新 Paper Engine 新增 evidence-bounded recommendation layer：

- forecast：使用 point + interval，而不是只用点值；
- inference：用于解释关联，不宣称因果；
- distribution：使用完整分布与 uncertainty；
- classification：类别 + probability 共同表达；
- exploration：作为 follow-up hypothesis，而非确认性事实。

不新增任何实验数字。

## 优秀论文资料如何被使用

工作区内：

`config/ref_models/excellent_c7/`

共有 11 份 2010–2025 优秀 C 题**提炼稿**。已重新核验文件本身明确自称“提炼稿”。

本阶段只把它们作为：

- structure prior
- narrative prior
- cross-year recurring strong-point taxonomy

不会把它们冒充优秀论文全文，也不会把“关键词命中”解释成获奖概率。

为避免中文提炼稿 vs 英文 MCM 论文造成假差距，CompetitionPaperAuditor 增加了保守的双语语义代理，例如：

- 模型假设 <-> assumptions/scope
- 子问题逻辑衔接 <-> depends on/synthesis/cross-question
- 结果量化 <-> accepted quantitative results
- 敏感性 <-> robustness/bootstrap/uncertainty
- 优缺点 <-> strength/limitation/improvement

这些代理只能**消除明显假阳性 REVIEW**，不能制造 PASS。

## Wordle 真实 old-vs-new Gate

同一个 `CompetitionPaperAuditor`、同一个真实 Wordle Research State：

### Old baseline

旧 `paper/final.md`：**BLOCK**。

重新检出：

- INTERNAL_REGISTRY_ID_LEAK
- FOREIGN_ENERGY_UNIT_POLLUTION
- FOREIGN_CURRENCY_UNIT_POLLUTION
- reference placeholder / missing concrete bibliography
- 以及既有人工审计确认的 generic state-space 污染

### New Research-State draft

`ResearchStatePaperService` 生成的新稿：当前内部 Gate 为：

```text
BLOCK = 0
REVIEW = 0
```

并通过硬测试：

- Question 1–6 全覆盖
- SP1 包含 2023-03-01 目标预测
- SP3 为真实分布预测
- SP4 为真实 classification
- 至少四种不同方法
- 无 `A_t/B_t`
- 无 artifact/result/table/claim/figure ID
- 有实际表格/semantic figures
- 有 method-registered equations
- 有 concrete verified method references
- excellent_c7 当前已编码跨年份 strong-point 不再留下 unexplained gap

**重要：0/0 只表示当前已编码 Auditor 下无缺陷，不等于优秀论文认证。**

## Bibliography 当前状态

新增最小 verified method bibliography，当前只覆盖已执行方法所需的经典来源，例如 ridge、forecasting、bootstrap、statistical learning/classification。

这解决的是“References 不允许编造/占位”的 P0。

仍未解决：

- Wordle / puzzle / behavioral-domain 的领域文献；
- 更完整的方法来源；
- citation-to-claim coverage；
- full excellent-paper bibliography pattern。

因此 bibliography 仍是 Section 6 后续重点，不应把“有 4 个真实方法来源”理解为文献质量已经优秀。

## Competition Auditor -> M-Round Repair

CompetitionPaperAuditor finding 已接回 Section 5：

- DOCUMENT BLOCK -> paper / paper_draft
- DOCUMENT REVIEW -> paper / refinement_loop
- RESEARCH validation -> exact SP / experiments
- RESEARCH solver/modeling -> exact SP / model_plan
- RESEARCH evidence -> exact SP / model_selection

已新增测试验证：

- internal ID leak 留在 paper cell；
- SP3 narrative validation defect 回到 `SP3 / validation / experiments`。

## 当前验证

本阶段最新：

```text
Section 1–6 research/paper/recurrent core: 49 passed
Protected legacy WIP regression group: 31 passed
Total across these non-overlapping targeted groups: 80 passed
```

完整：

```text
python -m pytest -q
```

仍在 collection 阶段只有既有 2 个环境错误：

- `tests/test_agent_runtime_semantics.py`
- `tests/test_runtime_conformance.py`

根因仍为 Python 3.11 + Tenacity 5.1.5 使用已移除的 `asyncio.coroutine`。

## 客观剩余差距

即使当前内部 Gate 0/0，距离真正优秀论文仍有至少这些未验证项：

1. **全文优秀论文 corpus 尚未读取。** `excellent_c7` 是提炼稿，不是全文。
2. **没有 blind/human competition review。** 当前 Auditor 仍是我们编码的标准，虽然已减少 self-validation，但不能独立证明 O/F。
3. **替代方案目前主要是 feasibility comparison。** 不是所有 subproblem 都做了多个可执行方法的 head-to-head experiment；不能声称已有充分 model comparison。
4. **领域 bibliography 薄。** 当前主要是方法论经典来源。
5. **prose 仍是 deterministic research-state renderer。** 结构和证据边界更可靠，但语言成熟度、摘要压缩、叙事自然度还需要 evidence-locked writer/reviewer 提升。
6. **semantic figures 已有研究目的，但视觉 polish/版式还未与真实优秀全文逐图比较。**
7. **跨赛题泛化未验证。** Section 6 当前第一 Gate 仍只有真实 Wordle；至少还需要一题不同 family 的历史题验证 Paper Engine。

## Goal 6.2A — 同题 O 奖全文差距驱动改进

### 原始优秀论文现在已真实可读

重新通过 DevSpace 验证：

`D:\作业\竞赛\大学生数学建模\美赛\备赛\资料`

当前可以只读枚举并用本机 `pdfinfo/pdftotext` 解析原始 PDF。最重要的是：资料中存在 **2023 MCM C Wordle 同一道题的 O 奖论文至少 12 篇**。

因此本阶段不再用“自己的 rubric + 自己的论文”做主要优秀标准，而是先选择 6 篇同题 O 奖全文：

- 2307166
- 2309397
- 2311717
- 2314151
- 2318036
- 2322645

仓库只保存派生 profile，不保存参考论文全文：

`config/ref_models/mcm_2023_c_wordle_oaward_fulltext.json`

### 六篇同题 O 奖的真实派生统计

全文文本结构抽取显示：

- Wordle / word feature engineering：6/6
- Wordle game semantics：6/6
- 显式 uncertainty / interval：6/6
- data preprocessing：6/6
- editor letter：6/6
- custom domain construct：5/6
- player/popularity mechanism：5/6
- workflow/model-framework figure signal：5/6
- strengths/weaknesses：5/6
- cross-validation / holdout：6/6

中位数仅作为描述性校准，不作为机械配额：

- 约 25 页
- abstract 约 483 words
- abstract 约 19 个 quantitative tokens
- abstract 约 5 类方法
- 全文约 7 类方法
- Figure 编号约 15
- Table 编号约 8
- References 约 9 条

这些数字不能被解释成“达到数量就能 O 奖”。它们只说明旧系统的“格式完整 + 一个模型 + RMSE”研究密度远远不够。

### SameProblemExcellentAssessor

新增：

`src/mathworkstation/same_problem_benchmark.py`

主原则：

- 单篇 O 奖的花哨算法不能变成强制标准；
- 只有多篇同题论文反复出现的能力才升级成 gap；
- gap 分 `DOCUMENT` 与 `RESEARCH`；
- RESEARCH gap 必须回 Section 2–5，Paper Writer 无权通过措辞修复；
- raw reference-paper text 不进入仓库。

第一轮对 6.1 Wordle 新稿的可信 gap 为：

```text
DOCUMENT
- data preprocessing narrative
- explicit strengths/weaknesses
- actual editor letter

RESEARCH
- SP2/SP3/SP4: stronger Wordle-specific construct
- SP1: popularity/player-dynamics mechanism alternative
```

### 三个 DOCUMENT gap 已真实修复

Paper Engine 现在新增：

- `Data Preprocessing and Feature Construction`：仅从 accepted solver plan 恢复真实列/时间顺序/feature schema，不倒编清洗故事；
- `Model Evaluation: Strengths, Weaknesses, and Robustness`：weaknesses 直接来自各 node limitation；
- 真正的 `Letter to the Puzzle Editor of The New York Times`：只综合 SP1–SP5 accepted answers/recommendations，不新增数字。

同题全文 DOCUMENT alignment 已从 REVIEW -> **PASS**。

### SP2/SP3 的 Wordle-specific construct：不是照抄 O 奖，而是独立设计 + ablation

在已有 8 个词特征之外，基于**题目自身单词序列**构造：

- `positional_letter_surprisal`：位置条件字母负对数概率；
- `letter_transition_surprisal`：相邻字母一阶转移负对数概率。

没有使用外部词频/熟悉度数据，因此不会偷偷扩大数据权限。

真实 Wordle ablation：

- SP2：positional surprisal 在 4 个 temporal holdout 下 MAE 均改善；RMSE 只有约 0.04–0.14% 极小退化；bootstrap effect CI 在 3/4 split 排除 0。因此保留用于 explanatory inference。
- SP3：两个 surprisal 一起使用，在 15% / 20% / 25% / 30% 四个 temporal holdout 下 RMSE 与 MAE **全部改善**；20% holdout RMSE 约 `4.798 -> 4.723`，MAE 约 `3.576 -> 3.505`。
- SP4：新增特征多 seed 表现不稳定，因此分类仍保留原 base8，不为了“创新”强行加入。

`wordle_task_feature_sets()` 固化了这种 per-subproblem feature contract；不再把一个 feature set 强行服务所有问题。

### SP1：机制模型真实执行，但被稳健性 Gate 拒绝

没有照抄 O 奖常见 SIR，因为当前数据没有可辨识的潜在/活跃/退出玩家三舱室观测。

新增独立 SolverPlugin：

`gold.popularity_lifecycle`

机制为两阶段 piecewise exponential popularity lifecycle：

- log report count；
- training-only change-point selection；
- change point 前后允许不同衰减率；
- temporal holdout；
- centered residual bootstrap interval；
- 明确 guard：不声称观测到了 latent player compartments。

真实多 horizon 对比：

| test holdout | Ridge RMSE | Holt RMSE | Lifecycle RMSE |
|---:|---:|---:|---:|
| 15% | 8792 | 6541 | 3608 |
| 20% | 9900 | 6005 | 3145 |
| 25% | 11106 | 4676 | 12755 |
| 30% | 12037 | 4542 | 14394 |

因此：

- Lifecycle 只在 2/4 horizons 胜出，长 horizon 明显崩溃 -> **拒绝作为 accepted model**；
- Holt 在 4/4 horizons 都显著优于旧 Ridge -> **SP1 accepted solver 改为 damped Holt exponential smoothing**。

这比“为了像 O 奖就套 SIR”更符合研究证据。

### Head-to-head comparison 也升级为 stress-aware

`SubproblemAlternativeComparisonService.compare()` 现在支持 forecasting temporal stress grid。

原则：

- 至少 3 个 stress splits；
- alternative 至少在 75% splits 上超过 1% tolerance；
- median relative improvement 也必须超过 tolerance；
- validation 不得 FAIL；
- 否则保持 accepted model，即使某个单一 holdout alternative 很强。

并修复语义漏洞：stress decision `KEEP_ACCEPTED` 时，`best_method` 不得残留单 split winner。

AutoPipeline 新增 `compare_subproblem_alternatives()` 生产入口。

NarrativeGraph / Paper Engine 会投影**真实执行过的** head-to-head comparison，包括 stress split、median/worst metric、win rate 和 robust decision；不会给未执行 alternative 编性能数字。

### 6.2A 当前同题 Gate

在真实 Wordle Research State 上执行：

```text
Accepted SP1 = Holt
Alternative 1 = Ridge
Alternative 2 = Popularity Lifecycle
Stress splits = 15%, 20%, 25%, 30%
```

再生成 Research-State Paper 后：

```text
same-problem full-text DOCUMENT gaps = 0
same-problem full-text RESEARCH gaps = 0
same-problem Gate = PASS
```

这代表：**当前已编码的 2023 Wordle 同题 O 奖全文 recurring capability gap 被实证研究闭合。**

## Milestone 6.2B — 2018 Energy cross-problem Gate

第二道真实历史题使用 **2018 MCM C Energy Production / four-state energy compact**。它的任务族组合明显不同于 Wordle：

```text
I-A exploratory profile
I-B historical trend characterization
I-C multi-criteria ranking
I-D multi-entity forecasting
II-A optimization
II-B synthesis/actions
III governors memo
```

官方 `ProblemCData.xlsx` 已验证包含 AZ/CA/NM/TX 四州、1960–2009、605 个指标定义。5 篇同题 O 奖原文（72969/73767/78577/80560/82150）被抽成 derived profile，仓库只保存：

`config/ref_models/mcm_2018_c_energy_oaward_fulltext.json`

同题 5 篇 recurring capability：energy profile / multi-criteria evaluation / 2025-2050 forecast / compact targets-actions / Governors memo 均为 5/5；算法本身高度多样，因此没有把任一 O 奖算法设为强制标准。

### 6.2B 暴露并修复的通用缺口

新增：

- `gold.panel_profile_summary`
- `gold.panel_trend_characterization`
- `gold.entropy_topsis`
- `gold.panel_holt`
- 对应 profile/trend/MCDM/panel-forecast validation protocols
- multi-entity profile/trend/forecast/MCDM/optimization semantic figures + result projection
- panel Holt / panel trend / Entropy-TOPSIS / LP method-specific equations and assumptions

第二题还暴露了真正的 Paper Engine 泛化污染：Wordle dataset、puzzle background、NYT editor letter 被硬编码，且 renderer 只取第一个 synthesis node。现已改为 dependency-aware prompt-specific deliverable renderer：Wordle 生成 editor letter，2018 生成 Governors' Memo，所有 synthesis nodes 都保留。

Readiness 的 alternative-comparison 语义也被收紧：`PLANNED` candidate 不再因为名字碰巧匹配 Solver alias 就自动升级成“可执行对照实验”；只有显式 `PASS` / `NEEDS_SOLVER` feasibility 才能产生 comparison / solver-depth gap。

### 真实 2018 结果

最小透明 profile 使用 RETCB/REPRB/TETCB/TEPRB/TETPB/TPOPP 派生四个共同维度，完整覆盖 4 states × 50 years = 200 state-years。

2009 Entropy-TOPSIS：

```text
CA > AZ > NM > TX
winner retention under leave-one-criterion-out = 1.0
mean rank Spearman = 1.0
```

Panel Holt 对 4 states × 2 renewable-share targets 的 8 条序列做 temporal holdout，并输出 2025/2050 共 16 个 point + interval forecasts；当前 aggregate holdout 约 RMSE 0.0174 / MAE 0.0132。

II-A targets 明确区分 no-policy forecast 与 historically bounded stretch target，不把优化目标伪装成自然预测或政策因果效果。

### 6.2B 最终内部 Gate

真实官方数据 case 最新：

```text
Research State closure = PASS
Competition BLOCK = 0
same-problem 2018 O-award DOCUMENT gaps = 0
same-problem 2018 O-award RESEARCH gaps = 0
structured excellent-summary alignment = PASS
method bibliography = PASS
domain bibliography = PASS
cross-problem generalization = PASS (2 historical MCM problems)
ExcellentReadiness internal_pass = true
```

唯一非 PASS：

```text
blind_human_competition_review = UNVERIFIED
```

这是故意保留的外部边界，不能通过内部代码自证。

### 当前验证

最新 Section 6 宽回归：

```text
47 passed
```

全仓 `python -m pytest -q` 仍只在 collection 阶段命中已知旧环境问题：Python 3.11 + Tenacity 5.1.5 的 `asyncio.coroutine` incompatibility，影响两个 runtime tests；本轮没有新增 collection/test failure。

Section 5 recurrent 收尾另有 20 passed。

## 下一 Goal — Section 7.1

Section 6 内部 Gate 到此冻结。下一步按 master plan 进入 **Excellent Paper Corpus + External Benchmark**：保留当前 2 道 MCM Gate，再选择 3 道 materially different CUMCM 历史题，形成至少 3 CUMCM + 2 MCM 的跨赛制全文 benchmark，并开始 figure-purpose / abstract-structure / model-transition / visual-layout 外部校准。

原则不变：Reviewer 若发现 Research defect，回 Section 5；只属于表达/叙事/格式的问题才留在 Paper/Corpus 层。

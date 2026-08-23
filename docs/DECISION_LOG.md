# DECISION_LOG

## 2026-08-19 — D001：把首要重构目标从“继续拆 Recurrent cells”切换为 ProblemGraph/Subproblem Engine

### 背景

现有 WIP 已经实现/开始实现 recurrent workstation、round hidden state、repair router、model/experiment cell 等能力。这些工作有效，应保留。

但重新检查 2023 MCM Wordle 真实论文后，发现更早的上游 P0：`ProblemAnalysis` 虽产生 SP1-SP6，主 `AutoPipelineService` 后续仍收缩为单个 ModelPlan / model comparison / best model，并把同一模型与 primary metric 用于多个 subproblem answer。

### 决策

Section 0 完成后，暂缓继续推进旧路线的 R2.1/R2.2 cell 拆分，先做 Section 1 `ProblemGraph / Subproblem Engine`。recurrent workstation 不删除、不回滚，后续在 Section 5 与 ProblemGraph 对齐。

### 原因

如果不先修 subproblem research branching，M-Round 只会更高效地重复错误的“单模型全题”研究状态；先做 cell 重入不能改善真实竞赛建模质量。

### 影响

- 新代码必须兼容现有 `SubproblemContract` / `SubproblemAnswerRecord` / recurrent WIP。
- `auto_pipeline.py` / `paper_contracts.py` 已 dirty，修改只能做最小侵入编辑。
- 第一 Gate 固定使用 2023 MCM Wordle。

---

## 2026-08-19 — D002：内部 deterministic benchmark 降级为 regression evidence

### 决策

`docs/M2_FINAL_REPORT.md` 中 synthetic dataset + FakeProvider + 自建 deterministic rubric 的 100/100 仅表示 L0 regression 通过，不再作为 competition-quality 证据。

### 原因

自生成、自评分、自总结优秀论文会形成 self-validation loop，无法证明真实赛题能力。

### 替代

采用 `docs/benchmark-spec-2026-08-19.md` 的 L0-L4 分层：unit/regression -> historical real problem -> cross-problem -> real excellent-paper corpus -> blind/human review。

---

## 2026-08-19 — D003：未全文读取的优秀论文 comparator 结论视为未验证

### 决策

此前 `docs/c-problem-paper-comparison-2026-08-06.md` 等未真正 OCR/全文读取优秀 PDF 的比较，不作为“接近优秀论文”的证据。

### 后续

Section 7 必须先解决 `D:\作业\竞赛\大学生数学建模\美赛\备赛\资料` 的真实访问，再做结构化全文抽取。

---

## 2026-08-19 — D004：完整 pytest 的 Tenacity collection error 记录为环境基线，不在 Section 1 顺手升级依赖

### 决策

当前 Tenacity 5.1.5 与 Python 3.11.9 不兼容导致 full pytest collection error。Section 1 不为解决研究主线而顺手修改全局 Python 依赖，以免扩大 WIP 风险。

### 约束

每次代码修改至少运行不触发该 collection path 的相关定向测试；环境依赖修复作为独立 issue 处理。

---

## 2026-08-19 — D005：ProblemGraph Research State 不继承旧 SubproblemContract 的“COMPLETED”语义

### 背景

旧 pipeline 在 problem analysis 后就通过 `_complete_subproblem_contracts()` 把所有子问题标为 `COMPLETED`，但那一刻实际上只完成了题意抽取，并没有每个子问题自己的实验、证据和答案。

### 决策

ProblemGraph 从旧 contract 构造 node 时，研究状态统一从 `PLANNED` 开始；只有 node 拥有独立 answer + evidence 且依赖满足后才能成为 `COMPLETED`。新增 `structure_gate / research_gate`，对“COMPLETED without answer/evidence”直接 FAIL。

### 原因

不能让兼容层的历史状态字段继续制造 false completion。旧 contract 暂时保留以避免破坏 PaperContract WIP，但新的 Research State 才是 Section 1 的研究完成真源。

---

## 2026-08-19 — D006：unsupported subproblem family 禁止 fallback 到全题 regression

### 决策

为 `explanatory_inference`、`distribution_forecasting`、`exploratory_analysis` 增加专用执行器；现有 forecasting/classification/optimization/simulation/ranking 继续复用仓库已有 executor。以后找不到专用 executor 时应 BLOCK/显式暴露缺口，不允许偷偷回退到 generic regression。

### 原因

2023 Wordle 已证明“万能回归 fallback”会把不同数学问题压成同一个 RMSE，并进一步污染 Paper Engine。

---

## 2026-08-19 — D007：Section 1 首个真实 Gate 分成 Research Gate 与 Paper Gate

### 决策

2023 Wordle 当前先验证 Research State：SP1-SP5 各自执行不同 family/method/validation，SP6 synthesis，并为 SP1-SP5 注册独立 artifact。该 Gate 已 PASS。

但旧 `final.md` 尚未用新 state 重新生成，因此 Section 1 不能仅凭研究层 PASS 就宣布完全结束。下一道 Gate 必须验证正式 Result/Answer/Claim/Table/Figure lineage 和重生论文，确保六问正文、摘要和 editor letter 真正使用 node-specific evidence。

### 原因

避免再次出现“内部状态看起来正确，但最终论文仍模板化/证据错配”的 self-validation loop。

---

## 2026-08-19 — D008：Skills 只作为 Modeling Brain 的 advisory source，不直接作为 Solver

### 背景

仓库 `examples/ai_skills_extracted/.../skills/` 中存在 model-selector、prediction、classification、optimization、simulation 等 SKILL.md 和 example scripts，但当前没有 runtime skill executor registry。

### 决策

新增只读 `ModelingSkillRetriever`，抽取 SKILL.md 中真实存在的使用/禁用条件、质量检查和方法提示，作为 Modeling Brain 第四类候选来源；不直接执行 example scripts，不复制为第二套 Solver。

### 原因

Skill 的职责是提供 workflow/方法边界，是否可执行必须继续由 SolverRegistry 决定。这样既让 Skills 真正参与选模，又避免 example code 绕开统一 provenance / validation / solver gate。

---

## 2026-08-19 — D009：SolverRegistry 成为“方法是否可执行”的唯一真源

### 背景

Section 2 初版 Feasibility Critic 仍有局部手写 capability map，存在与实际执行器漂移的风险；旧 optimization executor 也只有 bounded-grid，却容易在语义上被当成完整 LP/MILP/NLP。

### 决策

新增统一 SolverPlugin / SolverRegistry；Modeling Brain 通过 `supports_method(method, task_family)` 查询真实 plugin capability。`NEEDS_SOLVER` 候选持久化成 `solver_capability_gap` Artifact。

首批独立 plugin 包括 forecasting、classification、explanatory inference、distribution forecasting、exploration、LP、MILP、K-Means/DBSCAN、bounded-grid、Monte Carlo、ranking。

### 原因

方法检索与计算求解必须分层。知识库里存在某方法不等于项目已经实现该方法；只有 SolverRegistry 有匹配 plugin 才能标 PASS。

---

## 2026-08-19 — D010：ValidationProtocol 作为独立证据，不再把 executor 自报指标视为验证完成

### 决策

Section 4 建立 family-specific ValidationProtocol Registry / Runner。Solver solve 后必须经过独立 validation assessment，并把 validation artifact 写入 `SubproblemExperiment` lineage。

### 原因

同一个 RMSE/CV 不能验证 forecasting、classification、inference、distribution、optimization、exploration。验证协议本身必须是 Research State 的一部分，Reviewer 才能知道应该回退 solver、experiment 还是 paper。

---

## 2026-08-19 — D011：Section 5 的最小修复单元升级为 `subproblem_id + repair_phase`

### 决策

保留现有 Recurrent Workstation 的 transaction / rollback / recovery，但 `WorkstationFinding`、`WorkstationRoundPlan`、AutoPipeline recurrent executor 增加 subproblem-aware repair target。

Research defect 必须优先执行指定 subproblem 的 replay；只有没有 research target 时才使用旧 workflow-level model/paper reentry。

Solver execution 同时持久化实际 `solver_input_frame`，确保下一 Round 能精确重放派生特征。

### 真实 Gate

2023 Wordle SP3 validation defect 被 AutoPipeline 精确路由并仅执行 `subproblem:SP3:validation`；修复后 finding 消失并接受 Round。

### 原因

M-Round 的目标是优化整个 Research State，而不是更高效地重复整条单模型 pipeline，或把研究错误交给 LLM 润色。

---

## 2026-08-19 — D012：`excellent_c7` 只作为 Section 6 结构/叙事先验，不升级为全文优秀论文证据

### 重新核验

`config/ref_models/excellent_c7/` 当前包含 2010–2025 共 11 份 Markdown，文件与 index 都明确标记为“提炼稿”。内容包括结构大纲、摘要写法、建模套路、图表风格、语言特点、评分亮点与 strong_points。

### 决策

Section 6 可以利用这些提炼稿建立 CompetitionPaperAuditor 的结构/叙事先验与 gap taxonomy，但不得宣称已经基于优秀论文全文完成外部 benchmark。

### 原因

这样既能立即利用用户准备的资料提高 Paper Engine，又不重复 D003 的 self-validation 错误。真正的 L3/L4 excellent-paper benchmark 留到能够读取原始 PDF/全文 corpus 后执行。

---

## 2026-08-19 — D013：Section 6 正式采用 ProblemGraph -> ModelGraph -> EvidenceGraph -> NarrativeGraph -> Paper

### 决策

不再让 Paper Engine 直接从 whole-problem ModelPlan 或 section template 取内容。新增独立 ModelGraph / EvidenceGraph，NarrativeGraph 的 PASS 必须同时要求 ProblemGraph、ModelGraph、EvidenceGraph 全部闭合。

### 原因

只有分开“问题是什么 / 用什么模型 / 有什么证据 / 怎么讲故事”，Reviewer 才能把错误精确路由到 model、experiment/evidence 或 document 层；否则 Narrative/Paper 层会再次变成把上游缺陷写漂亮的黑箱。

---

## 2026-08-19 — D014：Paper equation / assumption / figure 必须由 executed solver schema 派生

### 决策

- 公式：只有 SolverRegistry 已执行方法存在 equation schema 才输出；unknown method 不填 generic formula。
- 假设：只写 solver/validation implied assumptions，不写通用竞赛套话。
- 图：优先 task-specific semantic plot；fallback 必须显式标记，不允许把“有图”当质量完成。

### 真实 Wordle 结果

SP1–SP5 当前分别生成 forecast interval、effect CI、distribution uncertainty、class probabilities、association ranking，五问无 fallback。

### 原因

直接解决旧 Wordle 的 `A_t/B_t/x_t`、kWh/kW/CNY 等跨题模板污染，并让图表承担问题级论证功能。

---

## 2026-08-19 — D015：优秀论文“多方案对比”只能来自真实 candidate consideration，不得补造对比实验

### 背景

excellent_c7 提炼稿中“分情形/多方案对比呈现”在 11/11 年份重复出现。第一版 Research-State draft 缺这一点。

### 决策

NarrativeGraph 投影 ProblemGraph / ModelingBrain 的真实 candidate considerations，包括 source、PASS/NEEDS_SOLVER/REJECT/PLANNED 和 rationale。论文可以说明考虑过哪些方案及为何采用当前执行方案，但未执行 alternative 不得出现虚构性能数字。

如果后续 Reviewer 判断某题真正需要 head-to-head model comparison，则作为 Research defect 回 Section 2–4 补实验，而不是由 Section 6 写出来。

---

## 2026-08-19 — D016：内部 Auditor 0/0 只表示已编码 Gate 干净，不作为优秀论文认证

### 决策

新 Wordle Research-State draft 当前在 CompetitionPaperAuditor 下达到 0 BLOCK / 0 REVIEW，同时 excellent_c7 当前已编码跨年份 prior gap 为 0；仍不得宣称达到国奖/O-F。

### 原因

- excellent_c7 是提炼稿而非全文；
- Auditor 仍由本项目编码；
- blind/human review 尚未做；
- domain bibliography、跨题泛化、语言成熟度仍未充分验证。

因此 Section 6 只将 Milestone 6.1 判 PASS，Section 6 整体保持 IN PROGRESS。

---

## 2026-08-19 — D017：M-Round acceptance 必须识别“本轮目标 issue 已解决”，不能只看聚合总分

### 背景

Section 6 增加新的 P2 优秀论文准备度审计后，真实 Wordle SP3 validation defect 已被 node-targeted replay 修复，但 aggregate quality 可能因其它无关 P2 finding 保持不变，旧 `decide_round()` 因 `total_delta < min_delta` 错误拒绝成功修复的 Round。

### 决策

`decide_round()` 增加 `selected_issue_ids`；`run_round/resume_round` 把本轮 plan 的 selected issues 传入 decision。只要本轮目标 issue 确实从 after-audit 消失，且没有新增 P0 或超限 domain regression，就把它视为 material progress。

### 验证

新增 targeted-P2 / flat-total 回归；Section 5 recurrent 组重新验证 `20 passed`。

### 原因

Research State repair 的成功标准首先是“目标缺陷是否真正消失”，聚合质量分只能作为辅助指标；否则 Auditor 标准扩充会反过来破坏 M-Round 的事务语义。

---

## 2026-08-19 — D018：Section 6.2 改用同题 2023 MCM C O 奖全文校准，而不是继续只靠提炼稿

### 重新核验

DevSpace 当前可以只读访问：

`D:\作业\竞赛\大学生数学建模\美赛\备赛\资料`

其中 `2023年美赛特等奖论文/.../C` 目录实际存在至少 12 篇 2023 MCM C Wordle O 奖 PDF。已用 `pdfinfo/pdftotext` 读取 team 2309397 / 2318036 / 2322645 的摘要、目录和正文起始部分。

### 决策

Goal 6.2 首先建立 same-question full-text calibration：至少 5 篇 2023 Wordle O 奖论文，抽取派生 profile（不复制全文），重点覆盖 abstract、model sequence、domain-specific innovation、validation/uncertainty、figure/table/reference density、strengths/weaknesses、editor deliverable。

Competition gap 必须分类：

- DOCUMENT：摘要密度、章节叙事、引用、图表承载、表达等；
- RESEARCH：模型深度、Wordle-specific feature/mechanism、alternative experiment、uncertainty、validation 等。

RESEARCH gap 必须回 Section 2–5，不允许 Section 6 prose writer 伪装修复。

### 原因

这是对 D003 self-validation loop 的直接修复：同一道 Wordle 题有真实 O 奖全文时，不应继续用本项目自建 rubric 或别题提炼稿证明“接近优秀”。

---

## D019：同题优秀论文只能提供 recurring capability prior，不能变成算法模仿清单

2023 Wordle O 奖全文显示了 SIR、ARIMA/BP、LSTM、Bayesian/MCMC、Subset Entropy 等多种完全不同的成功路线。因此“某篇 O 奖用了某算法”本身不能成为本项目的缺陷。

决策：`SameProblemExcellentAssessor` 只将跨多篇同题 O 奖反复出现的能力提升为 gap；单篇模型技巧保留为参考，不进入强制 Gate。RESEARCH gap 必须有可执行研究证据才能消除，不能靠 Paper Engine 写出类似术语。

---

## D020：Wordle-specific feature 必须逐子问题 ablation，禁止一套创新特征强塞全题

基于题目自身单词集合新增 `positional_letter_surprisal` 与 `letter_transition_surprisal`，没有引入外部熟悉度/词频标签。真实多 split/seed ablation 后：

- SP2 保留 positional surprisal；
- SP3 保留 positional + transition surprisal；
- SP4 新特征收益不稳健，继续使用 base8；
- SP5 可把两项作为探索变量。

这说明 ProblemGraph 的 feature contract 也必须 per-subproblem，而不是 whole-problem feature set。

---

## D021：SP1 模型选择由 temporal stress robustness 决定，单一 holdout winner 无权自动切换

新建 `gold.popularity_lifecycle` 两阶段 popularity mechanism alternative，但真实 15/20/25/30% temporal holdout 显示其只在前两个短 horizon 很强，在后两个长 horizon 明显崩溃。与此同时 damped Holt exponential smoothing 在 4/4 horizons 均显著优于旧 Ridge。

决策：

- Wordle SP1 accepted solver 改为 Holt；
- popularity lifecycle 保留为“真实执行但因跨 horizon 不稳定而拒绝”的机制 alternative；
- forecasting head-to-head 增加 stress grid：至少 3 splits，至少 75% splits 超过 1% materiality tolerance，且 median relative improvement >1%、validation 不 FAIL，才可 `REVIEW_SWITCH`；
- stress Gate 若 `KEEP_ACCEPTED`，`best_method` 必须与 accepted method 一致，不能残留单 split winner。

---

## D022：Wordle 同题全文 Gate PASS 只关闭 6.2A，不得升级为 O/F 认证

在真实 Wordle case 中，接受 Holt、执行 Ridge + Popularity Lifecycle stress comparison，并将 Wordle-specific surprisal 经过 ablation 后进入对应节点，当前 same-problem O-award full-text assessor 已达到：DOCUMENT gaps=0、RESEARCH gaps=0、Gate=PASS。

该结论只表示“当前六篇同题 O 奖全文中已编码的 recurring capability gap 已由真实 Research State 证据闭合”。以下仍未验证：跨赛题泛化、PDF 图表视觉/版式质量、blind/human review、更大/更多年份优秀论文样本。因此 Section 6 继续进入 6.2B/6.3，而不是继续为 Wordle gap=0 堆功能。

---

## D023：Section 6 第二道真实 Gate 采用 2018 MCM C Energy Compact，并优先补通用 panel/MCDM 能力

### 背景

2018 MCM C 同时包含四州 energy profile、历史演化、best-state ranking、2025/2050 forecast、compact target optimization、actions 和 Governors memo，任务族与 2023 Wordle 明显不同。用户原始资料中存在官方 `ProblemCData.xlsx` 和 5 篇同题 O 奖全文。

### 决策

不把旧 TX-only fixture 当真实研究数据；使用官方四州 SEDS attachment，建立最小透明 profile，并由真实题目暴露 Solver/Validation gap。

因此新增：

- panel profile summary
- panel trend characterization
- Entropy-TOPSIS MCDM + leave-one-criterion-out stability
- panel Holt + entity-wise temporal holdout/interval
- LP target setting with explicit forecast lower bound / historical stretch envelope

### 原因

如果第二题只是把 Wordle solver 换数据重跑，就不能证明架构泛化。新增能力必须是第二题真实语义要求，而不是为测试造的题目特例。

---

## D024：同题 O 奖标准比较 recurring capability，不比较“是否用了同一个算法”

5 篇 2018 C O 奖论文算法高度分散：GPR/ARMA、BP、ARIMA、New Keynesian、VAR、TOPSIS/PCA/PROMETHEE 等均存在，但 5/5 都有 energy profile、multi-criteria evaluation、2025/2050 prediction、compact targets/actions、Governors memo。

决策：2018 same-problem profile 只把这些跨论文反复出现的能力升级为 research/document signal。任何单篇算法都不成为强制 Gate。

---

## D025：PLANNED candidate 不等于可执行 alternative；Readiness 不再用 Solver alias 猜 head-to-head obligation

### 背景

第二题暴露：ProblemGraph 的 generic candidate label 可能和 SolverRegistry alias 文本相似，但输入/协议并不兼容。例如 scalar Ridge 不能自动成为四州 panel forecast alternative，IR pairwise/listwise ranking 也不能自动成为 Entropy-TOPSIS 的同题 MCDM alternative。

### 决策

`empirical_alternative_comparison` / `alternative_solver_depth` 只接受显式 candidate feasibility：

- `PASS` -> 可以产生真实 comparison obligation；
- `NEEDS_SOLVER` -> 可以产生 solver-depth gap；
- `PLANNED` -> 仅保留研究想法，不自动升级。

ExcellentCorpus 的“多方案对比”同样只在存在显式 executable PASS alternative 时要求 head-to-head；否则禁止为满足模板伪造比较。

---

## D026：Paper Engine 必须按 prompt deliverable 渲染，禁止 Wordle-specific 文案留在 generic renderer

2018 Gate 发现 generic renderer 仍硬编码：`Wordle dataset`、`underlying puzzle`、NYT Puzzle Editor，并且只渲染第一个 synthesis node。

决策：

- data/background 文案改为 domain-neutral；
- 所有 synthesis nodes 都进入 Cross-Question Synthesis；
- editor/letter 目标才渲染 editor letter；
- memo/governor 目标渲染真实 Governors' Memo；
- prompt-specific deliverable 只能使用其 dependency Research State，不补造新数值。

---

## D027：Section 6 内部 Gate 以“两道 materially different 历史题 + same-problem full-text calibration”收口

2023 Wordle 与 2018 Energy 两道完整历史 Gate 当前均通过。2018 官方数据 case 的 ExcellentReadiness 中，除 `blind_human_competition_review=UNVERIFIED` 外其余维度全部 PASS；same-problem 2018 O-award DOCUMENT/RESEARCH gaps 均为 0。

决策：Section 6 标记 **INTERNAL GATE PASS** 并冻结，不继续为无法内部自证的 blind review 无限加功能。下一 Goal 进入 Section 7：保留 2 道 MCM Gate，再增加至少 3 道 CUMCM 历史全文 benchmark，开展跨赛制 corpus、figure-purpose / abstract / model-transition / visual-layout 外部校准。

---

## D028：Section 7 起正式冻结为 C题专精，不再追求全题型覆盖

### 用户决策

近期只做 C题，A/B/D/E/F 暂时不进入正式研发与优秀论文 benchmark。

### 决策

正式 Section 7 benchmark 改为：

```text
3 × CUMCM C
+
2 × MCM C
```

当前两道 MCM C 固定为 2023 Wordle 与 2018 Energy Compact。新增 CUMCM benchmark 也只能从真实 C题中选择，并优先让三道 C题任务结构互补。

通用基础设施继续保持 generic，但上层建立：

```text
C-Problem Generic Profile
-> MCM C Profile
-> CUMCM C Profile
```

其它比赛未来优先仿照最接近的 C题 profile；不在当前阶段为其它题型扩 Solver / Paper scope。

### 原因

当前目标是把一个赛题方向做深，而不是横向堆覆盖率。C题本身已经足够包含数据分析、预测、评价、优化、统计推断与综合决策链，适合检验 Research State 的深度与泛化。

---

## D029：外部 9GB 资料库先建立 Asset Registry，再进入 Section 7.1 全文学习

### 已重新验证的资料根目录

`D:\\作业\\竞赛\\大学生数学建模\\美赛\\备赛\\资料`

只读扫描显示：

- `论文`：约 9.1GB，867 文件 / 180 目录；
- `课程课件`：209 文件 / 24 目录；
- 包含 MCM C 连续赛题及附件、MCM O奖全文、高教社 CUMCM 原题与优秀论文、30 类常用模型、完整 AI Skills 包、写作/预测/优化/统计课程和模板。

### 决策

新增：

- `docs/LOCAL_MODELING_KNOWLEDGE_BASE_README.md`
- `config/ref_models/local_knowledge_base_registry.json`

知识库严格分层：

```text
RAW Archive
-> Asset Registry
-> Derived Knowledge
-> Skill / Routing Knowledge
-> Runtime Research State
```

Raw 资料不复制进仓库。教材、课程、Prompt、Skill 只能作为 advisory prior；SolverRegistry 与当前 case accepted evidence 仍是执行/结论真源。

### 人工审核策略

人工审核不在开发中间频繁打断。到 Goal 7.5，在内部 C题 Gate 已经值得审阅时，再明确交付审阅稿和审阅清单给用户；在真实人工反馈发生前 `blind_human_competition_review` 必须保持 UNVERIFIED。

---

## D030：正式 C题优秀论文 benchmark 锁定为 5 题 / 21 篇，并以研究行为而非算法频率为主

### 最终五题

- CUMCM 2010 C — 输油管布置 — 3 篇可解析优秀论文；
- CUMCM 2018 C — 大型百货商场会员画像 — 3 篇；
- CUMCM 2023 C — 蔬菜定价与补货 — 4 篇；
- MCM 2018 C — Energy Compact — 5 篇 O奖；
- MCM 2023 C — Wordle — 6 篇 O奖。

总计 **21 篇**。

机器 Gate：`c_problem_excellent_benchmark_v1.json` + `c_problem_benchmark.py`。任何非 C题进入 primary benchmark，或少于 3 道 CUMCM C / 2 道 MCM C，都直接失败。

### 核心结论

同一道 C题的优秀论文算法经常高度分散，因此 method prevalence 只能提供 candidate prior，不能成为模型选择理由。真正可复用的是：问题特异表示、前后问递进、数据/机理/约束驱动选模、量化摘要、claim-specific validation、evidence-backed decision/deliverable。

---

## D031：Excellent-paper corpus 只能成为 Research Obligation，不能成为 Candidate Source

Goal 7.2 将五题 corpus 接入 ModelingBrain，但没有增加 `corpus` 候选来源。候选仍只有：

```text
native / hmml / knowledge_card / skill
```

Corpus 只新增：

- research obligations；
- validation obligations；
- forbidden shortcuts；
- benchmark provenance。

SolverRegistry 仍是 feasibility 真源。

`WorkstationGlobalAuditor` 只在已完成且显式携带 C-problem benchmark prior 的节点上检查：validation artifact 是否存在、validation family 是否与 ProblemGraph task family 一致。真实 Wordle SP3 mismatch 注入验证：错误 family 精确回 `SP3 / validation`，正确 family 不产生 finding。

---

## D032：Research State 共用，MCM-C / CUMCM-C 只在下游 Paper Profile 分叉

### 缺陷

`ResearchStatePaperService.generate(..., competition=...)` 原本虽然有 `competition` 参数，但 renderer 实际忽略它，导致 CUMCM 仍生成英文 MCM 风格章节。

### 决策

建立 `c_problem_paper_profiles_v1.json`：

- MCM-C：英文 `Summary`、MCM 研究叙事、prompt 明确要求时才渲染 memo/letter；
- CUMCM-C：中文 `摘要 / 问题重述与分析 / 数据预处理 / 模型建立检验与结果 / 模型评价 / 结论 / 参考文献`。

两个 profile 只能修改标题、连接句和交付形式；不能修改 NarrativeGraph 中的 accepted method、equation、key result、validation、answer、limitation。

CompetitionPaperAuditor 的 profile finding 全部属于 DOCUMENT。跨赛制标题污染可 BLOCK 文档，但不得触发研究重跑。

---

## D033：V3 每个阶段强制 Research Refresh；官方硬规则与优秀论文软先验彻底分层

### 背景

2026-08-22 的人工审阅指出三类新的主要整改方向：图表/流程图视觉语言、比赛论文版式、以及“前两问核心建模、后续问继承扩展”的建模重心。用户同时明确要求：每完成一个阶段都重新检索本地资料库和 GitHub/网络成熟科研智能体，不能机械执行一次性计划。

### 新证据

重新核验 2026 CUMCM 官方格式后确认：A4、至少 2.5 cm 页边距、摘要页、正文页数、无目录、匿名、引用、附录代码与电子文件限制属于硬规则；但字号、字体、行距、颜色并没有全国统一规定。电子版还明确排除纸质承诺书与编号页，因此电子 PDF 第一页应直接是摘要专用页。

本地 C 题 excellent-paper priors 与 2023C 同题优秀论文则再次说明：算法选择高度多样，稳定重复的是“数据结构识别 → 核心模型 → 约束/场景扩展 → 决策/验证”的研究链，而不是某个固定高级算法。

### 决策

新增 `competition_paper_standard_v2.json` 和 `CompetitionPaperStandardRegistry`，按以下优先级消费证据：

```text
Official hard constraints
> Task-specific evidence
> Excellent-paper soft priors
> Human visual preferences
> Open-source engineering patterns
```

V3 后续每一阶段固定执行：

```text
本地优秀论文/资料库刷新
-> 当年官方规则刷新
-> GitHub 成熟科研智能体刷新
-> 偏差备忘录/计划微调
-> 实现
-> 真实赛题 Gate
-> 下一轮 Research Refresh
```

### 影响

- 不再把某种字体、颜色、模型或图数量伪装成“官方标准”；
- 默认反对每问一个互不相关模型、算法动物园、以公式数衡量建模深度、以图数量衡量视觉质量；
- 当前 2023C PDF 的 A4/页数/电子首页等基本项通过，但源代码附录与 2026 AI disclosure/supporting PDF 尚未接入正式 submission package，因此官方提交合规仍为 REVIEW；
- Stage 2 开始前应再次做 Research Refresh，并优先构建 figure-purpose router、科研配色/图型库与技术路线图，而不是继续“给 Graphviz 换皮”。

---

## D034：论文建模主线由 Problem/Narrative 依赖结构推断，不硬编码“第2问=核心模型”

### 缺陷

旧 Research-State renderer 虽然已经做到逐问证据独立，但论文仍容易呈现成“每问一个模型”的并列结构。这样会掩盖真正的核心模型，也会让后续扩展问重复推导、公式膨胀。

### 决策

新增 `ModelSpinePlanner`，把研究节点投影为 `FOUNDATION / CORE_MODEL / EXTENSION / INDEPENDENT_MODEL / SYNTHESIS`。核心节点根据：

- 是否属于实质性建模 family；
- 下游有多少问题直接或间接复用；
- 当前 ProblemGraph / NarrativeGraph 的真实依赖；

共同决定。题号只用于显示，不参与核心模型判定。

同步新增 presentation-only Formula Budget：完整公式注册仍保留用于执行和审计，正文只按节点角色选择最能说明模型本质的公式。常规估计、调参、指标定义可留在文字或可复现证据中。

### 2023C 实证

真实 2023C 自动得到：

```text
SP1 FOUNDATION
 -> SP2 CORE_MODEL
 -> SP3 EXTENSION (CONSTRAINT)
 -> SP4 SYNTHESIS
```

Q2 正文登记公式从 5 个压缩为 3 个核心式，且季节/趋势项收束为 `s_c(t)`，没有改变实际 solver。

---

## D035：图表配色从 competition-wide 单一科研蓝改为 semantic palette routing

### 缺陷

统一 publication profile 虽保证了整洁，但会把不同证据图全部推向同一种蓝色视觉语言，和优秀竞赛论文中“同篇协调、逐图有差异”的呈现存在明显差距。

### 决策

建立 `figure_palette_bank_v1.json + FigureColorDirector`：

- categorical/comparison/sensitivity/ranking/correlation 等根据 semantic kind 路由；
- 使用 NPG/JAMA/NEJM/Lancet-inspired 离散方案和低饱和自定义方案；
- correlation/effect 连续证据使用 diverging palette；
- palette 选择由 figure semantic intent + stable identity 决定，不绑定某一道题的变量名；
- `VisualQualityService` 新增 palette-diversity 检查，至少已有 3 张 routed data figure 时才启用，避免对 legacy/imported 图误判。

这条规则已经接入 SubproblemPaperEvidenceBridge、ScientificFigureFactory 与 alternative-comparison figure path。

---

## D036：生成式流程图只作为设计候选；必须经过 rendered-image review 才能宣称视觉 PASS

### 证据

LiveFigure、科学图 MCP 和多种科研 Agent 的共同模式不是“生成一次就结束”，而是 semantic planning → render → visual diagnosis → edit/refine。生成模型尤其可能出现文字错误、依赖箭头错误或视觉漂亮但科研语义错误。

### 决策

工作站保留：

```text
NarrativeGraph + ModelSpine
 -> Visual Brief
 -> GPT Image / scientific-image MCP candidate
 -> PPT MCP editable redraw
 -> rendered preview
 -> human/vision-agent review
 -> publication figure
```

新增 `FigureVisualReviewService`，视觉审查和 research-evidence approval 分离。`semantic_fidelity` 是硬门：图再漂亮，只要语义不正确就 REJECT。`VisualQualityService` 只有读到明确 PASS review artifact 才关闭 diagram visual-review gate。

当前没有实际连接 PPT MCP / image route 的运行环境时，仍使用 deterministic SVG/PNG 作为 paper-safe fallback，同时保留 AI/PPT handoff，不伪装成已完成视觉审查。

---

## D037：比赛格式 Profile 与建模题型 Profile 分离，禁止由“比赛名称”推断模型

### 背景

2024 MCM C 的独立 PDF 验证表明，MCM/CUMCM 的版式 profile 已能工作，但现有 `CProblemPaperProfileRegistry` 只认识 `MCM_C / CUMCM_C`，同时系统部分建模分支仍把 competition/profile 和 task family 过度耦合。用户明确要求后续覆盖国赛、高教杯/校赛体系、华数杯、MCM/ICM 等不同 C 题，必须根据题目本身识别建模类型，不能因为都是 C 题或同一比赛就采用固定路线。

### 决策

V5 将两个概念彻底拆开：

```text
CompetitionProfile -> 语言、纸张、页数、摘要/目录/Memo/AI Report 等提交约束
ModelingProfile    -> 状态、机制、概率、动态、优化、仿真、网络、空间等研究结构
```

CompetitionProfile 不得选择模型；ModelingProfile 不得决定官方提交格式。其它杯赛通过注册新 competition profile 接入，而不是伪装成 CUMCM。

---

## D038：ModelingBrain V2 先设计数学结构，再选择算法/求解器

### 缺陷

当前 `ModelPlan` 主要围绕 regression/classification 和 linear/ridge/RF/GB 等通用监督学习模型，这会把数学建模弱化为“选算法 + 比指标”。2024 MCM C 的第一版正暴露了这一问题：证据和逻辑可靠，但数学结构感不足。

### 决策

ModelingBrain 下一版必须先形成 `ModelStructurePlan`，至少描述：

- modeled entities / state variables / latent variables；
- mechanisms / transition law / dependency structure；
- constraints / uncertainty / objective；
- inheritance from upstream subproblems；
- identifiability；
- validation obligations；
- 最后才映射 solver requirements。

算法是求解器，不是模型本体。2024 MCM C 可以把 Bayesian / probabilistic graphical model 作为由题目结构推导出的候选，但不得把它硬编码为所有 C 题默认方法。

---

## D039：不设图/表/公式数量 quota；由 Evidence Expression Planner 决定表达媒介

### 背景

用户认可当前 MCM 配色与基本图形美观度，但指出图数量、种类和论文中的出现位置仍不足，缺少流程图；同时 2.1 中 `0.6731` 这样的裸数字说明公式/正文/表格表达选择还不成熟。优秀论文通常自然出现较多图表，但“10–20 张图”是结果分布，不应成为硬指标。

### 决策

新增统一 `EvidenceExpressionPlanner`：每个 argument/evidence 先选择最合适的表达：

```text
TEXT | EQUATION | FIGURE | TABLE | PANEL | ALGORITHM | DEFINITION
```

再由 FigureDemandPlanner / MathematicalExpressionPlanner / PaperLayoutIR V2 具体实现。流程图、统一模型框架图、机制图、状态转移图、敏感性图等必须由研究/叙事需求触发，而不是为了补数量生成。数字根据语义角色决定进入公式、结果句或表格；核心模型章节应定义状态、关系/概率/目标、约束与估计过程，但不以公式数量评分。

正式比赛时预留 Problem Interpretation / Modeling Direction / Evidence Story / Final Paper 四个可选 human checkpoint；当前重构阶段默认 `human_loop_mode=OFF`，只实现状态接口，不强制打断自动流程。

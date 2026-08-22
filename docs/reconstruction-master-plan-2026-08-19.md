# 数学建模 AI 工作站完整重构主计划

日期：2026-08-19  
状态：执行中  
长期目标：把当前工程底座较成熟、但研究主线偏弱的工作站，升级为能够在真实历史赛题上持续产出 CUMCM 国奖 / MCM-ICM O/F 级研究过程与论文的系统。

## 核心判断

当前项目不是“没有东西”。DAG/workflow、Artifact/Dataset/Experiment/Claim/Figure registry、SHA-256 provenance、checkpoint/recovery、frozen accepted versions、approval gate、evidence-first、submission/preflight、learning/reflection、AI ledger 等工程底座已经相当完整。

真正的 P0 是研究主线：题目虽然会被分析成多个 subproblem，但主流水线随后仍收缩为单个 ModelPlan / 单个 comparison / 单个 best model，最终多个 SubproblemAnswer 共享同一模型和同一 primary metric。真实 2023 MCM Wordle 论文已经证明这会把性质完全不同的 SP1-SP6 压扁成同一 generic ML report，甚至把 editor letter 当成模型训练问题。

因此，本轮重构不以继续堆工程设施为主，而以“每个子问题拥有独立研究状态，并能在 M-Round 中被真实修复”为主线。

## 新的主研究状态链

```text
ProblemGraph
-> Model / Solver
-> Experiment
-> Evidence
-> Figure / Table
-> Narrative
-> Paper
-> Reviewer
-> Repair Router
-> next Research Round
```

Reviewer 必须区分两类缺陷：

- Document defect：事实与研究状态已经正确，只需要修复表达、结构、版式或叙事，可直接进入 paper repair。
- Research defect：题意、数据、方法、求解、验证、实验、证据本身不足，必须回退到对应上游节点，重新产生证据；禁止仅让 LLM 把错误结论写得更漂亮。

## M-Round 保留，但优化对象从 Paper 升级为 Research State

建议默认六轮语义：

- Round 0 — Coverage：覆盖所有子问题与交付物，先形成完整研究状态。
- Round 1 — Correctness：修目标、约束、数据语义、泄漏、错误模型与错误验证。
- Round 2 — Modeling Depth：提升模型选择理由、数学结构、求解深度与任务特异性。
- Round 3 — Robustness：补交叉验证、敏感性、不确定性、误差切片、消融、反事实/场景分析。
- Round 4 — Storyline：让 ProblemGraph -> EvidenceGraph -> NarrativeGraph 一致，减少拼贴与模板化。
- Round 5 — Competition Polish：摘要、图表、符号、引用、版式、信件/附录/提交包等竞赛级打磨。

现有 recurrent workstation / refinement WIP 保留；但当前优先级从继续拆 cell 暂时切换到 ProblemGraph/Subproblem Engine，因为真实赛题已经证明“单模型主线压扁所有子问题”是更早、更致命的上游缺陷。该优先级调整写入 `docs/DECISION_LOG.md`。

## Section 0 — Freeze / Baseline / Benchmark / Persistent Memory

目标：建立后续每一轮都能引用的真实起点，避免聊天记忆、自测分数和 synthetic fixture 自证。

必须产物：

- `docs/reconstruction-master-plan-2026-08-19.md`
- `docs/current-baseline-2026-08-19.md`
- `docs/benchmark-spec-2026-08-19.md`
- `docs/WORKING_MEMORY.md`
- `docs/CURRENT_STATE.md`
- `docs/DECISION_LOG.md`
- `docs/KNOWN_ISSUES.md`
- `.internal/resume_brief.md`

Gate：

1. 当前 branch / dirty state 被记录，existing WIP 有明确保护边界。
2. 当前 Python/依赖与 full/targeted test 状态被重新验证。
3. 2023 MCM Wordle 的现有真实论文被重新读取，而不是引用旧聊天结论。
4. benchmark 明确禁止 synthetic-only、自建 rubric-only、文件名推断优秀论文等 self-validation loop。
5. 下一会话仅靠 AGENTS + resume_brief + CURRENT_STATE 即可恢复当前工作。

## Section 1 — ProblemGraph / Subproblem Engine

这是第一优先级代码重构。

核心对象：

- `ProblemGraph`
- `SubproblemNode`
- `DependencyEdge`
- `SubproblemState`
- `SubproblemContract`
- `SubproblemPlan`
- `SubproblemExperiment`
- `SubproblemAnswer`

每个 Subproblem 必须独立拥有：

```text
objective
inputs
outputs
constraints
task_family
dependencies
candidate_methods
selected_method
experiments
validation
evidence
answer
status
```

最小侵入策略：优先兼容现有 `SubproblemContract` / `SubproblemAnswerRecord` / registries，不重写现有 refinement / excellent-paper-comparator WIP。先增加 ProblemGraph 领域层与适配层，再逐步让 AutoPipeline 从“全题单 ModelPlan”转为“按可执行 subproblem 形成 plan/experiment/evidence/answer”。

2023 MCM Wordle Gate：

- SP1：报告数量随时间变化与未来区间预测；应是 time-series / regression with temporal validation 类节点。
- SP2：word attributes 对 Hard Mode 比例影响；应是解释/统计推断/特征效应类节点。
- SP3：未来单词+日期的 1..6/X 分布预测；应是 compositional / multi-output distribution prediction 类节点，并有不确定性。
- SP4：单词难度分类 + EERIE；应是 classification / ordinal / difficulty construct 类节点。
- SP5：其它有趣特征；应是 exploratory / discovery 类节点，不强制套 supervised best model。
- SP6：给编辑的 1–2 页信；必须是依赖 SP1-SP5 已接受结论的 synthesis/deliverable node，不能创建训练实验。

Gate 通过条件不是“对象建出来了”，而是同一次真实 Wordle run 中 SP1-SP6 的 task type、method、experiment/evidence/answer 出现实质差异，SP6 不再训练模型。

## Section 2 — Modeling Brain

```text
Subproblem
-> Method Retrieval
-> Candidate Strategies
-> Feasibility Critic
-> Selected Candidate Set
```

让现有 HMML / Knowledge Cards / Skills 真正参与选模。方法检索要回答“为什么这个模型适合这个子问题”，而不是只输出模型名。

## Section 3 — Solver Engine

统一 `SolverPlugin`：

```text
supports()
validate_inputs()
build()
solve()
diagnose()
sensitivity()
export_evidence()
```

先建立高频 Gold Solver Set：regression/statistics、time series、classification、evaluation/ranking、LP/MILP/NLP、multiobjective、graph/network、clustering、Monte Carlo/scenario、ODE/difference/Markov、fitting/interpolation、uncertainty/bootstrap。

不以模型数量作为完成标准。

## Section 4 — ValidationProtocol Registry

不同 task family / solver 使用真正对应的验证协议：时间序列禁止默认 random split；分类、排序、优化、仿真、分布预测、统计检验分别使用适合自己的指标、切分、稳健性与不确定性检查。

## Section 5 — M-Round Research Refinement

把现有 recurrent workstation 的 Repair Router 与新的 ProblemGraph / ModelGraph / EvidenceGraph 对齐。finding 必须能定位到具体 subproblem 和最早 repair node。研究缺陷回上游，论文缺陷留在 paper cell。

## Section 6 — Paper Engine

目标：

```text
ProblemGraph
-> ModelGraph
-> EvidenceGraph
-> NarrativeGraph
-> Paper
```

假设、符号、公式、图表、结果只能来自当前 accepted research state。禁止 generic template pollution；禁止内部 claim/result/table/figure ID 泄漏到用户论文；引用必须有真实 bibliographic source。

## Section 7 — C-Problem Excellent Corpus + External Benchmark

本地优秀论文资料路径：

`D:\作业\竞赛\大学生数学建模\美赛\备赛\资料`

此前 DevSpace root 无法直接读取，因此此前 comparator 文档不能被当作全文优秀论文分析结论。进入本节必须先解决真实访问/OCR/全文读取问题。

抽取结构至少包括：Question type、Model sequence、Why this model、Model transition、Validation type、Figure purpose、Innovation pattern、Abstract structure、Failure patterns。

### Scope freeze：只专精 C 题

近期研发、优秀论文 benchmark、真实 Paper Gate **只做 C 题**：

```text
Generic mathematical-modeling infrastructure
-> C-Problem generic research profile
   -> MCM C profile
   -> CUMCM C profile
```

A/B/D/E/F 资料保留为 archive / 方法旁证 / 回归样本，但不进入 primary excellent-paper benchmark。

### Goal 7.0 — Local Modeling Knowledge Base

先把外部资料库梳理成 Asset Registry / README，区分原题、优秀论文、方法教材、课程、Skill、模板、工具与低价值重复资产。Raw 资料不复制进仓库，只保存路径、标签和 derived knowledge。

### Goal 7.1 — C-Problem Excellent Corpus

历史正式 benchmark 固定为：

```text
3 × CUMCM C
+
2 × MCM C
```

当前两道 MCM C 已通过：2023 Wordle、2018 Energy Compact。CUMCM 只从真实 C题优秀论文与原题附件中选择任务结构互补的 3 道题。

全文抽取至少包括：Question type、Model sequence、Why this model、Model transition、Validation type、Figure purpose、Innovation pattern、Abstract structure、Failure patterns。

### Goal 7.2 — C-Problem Modeling Knowledge

把跨 C题重复出现的研究行为转成 ModelingBrain / Validation / Repair prior；禁止把单篇优秀论文的具体算法变成硬规则。

### Goal 7.3 — Paper Profiles

分别建立 `MCM_C` 与 `CUMCM_C` 的摘要、模型叙事、图表、公式、引用、交付风格；其它比赛后续仿照最接近 profile。

### Goal 7.4 — Five Real C Problem Gates

五道正式 C题完整通过 Research State -> Paper -> Excellent Benchmark；任何 Research defect 回 Section 1–5。

### Goal 7.5 — Human Review

内部 Gate 做到值得人工审阅后，再请求用户进行独立审阅，并将反馈重新路由到 Research / Paper / Delivery 层。未经真实人工审阅不得把 blind/human dimension 标记为 PASS。

## Section 8 — Competition Delivery

CUMCM C 与 MCM C 使用不同 profile。最终产物是 submission package，而不只是 `paper.pdf`。其它数学建模比赛后续优先复用最接近的 C题 profile，而不是现在单独建设完整体系。

## 固定开发节奏

每个 Section / 小节固定：

```text
本地优秀论文 / 资料库刷新
-> 当年官方规则刷新
-> GitHub 成熟科研智能体 / 自动论文系统刷新
-> 写偏差备忘录并微调计划
-> 设计
-> 实现
-> 真实赛题验证
-> 复盘
-> 再次 Research Refresh 后才进入下一阶段
```

这里的“调研”不是项目开头做一次后长期复用。V3 起每一个阶段至少重复检查三类来源：

- 用户本地 C 题优秀论文、模型资料、模板与派生 prior；
- CUMCM / COMAP 当年最新官方格式、提交、AI 使用与评阅规则；
- AI-Scientist / AI-Scientist-v2、Agent Laboratory、data-to-paper、MM-Agent、STORM 等成熟开源研究智能体的新机制与实现变化。

每完成一小节必须回答：

1. 原来具体有什么问题？
2. 本地优秀论文与用户人工样例告诉了我们什么？
3. 当年官方规则有没有推翻旧假设？
4. 外部成熟项目怎么做，哪些机制值得借、哪些不适合比赛场景？
5. 我们具体改了什么？
6. 真实赛题是否明显变好？
7. 下一阶段计划是否需要根据新证据调整？

上一 Gate 不通过，不以“测试绿了”为理由进入下一阶段。详细第一轮基线见 `docs/v3-stage-1-paper-standard-research-2026-08-22.md` 与 `config/ref_models/competition_paper_standard_v2.json`。

## 重点参考项目

- `usail-hkust/LLM-MM-Agent`：problem analysis、mathematical modeling、computational solving、reporting、HMML、iterative solver。
- `Technion-Kishony-lab/data-to-paper`：data-chained provenance、rewind/replay、human oversight、evidence -> code -> number traceability。
- `stanford-oval/STORM`：写作前研究、多视角问题探索、结构化长文研究。
- `SakanaAI/AI-Scientist`：experiment -> review -> reflection -> iteration、review ensemble。
- `handsomeZR-netizen/mathmodel-skill`：contest workflow、per-question state、decision log、stage gate、AI ledger/disclosure。

原则：不整仓复制，只吸收在本项目真实赛题 Gate 中被证明有效的机制。

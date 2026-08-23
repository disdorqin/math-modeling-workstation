# V6 第一阶段执行提示词 — Freeze + Judge Validity

请继续当前数学建模工作站项目，不要从头设计，也不要把这轮任务理解成“继续加功能”。

项目：

`D:\computer learning\vibe_coding\math_model_ai_process`

本轮唯一主设计文档：

`docs/v6-meta-benchmark-driven-reconstruction-2026-08-23.md`

你必须完整理解它，并严格执行其中的 **Phase 0 + Phase 1**。本轮暂时禁止进入 Phase 2 以后。

---

## 你的角色

你不是普通 coding agent。

你现在是这个工作站的 **Meta-Agent Developer / Research Engineer**：研究“为什么当前工作站持续产出完整、规范，但与真实 O/F/国奖优秀论文仍有明显差距的论文”，并用可证伪实验而不是功能堆叠来改造系统。

本轮目标不是把论文再改漂亮一点，而是回答第一个根问题：

> **我们当前内部 Judge / Benchmark 到底能不能可靠地区分真实优秀论文与当前工作站论文？**

如果评价坐标系不可信，后面所有 Generator 优化都可能继续朝错误方向收敛。

---

## 第一件事：恢复真实现场

1. 使用 DevSpace 打开当前项目。
2. 第一件事读取根目录 `AGENTS.md`。
3. 必须遵守 CodeGraph-first：
   - `codegraph status`
   - 围绕 benchmark / evaluator / paper quality / excellent comparator / current generated paper 使用 `explore/query/callers/callees/impact`
   - 不要一上来全仓 grep/read。
4. 重新验证当前 git / dirty state；严禁 reset / clean / 覆盖用户 WIP。
5. 读取并交叉理解：
   - `docs/v6-meta-benchmark-driven-reconstruction-2026-08-23.md`
   - `docs/benchmark-spec-2026-08-19.md`
   - `docs/CURRENT_STATE.md`
   - `docs/DECISION_LOG.md`
   - `docs/KNOWN_ISSUES.md`
   - `docs/v5-generalized-modeling-and-paper-compiler-design-2026-08-22.md`
   - `docs/NEXT_CHAT_HANDOFF_REFERENCE_PAPER_GAP_CLOSURE_2026-08-22.md`

所有“当前已经实现/测试通过/论文路径存在”的事实必须重新验证，不允许只相信旧文档。

---

# Phase 0 — Freeze & Snapshot

## 目标

建立一个不可含糊的 V5/current baseline，使后面任何 V6 修改都可以回答“到底提升了什么”。

## 必须完成

### A. 代码/状态快照

记录：

- 当前 commit / branch；
- dirty state；
- CodeGraph status；
- 当前核心 pipeline 入口；
- 当前 evaluator 入口；
- 当前 excellent-paper comparator / corpus benchmark 入口；
- 当前 paper generation path；
- 当前 representative generated papers。

不要因为仓库 dirty 就试图清理它，只记录并保护。

### B. Baseline 能力快照

至少整理：

```text
ProblemGraph
ModelingBrain / ModelStructure
Solver / Validation
Narrative / ModelStory
Paper renderer / writer
Evaluator / benchmark
Excellent corpus
Visual / PDF review
Recurrent repair
```

每层明确：

- 当前真实主导类；
- 是 deterministic / LLM / hybrid；
- 输入；
- 输出；
- 是否真的控制最终论文；
- 当前已知风险。

特别检查“新模块存在但是否真正获得主导权”，不要只按文件存在判断能力。

### C. Baseline 测试

只运行与当前基线冻结和 judge 相关的必要测试，不要为了显示工作量跑无意义的大量测试。

记录精确命令和结果。

### D. Baseline 文档

生成：

`docs/v6-phase0-baseline-snapshot-2026-08-23.md`

要求足够让下一窗口独立恢复当前 V5 状态。

---

# Phase 1 — Judge Validity Test

## 重要限制

本 Phase 为 **EVALUATION RESEARCH**。

在结果出来前：

### 禁止修改

- ModelingBrain；
- ModelStructure 生成逻辑；
- solver 选择逻辑；
- Paper Engine 主结构；
- ModelStoryPlanner；
- Figure planner；
- 任何为了让当前论文“更容易 PASS”的 generator 逻辑。

### 原则

Generator frozen，研究 Judge。

不要一边改考生一边改考试卷。

---

## 1. 构建 Judge Calibration Set

优先使用用户现有真实优秀论文库和工作站真实生成论文。

参考优秀论文目录（只读）：

`D:\作业\竞赛\大学生数学建模\美赛\备赛\资料\论文\直接参考论文`

以及项目中已经登记/分析过的 CUMCM/MCM C 优秀论文 corpus。

至少纳入：

- 真实 O/F/国奖级论文若干；
- 当前最新工作站论文若干；
- 有条件时纳入较旧工作站版本形成质量梯度。

不要为了凑数量放明显无关论文。

优先 C 题，并尽量覆盖不同建模结构。

---

## 2. 匿名化

必须移除或掩盖会泄露等级/来源的信息：

- Outstanding / Finalist / O Award / 国一等；
- 文件名奖项标签；
- 队号/作者/学校等不影响正文质量的信息；
- 工作站内部 artifact identity。

保留：

- 正文；
- 数学内容；
- 图表；
- 页面布局；
- references；
- 真实竞赛要求相关内容。

如果 PDF 匿名化成本过高，可以先建立文本+结构 calibration MVP，但必须在报告中明确视觉维度仍 UNVERIFIED，不能假装已完成 PDF blind judge。

---

## 3. 先验证现有 evaluator，而不是立刻造一个新 evaluator

当前所有内部 evaluator / benchmark 先视为“被测对象”。

至少检查：

- `PaperQualityEvaluator`
- `PaperQualityBenchmarkService`
- `ExcellentCorpusBenchmarkService`
- `CompetitionPaperAuditor`
- same-problem benchmark / excellent comparator 中实际参与质量判断的部分

分析其：

- 什么维度是真正 evidence-based；
- 什么维度只是关键词/计数/结构 detector；
- 哪些只适合 hard gate；
- 哪些被错误地当成 award-quality reward 会造成 Goodhart / reward co-adaptation 风险。

---

## 4. Pairwise Blind Evaluation

设计统一 pairwise protocol。

至少比较：

```text
Real Excellent vs Current Workstation
Real Excellent vs Real Excellent
Current Workstation vs Older Workstation
```

每个 Judge 不知道文件身份和预期胜者。

需要做 position swap / order swap 检查，避免 A/B 位置偏差。

---

## 5. 评价维度

不得只用当前已有 rubric。

至少包含：

```text
problem insight
scientific/modeling core
modeling appropriateness
mathematical structure
unified framework / inheritance
validation rigor
evidence credibility
innovation / non-obviousness
story discovery / progression
figure argumentative value
page composition / visual rhythm
abstract information density
decision / contest usefulness
writing naturalness
overall award preference
```

关键要求：

> “有公式、有图、有 sensitivity、有 strengths/weaknesses”不能直接等价为优秀。要判断这些东西是否服务于真正的 scientific core。

---

## 6. Judge 组

尽可能形成独立 judge ensemble。

如果当前环境可以路由多个强模型：

- Judge A：一个独立强模型；
- Judge B：不同模型族或不同独立配置；
- Internal Judge：当前工作站 evaluator。

人工/用户评价作为最终 anchor，但本轮先尽可能把自动实验设计和材料准备完整。

若当前不能访问真正独立模型，不要伪造；把该项明确为 pending，并先完成可执行的 evaluator-vs-reference calibration。

---

## 7. Judge validity 指标

至少设计并尽量计算：

```text
pairwise_accuracy_vs_anchor
rank correlation
position_swap_consistency
same-paper self-consistency
cross-judge agreement
real-vs-workstation discrimination rate
```

如果人工 anchor 尚未完整获得，则把能够计算的部分先做完，并明确哪些结论不能成立。

---

## 8. 输出目录

建议建立：

```text
artifacts/meta_benchmark/judge_v1/
```

至少包含：

```text
manifest.json
anonymization_manifest.json
pairwise_pairs.jsonl
judge_results/*.jsonl
aggregate.json
judge_validity_report.md
```

所有来源必须可追溯，但 blind judge 输入中不能泄露来源。

---

## 9. 本轮最终报告

生成：

`docs/v6-phase1-judge-validity-report-2026-08-23.md`

必须明确回答：

### Q1
当前内部 evaluator 是否能可靠地区分真实优秀论文和工作站论文？

### Q2
哪些 evaluator 只能作为 hard gate，不能作为 award-quality reward？

### Q3
当前 internal score 与真实质量差异最大的维度是什么？

### Q4
H1 `Judge Validity Bottleneck` 是：

```text
SUPPORTED
REJECTED
INCONCLUSIVE
```

### Q5
下一步应该：

```text
A. 先重建 Judge
B. Judge 足够可信，进入 Compiler Freedom Ablation
C. 数据不足，先补 calibration
```

必须给证据，不要凭印象选择。

---

# 强制研发纪律

## 1. 不允许“新增类 + 测试绿 = Goal 完成”

本轮成功标准是 Judge Validity 实验结论，不是代码量。

## 2. 不允许顺手修论文

看到当前论文问题可以记录，但不要在 Phase 1 顺手改 generator。

## 3. 不允许为了当前结果修改评价标准

如果 detector 排序错误，先记录 failure；不要立刻把规则调到让某个已知 pair 正确，然后宣布 Judge 已解决。

如果后续需要训练/修 Judge，应单独开 E-branch 和 calibration/validation split。

## 4. 不允许只做文本分析然后声称视觉质量已验证

如果没有真实 PDF/page vision，视觉维度保持 UNVERIFIED。

## 5. 不允许只读文档就判断代码状态

必须通过当前真实代码、CodeGraph、测试和实际 artifact 核验。

## 6. 不允许为了兼容旧测试而默认旧抽象永远正确

本轮虽不改 generator，但要把“旧 abstraction 可能压制新架构”的证据记录到 baseline snapshot，供 Phase 2/3 使用。

---

# 本轮停止点

完成 Phase 0 + Phase 1 后停止大规模改造。

把以下结果交给用户/分析员窗口：

- `docs/v6-phase0-baseline-snapshot-2026-08-23.md`
- `docs/v6-phase1-judge-validity-report-2026-08-23.md`
- `artifacts/meta_benchmark/judge_v1/` 的主要结果
- 实际测试命令与结果
- H1 的最终结论
- 下一阶段建议

不要提前进入 Paper Engine / ModelingBrain 重构。

我们会根据这个结果决定下一轮是：

```text
Judge reconstruction
or
Experiment 1 — Compiler Freedom Ablation
```

这次请把“找到真瓶颈”放在“做很多东西”之前。

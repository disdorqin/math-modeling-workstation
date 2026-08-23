# V6 Phase 0 Baseline Snapshot — 2026-08-23

状态：**FROZEN BASELINE RECORDED**  
范围：V6 Meta-Benchmark 重构前的 current/V5 工作站  
原则：本文件记录“当前真实是什么”，不把内部 PASS/高分解释为 O/F/国奖能力证明。

---

## 1. Git / workspace baseline

冻结时主分支：

```text
m2-contest-grade-paper
```

冻结 commit：

```text
63f6459688cad47ee09323f1d1b93404eb106032
feat: generalize contest-grade paper research pipeline
```

冻结前远程关系：

```text
origin/m2-contest-grade-paper...HEAD = 0 / 0
```

即已提交代码与远程一致。

V6 启动前 dirty state 仅包含：

```text
?? docs/v6-meta-benchmark-driven-reconstruction-2026-08-23.md
?? prompts/v6_meta_benchmark_first_goal.md
```

这两个 V6 协议文件当时尚未 commit/push。Phase 0/1 的实现文件是在此 baseline 之后新增，不属于被冻结的 V5 能力本体。

---

## 2. CodeGraph baseline

2026-08-23 重新执行：

```text
codegraph status
```

结果：

```text
Files: 326
Nodes: 5,852
Edges: 17,785
DB Size: 21.57 MB
Backend: node:sqlite
Index: up to date
```

本轮遵守 `AGENTS.md` 的 CodeGraph-first 要求，围绕 evaluator / benchmark / ModelingBrain / ModelStory / ResearchStatePaper 做定向 explore，而未进行全仓库扫描式理解。

---

## 3. 当前生产主线

当前真实主链可概括为：

```text
Problem ingestion / Subproblem contracts
-> ProblemGraph
-> ModelingBrain
   -> C-problem priors
   -> HMML / knowledge cards / modeling skills
   -> ModelStructurePlanner
   -> EvidenceExpressionPlanner
   -> Solver feasibility filtering
-> Subproblem Solver / Validation
-> Result / Table / Figure / Claim registries
-> ModelGraph / EvidenceGraph / NarrativeGraph
-> ModelStory / expression planning
-> ResearchStatePaperService
-> CompetitionPaperAuditor
-> PaperQualityBenchmark / ExcellentCorpus / SameProblem benchmark
-> EvidenceLockedWriter / refinement
-> LaTeX / PDF / visual review
-> recurrent repair routing
```

这条链已经远超“LLM 一次性写论文”，但 V6 的关键问题是：**各层是否真正因果提升最终 award-quality，而不是只让内部 Gate 更完整。**

---

## 4. 能力层真实状态

| 层 | 当前真实主导实现 | 类型 | 主要输入 | 主要输出 | 是否影响最终论文 | Phase 0 风险 |
|---|---|---|---|---|---|---|
| ProblemGraph | `ProblemGraphService` + contract dependency inference | hybrid，结构化/规则为主 | 题意抽取、SubproblemContract | node / dependency / task family | 是 | 上游 contract 质量仍决定搜索空间 |
| ModelingBrain | `ModelingBrainService` | deterministic retrieval + rule/hybrid infrastructure | ProblemGraph node、HMML、Cards、Skills、C-priors | candidates、selected methods、obligations | 是 | 候选搜索仍受已有 registry / solver 可用性强约束 |
| ModelStructure | `ModelStructurePlanner`，由 ModelingBrain 调用 | deterministic planner | node + graph + preference | `ModelStructurePlan` / unified framework | 是，但需继续做 influence audit | 新抽象存在，不代表已获得足够高层主导权 |
| Solver / Validation | SolverRegistry / SubproblemEngine / ValidationProtocol | deterministic execution | selected executable method + data | 真实结果、validation | 是 | 当前最可信层之一；V6 不应破坏 |
| Evidence / Provenance | contracts / claims / figures / artifacts / evidence graph | deterministic governor | solver outputs | 可追溯 evidence | 是 | 强项，应保留 |
| ModelStory | `ModelStoryPlanner` / NarrativeGraph | planner + deterministic projection | Research State / Model Spine | story stages / narrative | 是 | 是否显著改变最终 paper architecture 尚未做 causal ablation |
| Paper compiler | `ResearchStatePaperService` + outline/renderer + EvidenceLockedWriter | deterministic/hybrid | Narrative + evidence | Markdown/LaTeX paper | 是，当前主导 | 固定 grammar/section contract 可能压制自由结构，H2 待测 |
| Internal quality | `PaperQualityEvaluator`, `PaperQualityBenchmarkService`, `CompetitionPaperAuditor`, `ExcellentCorpusBenchmarkService` 等 | 规则/统计 detector 为主 | paper text + generator-side structured state | gate / score / gap | 是，驱动 refinement | 当前最可疑：能守底线，但 award preference 未验证 |
| Visual / PDF | Figure Art/Color/Composition + PDF visual structural review | hybrid | figures + final PDF | figure/layout review | 是 | page-vision/human review 仍不完整 |
| Recurrent repair | `RecurrentWorkstationService` / repair router | deterministic governor | findings / issue severity | rollback/pivot/repair target | 是 | 依赖上游 Judge 的 issue 是否真的代表 award gap |

---

## 5. 旧抽象仍然存在的证据

当前仓库仍保留旧 `ModelPlan`：

```text
ModelPlan.task_type = regression | classification
REGRESSION_MODELS = linear/ridge/lasso/elastic_net/random_forest/gradient_boosting
CLASSIFICATION_MODELS = logistic/random_forest/gradient_boosting
```

虽然新的 ProblemGraph / ModelStructure / task-specific solver 已经扩展研究表达，但这个历史抽象仍然存在于真实 pipeline 与 evaluation service 中。

因此 Phase 0 不得假定：

> “有 ModelStructurePlan 文件” = “研究架构已经完全脱离旧 regression/classification 抽象”。

该问题留给 V6 Experiment 2/3，而不是本轮修改。

---

## 6. Representative generated papers

### 6.1 当前 MCM 2024 C

Case：

```text
20260823-MCM-0004-D97D
```

PDF：

```text
docs/generated_samples/mcm2024_c_showcase/workspace/20260823-MCM-0004-D97D/paper/submission/mcm-2024-c-showcase.pdf
```

冻结时记录：

```text
pages = 19
figures = 11
tables = 4
paper_audit = PASS
visual_quality = REVIEW:91.0
pdf_visual_structural = PASS
pdf_visual_vision = REVIEW_PENDING
```

同一稿件内部 `PaperQualityBenchmarkService` 已持久化：

```text
score = 88.75
gate = REVIEW
```

但该 88.75 仅来自：

- abstract density；
- abstract numeric density；
- figure density；
- table density。

因此它是 document-density calibration，不是 award-quality score。

### 6.2 当前 CUMCM 2023 C

Case：

```text
20260822-CUMCM-0031-SRTA
```

PDF：

```text
docs/generated_samples/cumcm_2023_c_showcase/workspace/20260822-CUMCM-0031-SRTA/paper/submission/cumcm-2023-c-showcase.pdf
```

冻结时记录：

```text
pages = 20
figures = 10
tables = 6
visual_quality = REVIEW:91.0
audit = PASS
pdf_visual_structural = PASS
pdf_visual_vision = REVIEW_PENDING
```

这些结果说明 current pipeline 可以稳定生成完整、可编译、内部规则较干净的论文；它们**不证明**与 O/F/国奖论文的盲评差距已缩小。

---

## 7. Excellent-paper corpus baseline

Primary C-problem benchmark registry：

```text
config/ref_models/c_problem_excellent_benchmark_v1.json
```

当前登记：

```text
3 CUMCM C corpora
2 MCM C corpora
21 reference papers
```

benchmark registry 自己已经诚实标记：

```text
fulltext_text_layer = PASS
cross_competition_corpus = PASS
pdf_visual_layout = UNVERIFIED
blind_human_competition_review = UNVERIFIED
```

这两个 `UNVERIFIED` 是 V6 Phase 1 的直接前提，不能被内部分数覆盖。

外部“直接参考论文”目录已重新验证可读：

```text
D:\作业\竞赛\大学生数学建模\美赛\备赛\资料\论文\直接参考论文
```

其中本轮优先选用：

```text
2318036_2023_MCM_C_Outstanding.pdf
2409404_2024_MCM_C_Outstanding.pdf
```

因为它们与当前 C-only 目标一致，且 2024 文件可与当前 2024 MCM C 工作站稿构成 same-problem calibration pair。

---

## 8. Evaluator baseline classification

### `PaperQualityEvaluator`

主要维度存在明显关键词/结构信号：

- problem/data/model/result keyword coverage；
- 是否有公式；
- claim/figure refs coverage；
- abstract 目的/方法/结果/结论关键词；
- abstract 长度；
- paragraph useful length / duplicate ratio。

适合：

```text
hard integrity / regression / completeness / local refinement signal
```

未经验证，不适合直接作为：

```text
O/F/国奖 award-quality reward
```

### `PaperQualityBenchmarkService`

当前主要比较：

```text
abstract units
abstract numeric tokens
figure density
table density
(reference density only when verified source allows)
```

适合 document-density calibration，不等于 scientific-core judge。

### `ExcellentCorpusBenchmarkService`

大量 detector 检查 recurring pattern，例如：

- assumptions；
- strengths/weaknesses；
- quantified results；
- workflow figure；
- sensitivity/robustness；
- recommendation；
- formulas / metrics。

其代码注释已强调不能据此虚构实验，这是强项；但 pattern MET 数量本身未被证明能预测真实 award preference。

### `CompetitionPaperAuditor`

强项：

- internal ID / contamination；
- references；
- research state coverage；
- document/research defect routing；
- competition profile hard rules。

风险：若把 `BLOCK/REVIEW` 数量进一步当成奖级排序，会把 hard-gate 语义误用为 award reward。Phase 1 已直接观察到这一点。

---

## 9. Baseline tests

本轮没有为了让 V6 变绿而修改旧 evaluator。

执行：

```text
PYTHONPATH=src python -m pytest -x -vv \
  tests/test_competition_paper_auditor.py \
  tests/test_paper_quality_benchmark.py \
  tests/test_excellent_corpus_benchmark.py \
  tests/test_same_problem_benchmark.py \
  tests/test_c_problem_benchmark.py
```

结果在第 11 项停止：

```text
10 passed
1 failed
```

失败：

```text
tests/test_excellent_corpus_benchmark.py::test_wordle_gap_benchmark_separates_research_from_document_gap
```

失败原因不是数值/逻辑 gate 变化，而是测试仍断言旧 evidence 文案：

```text
No distinct alternative is explicitly registered as executable PASS
```

当前 HEAD 实际文案已经是：

```text
No distinct alternative is both solver-available and semantically comparable; comparison is not fabricated from alias availability or PLANNED candidate labels.
```

Phase 0 只冻结该回归，不在 Judge Validity 研究中顺手修旧测试。

随后单独执行：

```text
PYTHONPATH=src python -m pytest -q tests/test_same_problem_benchmark.py tests/test_c_problem_benchmark.py
```

结果：

```text
7 passed
```

V6 新增 JudgeEval 基础设施测试：

```text
PYTHONPATH=src python -m pytest -q tests/test_judge_validity.py
```

结果：

```text
5 passed
```

---

## 10. Phase 0 frozen known gaps

1. `blind_human_competition_review` 仍为 `UNVERIFIED`。
2. `pdf_visual_layout` / true page-vision award comparison 仍为 `UNVERIFIED`。
3. current internal evaluators 没有经过 JudgeEval 校准。
4. generator-side structured state 与 external raw paper 输入不完全对称；某些 evaluator 天生更适合审工作站 artifact，而不是公平审外部论文。
5. `ModelStoryPlanner` / `ModelStructurePlanner` 已存在，但尚无 causal influence ablation 证明其对最终 award preference 的贡献。
6. 旧 `ModelPlan(regression/classification)` 抽象仍存在，是否限制 Creator 尚未验证。
7. 当前论文内部 gate/visual score 较高，但用户对照真实优秀论文后仍观察到明显 gap；V6 不再用“再加模块”直接响应该症状。

---

## 11. Phase 0 Gate

现在可以明确回答：

> **V5/current 是什么？**

它是一个 evidence/governance 较强、真实 solver/validation/traceability 基础完整、paper compiler 与多层 detector 已高度工程化的 C题工作站；但其 award-quality evaluator 尚未被证明可信，且 Creator/Compiler 新模块的因果影响尚未系统测量。

因此：

```text
Phase 0 = PASS
```

PASS 的含义仅为：baseline 已冻结、可复现、可比较。

它不表示工作站已达到 O/F/国奖水平。

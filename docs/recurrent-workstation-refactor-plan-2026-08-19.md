# 数模 AI 工作站：M 轮全链路循环重构计划

状态：执行中  
日期：2026-08-19  
目标：把当前“单次建模主链 + 成稿后论文精修循环”升级为“同一个 Case 上执行 M 轮完整科研/论文循环”的工作站。

---

## 0. 先纠正一个最重要的架构理解

用户最初的设计不是：

```text
problem -> data -> model -> experiment -> paper -> refinement x M
```

也不是“先只跑一次建模，最后把同一篇论文润色 M 次”。

真正目标是：

```text
Round 1: 题意 -> 数据 -> 建模 -> 实验 -> 证据 -> 论文 -> 评审
                         ↓ hidden state / artifacts / lessons
Round 2: 题意 -> 数据 -> 建模 -> 实验 -> 证据 -> 论文 -> 评审
                         ↓
Round 3: 题意 -> 数据 -> 建模 -> 实验 -> 证据 -> 论文 -> 评审
                         ↓
...
Round M: 全链路终审 -> LaTeX/PDF -> submission
```

每一轮都必须“看见并审计”全链路，但不是机械地把所有步骤重新计算一遍。没有变化、证据仍有效的节点应复用；发现上游缺陷时，从最早受影响节点开始重新执行，并自动使下游结果失效后重建。

所以：

- **Round = 工作站级循环**，覆盖题意、数据、模型、实验、证据、论文、图表、提交。
- **Stage = Round 内的局部执行单元**，例如模型搜索、敏感性实验、论文局部修补。
- 现有 `refinement_loop` 保留，但降级为 **Round 内的 paper repair cell**，不再承担整个 M 轮架构。
- 现有 `refinement/hidden_state.json` 继续服务论文局部精修；新增工作站级 hidden state 管理 Round 间状态。

---

## 1. 当前代码与目标架构的差距

当前 `default_workflow_graph()` 是单向 DAG：

```text
input_validation
-> problem_analysis
-> data_registration -> data_quality -> eda
-> model_plan -> baseline -> experiments -> model_selection -> sensitivity
-> paper_outline -> paper_draft -> consistency_check
-> refinement_loop
-> final_review -> export
```

当前优点：

- 证据优先、Artifact append-only、Claim/Result/Table 可追踪；
- 有 `mark_stale()`，上游变化可以让下游节点失效；
- 有完整的论文精修事务、接受/回滚、隐藏状态；
- 有多模型 fan-out / judge / adjudicator 的独立实现；
- 有优秀论文 Comparator、知识卡、学习回路等增强模块。

但与原始设计相比仍有五个结构性问题：

1. **循环位置错误**：循环只发生在 `paper_draft` 之后，模型和实验不会因为后续评审而重新进入。
2. **工作站级状态缺失**：只有 paper refinement hidden state，没有“本轮模型为什么变、实验缺什么、下一轮从哪里修”的统一记忆。
3. **修复路由缺失**：评审发现“模型证据不足”时，当前主要只能修文字，不能自动路由回 `model_plan / experiments`。
4. **多模型探索未进入主链**：仓库已有 fan-out / judge，但 `AutoPipelineService.run()` 仍以单个模型计划主线为中心。
5. **Round 级事务缺失**：缺少“本轮开始快照 -> 修改上游 -> 重建下游 -> 全局评分 -> 接受/拒绝 -> 保留历史”的事务语义。

---

## 2. 目标架构：外层 Recurrent Workstation Loop

最终结构：

```text
                 ┌──────────────────────────────────────┐
                 │   Workstation Hidden State h_t      │
                 │ quality / issues / lessons / lineage│
                 └──────────────────┬───────────────────┘
                                    │
                                    v
┌────────────────────────────────────────────────────────────────┐
│ Round t                                                        │
│                                                                │
│  A. Global Audit                                               │
│     problem / data / model / experiment / evidence / paper /   │
│     figures / submission                                       │
│                         │                                      │
│                         v                                      │
│  B. Repair Router                                              │
│     选择最早需要重跑的 workflow node                            │
│                         │                                      │
│                         v                                      │
│  C. Invalidate + Rebuild                                       │
│     mark_stale(pivot) -> 从 pivot 重建受影响链路                │
│                         │                                      │
│                         v                                      │
│  D. Inner cells                                                │
│     model fan-out / experiments / paper refinement / figures   │
│                         │                                      │
│                         v                                      │
│  E. Round Evaluation                                           │
│     与上一轮比较质量、证据、成本、稳定性                          │
│                         │                                      │
│                         v                                      │
│  F. Commit / Reject                                            │
│     接受新 ACTIVE lineage；拒绝则恢复上一轮 active pointers     │
└────────────────────────────────────────────────────────────────┘
                                    │
                   convergence? ----┴---- no -> Round t+1
                            yes
                             v
                    final_review -> submission
```

### 2.1 “每轮覆盖全流程”如何理解

每轮必须执行 **Global Audit**，对全部领域给出状态；但执行阶段允许复用稳定节点。

例如 Round 2 发现：

- 题意分析：PASS
- 数据语义：PASS
- 模型对比：弱，只有一条主路线
- 误差分析：不足
- 论文：结果解释弱

则 Round 2 的 pivot 是 `model_plan`，而不是重新解析题目、重新上传数据。随后：

```text
model_plan (新候选/新假设)
-> experiments
-> model_selection
-> sensitivity/diagnostics
-> evidence refresh
-> paper affected sections rebuild
-> local refinement
-> round review
```

这既符合“每一轮覆盖整个工作站”，又避免无意义重复计算。

---

## 3. 工作站级 Hidden State

新增：

```text
<case_root>/workstation/hidden_state.json
<case_root>/workstation/rounds/round-001/
<case_root>/workstation/rounds/round-002/
...
```

`hidden_state.json` 只保存紧凑、可恢复、可审计的信息，不保存大段原始上下文：

```json
{
  "schema_version": 1,
  "case_id": "...",
  "round": 2,
  "status": "RUNNING",
  "quality": {
    "problem": 1.0,
    "data": 0.92,
    "model": 0.71,
    "experiment": 0.66,
    "evidence": 0.90,
    "paper": 0.78,
    "presentation": 0.70,
    "submission": 0.45,
    "total": 0.765
  },
  "open_issues": ["..."],
  "resolved_issues": ["..."],
  "next_pivot": "model_plan",
  "lessons": ["当前单模型路线对高波动区解释不足"],
  "active_lineage": {
    "model_plan": "artifact-...",
    "model_comparison": "artifact-...",
    "paper": "artifact-..."
  },
  "round_history": [
    {"round": 1, "accepted": true, "pivot": "bootstrap", "delta": 0.0},
    {"round": 2, "accepted": true, "pivot": "model_plan", "delta": 0.07}
  ]
}
```

原则：

- 原始证据仍以 Artifact/Registry 为真源；
- hidden state 只保存“下一轮应该怎么继续”的控制信息；
- 每个 Round 的详细 audit / plan / before / after / decision 都单独落盘；
- 跨对话时，新的 AI 首先读取此文件与本设计文档，即可恢复工作。

---

## 4. Round 级质量向量

论文质量不能再由单一 paper evaluator 代表。工作站级质量至少包含：

| 维度 | 关注内容 | 典型修复 pivot |
|---|---|---|
| `problem` | 子问题覆盖、目标/约束/输出是否明确 | `problem_analysis` |
| `data` | 数据语义、缺失/异常/泄漏、切分正确性 | `data_quality` / `eda` |
| `model` | 候选充分性、公式/假设、模型选择合理性 | `model_plan` |
| `experiment` | baseline、对照、CV、消融、敏感性、误差分析 | `experiments` |
| `evidence` | Result/Claim/Table/Figure 可追踪与 paper-ready | `model_selection` 或证据桥 |
| `paper` | 结构、论证、语言、引用、结果解释 | `paper_outline` / `paper_draft` / `refinement_loop` |
| `presentation` | 图表、流程图、公式、LaTeX、版式 | figure / LaTeX cell |
| `submission` | 最终格式、隐私、引用、PDF/ZIP 完整性 | `final_review` / submission |

Round 接受不只看 `total`，还必须满足：

- 不新增 P0/P1 硬错误；
- 不破坏已验证证据；
- 目标维度至少有可解释提升；
- 若上游发生实质变化，下游证据必须完成重建；
- 成本/时间不得无限增长。

---

## 5. Repair Router：评审必须能回到上游

每个 finding 必须带：

```json
{
  "issue_id": "...",
  "domain": "experiment",
  "severity": "P1",
  "code": "NO_ABLATION",
  "message": "核心方法缺少消融",
  "repair_node": "experiments",
  "evidence_ids": ["artifact-..."],
  "round": 2
}
```

Router 规则：

1. 收集全域 findings；
2. 按 P0 > P1 > P2 排序；
3. 找到所有待修问题中 **workflow 最早的 repair node** 作为本轮 pivot；
4. `mark_stale(pivot)` 使依赖其的下游 ACTIVE 结果进入 STALE；
5. 从 pivot 开始重建，直到 paper/final review；
6. 完成后重新做 Global Audit。

这条规则解决当前系统最大问题：

> “评审说模型/实验有问题，但循环只能改论文文字”。

以后如果缺的是实验，系统就必须回实验；缺的是模型，就必须回模型；只有真正的文字问题才进入 paper refinement。

---

## 6. 模型主线重构

当前主 `AutoPipelineService` 仍偏单计划/单最优模型路径；仓库已有 fan-out/judge/adjudicator，但没有成为主链默认能力。

目标：

```text
model_plan
  -> candidate family fan-out
      -> simple baseline
      -> statistical / classical
      -> ML
      -> task-specific candidate
      -> optional LLM-proposed candidate
  -> protocol-normalized evaluation
  -> diagnostics / failure slices
  -> judge
  -> adjudicator
  -> winner or TIE / NO_ACCEPTABLE_WINNER
```

下一 Round 不应只是“再训练一次同模型”，而是根据失败模式更新搜索空间：

- 欠拟合 -> 增加表达能力；
- 高方差 -> 简化模型/正则/更多稳健验证；
- 某区间失败 -> 构造分段/专家/特征；
- 数据量不足 -> 优先简单模型与稳健性；
- 两模型容差内 -> 简单模型优先；
- 无可接受模型 -> 扩充候选而不是硬选一个。

所有候选失败必须保留，不允许只保留最终 winner。

---

## 7. 论文在 Round 中的位置

论文不再是最后一次性生成，也不能每轮整篇重写。

策略：

- Round 1 生成第一版完整论文；
- 后续 Round 根据新的 Artifact lineage，计算受影响章节；
- 未受影响章节保持原文；
- 受影响章节重新生成/局部修补；
- 最后再进入现有 `refinement_loop` 做 bounded paper repair；
- `refinement/hidden_state.json` 作为 paper cell 内部状态，工作站 `workstation/hidden_state.json` 作为外部 Round 状态。

因此是“两层记忆”：

```text
workstation hidden state  —— 研究/建模/实验/论文之间
        |
        └── paper refinement hidden state —— 论文内部 Stage 之间
```

---

## 8. Round 事务与回滚

每轮目录：

```text
workstation/rounds/round-002/
  audit.before.json
  plan.json
  lineage.before.json
  execution.jsonl
  audit.after.json
  decision.json
  summary.md
```

Round 开始时记录 ACTIVE lineage 快照。

Round 结束：

- ACCEPT：新产物保持 ACTIVE，旧产物由现有 ArtifactRegistry 规则变为 SUPERSEDED；更新 hidden state。
- REJECT：不删除新产物，标记为 rejected/debug lineage；恢复上一轮 active pointers / checkpoint；记录拒绝原因。
- CRASH：`hidden_state.status=RUNNING` + round 目录存在 pending 信息，新进程可 resume/reconcile。

绝不通过 `git restore` 或删除 Case 文件实现业务回滚。

---

## 9. 实施路线

### R0 — 设计冻结与基线

- 写本文件；
- 记录当前 git dirty state；
- 固定现有测试基线；
- 记录已知失败，不把旧失败误算为新回归。

### R1 — Workstation hidden state + Round audit/router

新增：

- `src/mathworkstation/recurrent_workstation.py`
- 工作站级状态存储；
- domain quality / finding schema；
- 从现有 workflow/review/refinement 产物做确定性 Global Audit；
- Repair Router；
- round begin/commit/reject/reconcile；
- 单元测试。

### R2 — 将 AutoPipeline 拆成可重入 stage executor

目标：不再只有一个 200+ 行 `run()` 一次性串到底。

拆成：

```text
bootstrap_inputs()
run_problem_cell()
run_data_cell()
run_model_cell()
run_experiment_cell()
run_evidence_cell()
run_paper_cell()
run_submission_cell()
```

每个 cell：

- 输入来自 Artifact IDs；
- 可判断“仍有效则复用”；
- 可从 STALE/RETRYING 状态重跑；
- 返回统一 execution record。

### R3 — RecurrentWorkstationService

新增：

```text
run_round()
run_until_converged(max_rounds=M)
resume_round()
```

流程：audit -> route -> mark stale -> execute from pivot -> audit -> decision -> state update。

### R4 — 模型 fan-out 主链接入

- 将已有 `agents/modeling.py` 的候选/评估/裁判能力接入 `run_model_cell()`；
- 默认至少 baseline + 2 个互补候选；
- Round 间依据 diagnostics 修改候选集；
- 保留 TIE / NO_ACCEPTABLE_WINNER；
- 继续复用现有 1% 容差与简单模型优先规则。

### R5 — Experiment repair / learning loop

- 缺少消融、敏感性、误差切片、稳定性时自动回 experiments；
- 将 previous round failure modes 写入下一轮 model/experiment context；
- 对相同 protocol + dataset + hyperparameters 复用计算。

### R6 — Incremental paper rebuild

- Artifact lineage diff -> section impact map；
- 只重建受影响章节；
- 现有 paper refinement 作为内层 bounded repair；
- 优秀论文 Comparator 只提供“泛化缺口”，不得把参考年份/外部数字直接注入冻结正文。

### R7 — Web/CLI

展示：

- Round N / M；
- 当前 pivot；
- 8 维质量向量；
- open/resolved issues；
- 本轮模型候选与实验状态；
- paper inner-stage；
- accept/reject 原因；
- resume/retry。

### R8 — 国赛级 Benchmark

至少跑：

- CUMCM 不同题型；
- MCM/ICM；
- 预测、优化、评价、机制/仿真；
- 故意注入数据泄漏、弱模型、少实验、错误图表、证据断链；
- 验证 Router 是否真的回到正确上游；
- 盲评论文质量，而不是只看内部 keyword score。

---

## 10. 当前执行断点（供下一次对话接手）

2026-08-19 接手时确认：

- 仓库：`D:\computer learning\vibe_coding\math_model_ai_process`
- CodeGraph：索引正常且最新；
- `refinement_hidden_state.py` 已存在；
- `RefinementService` 已具备可选 hidden state hook；
- 当前主链仍是单次 DAG + 尾部 `refinement_loop`；
- 当前工作区有未提交的 ExcellentPaperComparator 接线改动；不得重置；
- 基线测试：`test_refinement_hidden_state.py`、`test_workflow_recovery.py`、`test_full_smoke_dag_order.py` 通过；`test_auto_pipeline_e2e.py` 有 1 个既有失败：期望 accepted_stages=[1]，实际 []；
- 下一步从 **R1** 开始编码，不重复实现 paper hidden state。

---

## 11. 这次重构的验收标准

不能只看“代码有循环”。真正验收必须满足：

1. 一个 Case 可执行 M 个 Workstation Round；
2. 每个 Round 都产生全域 audit；
3. 评审发现模型/实验问题时能自动路由回上游，而不是只改文字；
4. 上游变化会使下游 stale 并重建；
5. Round 间有持久 hidden state，跨进程/跨对话可恢复；
6. 一轮失败不会污染上一轮有效论文/证据；
7. 多模型候选成为主链能力，不再只有单一路线；
8. 论文是同一篇持续更新，不是 M 篇独立稿件；
9. 所有数值仍来自证据注册表，不从 hidden state/LLM 记忆生成；
10. 最终质量用真实题目和盲评验证，不以内部 0.9x 分数自证。

这十条全部成立，才算真正实现用户最初的“RNN/GRU/LSTM 式 M 轮数学建模工作站”。

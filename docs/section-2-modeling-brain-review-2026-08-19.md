# Section 2 复盘：Modeling Brain

日期：2026-08-19
状态：Gate PASS
真实验收题：2023 MCM Problem C — Wordle

## 原来具体有什么问题

仓库并不是没有方法知识：已经有 HMML、Knowledge Cards、模型目录和一批数学建模 Skills。真正的问题是这些知识此前主要进入“全题一个 ModelPlan”的 prompt，无法回答更细的问题：

- SP1 为什么应该优先时序/趋势/区间模型？
- SP2 为什么需要解释性效应估计而不是追求单纯预测误差？
- SP3 为什么需要分布约束和不确定性？
- SP4 为什么需要分类/校准？
- SP5 为什么应该做探索发现而不是训练同一个 best model？

也就是说，知识库存在，但没有成为每个 SubproblemNode 的独立“选模脑”。此外，“检索到一个方法”和“当前工程已经能执行这个方法”此前没有强制分离，容易把建议误写成已实现能力。

## 外部成熟项目怎么做

本节重新核验了 MM-Agent / LLM-MM-Agent 的公开仓库。其公开说明明确采用：

```text
Problem Analysis
-> Mathematical Modeling
-> Computational Solving
-> Solution Reporting
```

并在 Mathematical Modeling 阶段使用三层 HMML（domain / subdomain / method nodes）做问题感知的方法检索，再由求解阶段执行代码。公开说明还强调先把复杂问题拆成子任务，再为子任务检索合适方法，而不是对整题一次性选择一个模型。

这与本节采用的核心分层一致：

```text
SubproblemNode
-> method retrieval
-> candidate strategy set
-> feasibility critic
-> executable / needs-solver / reject
-> Solver Engine
```

同时继续保留 data-to-paper 的边界：检索/建议本身不是论文证据；真正可以进入 paper lineage 的数值必须来自已执行、可回溯的计算产物。

## 我们具体改了什么

新增：

- `src/mathworkstation/modeling_brain.py`
  - `CandidateStrategy`
  - `ModelingBrainDecision`
  - `ModelingBrainService`
- `src/mathworkstation/modeling_skills.py`
  - 读取仓库已有 `examples/ai_skills_extracted/.../skills/*/SKILL.md`
  - 只抽取使用条件、禁用条件、质量检查和真实存在的方法提示
  - 不执行 example 脚本，不把 Skill 当 Solver
- `tests/test_modeling_brain.py`
- `tests/test_modeling_skills.py`

ProblemGraph 的 `SubproblemPlan` 增加：

- `modeling_brain_artifact_id`
- `selected_candidate_ids`

Modeling Brain 目前同时使用四类来源：

1. `native`：ProblemGraph 初始方法路线；
2. `hmml`：仓库现有 HMML MethodRetriever；
3. `knowledge_card`：仓库现有 KnowledgeCardRetriever；
4. `skill`：仓库已有数学建模 SKILL.md 中的真实方法提示、使用边界与质量检查。

每个候选必须经过 Feasibility Critic：

- `PASS`：当前 Solver/执行层已经有兼容能力；
- `NEEDS_SOLVER`：方法合理，但当前 Solver Engine 还没有插件；
- `REJECT`：方法语义与当前 subproblem task family 不匹配。

所以例如 ARIMA 可以因 Wordle SP1 被检索出来，但如果当前 Solver Engine 没有 ARIMA plugin，它只能是 `NEEDS_SOLVER`，绝不能伪装成“已使用 ARIMA”。

AutoPipeline 的生产入口 `execute_subproblem_node()` 现在执行：

```text
ProblemGraph node
-> ModelingBrain.deliberate()
-> modeling_brain_decision artifact
-> SubproblemEngine family dispatch
-> independent execution artifact
-> SubproblemPaperEvidenceBridge
-> Result / Answer / Table / Figure / Claim
```

Modeling Brain decision artifact 被加入 execution upstream provenance，因此方法决策不是旁路报告，而是实际求解链的一部分。

## Skills 怎么处理

仓库里确实存在一套 extracted Skills，例如：

- `mm-model-selector`
- `mm-prediction-models`
- `mm-classification-clustering`
- `mm-optimization-models`
- `mm-simulation-models`
- `mm-evaluation-models`
- `mm-data-eda-cleaning`

但它们目前是 `examples/` 资产，不是 runtime solver registry。

本节没有复制这些脚本到生产层，而是建立只读 `ModelingSkillRetriever`：Skill 负责告诉 Modeling Brain “什么时候该用/不该用、有哪些候选方向、质量检查是什么”；真正能否运行仍由 Feasibility Critic + Section 3 Solver Engine 决定。

这避免了第二套重复 Solver 和 example code 直接进入生产链。

## 真实 Wordle 是否明显变好

真实 Wordle contracts 上已经验证：

- SP1-SP5 分别生成独立 Modeling Brain decision；
- SP6 为 synthesis deliverable，Modeling Brain `SKIP`；
- SP1 确实出现非 native 的方法候选；
- SP4 确实从真实 Knowledge Cards / HMML / Skills 获得分类相关候选；
- 每个 SP1-SP5 的 ProblemGraph plan 都登记独立 `modeling_brain_artifact_id`；
- ArtifactRegistry verify PASS。

更重要的是，检索到的高级方法不会立即被算作完成：缺 Solver 的候选保留为 `NEEDS_SOLVER`，正好成为 Section 3 的能力缺口输入。

最新相关回归：

```text
62 passed
```

覆盖 Modeling Skills、Modeling Brain、真实 Wordle、Subproblem Engine/Paper Bridge、Task executors、claims、AutoPipeline E2E、Recurrent Workstation、Paper contracts。

完整 pytest 仍由既有 Python 3.11 + Tenacity 5.1.5 collection incompatibility 阻塞，与本节无关。

## Section 2 Gate 结论

PASS。

现在 HMML / Knowledge Cards / Skills 不再只是全题 prompt 装饰，而是对每个 ProblemGraph node 独立生成候选与可行性判断，并进入求解 provenance。

下一节：Section 3 Solver Engine。

首要原则仍然是不堆 100 个算法：先统一 SolverPlugin 接口，把当前真正可执行的 gold capabilities 注册起来，同时把 Modeling Brain 的 `NEEDS_SOLVER` 显式转成 solver capability gap。

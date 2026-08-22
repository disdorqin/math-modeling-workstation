# Section 3 复盘：Solver Engine

日期：2026-08-19
状态：第一阶段 Gate PASS
真实验收题：2023 MCM Problem C — Wordle

## 原来具体有什么问题

Section 1 虽然已经让每个 SubproblemNode 拥有独立 task family，Section 2 也能从 HMML / Knowledge Cards / Skills 给每个节点产生方法候选，但执行层仍是分散的：

- `task_executors.py` 有 forecasting/classification/optimization/simulation/ranking；
- `subproblem_executors.py` 有 explanatory/distribution/exploration；
- `SubproblemEngineService` 需要自己维护 family 分发；
- Modeling Brain 的 Feasibility Critic 还可能把“family 有 executor”误解成“某个具体方法已有 solver”。

尤其 optimization 是典型风险：仓库原 executor 只是 bounded grid，却容易在语义上被写成“已经支持 LP/MILP/NLP”。

## 外部成熟项目怎么做

本节重新核验了 MM-Agent / LLM-MM-Agent 的公开仓库说明。其建模阶段通过 HMML 形成方法方案，而 Computational Solving 阶段单独使用 MLE-Solver 生成并迭代代码；方法检索与可执行求解是两个层次，不因为知识库里有一个方法就等于 solver 已经存在。

同时参考 data-to-paper 的 coding guardrails / backward traceability 原则：真正进入科学结论链的计算必须来自可执行代码及其结果，而不是模型在自然语言里声称“做过某实验”。

本节因此采用：

```text
Modeling Brain
-> candidate strategy
-> SolverRegistry capability check
-> SolverPlugin
-> validate_inputs
-> build
-> solve
-> diagnose
-> sensitivity hook
-> export_evidence
```

## 我们具体改了什么

新增：

- `src/mathworkstation/solver_engine.py`
- `tests/test_solver_engine.py`

统一接口 `SolverPlugin`：

```text
supports()
validate_inputs()
build()
solve()
diagnose()
sensitivity()
export_evidence()
```

`SolverEngineService.execute()` 统一：

1. Registry 解析 solver；
2. 输入验证；
3. build；
4. solve；
5. diagnose；
6. sensitivity hook；
7. 写 `solver_execution_result` Artifact。

`SubproblemEngineService` 已改为通过 Solver Engine 求解，不再维护标准/custom/future-aware 三套 if/elif 分发。

### 当前 Gold Solver Registry

已统一注册并真实可执行：

- `gold.forecasting`
  - temporal forecasting baseline
  - future point forecast
  - residual-bootstrap prediction interval
- `gold.classification`
  - logistic baseline
  - future-item classification
- `gold.explanatory_inference`
  - standardized Ridge effect estimation
  - bootstrap effect intervals
- `gold.distribution_forecasting`
  - multi-output Ridge
  - simplex projection
  - future component uncertainty
- `gold.exploratory_analysis`
  - Spearman association
  - IQR outlier scan
  - mean-shift scan
- `gold.linear_programming`
  - SciPy HiGHS `linprog`
- `gold.milp`
  - SciPy `milp`
  - integer/binary integrality
- `gold.clustering`
  - K-Means
  - DBSCAN
- `gold.optimization_grid`
  - 仅作为小规模 bounded-grid baseline
- `gold.monte_carlo`
- `gold.ranking`

本节没有一次性堆 ODE/图论/插值/全部启发式算法；缺失能力继续作为 capability gap 留到后续增量补齐。

## Feasibility Critic 现在以 Registry 为真源

Modeling Brain 不再维护一份容易漂移的“哪些方法可执行”静态表。

现在：

```text
candidate method
-> SolverRegistry.supports_method(method, task_family)
-> PASS / NEEDS_SOLVER
```

例如：

- `bounded-grid optimization`：PASS；
- `linear programming`：只有新增 LP plugin 后才 PASS；
- `integer programming / MILP`：只有新增 MILP plugin 后才 PASS；
- `ARIMA`：仍然 NEEDS_SOLVER；
- `GM(1,1)`：仍然 NEEDS_SOLVER；
- `K-Means`：新增 clustering plugin 后可 PASS；
- `nonlinear programming`：仍然 NEEDS_SOLVER。

因此“加一个 SolverPlugin → capability gap 自动减少”，不会再靠手工修改两个不同模块的判断表。

### solver capability gap

新增持久化：

```text
analysis/solver_gaps/<SP>.json
```

Artifact type：

```text
solver_capability_gap
```

AutoPipeline 的 `execute_subproblem_node()` 当前 provenance：

```text
ProblemGraph node
-> ModelingBrain decision
-> solver capability gap
-> SolverPlugin execution
-> solver execution artifact
-> Result/Answer/Table/Figure/Claim
```

## 真实赛题是否明显变好

是。

真实 2023 Wordle 的通用生产链测试已经在 Solver Engine 接入后重新通过：

- SP1 forecasting 由 `gold.forecasting` 执行；
- SP2 explanatory inference 独立执行；
- SP3 distribution forecast 独立执行；
- SP4 classification 独立执行；
- SP5 exploratory analysis 独立执行；
- SP6 synthesis 不进入 Solver Registry；
- node-specific evidence 继续进入 Result/Answer/Table/Figure/Claim；
- research Gate PASS；
- ArtifactRegistry verify PASS。

此外新增真实数值单测：

- LP 小模型由 `scipy.optimize.linprog` 求出最优解并通过约束诊断；
- MILP 小模型由 `scipy.optimize.milp` 求出整数最优解；
- K-Means 两簇样本得到 2 cluster 并输出 silhouette；
- Modeling Brain 的 ARIMA `NEEDS_SOLVER` 可持久为 gap artifact。

当前相关验证：

- 核心 Solver/Wordle/AutoPipeline/Recurrent/Paper-contract：41 passed；
- task/custom executors + claims + modeling fan-out：36 passed。

完整 pytest 仍由既有 Tenacity 5.1.5 / Python 3.11 collection incompatibility 阻塞。

## Section 3 Gate 结论

第一阶段 PASS。

原因：Section 3 的核心目标不是算法数量，而是建立统一、真实、可审计的求解插件层，并让方法检索与执行能力脱钩。该架构已在真实 Wordle 主链中生效，且新增 LP/MILP/聚类证明 Registry 可扩展。

仍未注册的 Gold 能力（NLP、多目标、图网络、ODE/Markov、拟合/插值等）不伪装成已完成，将由后续真实题/能力缺口驱动增量加入。

下一节：Section 4 ValidationProtocol Registry。

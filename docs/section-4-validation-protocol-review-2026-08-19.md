# Section 4 复盘：ValidationProtocol Registry

日期：2026-08-19
状态：Gate PASS
真实验收题：2023 MCM Problem C — Wordle

## 原来具体有什么问题

旧主线的评价结构严重偏向“统一模型比较”：随机/固定 CV、一个 primary metric、再做全题 sensitivity。即使题目实际包含时间预测、解释性效应、分布预测、分类、探索发现，这些问题也容易被同一套 regression/RMSE 验证语义覆盖。

Section 1-3 已经让 task 和 solver 分开，但如果验证层仍是一套协议，研究结论仍然会错配。例如：

- 时间预测不能随机切分；
- 解释性效应不能只报 RMSE；
- 分布预测必须验证 simplex；
- 分类不能只报 accuracy；
- 探索发现不能因“相关性大”直接升级为确认性结论；
- 优化不能只报 objective value 而不查 feasibility/solver status；
- 仿真不能拿一次随机结果当稳健结论。

## 成熟机制如何处理

本节继续沿用两个已核验原则：

- MM-Agent 的 problem/modeling/solving 分层意味着求解后必须按具体问题语义验证，而不是把所有候选压成一个通用评分；
- data-to-paper 的 guardrail / traceability 原则要求验证结果本身也成为可回溯证据，而不是只在 LLM 文本中声称“验证通过”。

本项目因此把 validation 从 SolverPlugin 内部零散逻辑抽成独立 Registry，并让 solver evidence 显式依赖 validation artifact。

## 我们具体改了什么

新增：

- `src/mathworkstation/validation_protocol.py`
- `tests/test_validation_protocol.py`

核心对象：

```text
ValidationProtocol
ValidationFinding
ValidationAssessment
ValidationProtocolRegistry
ValidationRunner
```

SolverEngine 现在执行：

```text
SolverPlugin.solve
-> SolverPlugin.diagnose
-> ValidationProtocolRegistry.resolve
-> ValidationRunner.assess
-> validation_assessment artifact
-> SolverPlugin.export_evidence
```

若 validation `FAIL`，solver result 不会被当成可接受研究结果继续推进。

`solver_execution_result` 的 upstream 现在包含对应 `validation_assessment` artifact。

ProblemGraph 的 `SubproblemExperiment` 新增：

- `validation_artifact_ids`

并把原先 plan 中的泛化验证文字替换成实际运行后的 protocol id。

## 当前 Validation Registry

### Forecasting

`forecasting.temporal-uncertainty.v1`

检查：

- temporal / rolling-origin split；
- timestamp 有效且无重复；
- leakage guard；
- RMSE / MAE；
- future prediction 时必须有双侧 interval；
- point 必须落在有序 interval 内。

### Classification

`classification.stratified-calibration.v1`

检查：

- stratified holdout；
- accuracy / macro-F1 / balanced accuracy；
- confusion matrix；
- 独立重算 per-class recall；
- multiclass log-loss；
- confidence calibration ECE；
- ECE 弱则 REVIEW，而不是假装校准良好。

### Explanatory inference

`inference.bootstrap-effects.v1`

检查：

- 时间任务使用 temporal holdout；
- RMSE / MAE / R² 仅作为拟合辅助；
- 每个 effect 必须有 bootstrap CI；
- `associational_not_causal` guard；
- bootstrap runs；
- 稳定 effect 数量。

### Distribution forecasting

`distribution.temporal-simplex.v1`

检查：

- temporal holdout；
- MAE / RMSE；
- projected simplex error；
- future distribution 非负且总和满足约束；
- future component uncertainty 存在。

### Exploratory analysis

普通探索：`exploration.discovery-bootstrap.v1`

- strongest association 只作为 hypothesis-generating；
- 对 leading Spearman pair 做 bootstrap sign stability；
- outlier/change scan 仍保留；
- 稳定性不足 → REVIEW。

聚类：`exploration.clustering-stability.v1`

- cluster/noise count；
- 至少两簇时 silhouette；
- 单簇不 BLOCK 代码，但研究结论进入 REVIEW。

### Optimization

`optimization.exact-linear.v1` / `optimization.bounded-grid.v1`

- constraint feasibility；
- LP/MILP solver termination status；
- exact solver 若尚未做 RHS/objective sensitivity → REVIEW，不冒充完全稳健。

### Simulation

`simulation.replication-uncertainty.v1`

- replications；
- seed；
- scenarios；
- mean/std/p05/p95 不确定性。

### Ranking

`ranking.protocol-stability.v1`

- explicit pairwise/listwise protocol；
- MRR/NDCG/pairwise accuracy；
- query groups 有效；
- 后续强排序结论仍需权重/协议 sensitivity。

## 真实 Wordle 是否明显变好

是。

真实 Wordle 数据重新经过 SolverEngine + Validation Registry：

```text
SP1 -> forecasting.temporal-uncertainty.v1
SP2 -> inference.bootstrap-effects.v1
SP3 -> distribution.temporal-simplex.v1
SP4 -> classification.stratified-calibration.v1
SP5 -> exploration.discovery-bootstrap.v1
```

五个 protocol 完全不同，且没有任何节点 validation FAIL。

新增真实检查包括：

- SP1 future interval 结构；
- SP2 bootstrap effect CI；
- SP3 projected simplex error；
- SP4 calibration ECE；
- SP5 bootstrap association sign stability。

因此现在不能再用一个 RMSE 宣称“六问都验证通过”。

## 回归结果

最近：

- Validation/Solver/Brain/真实 Wordle/AutoPipeline/Recurrent/Paper-contract：45 passed；
- executors/claims/modeling-fanout：38 passed。

完整 pytest 的既有 Tenacity/Python 3.11 collection incompatibility 仍单独存在。

## Section 4 Gate 结论

PASS。

不同研究任务已经有不同的验证协议，且 validation 自身被持久化并进入 solver provenance。

下一节：Section 5 — 真正的 M-Round Research Refinement。

重点不再是论文 Stage 循环，而是 Reviewer 根据 ProblemGraph/ModelingBrain/SolverGap/ValidationFinding，把研究缺陷路由回对应 node，并在下一 Round 重新执行 Research State。

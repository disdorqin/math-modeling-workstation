# Section 5 Review — M-Round Research Refinement

Last updated: 2026-08-19 23:10 +08:00

## Gate

**PASS。** Section 5 已从“论文反复润色”升级为可回退、可重放、依赖感知的 Research State repair loop。

生产主链：

```text
ProblemGraph / Solver / Validation / Evidence
-> WorkstationGlobalAuditor
-> WorkstationFinding(subproblem_id, repair_phase)
-> WorkstationRepairRouter
-> ResearchRepairTarget
-> AutoPipeline.run_recurrent_round()
-> replay exact solver input / repair exact subproblem
-> invalidate dependent synthesis
-> rebuild downstream evidence-locked deliverable
-> audit again
-> accept / reject Round
```

## 原问题

旧 recurrent workstation 虽已有 round transaction、hidden state、rollback/recovery，但修复粒度主要仍是 `model_plan / experiments / paper_draft / refinement_loop`。真实研究缺陷不能精确定位到“哪个子问题、哪个研究阶段”，也无法保证 Round 2 重放 Round 1 的派生特征。

## 本节完成

- `WorkstationFinding` 增加 `subproblem_id / repair_phase / research_artifact_id`。
- `WorkstationRoundPlan` 增加 `repair_targets` 与 M-Round `focus`。
- Auditor 纳入 ProblemGraph node state、blocking solver gap、validation assessment、subproblem evidence projection。
- `AutoPipeline.run_recurrent_round()` 真正消费 node-level research target。
- Solver 保存实际执行输入快照 `solver_input_frame`，后续 Round 精确 replay。
- M-Round curriculum：Coverage → Correctness → Modeling Depth → Robustness → Storyline → Competition Polish；P0/P1 始终高于阶段 focus。
- Round acceptance 不再只看粗粒度 domain 总分；finding severity burden 的实质下降也可构成进步，但不能用它掩盖新 P0 或 domain regression。

## 真实 Wordle Gate

### SP3 validation 精确回退

对真实 2023 MCM Wordle 临时 Case 注入 SP3 distribution validation REVIEW：

```text
SP3 / validation / experiments
```

Router 精确定位，AutoPipeline 不进入 legacy whole-model reentry，也不进入 paper-only refinement。

### Downstream dependency correctness

SP3 新 solver/validation generation 会使依赖旧 SP3 evidence 的 SP6 synthesis 自动失效。系统现在不会保留旧 editor-letter 证据链，而是自动执行：

```text
subproblem:SP3:validation
subproblem:SP6:synthesis
```

SP6 自动重建稿只拼接当前 accepted dependency answers，不新增数字或推断；竞赛级表达留给 Section 6 Paper/Narrative Engine。

这修复了 Section 5 最后的重要语义漏洞：**上游研究变化后，下游交付物不能继续引用旧证据。**

### Solver gap routing

blocking capability gap 可保持在：

```text
SPx / solver / model_plan
```

不会错误降级成 paper polishing。

## 最新验证

```text
python -m pytest -q \
  tests/test_research_recurrent_router.py \
  tests/test_recurrent_workstation.py \
  tests/test_validation_protocol.py \
  tests/test_solver_engine.py \
  tests/test_wordle_2023_problem_graph_gate.py

34 passed
```

Full pytest 的既有 Python 3.11 + Tenacity 5.1.5 collection incompatibility 仍是环境阻塞，不是 Section 5 新回归。

## 客观结论

Section 5 Gate 通过。Research defect 已能回到具体研究节点并正确传播 downstream invalidation；Document defect 仍留在 Paper Cell。接下来主要进入 Section 6，并把优秀论文资料真正变成 gap-driven Paper Engine 的外部镜子。

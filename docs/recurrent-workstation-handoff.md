# Recurrent Workstation Handoff

Last updated: 2026-08-19

> 新对话 / 新 Agent 接手本项目时，先读：
>
> 1. `AGENTS.md`
> 2. `docs/recurrent-workstation-refactor-plan-2026-08-19.md`
> 3. 本文件
>
> 然后运行 `codegraph status`，不要重新从“论文 hidden state”开始设计。

## 用户真正要的架构

不是：

```text
一次建模 -> 一篇论文 -> refinement x M
```

而是：

```text
Bootstrap
-> Round 1: 全域审计 -> 找最早缺陷 -> 重跑受影响链 -> 全域复审
-> Round 2
-> ...
-> Round M
-> submission
```

每轮审计全部领域，但不机械重复所有计算。没有变化且证据仍有效的节点复用；一旦上游改变，用现有 `WorkflowController.mark_stale()` 让下游失效，再从最早 repair pivot 重建。

现有 `refinement_loop` 只是 Round 内的 paper repair cell；不要再把它当整个工作站的外层循环。

## 已完成

### R0：设计冻结

已新增：

- `docs/recurrent-workstation-refactor-plan-2026-08-19.md`

里面定义 Round/Stage、双层 hidden state、8 维质量、Repair Router、Round 事务、R0-R8 路线和验收标准。

### R1：工作站级控制平面

已新增：

- `src/mathworkstation/recurrent_workstation.py`
- `tests/test_recurrent_workstation.py`

当前能力：

- `RecurrentWorkstationConfig`
- `WorkstationFinding`
- `WorkstationAudit`
- `WorkstationRoundPlan`
- `WorkstationRoundDecision`
- `WorkstationGlobalAuditor`
- `WorkstationRepairRouter`
- `WorkstationRoundStore`
- `RecurrentWorkstationService`
- `decide_round()`

Case 级持久状态：

```text
workstation/hidden_state.json
workstation/rounds/round-001/
  audit.before.json
  plan.json
  lineage.before.json
  execution.jsonl
  audit.after.json
  lineage.after.json
  decision.json
```

Repair Router 已能把：

- workflow STALE/FAILED/BLOCKED
- paper consistency
- CompletePaperContract 缺陷
- refinement 异常停止
- 关键产物缺失

映射回 `problem_analysis / data_quality / model_plan / experiments / model_selection / paper_draft / refinement_loop / final_review / export` 等上游 pivot。

Round reject 不删除候选结果，只恢复上一轮 active lineage 指针。

### Bootstrap 已接入 AutoPipeline

`AutoPipelineService.__init__` 已创建：

```python
self.recurrent = RecurrentWorkstationService(cases, self.workflow)
```

一次原有全流水线完成 export 后，会调用：

```python
self.recurrent.register_bootstrap(...)
```

并写入 `workstation/hidden_state.json`，作为 Round 0 baseline。

active lineage 当前登记：

- dataset id
- problem source artifact
- problem analysis artifact
- model plan artifact
- model comparison artifact
- model selection artifact
- sensitivity artifact
- paper draft artifact
- paper final artifact
- complete-paper review artifact
- full review artifact
- case export artifact

`AutoPipelineService.run()` 返回值新增 `workstation` 摘要（round/status/gate/quality/open issues）。

### ExcellentPaperComparator 接线冲突已修复

接手时仓库原有一个红灯：

```text
test_auto_pipeline_produces_traceable_refined_export
expected accepted_stages == [1], actual []
```

根因不是 refinement loop 本身，而是 Comparator 的诊断 `reason` 带“参考年份/出现次数”，确定性测试把这些外部数字复制进论文；refinement 的 frozen-number gate 正确拒绝了 patch。

现在：

- Comparator 完整报告仍保存在内部审计 context；
- `_prompt_safe_excellent_ref()` 只给论文 proposer 暴露定性的 `focus/aspect/keywords`；
- prompt 明确禁止复制 comparator provenance、年份、篇数和任何外部数字。

该 e2e 红灯已消失。

### R2 已开始：model/experiment cell 已抽出

`AutoPipelineService` 新增：

```python
_run_model_experiment_cell(...)
```

当前拥有 DAG 段：

```text
model_plan
-> baseline
-> experiments
-> model_selection
-> sensitivity
```

原 `run()` 已改为调用这个 cell，行为保持一致。

这一步的意义：以后 Round 把 `model_plan` 标为 STALE 后，可以重入模型/实验段，而不需要重新做 problem ingestion 和 data registration。

注意：当前 cell 的第一版仍默认从 `model_plan` 起跑；R2 下一步要给它增加 later-pivot entry（baseline / experiments / model_selection / sensitivity），并继续抽 evidence/paper/submission cell。

## 当前测试基线

最近一次已通过：

```text
python -m pytest \
  tests/test_recurrent_workstation.py \
  tests/test_auto_pipeline_e2e.py \
  tests/test_refinement_hidden_state.py \
  tests/test_workflow_recovery.py \
  tests/test_full_smoke_dag_order.py \
  tests/test_excellent_paper_comparator.py -q

35 passed
```

模型 cell 抽取后又跑：

```text
python -m pytest \
  tests/test_auto_pipeline_e2e.py \
  tests/test_auto_pipeline_approval_callback.py \
  tests/test_recurrent_workstation.py -q

11 passed
```

后续改动必须至少保持这两组不回归。

## 当前 git 状态的重要提醒

开始本轮之前工作区已经存在未提交的 ExcellentPaperComparator / knowledge / 优秀论文对比相关改动。

不要：

- `git reset --hard`
- `git restore .`
- 删除 `config/ref_models/`
- 把原有 dirty 文件当成“本轮垃圾”清掉

本轮新增/主动修改的核心文件包括：

- `docs/recurrent-workstation-refactor-plan-2026-08-19.md`
- `docs/recurrent-workstation-handoff.md`
- `src/mathworkstation/recurrent_workstation.py`
- `tests/test_recurrent_workstation.py`
- `src/mathworkstation/auto_pipeline.py`
- `prompts/internal/paper_refinement.json`（原本已 dirty，本轮只补 comparator 数字隔离规则）

## 下一步：从这里直接继续，不要重新设计

### R2.1 later-pivot model cell

让 `_run_model_experiment_cell()` 支持：

```text
start_at=model_plan
start_at=baseline
start_at=experiments
start_at=model_selection
start_at=sensitivity
```

跳过前置节点时，从 `workstation.hidden_state.active_lineage` / ACTIVE Artifact 恢复：

- model plan
- comparison experiment id
- comparison artifact
- selected model

必须加真实“mark stale -> 重入 cell”的测试。

### R2.2 evidence cell

从 model comparison / selection / sensitivity 重新构造：

- paper-ready evidence
- ResultRecord
- TableRecord
- diagnostics
- claims
- figures

上游实验改变后，旧 paper evidence 必须 supersede / stale，不能混用旧数字。

### R2.3 paper cell

抽：

```text
paper_outline
-> section impact/rebuild
-> paper_draft
-> consistency_check
-> refinement_loop
-> CompletePaperContract
-> full review
```

Round 2+ 不应默认整篇重写。先做 Artifact lineage diff -> affected sections；只重建受影响 section，再用现有 refinement loop 做 bounded repair。

### R2.4 submission cell

抽：

```text
final_review
-> submission.prepare
-> export
```

### R3：真正闭合一个 Round

等以上 cell 可重入后，给 `RecurrentWorkstationService` 接 executor，完成：

```text
audit before
-> router
-> begin_round
-> mark_stale(pivot)
-> execute cells from pivot
-> audit after
-> decide
-> commit/reject
```

然后实现：

```python
run_round()
run_until_converged(max_rounds=M)
resume_round()
```

## 不要提前宣称已经完成的部分

目前还**没有**完成：

- 自动执行完整 Round 1..M
- later-pivot 重入
- model fan-out 主链化
- Round 间依据 diagnostics 自动改搜索空间
- incremental section rebuild
- Round reject 的实际 Artifact ACTIVE 指针恢复（当前 store 已记录 lineage 语义，但 ArtifactRegistry 还需要 lineage 激活层）
- Web/CLI Round UI
- 国赛级 benchmark / blinded human evaluation

所以当前准确状态是：

> 外层循环的 R1 控制平面已经真实可运行；bootstrap 已登记为 Round 0；R2 已完成第一段 model/experiment cell 抽取，但完整 M 轮执行器尚未闭环。

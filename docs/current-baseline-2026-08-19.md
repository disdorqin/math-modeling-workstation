# Current Baseline — 2026-08-19

本文件记录 Section 0 冻结时重新验证的当前现场。任何后续“提高了多少”的判断，都必须与这里的真实基线比较，不能与聊天记忆或 synthetic benchmark 比较。

## Git / Workspace

项目：`D:\computer learning\vibe_coding\math_model_ai_process`

当前分支：`m2-contest-grade-paper`  
远端状态：`origin/m2-contest-grade-paper [gone]`

CodeGraph：可用。

```text
Files: 238
Nodes: 4,011
Edges: 11,675
DB: 13.14 MB
Pending Changes: Added 3, Modified 7
```

因此图谱可用于结构定位，但不是完全同步状态；命中待修改文件时必须再读取 current on-disk source。

## Section 0 冻结时的 dirty state

Tracked modifications：

```text
M prompts/internal/paper_refinement.json
M src/mathworkstation/agents/modeling.py
M src/mathworkstation/auto_pipeline.py
M src/mathworkstation/paper_contracts.py
M src/mathworkstation/refinement.py
M tests/test_auto_pipeline_e2e.py
M tests/test_modeling_fanout.py
M tests/test_paper_contracts.py
```

重要 untracked/WIP：

```text
src/mathworkstation/excellent_paper_comparator.py
src/mathworkstation/model_decision.py
src/mathworkstation/recurrent_workstation.py
tests/test_excellent_paper_comparator.py
tests/test_recurrent_workstation.py
config/ref_models/
docs/recurrent-workstation-refactor-plan-2026-08-19.md
docs/recurrent-workstation-handoff.md
```

另有 comparator / knowledge-card / fleet / CLINE 等相关 docs/config 和 `.cline/`、`.pytest-recurrent.log`。

保护规则：不得 reset、restore 全仓、checkout 覆盖、clean untracked；不得擅自重写 refinement / excellent-paper-comparator / recurrent-workstation WIP。若 Section 1 需要改 `auto_pipeline.py` 或 `paper_contracts.py`，只做最小、可定位的兼容性编辑，并先读 current diff/相关测试。

## Python / dependency baseline

重新验证：

```text
Python 3.11.9
langgraph 1.1.2
langchain-core 1.2.19
tenacity 5.1.5
```

完整 `python -m pytest -q` 当前不能完成 collection。两个 collection error 均来自 Tenacity 5.1.5：

```text
AttributeError: module 'asyncio' has no attribute 'coroutine'
```

触发路径为 LangGraph -> langchain_core -> tenacity。失败文件：

```text
tests/test_agent_runtime_semantics.py
tests/test_runtime_conformance.py
```

这属于当前环境依赖兼容性阻塞，不得被误算成 Section 1 代码回归；但在最终工程健康度中仍必须解决。

## Targeted regression baseline

重新运行：

```text
python -m pytest \
  tests/test_recurrent_workstation.py \
  tests/test_auto_pipeline_e2e.py \
  tests/test_refinement_hidden_state.py \
  tests/test_workflow_recovery.py \
  tests/test_full_smoke_dag_order.py \
  tests/test_excellent_paper_comparator.py -q
```

结果：

```text
40 passed
```

`test_auto_pipeline_produces_traceable_refined_export` 当前已通过，说明旧记录中的 `accepted_stages == []` 红灯已被现有 WIP 修复；后续不能再把它列为“当前失败”。

## Real Competition Baseline — 2023 MCM Wordle

重新定位并读取：

`output/mcm-c-2023/v3/20260805-MCM-0001-EUP7/paper/final.md`

当前真实论文仍存在以下已验证问题：

1. 论文明确列出 SP1-SP6，但主模型仍集中在 `Number in hard mode` 的单个回归任务，并把 `gradient_boosting` + RMSE 作为全篇主结论。
2. 摘要及量化结果直接泄漏 `claim-*`、`result-*`、`table-*` 等内部 registry ID。
3. SP6 是 editor letter / synthesis deliverable，却在当前研究状态中与其它 SP 一样被标记 COMPLETED，没有独立依赖与 deliverable execution semantics。
4. 符号说明出现与 Wordle 无关的通用状态空间模板：`x_t/y_t/z_t`、`A_t/B_t`、状态转移方程、容量/价格系数等。
5. 单位出现 `h/kWh/kW/CNY`，与 Wordle 任务无关，证明 Paper Engine 存在 generic template pollution。
6. 当前模型验证仍出现“日序列存在显著时序结构，但主模型采用 random split”的内部不一致，说明 ValidationProtocol 未按 task type 驱动。
7. 论文整体仍更像围绕一个 sklearn 回归 baseline 展开的 generic ML report，而不是六个不同子问题各自有建模、求解、验证和证据的竞赛论文。

这份 Wordle v3 论文是 Section 1 的第一真实 Gate，不允许用更容易的 synthetic fixture 替代。

## 当前客观成熟度基线

沿用此前审计、但仅作为方向性工程判断：

```text
工程骨架成熟度：约 75–80 / 100
整体项目完成度：约 70 / 100
当前直接用于 CUMCM 国奖 / MCM-ICM O/F：约 36 / 100
```

后续不再用单一自建分数证明“达到国奖/O奖”。真正提升必须体现为历史真实赛题中的研究结构、模型合理性、验证协议、证据、叙事和盲评质量提升。

# Section 1 复盘：ProblemGraph / Subproblem Engine

日期：2026-08-19
状态：Gate PASS
真实验收题：2023 MCM Problem C — Wordle

## 原来具体有什么问题

旧 AutoPipeline 虽然能从题面识别出 SP1-SP6，但研究链进入建模后收缩成一个 ModelPlan / model comparison / best model。`_register_content_evidence()` 再把同一个 `best_model + primary_metric` 复制给所有 SubproblemAnswerRecord。

真实 Wordle 论文因此出现：SP1-SP6 都被 gradient_boosting + RMSE 主线概括；Hard Mode 属性效应、未来 1/2/3/4/5/6/X 分布、难度分类、探索发现和 editor letter 没有各自研究语义。旧 contract 还在 problem analysis 阶段提前把所有 subproblem 标成 COMPLETED，形成 false completion。

## 外部成熟项目怎么做

本节继续采用此前确认的成熟机制，而不是整仓复制：

- LLM-MM-Agent：问题分析后先形成可独立求解的问题/方法结构，再进入 mathematical modeling 与 computational solving；核心启发是“问题节点先分流，再求解”，而非全题一个模型。
- data-to-paper：每个结论必须沿 evidence/code/result lineage 回溯；核心启发是“没有对应计算证据就不允许生成结论”。
- AI-Scientist：experiment/review/reflection 是独立研究状态，不把写作层修饰当成实验完成。
- mathmodel-skill：per-question state + stage gate；核心启发是每问拥有自己的状态，而不是只存一个全题 status。

## 我们具体改了什么

新增：

- `src/mathworkstation/problem_graph.py`
  - ProblemGraph
  - SubproblemNode
  - DependencyEdge
  - SubproblemState
  - SubproblemPlan
  - SubproblemExperiment
  - SubproblemAnswer
  - structure_gate / research_gate
- `src/mathworkstation/subproblem_executors.py`
  - explanatory_inference
  - distribution_forecasting
  - exploratory_analysis
  - future scalar forecast + prediction interval
  - future classification
- `src/mathworkstation/subproblem_engine.py`
  - family-specific dispatch
  - dependency gate
  - no generic-regression fallback
  - node execution evidence registration
  - synthesis completion
- `src/mathworkstation/subproblem_paper_bridge.py`
  - node execution → ResultRecord
  - node execution → SubproblemAnswerRecord
  - node execution → Table/Figure/Claim
  - per-subproblem evidence index
  - all nodes complete 后 activate node-specific Result/Table lineage
- `src/mathworkstation/word_features.py`
  - 仅使用题目允许的 Wordle corpus 构造 word attributes
  - EERIE 与训练数据共用同一 feature schema
- `src/mathworkstation/wordle_2023_gate.py`
  - 真实历史赛题 adapter，仅用于 Gate，不作为通用路由器

AutoPipeline 最小侵入接入：

- problem analysis 后持久化 ProblemGraph + assessment；
- 提供 `execute_subproblem_node()`；
- 提供 `complete_subproblem_synthesis()`；
- 旧“所有 subproblem 共享 best model/metric”的 answer 逻辑已切断。

ResultRecord 增加与真实研究语义匹配的类型：

- EXPLANATORY
- DISTRIBUTION_FORECAST
- EXPLORATORY
- CLASSIFICATION

## 真实赛题是否明显变好

是，且验收不是 synthetic fixture。

直接使用仓库真实：

`output/mcm-c-2023/v3/20260805-MCM-0001-EUP7`

真实数据：

`input/data/uploaded/_wordle_data_clean.csv`

真实 SP contracts：

`results/contracts/subproblems.jsonl`

新研究图：

```text
SP1 forecasting
  -> 2023-03-01 reported-results point forecast + prediction interval

SP2 explanatory_inference
  -> word attributes -> Hard Mode percentage association + bootstrap effect intervals

SP3 distribution_forecasting
  -> EERIE 2023-03-01 1/2/3/4/5/6/X distribution + simplex constraint + uncertainty

SP4 classification
  -> explicit difficulty construct + classifier + EERIE future class

SP5 exploratory_analysis
  -> independent association/outlier/change-pattern discovery

SP6 synthesis / DELIVERABLE
  -> depends on SP1-SP5
  -> no model execution
```

同一真实数据又通过通用生产 engine + paper evidence bridge 重跑，确认：

- SP1-SP5 各有独立 execution artifact；
- ResultType 至少覆盖 FORECAST / EXPLANATORY / DISTRIBUTION_FORECAST / CLASSIFICATION / EXPLORATORY；
- conclusion evidence pack 有 SP1-SP6 六个独立 answer；
- SP6 synthesis artifact 的 upstream 指向前序研究 evidence；
- active evidence lineage 切换到 node-specific results/tables；
- ArtifactRegistry verify PASS。

最新宽相关回归：57 passed。

完整 pytest 仍只有既有环境阻塞：Tenacity 5.1.5 在 Python 3.11 使用已移除的 `asyncio.coroutine`，collection 2 errors。

## Section 1 Gate 结论

PASS。

这不表示最终 Wordle 论文已经达到 O/F。Section 1 只证明“研究状态不再被单模型压扁”。旧 `final.md` 的 internal ID 泄漏、generic notation pollution、摘要模板化、references 等问题留到 Paper Engine / Excellent Paper Corpus 对应 Section 继续处理。

下一节：Section 2 Modeling Brain。

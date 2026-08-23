# WORKING_MEMORY

用途：保存跨会话仍稳定成立的项目事实、架构判断和硬约束。短期测试结果不要写在这里，写 `CURRENT_STATE.md`。

## 项目目标

数学建模 AI 工作站的目标不是“自动生成一篇格式完整的论文”，而是建立可追踪、可恢复、可迭代的完整 Research State，在真实 CUMCM / MCM-ICM 历史题上逐步逼近国奖 / O-F 级研究质量。

## 已有优势

项目已有较成熟工程底座：workflow/DAG、Artifact/Dataset/Experiment/Claim/Figure registry、provenance、checkpoint/recovery、approval、frozen accepted versions、submission/preflight、learning/reflection、AI ledger。

因此优先补研究能力，不优先继续堆基础设施。

## 当前最高优先级缺陷

主链虽能产生多个 `SubproblemContract`，但后续仍集中为一个 `ModelPlan` / model comparison / best model，并把同一 best model + primary metric 复制给多个 `SubproblemAnswerRecord`。

真实 2023 MCM Wordle 已证明该缺陷会把六个性质不同的问题压成同一 generic ML report。

## 正确主线

```text
ProblemGraph
-> Model/Solver
-> Experiment
-> Evidence
-> Figure/Table
-> Narrative
-> Paper
-> Reviewer
-> Repair Router
-> next Round
```

Research defect 回上游；Document defect 才允许只修论文。

## M-Round 定义

保留用户最初的 M-Round 思想，但每轮优化整个 Research State，不只是 paper text。

默认语义：Coverage -> Correctness -> Modeling Depth -> Robustness -> Storyline -> Competition Polish。

现有 recurrent workstation / refinement 实现属于可复用资产，不推倒重来。

## Section 顺序

0. Freeze / baseline / benchmark / memory
1. ProblemGraph / Subproblem Engine
2. Modeling Brain
3. Solver Engine
4. ValidationProtocol Registry
5. M-Round Research Refinement
6. Paper Engine
7. Excellent Paper Corpus + External Benchmark
8. Competition Delivery

Gate 不通过，不以“单测绿了”代替真实赛题验收。

## 第一固定真实 Gate

2023 MCM Wordle。不要换成 synthetic fixture。

SP1-SP5 必须形成不同 task/method/experiment/evidence/answer；SP6 必须是依赖 SP1-SP5 的 synthesis/deliverable node，不训练模型。

## WIP 保护

当前分支长期存在未提交 WIP。尤其保护：

- `prompts/internal/paper_refinement.json`
- `src/mathworkstation/refinement.py`
- `src/mathworkstation/excellent_paper_comparator.py`
- `src/mathworkstation/recurrent_workstation.py`
- `src/mathworkstation/auto_pipeline.py`
- `src/mathworkstation/paper_contracts.py`
- 相关 tests/config/docs

不要 `git reset --hard`、`git restore .`、`git clean`、checkout 覆盖或删除 untracked。

## CodeGraph 规则

打开项目先读 `AGENTS.md`。优先 `codegraph status/explore/query/callers/callees/impact`。当前图谱可用，但若 status 显示 pending changes，修改命中文件前还要核验 current on-disk source。

## Benchmark 规则

- `docs/M2_FINAL_REPORT.md` 的 synthetic/FakeProvider/deterministic 100/100 只算 regression benchmark。
- 未真正全文读取优秀论文前，不能声称 comparator 已验证接近优秀论文。
- 真实能力至少需要 historical problems + external/excellent-paper corpus + blind/human review。

## 参考项目

重点参考：LLM-MM-Agent、data-to-paper、STORM、AI-Scientist、mathmodel-skill。只吸收经过本项目真实赛题验证有效的机制，不整仓复制。

## 文档职责

- `WORKING_MEMORY.md`：长期稳定事实。
- `CURRENT_STATE.md`：现在做到哪、当前测试/Gate/失败。
- `DECISION_LOG.md`：重要架构/优先级改变。
- `KNOWN_ISSUES.md`：已知问题与阻塞。
- `.internal/resume_brief.md`：下一会话极简恢复入口。

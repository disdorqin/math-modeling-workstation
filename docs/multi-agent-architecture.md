# 多智能体架构：Agent 提案，工作流裁决

**当前状态（精确标签，2026-07-26 第三次迭代后）：**

- **builtin implementation executed** — 契约层、裁决器、内建顺序执行器、
  四个确定性审计智能体、有界建模 fan-out 均已落地并在真实 Case 上用
  内建执行器跑通。
- **bounded fan-out executed** — 三候选（linear/tree/robust_baseline）→
  评估 → 裁判 → 裁决器的有界 fan-out 在真实糖尿病 Case 与合成 Case 上
  均真实执行；计算级复用（第二次相同调用零次拟合）已由真实 pytest 验证。
- **evidence promotion executed** — `ModelingEvidenceGate` + `recheck-
  claim-evidence` 已在真实糖尿病 Case `20260726-CUMCM-0001-DEGF` 上把
  `DRAFT` 模型选择 claim（`claim-c75433559a9c`）晋升为 `VERIFIED`
  （见 13.3 节）。
- **full deterministic paper smoke executed (locally)** — 从赛题输入到
  投稿包的完整 DAG 主链路（含数据质量门、EDA、模型比较、敏感性、
  分章节论文、图形入文、一致性门、投稿预检、审计导出、两次
  `validate-case` 无哈希漂移）由单一脚本
  `scripts/run_full_deterministic_smoke.py` 驱动，本地实跑通过；
  但**尚未由 GitHub Actions 执行**。
- **LangGraph implementation not executed** — LangGraph 执行器代码已实现，
  但真实 LangGraph 引擎从未在任何可及环境中执行（本沙箱 PyPI 被封锁，
  见 12.1 节）；`compare-agent-runtimes` 的"两运行时一致"路径因此从未
  真正跑过。
- **GitHub Actions not observed** — `.github/workflows/agent-layer-tests.yml`
  已完成并本地校验/彩排，但从未被 GitHub Actions 实际运行过一次。
- **concurrent fan-out design-only** — 并发建模、多裁判仲裁、多轮辩论
  仍仅为设计，未实现（见第 6.3 节目标拓扑与第 8 节迁移表 M4）。

日期：2026-07-26（首次实跑，第 11 节）／第二次迭代（第 12 节）／
第三次迭代（第 13 节，验证、复用、证据晋升、双 smoke 与 CI）

---

## 1. 为什么不是"让智能体自己跑完"

把整条链路交给自主智能体，最容易丢掉的恰恰是本仓库唯一值钱的东西：**结论可追溯**。
一个能自由写文件的写作智能体，可以在论文里写下任何数字；此时"无证据不进论文"退化成
一句提示词里的祈使句，而提示词不是保证。

因此本架构的唯一硬约束是：

> **智能体只能提出「提案」，任何对 Case 的写入都必须经过裁决器，并复用既有的
> Claim 注册表、Figure 注册表与 DAG 状态机。**

这条约束带来三个直接后果：

1. 编造的数字**在机制上**进不了论文——Claim 注册表仍然要求背后有 `paper_eligible` 产物，
   与提案者是人还是模型无关；
2. 智能体链路与手工 CLI 链路产生**同一套审计记录**，两者可互相复现与比对；
3. 换掉编排框架（LangGraph → 别的）不影响证据保证，因为保证不在编排层。

## 2. 分层

```
┌──────────────────────────────────────────────────────────────┐
│ 编排层  agents/graph.py                                       │
│   LangGraph StateGraph（已安装时） / 内建顺序执行器（回退）      │
│   一个智能体 = 一个节点；节点只返回状态增量                      │
└───────────────┬──────────────────────────────────────────────┘
                │ AgentRequest（只读证据视图）
                ▼
┌──────────────────────────────────────────────────────────────┐
│ 智能体层  agents/roster.py                                    │
│   DeterministicAgent：包裹既有引擎，无需 API Key，可复现        │
│   LLMAgent：受控路由，把证据变成语言，不得引入新数字            │
│   输出：AgentReport { proposals: Proposal[] }                 │
└───────────────┬──────────────────────────────────────────────┘
                │ Proposal
                ▼
┌──────────────────────────────────────────────────────────────┐
│ 裁决层  agents/adjudicator.py   ← 唯一有写权限的组件            │
│   ① 通用可采性检查（证据存在性 / paper_eligible / 数字断言）     │
│   ② 分类型 handler → 调用既有服务                              │
│   输出：Verdict + 追加写入 agents/decisions.jsonl              │
└───────────────┬──────────────────────────────────────────────┘
                ▼
      既有内核：ClaimRegistry · FigureRegistry · WorkflowController
                ArtifactRegistry · PaperConsistencyChecker
```

智能体层**没有**文件系统写权限，也不持有任何 registry 的写方法。这不是靠约定，
而是靠依赖注入：`AgentRequest` 里没有 writer，智能体构造函数里注入的引擎要么只读，
要么其写入本身就走既有的产物注册流程。

## 3. 契约

全部定义在 `agents/contracts.py`。智能体 API 表面就这几个模型——
无法表达为 `Proposal` 的东西，就无法影响 Case，这是刻意的。

### 3.1 Proposal

| 字段 | 作用 |
|---|---|
| `kind` | 提案类型，决定走哪个 handler |
| `agent` | 提出者，写入审计日志与 `created_by` |
| `payload` | 类型专属载荷，故意保持松散：新增 kind 不应改动本模型 |
| `evidence` | 指向**已登记**产物的引用列表 |
| `asserts_numbers` | 是否含数值断言，由基类自动检测，不由智能体自报 |
| `confidence` / `rationale` | 供人工复核与后续 judge 节点使用 |

`asserts_numbers` 由 `Agent.propose()` 用正则扫描 summary 与 payload 文本自动置位。
让智能体自己声明"我没有编数字"是无效设计。

### 3.2 ProposalKind

| Kind | 含义 | 当前 handler |
|---|---|---|
| `DECOMPOSITION` | 赛题拆解为子问题 | advisory |
| `DATA_ACTION` | 画像 / 清洗 / 重登记 | advisory |
| `ANALYSIS_ACTION` | EDA、诊断 | advisory |
| `MODEL_PLAN` | 候选模型与验证协议 | 待接 `ModelPlanService` |
| `EXPERIMENT_REQUEST` | 执行已登记协议 | 待接 `ModelEvaluationEngine` |
| `FIGURE_REQUEST` | 出图 / 图形晋升 | `FigureRegistry.promote` |
| `CLAIM` | 断言一条有证据支撑的结论 | `ClaimRegistry.create` |
| `SECTION_DRAFT` | 单节论文正文 | 待接 `PaperSectionWorkspace` |
| `REVIEW_FINDING` | 评审发现的缺陷 | 记录；BLOCK 级升级人工 |
| `REPAIR_REQUEST` | 写作前需要的上游返工 | advisory |

未实现 handler 的 kind 返回 `NEEDS_HUMAN`，而不是静默通过。

### 3.3 Verdict 与 RejectionCode

拒绝理由是枚举而非自由文本，因为它们要被断言、被统计、被当作回归基线：

`NO_EVIDENCE` · `EVIDENCE_NOT_PAPER_READY` · `EVIDENCE_UNKNOWN` · `OUT_OF_SCOPE` ·
`DEPENDENCY_UNMET` · `BUDGET_EXHAUSTED` · `SCHEMA_INVALID` · `APPROVAL_REQUIRED` · `DUPLICATE`

三种终局：`ACCEPTED` / `REJECTED` / `NEEDS_HUMAN`。第三种不是失败，是**升级**——
质量保证智能体发现 BLOCK 级问题时，正确行为是停下来找人，不是自行放宽门限。

## 4. 裁决规则

```
proposal
   │
   ├─ 通用可采性 ───────────────────────────────────────────┐
   │    · 每个 evidence artifact 必须存在        → EVIDENCE_UNKNOWN
   │    · asserts_numbers 且无 evidence         → NO_EVIDENCE
   │    · asserts_numbers 且证据未晋升           → EVIDENCE_NOT_PAPER_READY
   │                                                        │
   │  任一命中 → REJECTED（handler 根本不执行）              │
   └────────────────────────────────────────────────────────┘
   │
   ▼ 通过
分类型 handler → 调用既有服务 → ACCEPTED / REJECTED / NEEDS_HUMAN
   │
   ▼
追加写入 agents/decisions.jsonl（无论接受与否）
```

注意第二层的兜底：即使 handler 有 bug，`ClaimRegistry.create()` 自己仍会根据证据
是否 `paper_eligible` 把 Claim 标成 `DRAFT`；裁决器把 `DRAFT` 一律升级为
`NEEDS_HUMAN`。也就是说证据门有两道独立实现，任何一道单独失效都不会导致
无证据结论进入论文。

## 5. 智能体名册

### 5.1 已实现（确定性，无需 API Key）

| 智能体 | 职责 | 包裹的引擎 | 可提出的 Kind |
|---|---|---|---|
| `data_steward` | 数据画像、暴露质量门结论 | `DataService` | `DATA_ACTION`, `REPAIR_REQUEST` |
| `eda_analyst` | 探索性分析、提取共线性与目标关联结构 | `EDAEngine` | `ANALYSIS_ACTION`, `FIGURE_REQUEST` |
| `evidence_verifier` | 把已晋升的类型化记录转成 Claim | `ClaimRegistry` | `CLAIM`, `REPAIR_REQUEST` |
| `quality_assurance` | 执行一致性门、逐条上报 finding | `PaperConsistencyChecker` | `REVIEW_FINDING` |

两点设计取舍值得说明：

- **`data_steward` 不提 Claim**。数据事实要成为论文结论，前提是画像产物被人工晋升；
  数据管家的职责是让门限结论可见，不是绕过它。
- **`eda_analyst` 输出的是「结构」而非「图」**。它把共线特征对与目标关联度作为
  advisory 提案传下去，使建模智能体继承的是一个**理由**，而不只是一份数据集。
  这是 EDA 在竞赛论文里真正的作用。

`data_steward` 还实现了**重入**：当 `data_quality` 节点已经 SUCCEEDED 时，它从已登记
产物读取门限结论，而不是强行触发一次非法的 DAG 转移。智能体链路必须能在半成品
Case 上重跑。

### 5.2 设计中（LLM 驱动）

| 智能体 | 职责 | 输出 Kind | 硬约束 |
|---|---|---|---|
| `problem_analyst` | 赛题理解与子问题拆解 | `DECOMPOSITION` | 子问题必须可映射到某个任务族插件 |
| `model_architect` | 候选模型族、验证协议、选择准则 | `MODEL_PLAN` | 必须通过 `ModelPlan` schema 校验才提交 |
| `code_executor` | 生成并执行实验代码 | `EXPERIMENT_REQUEST` | 只能执行已登记协议；代码快照入产物 |
| `robustness_analyst` | 敏感性 / 稳健性 / 不确定性设计 | `EXPERIMENT_REQUEST` | 参数网格须显式登记 |
| `paper_architect` | 论文结构与证据分配 | `SECTION_DRAFT`（提纲） | 每节的 claim/figure 绑定须已 VERIFIED |
| `section_writer` | 分章节写作 | `SECTION_DRAFT` | 只能引用本节 `allowed_claims`；越界即 `OUT_OF_SCOPE` |
| `visualization_agent` | 图表、流程图、技术示意图 | `FIGURE_REQUEST` | 数据图必须由确定性脚本生成，模型只出版式建议 |

`section_writer` 的越界检测已有现成落点：章节 `context.json` 里的 `allowed_claims`
就是白名单，`PaperConsistencyChecker` 已经在检查 `CLAIM_OUT_OF_SCOPE`。

### 5.3 关于可视化的一条纪律

**数据图永远由本地确定性 Python 生成，模型不得产出数据图。**
模型可以提议图的类型、布局、配色与图题，但像素必须来自可复现脚本。
现有 `--image-routes` 分支的定位是对的：它生成的是供人重绘的**参考图**，
不是论文用图。可视化智能体沿用这一边界。

## 6. 编排

### 6.1 为什么是 LangGraph

三个候选的取舍：

| 方案 | 优点 | 代价 |
|---|---|---|
| 纯 Python | 零新依赖，契合 README「单一实现」的稳定性主张 | 并行、检查点、人工中断都要自己写 |
| **LangGraph** | 图状态机、检查点、`interrupt` 原生支持人工介入；已在 `pyproject` 可选依赖中 | 依赖较重 |
| pydantic-ai | 类型化输出与既有 pydantic 契约契合，更轻 | 编排能力弱，并行/中断需另配 |

选 LangGraph 的决定性理由是**人工中断**：本工作站的核心不是自动化程度，而是
"该停下来的时候真的停下来"。`NEEDS_HUMAN` 需要一等公民的挂起-恢复语义，
LangGraph 的 checkpointer + interrupt 直接提供，自研要重复实现一遍已有的
`CheckpointManager` 语义并保证两者一致。

### 6.2 但不能硬依赖

`agents/graph.py` 提供两个等价执行器：

```python
run(agents, adjudicator, state, prefer_langgraph=True)
#  → LangGraph 已安装：编译 StateGraph 执行
#  → 未安装：内建 run_sequence，节点函数、状态语义、决策日志完全一致
```

理由：安装一个智能体框架不应成为**运行、测试、复现**一个 Case 的前置条件。
回退执行器让本层在离线环境下仍可完整回归——本次实现正是在无法访问 PyPI 的
环境中通过 33 个用例验证的。

CLI 用 `--runtime {auto,langgraph,builtin}` 显式控制；`langgraph` 且未安装时报错而非
静默回退，避免"以为跑的是 LangGraph"。

### 6.3 当前拓扑与目标拓扑

必须区分三层拓扑，不要混为一谈：

**(1) 原有确定性审计-智能体流水线**（线性，已实现并实跑）：

```
START → data_steward → eda_analyst → evidence_verifier → quality_assurance → END
```

**(2) 已实现的建模-智能体子图**（有界 fan-out，已实现并实跑，见第 12/13 节）：

```
modeling_protocol（不可变协议）
    ├── linear_model_agent          ┐
    ├── tree_model_agent            ├─ 三候选，各自独立拟合，不自评获胜
    └── robust_baseline_agent       ┘
             ↓
    model_evaluation_agent          （协议感知的独立复核，无候选被静默丢弃）
             ↓
       model_judge_agent            （只读比较产物，提出 WINNER/TIE/NO_WINNER）
             ↓
          Adjudicator               （唯一写入者；DRAFT vs VERIFIED 由证据资格决定）
             ↓
    ModelingEvidenceGate            （复用 promote_to_paper 晋升协议/候选/比较）
             ↓
 ClaimRegistry.recheck_evidence     （DRAFT → VERIFIED，幂等）
```

这一子图是当前迭代的实现重点：三候选并非并发执行（仍为顺序），但它们
**逻辑上**是独立方案，由独立评估与独立裁判汇聚，这正是"三方案再评分"
胜过"一个方案反复精修"的价值所在。

**(3) 目标（引入 LLM 智能体后的）拓扑**（design-only，尚未实现）：

```
                          ┌→ model_architect#1 ┐
problem_analyst → data_steward → eda_analyst →┤→ model_architect#2 ├→ judge → code_executor
                          └→ model_architect#3 ┘                         │
                                                                          ▼
  quality_assurance ← section_writer ×12 ← paper_architect ← evidence_verifier ← robustness_analyst
          │
          └─ BLOCK finding → interrupt → 人工裁决 → 回到对应上游节点
```

建模阶段的 fan-out + judge 是最有价值的扩展点：竞赛建模的解空间很宽，
"三个独立方案再评分"比"一个方案反复精修"更接近人类队伍的实际做法。
`Proposal.confidence` 与 `rationale` 就是为 judge 节点准备的。

## 7. 与既有 DAG 的关系

智能体层**不替代** DAG，它驱动 DAG：

- 节点状态、审批、失败分类、断点恢复仍由 `WorkflowController` 负责；
- 智能体调用的引擎（`DataService` 等）内部本就会做 DAG 转移；
- `NEEDS_HUMAN` 对应既有的 `NEEDS_REVIEW` / `approve-node`；
- 本次新增的 `degrade-node` 让"有意省略某个可选分支"成为可记录的决策，
  智能体链路同样受益。

一句话：DAG 是宪法，智能体是提案人，裁决器是法院。

## 8. 迁移路径

下表反映**当前实现状态**（不是原始路线图愿景）：

| 阶段 | 内容 | 状态 | 依据 / 缺口 |
|---|---|---|---|
| **M0** | 契约、裁决器、编排、四个确定性智能体 | **completed** | 真实 Case 上 6 提案全部 ACCEPTED，2 条 Claim VERIFIED（第 11 节） |
| **M1** | 协议 → 候选执行 → 评估 → 选择 → 证据晋升 | **substantially completed** | 协议/候选/评估/选择/证据晋升均已实现并实跑（第 12/13 节）；**敏感性-智能体接入 fan-out 仍未完成**——敏感性目前只在确定性 CLI 主链路（`run-sensitivity`）中，未包装为建模子图内的智能体 |
| **M2** | 引入 `problem_analyst` / `section_writer` 两个 LLM 智能体 | **not implemented** | 判据（见下）未触及；本轮明确不做 |
| **M3** | 切到 LangGraph，接入 checkpointer 与 interrupt | **code implemented, not executed** | LangGraph 执行器与运行时对比命令代码已实现；真实 LangGraph 引擎、checkpointer/interrupt 恢复从未在可及环境执行（PyPI 封锁，第 12.1 节） |
| **M4** | 建模阶段 fan-out + judge | **bounded version implemented; concurrency design-only** | 有界确定性三候选 + 单裁判已实现并实跑、被淘汰方案保留可审计（第 12.4/13 节）；**并发执行、多裁判仲裁、多轮辩论仍为 design-only** |
| **M5** | 跨题型 benchmark | **not implemented** | 与既有 Phase F 基准矩阵合并，尚未开始 |

M2 的判据仍是整条路径上最重要的一条，留待未来：**在 LLM 智能体接入的
同一个提交里，必须同时提交一个"智能体编造数字"的负样本 fixture，并证明
它被拒绝。** 在真实 GitHub Actions 验证 LangGraph、全部测试、运行时一致性、
两个 smoke 之前，不启动 M2。

## 9. 风险

| 风险 | 后果 | 缓解 |
|---|---|---|
| 智能体绕过裁决器直接写盘 | 证据保证失效 | 智能体层不注入 writer；建议加一条 CI 检查：`agents/` 下除 `adjudicator.py` 外禁止 import `atomic_write_*` |
| 数值检测正则漏判 | 编造数字被当作定性描述放行 | 已剥离数学环境（见 `MATH_SPAN`）；漏判仍会被 `ClaimRegistry` 的第二道门拦住 |
| `NEEDS_HUMAN` 过多导致流程停摆 | 自动化收益归零 | 按 kind 统计升级率，作为 benchmark 指标；升级率高说明上游证据不足，不是门限过严 |
| LangGraph 版本漂移 | 编排层不可用 | 回退执行器始终可用；CI 两种 runtime 各跑一遍 |
| 并行智能体争抢同一 Case 目录 | 产物注册表竞态 | fan-out 阶段只允许只读智能体并行；写入串行经裁决器 |
| Token 预算失控 | 成本不可预期 | 复用既有 `BudgetPolicy`；`AgentRequest.remaining_tokens` 已预留字段，M2 接入 |

## 10. 用法

```powershell
$env:PYTHONPATH="src"

# 内建执行器（无需任何额外依赖）
mathworkstation --output-root <ROOT> run-agent-pipeline `
  --case-id <CASE_ID> --session-id <SESSION_ID> `
  --dataset-id <DATASET_ID> --target-column <TARGET> --runtime builtin

# LangGraph 执行器
python -m pip install -e ".[langgraph]"
mathworkstation --output-root <ROOT> run-agent-pipeline `
  --case-id <CASE_ID> --dataset-id <DATASET_ID> --runtime langgraph
```

产物：

- `agents/decisions.jsonl` — 每条提案与裁决的追加日志
- `agents/run_summary.json` — 本次运行摘要，已注册为 `agent_run_summary` 产物

## 11. 实跑验证（2026-07-26）

在第 3 节实跑所建的真实 Case 上执行 `run-agent-pipeline --runtime builtin`：

```
runtime: builtin | halted: False
verdicts: {'ACCEPTED': 6}
  data_steward       DATA_ACTION      数据画像完成，质量门为 PASS（442 行 / 11 列 / 0 缺失）
  eda_analyst        ANALYSIS_ACTION  提取相关结构：s1-s2 r=0.8967、s3-s4 r=-0.7385
  eda_analyst        ANALYSIS_ACTION  检出结构性多重共线性，建议正则化线性模型族
  evidence_verifier  CLAIM            lasso 在 5 折交叉验证下 rmse 最优 → VERIFIED
  evidence_verifier  CLAIM            样本比例与随机种子敏感性结果 → VERIFIED
  quality_assurance  REVIEW_FINDING   一致性检查通过
```

两条 Claim 均登记为 `VERIFIED`，因为其证据产物此前已通过 `approve-paper-ready` 晋升；
若未晋升，同样的提案会被拒为 `EVIDENCE_NOT_PAPER_READY`——这正是
`tests/test_agent_layer.py` 中断言的行为。

测试：`tests/test_agent_layer.py` 15 个用例 + `tests/test_deterministic_paper_path.py`
18 个用例，共 33 个全部通过；`run-task-paper` 发布 smoke 仍 `gate=PASS`。

**未验证项**：LangGraph 执行路径。本次环境无法安装 `langgraph`，
`build_langgraph()` 的代码结构正确但未实际运行过，需在可联网机器上补验。

---

## 12. 第二次迭代（2026-07-26）：回放语义、写入校验、建模 fan-out

第 11 节的六提案/两 Claim/33 测试结果是**第一次**实跑的记录。本节记录的是**新**执行
证据，不是对第 11 节的复述。状态标签统一使用以下六种（与英文最终报告一致，故保留
英文原文，不作翻译以免歧义）：*implemented and locally executed*、
*implemented and covered by automated tests*、
*implemented but not executable in the current environment*、
*configured for CI but CI result not observed*、*design only*、*not implemented*。

### 12.1 LangGraph

*implemented but not executable in the current environment.* `pyproject.toml`
的 `[project.optional-dependencies].langgraph` 早已声明；本次重新执行
`pip install langgraph --break-system-packages --dry-run` 与直接
`curl` 探测 `pypi.org` / `files.pythonhosted.org`，两者均返回 `403`
（沙箱网络策略，非代码问题）。CLI 侧 `run-agent-pipeline --runtime langgraph` 与新增的
`compare-agent-runtimes` 在检测到 langgraph 缺失时均给出**可识别的独立错误**并以
非零退出码退出（前者复用既有 `RuntimeError`，后者退出码固定为 `3`，
与"比较结果不一致"的退出码 `1` 明确区分）——这一错误路径本身是
*implemented and locally executed*，因为 langgraph 在本沙箱确实不可用。

### 12.2 回放 / 幂等语义

*implemented and covered by automated tests.* `Proposal.proposal_id` 由内容哈希
（`kind`/`agent`/`summary`/`payload`/`evidence`，显式排除 `created_at`）生成；
`Adjudicator.decide()` 在处理前先查 `agents/decisions.jsonl` 中是否已有该
`proposal_id` 的原始 `decision` 记录，命中则直接返回缓存的 `Verdict`（标记
`replayed=True`）并写入一条 `record_type="replay"` 审计记录，不重跑任何注册表写入。
`tests/test_agent_layer.py::test_identical_proposal_replays_instead_of_rerunning`
与 `test_identical_model_selection_replays` 断言：重复提交同一提案后，Claim
仅被创建一次。**真实 Case 复验**：对糖尿病 Case 完整重跑一次建模 fan-out
（协议 → 三候选 → 评估 → 裁判），`agents/decisions.jsonl` 中新增的全部记录
`record_type` 均为 `"replay"`，注册表中无新增产物——见第 12.5 节。

### 12.3 写入校验（Write-verification）

*implemented and covered by automated tests.* `_handle_claim` / `_handle_figure` /
`_handle_model_selection` 在调用 `claims.create()` / `figures.promote()` 后，
立即通过 `_verified_claim` / `_verified_figure` 读回同一条记录；读不回或状态不符时，
裁决降级为 `REJECTED` + `WRITE_VERIFICATION_FAILED`，而不是放行一个没有对应
注册表条目的 `ACCEPTED`。`tests/test_agent_layer.py::TestWriteVerification`
用一个"写入后读不到"的假 Claim 注册表验证了该路径。**未做**：真实文件系统层面
的崩溃注入（例如 `fsync` 后杀进程）——现有测试覆盖的是接口契约
（写入返回值与读回值不一致时的行为），不是操作系统级崩溃安全性；后者仍是
*not implemented*。

### 12.4 建模 fan-out：`agents/modeling.py`

*implemented and locally executed.* 新增：

- `build_modeling_protocol()` — 生成不可变协议产物（`modeling_protocol` 类型），
  内容包含数据集哈希、特征列、折叠的**具体行位置索引**（而非仅随机种子）、主指标与
  方向；协议产物路径固定，重复调用在输入不变时复用同一 `artifact_id`
  （`ArtifactRegistry.register_existing` 的按内容去重）。
- 三个候选智能体 `linear_model_agent` / `tree_model_agent` /
  `robust_baseline_agent`：均严格复用协议给定的折，各自拟合、各自写一份
  `model_candidate` 产物（18 个字段，覆盖要求的约 14 个），**互不比较、不自称获胜**；
  拟合失败时仍写产物，标记 `status=INVALID` 并给出 `invalid_reason`，不会消失。
- `model_evaluation_agent`：独立复核每个候选（协议匹配、数据集哈希匹配、必需字段、
  折数匹配），生成 `model_comparison` 产物；任何候选校验失败都保留在列表中并标注
  `INVALID` + 原因，不静默丢弃。
- `model_judge_agent`：只读 `model_comparison` 产物，不读任何智能体的自然语言描述；
  支持 `WINNER` / `TIE` / `NO_ACCEPTABLE_WINNER` 三种结果，容差内的数值并列走
  "更简单模型优先"规则（复杂度顺序：`robust_baseline` < `linear` < `tree`）；
  仅**提议** `MODEL_SELECTION`，不写任何注册表。
- `Adjudicator._handle_model_selection`：对 `MODEL_SELECTION` 提案独立复核协议哈希
  新鲜度、候选存在性与有效性、指标方向、必需字段、Claim 文本是否引用了实际指标值、
  优势断言是否被证据反驳（容差 1%，避免把"并列取简单模型"误判为不支持的优势断言）、
  是否与已接受的获胜者冲突；对应 9 个精确 `RejectionCode`
  （`STALE_EVIDENCE` / `PROTOCOL_MISMATCH` / `CANDIDATE_UNKNOWN` /
  `CANDIDATE_INVALID` / `MISSING_EVALUATION_FIELDS` / `METRIC_DIRECTION_MISSING` /
  `SELECTION_UNGROUNDED` / `UNSUPPORTED_SUPERIORITY_CLAIM` /
  `CONFLICTING_SELECTION`）。**最终获胜声明只能由 Adjudicator 写入**——判定智能体
  的提案在写入前必须先通过上述全部检查。

`tests/test_agent_layer.py::TestModelSelectionGate` 用合成协议/比较产物覆盖以上
9 类拒绝原因，并逐一断言拒绝后 `adjudicator.claims.created` 未增长（无非法写入）。

### 12.5 糖尿病 Case 真实执行（未预设获胜者）

*implemented and locally executed.* 对已存在的真实 Case
`20260726-CUMCM-0001-DEGF`（`dataset-9ecd95082b21`，442 行，10 特征，
目标列 `progression`）执行 `scripts/run_modeling_fanout_on_case.py`：

```
linear          rmse=54.849 (folds: 53.85/51.60/57.55/52.90/58.34)
tree            rmse=63.185
robust_baseline rmse=55.029
```

`linear` 与 `robust_baseline` 的相对差 0.33%，在 1% 容差内视为并列；按"更简单模型优先"
规则，`robust_baseline` 当选。该结果**不是预先设定的**——三个候选独立拟合，
裁判只在看到真实折内 RMSE 后才应用规则；`tree` 明显更差（未入围）也如实保留在
`model_comparison` 产物里，标注 `status=VALID` 但未获胜，而不是被删除。
最终 `Adjudicator` verdict 为 `NEEDS_HUMAN` + `EVIDENCE_NOT_PAPER_READY`
（协议 / 比较产物尚未 `paper_eligible`，与既有人工路径的证据晋升规则一致），
产生一条 `status=DRAFT` 的 Claim，等待人工晋升证据后才会变为 `VERIFIED`。

调试过程中发现并修复了两个真实缺陷（均在本次迭代内完成，详见最终英文报告）：
产物内容路径未相对 Case 根解析导致的 `SCHEMA_INVALID` 误判，以及优势断言检查
过严导致合法的"并列取简单模型"结果被误拒为 `UNSUPPORTED_SUPERIORITY_CLAIM`。
修复后对同一 Case 重跑两次，第二次的全部提案在 `agents/decisions.jsonl` 中
均为 `record_type="replay"`，无新增产物、无新增 Claim——即第 12.2 节所称的
回放语义在真实 Case 上成立，不仅是单测断言。

### 12.6 运行时语义契约与 `compare-agent-runtimes`

*implemented and covered by automated tests*（比较器逻辑）／
*implemented but not executable in the current environment*（与真实 LangGraph 的
跨运行时比较，因 12.1 节所述网络限制）。新增 `agents/semantics.py`：把
`WorkstationState` 的每个字段分类为 `EXACT` / `CANONICAL` / `RUNTIME_SPECIFIC`
三类之一（默认 `EXACT`，即"不认识的字段一律严格比较"，避免误把有意义的差异
规约掉）；`diff_states()` 按分类比较，`RUNTIME_SPECIFIC`（如 `decided_at`）
被显式跳过并在报告中可见，而不是被删除后不留痕迹。新增 CLI 命令
`compare-agent-runtimes`：为 builtin / langgraph 各建一份 Case 的隔离临时工作区
（`tempfile.TemporaryDirectory` + `shutil.copytree`），分别执行同一 Case，
diff 结果不一致时非零退出（`1`），langgraph 不可用时退出码为 `3`
（与`1`区分，因为"不可比较"与"比较后不一致"是两件事）。
`tests/test_agent_runtime_semantics.py` 中，比较器本身的正确性用合成状态验证
（9 个用例，*implemented and covered by automated tests*）；
`compare-agent-runtimes` 命令在真实沙箱里对一个真实 Case 执行，
真实得到退出码 `3` 与 `LANGGRAPH_UNAVAILABLE` 消息
（*implemented and locally executed*）——但该命令"两个运行时结果一致"这一路径
本身，在本环境从未真正跑过，因为 langgraph 装不上。

### 12.7 CI

*configured for CI but CI result not observed.*
`.github/workflows/agent-layer-tests.yml` 新增三个 job
（`builtin-env`、`langgraph-env`、`deterministic-smoke`），命令均为可直接复制执行的
真实命令（非伪代码）。本仓库当前工作副本没有 git 历史、没有连接 GitHub，
因此这个文件从未被 GitHub Actions 实际跑过一次；这里的状态仅代表"YAML 语法正确、
命令与本仓库当前真实的 CLI 参数一致"，不代表"CI 通过"。

### 12.8 已知限制（合并去重后的最终清单，见英文报告 Section M）

- 建模 fan-out 产物已改为不在哈希内容中嵌入 `created_at`，重跑幂等
  （已在 12.5 节验证）；~~但仍不具备……每次调用仍会重新拟合三个模型~~ ——
  **此限制已在第三次迭代中解决，见第 13 节：候选/比较产物路径已改为稳定路径，
  并加入了协议感知的复用判定，真实验证了"第二次相同调用零次模型拟合"。**
- 写入校验只覆盖"读回值与预期是否一致"，不覆盖操作系统级崩溃安全性。
- LangGraph 运行时路径、`compare-agent-runtimes` 的"两运行时一致"路径、
  三个新增 CI job，均因本沙箱网络限制从未被真实执行过一次。
- 并行建模拓扑（多裁判 / 多轮次仲裁）仍是 *design only*。

## 13. 第三次迭代（2026-07-26）：真实验证、计算级复用、证据晋升、身份契约复核

本节记录对本文档 12 节所述实现的一次**验证性**迭代：不新增智能体、不新增
写作/问题分析角色、不新增多轮裁决——范围严格限定在"把已实现的 M1 路径变得
可复现验证、计算可复用、证据可晋升"。所有变更均在
**验证沙箱镜像**（本会话对本仓库的真实文件级镜像；device shell 在本轮
全程不可用，见英文最终报告 Section A/N 对该限制的完整说明）中用真实 pytest
执行验证，而非手搓运行器。

### 13.1 计算级复用（`agents/modeling.py`）

*implemented and covered by automated tests（真实 pytest，真实 scikit-learn 拟合）*。

- 候选产物路径由 `candidate-{model_family}-{protocol_artifact_id}.json`
  改为稳定路径 `candidate-{model_family}.json`；比较产物路径由
  `comparison-{protocol_artifact_id}.json` 改为稳定路径 `comparison.json`。
  这直接复用 `ArtifactRegistry.register_existing()` 已有的
  "同路径内容哈希不变则复用同一 artifact_id，内容变化则将旧条目标记
  `SUPERSEDED` 并新建 `ACTIVE` 条目"机制——不新增任何字段，即同时解决了
  "计算级复用"（13.1）与"历史产物治理"（13.2）两个问题。
- 新增 `_CandidateModelAgent._find_reusable_candidate()`：仅当协议 id、协议
  哈希、候选自身超参数（`_hyperparameters()`）、候选状态（`VALID`）、
  以及登记表中该路径当前 `ACTIVE` 条目的 sha256 与磁盘文件实际内容五者
  全部匹配时才复用，跳过整个 K 折拟合；否则重新拟合。
  `record["reuse_status"]`（`"computed"` / `"reused"`）仅作为运行时信息
  附加在返回值与 Proposal payload 中，不写入被哈希的文件内容本身
  （与既有 `candidate_artifact_id` 的处理方式一致，见代码注释）。
- 新增 `ModelEvaluationAgent._EVALUATION_VERSION` 常量与
  `_find_reusable_comparison()`：仅当协议 id/哈希、评估实现版本号、以及
  当前候选集合的签名（按 candidate_id 排序的
  `{candidate_id, candidate_artifact_id, sha256}` 三元组列表）与既有
  `comparison.json` 中记录的完全一致时才复用比较产物。
- 真实验证（`tests/test_modeling_fanout.py`，8 个用例，均为真实 pytest 通过，
  非手搓断言）：
  - 第二次完全相同的调用：真实计数拟合调用次数为 0（不是靠
    `reuse_status` 字段推断，而是 monkeypatch 计数 `_evaluate` 的实际调用）。
  - 协议改变（`n_splits` 不同）强制重算，且旧候选被 `SUPERSEDED` 而非删除。
  - 数据集哈希改变（换一份内容不同的数据集）强制重算。
  - 仅一个候选的实现改变（如决策树 `max_depth`）：只有该候选被重新拟合，
    另外两个候选完全未被调用；比较产物因候选集合签名变化而重算，
    但其余候选的 artifact 历史版本数不变。
  - 复用不产生重复的登记表 / 审计条目。

### 13.2 历史调试产物治理

*implemented and covered by automated tests*。见 13.1 所述机制。真实测试
（`TestHistoricalCandidateFiltering`）构造了三代不同协议（对应三次调试性重跑），
确认：全部 9 个历史候选 artifact 均保留在登记表中（6 个 `SUPERSEDED`，
3 个 `ACTIVE`，append-only，无删除）；但对"当前"协议代的评估只看到当前这
一代的 3 个候选，而不是全部 9 个历史候选——`ModelEvaluationAgent` 原有的
"候选必须匹配当前协议 id"过滤逻辑，配合稳定路径的自动 supersede，二者
组合起来已经足以满足"只评估当前协议与当前 run 的候选集合"的要求，
未引入 `run_id` / `canonical` / `debug` 等额外元数据字段。

一个必须诚实记录的设计取舍：由于候选/比较产物是**稳定路径、单一 ACTIVE
条目**，一旦某一代协议的候选被写入，上一代协议的候选即被 supersede——
也就是说，**无法在写入新一代之后，再对旧一代协议重新发起一次"评估"**
（`ModelEvaluationAgent` 会返回 `BLOCKED: no candidate artifacts found for
this protocol`，因为此时登记表里已经没有属于旧协议、状态为 `ACTIVE`
的候选了）。这是刻意的取舍而非疏漏：旧协议的候选仍然是可查、可审计的历史
证据（`all_artifacts` 仍能读到，只是 `status=SUPERSEDED`），但它们不再是
"当前可比较的活跃输入"。如果未来需要支持"多条协议世系同时保持活跃、
可并行比较"，需要引入按协议 id 命名空间化的路径（如
`candidate-{model_family}-{protocol_id[:12]}.json`）而非当前的单一稳定
路径——这会牺牲一部分 13.1 节的自动 supersede 简洁性，换取多世系并存的
能力，是否需要取决于实际使用场景，本次迭代未做这个取舍。

### 13.3 证据晋升链（`paper_ready.py` 新增 `ModelingEvidenceGate`）

*implemented and covered by automated tests*。

糖尿病 Case（及本节所有单测中的合成 Case）中，模型选择的裁决结果此前止步于
`NEEDS_HUMAN` / `EVIDENCE_NOT_PAPER_READY`，因为 `modeling_protocol` 与
`model_comparison` 两个 artifact 从未被标记为 `paper_eligible`。没有新建
平行的晋升机制：新增的 `ModelingEvidenceGate.assess()` / `.approve()`
（`paper_ready.py`）复用了完全相同的、已有的
`ArtifactRegistry.promote_to_paper()` 原语（与既有 `PaperReadyGate.approve()`
调用的是同一个方法），只是把资格检查换成了建模 fan-out 自己的产物形状：
协议 artifact 类型/状态、比较 artifact 类型/状态、比较内容确实引用了
"这一个"协议 id 与协议哈希（防止用一份协议 A 下产生的比较去晋升协议 B
的证据）、比较中至少有一个 `VALID` 候选、以及既有的 case 级
`artifacts.verify()` 完整性检查。`approve()` 晋升协议、比较，以及比较所
引用的**全部候选** artifact（不仅是 Proposal 本身引用的两个），使真正
支撑这次裁决的完整证据链——协议、候选、比较——全部变为 `paper_eligible`，
而不只是让 claim 的资格检查刚好通过。

真正让 `NEEDS_HUMAN` 的旧 claim 变为 `VERIFIED` 还需要一步：`claims.py`
新增 `ClaimRegistry.recheck_evidence()`。原因是 Adjudicator 的回放缓存
（12.2 节）按 `proposal_id` 精确匹配——重新提交同一个裁判 Proposal 只会
从缓存里拿回*原来*的 `NEEDS_HUMAN` Verdict，不会重新跑一遍资格检查（这一点
已被真实测试验证：`replay.replayed is True` 且 `replay.status ==
NEEDS_HUMAN`，历史决策记录保持不变，符合审计可解释性要求）。
`recheck_evidence()` 复用的是 `ClaimRegistry.create()` 里*一模一样*的资格
判定规则（`missing_eligibility` 检查），只是应用在 claim 当前的证据状态
上，而不是创建时刻的状态——不是平行的新规则，是同一条规则在更晚的时间点
再判一次。它是幂等的、可安全重复调用的空操作（若尚未满足资格，或状态已
非 `DRAFT`，直接原样返回，不追加登记表行）。

真实端到端验证（`tests/test_modeling_evidence_promotion.py`，3 个用例）：
用真实的建模 fan-out（协议 → 三个候选 → 评估 → 裁判）在一个合成数值
数据集上跑出一个 WINNER 结果 → Adjudicator 写入 `DRAFT` claim
（`NEEDS_HUMAN`）→ `ModelingEvidenceGate.assess/approve` 真实晋升
→ 重新提交同一 Proposal 确认只是重放（不产生第二次判定）→
`recheck_evidence()` 把 claim 从 `DRAFT` 翻转为 `VERIFIED` →
`ClaimRegistry.list_claims()` 确认整个 Case 中**恰好一条** claim、且为
`VERIFIED`。CLI 新增 `assess-modeling-evidence` / `approve-modeling-evidence`
/ `recheck-claim-evidence` 三个命令，接线到同一批真实对象
（非独立的测试专用路径）。

**关于糖尿病真实 Case 本身**（本段在同一工作日内更新，替换早前一版
"未能在真实 Case 上执行"的记录——那句话在写下当时属实，但随后同一轮
工作中这条链确实在该 Case 上真实执行了，故按最新事实改写）：
证据晋升链已在验证沙箱的 Case `20260726-CUMCM-0001-DEGF`
（本会话一直使用的那个真实糖尿病 Case，442 行观测数据，
`dataset-9ecd95082b21`，数据哈希 `9193026b7622ff94…`）上真实执行完成：

- 裁判 Proposal `proposal-5186b65d8d5ab0e3`（`model_judge_agent`，
  获胜者 `candidate-robust_baseline`）的原始 Adjudicator 判定为
  `NEEDS_HUMAN` / `EVIDENCE_NOT_PAPER_READY`，产出 `DRAFT` claim
  `claim-c75433559a9c`（2026-07-26T11:19:33Z，`decisions.jsonl` 留有
  decision 与 replay 两条记录，历史未被改写）。
- `ModelingEvidenceGate.assess/approve`（等价 CLI：
  `assess-modeling-evidence` / `approve-modeling-evidence`）晋升了协议
  `artifact-41c1ee91a016`（哈希 `20482d9a600d45bb…`）、比较
  `artifact-60aeb4560769`（哈希 `00ca255f6a3b11cb…`）及三个候选
  `artifact-b53ddd04bfe0`/`artifact-989ef71cfa38`/`artifact-77d081078313`，
  批准产物为 `artifact-e835afa1a13d`。
- `ClaimRegistry.recheck_evidence`（CLI：`recheck-claim-evidence`）把
  `claim-c75433559a9c` 从 `DRAFT` 翻转为 **`VERIFIED`**（限制清空，
  `evidence_rechecked_at: 2026-07-26T13:30:15Z`）；再次调用为幂等空操作
  （登记表行数不变，已验证）。
- 晋升后 `validate-case` 返回 `valid: true`，无哈希漂移。

**准确的限制表述**：这个 Case 位于云沙箱（`output/` 类数据本就被
`.gitignore` 排除、从不进入 git 工作树），不在用户机器上；所以"真实"
指的是"本会话实际驱动过完整流水线的那个真实数据 Case"，而不是
"位于用户磁盘上的文件"。

### 13.4 Proposal 身份契约复核（`agents/contracts.py`）

*reviewed; no code change made, with documented reasoning*。

当前 `Proposal.proposal_id` 是 `sha256(kind, agent, summary, payload,
evidence)[:16]`，显式排除 `case_id`、schema 版本、agent 实现版本、
以及协议 id（`created_at` 已被排除，这是既有设计）。复核结论：

- **`case_id` 未被纳入哈希，是否是问题？** 结构上不是：`decide()` 的回放
  查找 `_find_original_decision(case_id, proposal_id)` 本身就是在
  "这个 Case 自己的 `decisions.jsonl`"里查找，跨 Case 的重放缓存物理上
  不可能互相污染——即使两个不同 Case 碰巧提交了内容完全相同的 Proposal，
  它们各自的回放判定只在各自的登记表文件里进行。因此不需要为了"防止
  跨 Case 撞车"而修改哈希内容；这是一条关于既有代码结构的确认，不是新增
  的保证。
- **`summary`（人类可读文本）是否应该排除出哈希？** 对本次迭代范围内的
  全部确定性 Agent（`agents/modeling.py` 五个 Agent）逐一检查后确认：
  它们的 `summary` 全部是从 `payload` 字段模板化生成的固定文本（例如
  `f"{self.model_family} 候选模型评估完成，状态 {record['status']}"`），
  不存在"内容相同但 summary 因无关原因（如 LLM 自由生成的措辞）而不同"
  的情形——真实回放测试（12.2 节、13.1 节、13.3 节共计三处独立测试）
  全部通过，证明当前方案在本次迭代的实际使用范围内没有造成误判。
  **结论：本次迭代不改动身份哈希方案**，原因有二：(1) 未观察到真实缺陷，
  没有理由为了一个假设性风险去做用户明确警告过的"随意的身份变更"；
  (2) 会写作/措辞自由生成 Proposal 的 LLM Agent 本次迭代被显式禁止新增
  （见 12.13 节范围约束），该风险目前是纯理论性的。
- **下一次迭代如果引入 LLM 撰写类 Agent 时的建议**（尚未实现，仅作为
  记录）：届时应将 `summary` 从内容哈希中移除（只哈希
  `kind`/`agent`/`payload`/`evidence`），或者在 `propose()` 处理链路中
  对撰写类 Agent 的输出做规范化（如去除标点与空白差异后再纳入哈希）；
  是否同时显式把 `case_id` 纳入哈希可作为纵深防御措施单独评估，但根据
  上面的结构性分析，这不是一个当前已知会触发的缺陷。
- 无需迁移/兼容层：因为没有对哈希算法做任何改动，现有 `decisions.jsonl`
  历史记录的 `proposal_id` 语义完全不受影响。

### 13.5 真实 pytest（本次迭代新增/变更部分）

本节曾记录一个 **70 passed** 的结果——那是在发现"沙箱镜像的 `tests/`
目录只有 3 个文件、而真实仓库有 48 个"之前的中间状态（当时全部 5 个
已同步测试文件确实是 70 例全过，该数字本身没有错，但它不是全量）。
同一工作日内补齐了缺失的 42 个既有测试文件后，最新的、最终的全量结果为：

- 环境：验证沙箱镜像（非用户机器），Python 3.11.15
  （`/usr/bin/python3`），pytest 9.0.3（`/root/.local/bin/pytest`，
  `uv tool` 独立环境，经 `PYTHONPATH` 桥接系统 site-packages）。
- `pytest --collect-only --ignore=tests/test_ui_app.py` →
  **176 tests collected**。
- `pytest -ra -vv --ignore=tests/test_ui_app.py` →
  **176 passed, 0 failed, 0 skipped, 0 xfailed**，546 个警告（全部为
  matplotlib 缺 CJK 字形的告警），退出码 0；`-ra` 未产生任何
  skip/xfail/fail 摘要条目。
- 不加 `--ignore` 的裸 `pytest -ra -vv` → **收集阶段即中断**（退出码
  2，`1 error`，0 个测试被执行）：`tests/test_ui_app.py`（含 1 个测试
  函数）在导入时因可选依赖 `streamlit`（`[ui]` extra）缺失而
  `ModuleNotFoundError`——本沙箱 PyPI 被网络封锁无法安装。因此该测试
  既不是 skipped 也不是 failed，而是 **collection error、从未执行**。
  之前对外表述过的"176/177"不精确：准确说法是磁盘上共 177 个测试函数，
  其中 176 个可收集且全部通过，1 个因环境缺依赖在收集阶段报错。
- 新增文件 `tests/test_modeling_fanout.py`（8 例）与
  `tests/test_modeling_evidence_promotion.py`（3 例）包含在上述 176 例
  之内。

### 13.6 本节范围内已知限制

- 本节所有验证均在验证沙箱镜像中完成（本会话对该仓库的真实文件级镜像，
  本轮持续从 `device_stage_files`/`device_commit_files` 同步用户实际仓库
  的文件内容）中完成，而不是在用户设备上原地对其真实 `.git` 仓库执行——
  本轮 `device_bash` 全程返回 "Workspace unavailable"，因此无法在用户
  自己的机器上运行 `git`/`pytest`/`pip install langgraph`/`git push`。
  这是一处已确认的外部环境限制，不是被回避的工作。
- 13.2 节末尾所述"无法对已被 supersede 的旧协议世系重新发起评估"的取舍，
  在真实糖尿病 Case 上的含义：该 Case 的历史候选（7 代协议、21 个旧路径
  候选 artifact）写于稳定路径方案之前，仍以旧的按协议命名的路径存在，
  不受新方案的自动 supersede 影响，也未被回溯清理（见英文报告
  Section I/N 的披露）。
- 13.4 节的身份契约复核是分析性结论，不是新增的自动化测试断言"summary
  差异不应影响身份"这类反例；如需更强保证，可在下一次迭代为该结论本身
  补充回归测试。

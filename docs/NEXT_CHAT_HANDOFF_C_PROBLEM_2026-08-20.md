# 新对话交接文档：C题专精数学建模工作站

日期：2026-08-20

> 这是下一轮对话的主交接文档。新 Agent 不应从头重新设计。先恢复现场、核实当前磁盘状态，再从 Goal 7.4 继续。

---

## 0. 新对话第一条执行指令

本地项目：

`D:\computer learning\vibe_coding\math_model_ai_process`

请使用 DevSpace 打开该项目并遵循以下顺序：

1. 先读根目录 `AGENTS.md`。
2. 按要求优先使用本地 CodeGraph，不要先全仓 grep/read。
3. 运行 `codegraph status`；若有 pending changes，先 `codegraph sync`。
4. 读取：
   - `docs/CURRENT_STATE.md`
   - `docs/section-7-stage-summary-2026-08-20.md`
   - 本文档 `docs/NEXT_CHAT_HANDOFF_C_PROBLEM_2026-08-20.md`
   - `.internal/resume_brief.md`
5. 运行 `git status --short`，保护当前所有 dirty/untracked WIP。
6. 禁止 reset / clean / restore-all / checkout overwrite。
7. 所有“当前文件是否存在、测试是否通过、代码当前实现是什么”都必须重新通过 DevSpace/CodeGraph 验证；聊天记忆只能做导航。

当前工作原则：**只专精 C 题。A/B/D/E/F 不再作为正式 excellent benchmark，只保留 archive / method reference / regression 用途。**

---

# 1. 项目现在是什么

这个项目不再是“让 GPT 一次性写一篇数模论文”。

当前主架构已经是一个 Evidence-Locked Research State 工作站：

```text
ProblemGraph
-> ModelingBrain
-> SolverRegistry / SolverPlugin
-> ValidationProtocol Registry
-> Result / Table / Figure / Claim evidence
-> ModelGraph
-> EvidenceGraph
-> NarrativeGraph
-> competition-specific Paper Renderer
-> CompetitionPaperAuditor
-> Excellent benchmark / Readiness
-> Research defect -> exact upstream repair
-> Document defect -> Paper repair
```

核心目标：

- 真实拆题；
- 每个子问题独立有 solver / validation；
- 后问复用前问 accepted Research State；
- 不让写作层补造结果；
- 研究缺陷精确回退；
- 最终形成 CUMCM-C / MCM-C 两套论文与交付 profile。

---

# 2. 已完成的阶段

## Section 0–5

已 PASS / 冻结为基础设施：

- baseline / benchmark / persistent memory
- ProblemGraph / Subproblem Engine
- ModelingBrain
- Solver Engine 第一批 Gold capability
- ValidationProtocol Registry
- M-Round Research Refinement

Section 5 的核心能力已经能把真实 defect 定位到 `subproblem + phase`，而不是重写整篇论文。

## Section 6 — Paper Engine

内部 Gate 已 PASS。

已跑通两道 materially different 的 MCM C 历史题：

1. 2023 MCM C Wordle
2. 2018 MCM C Energy Compact

这两题已经验证：

- Research State -> Paper；
- method equations / assumptions；
- per-question evidence；
- bibliography；
- same-problem O-award full-text comparison；
- Paper Auditor；
- ExcellentReadiness；
- prompt-specific memo/letter；
- Research gap 不允许靠 prose 修复。

## Goal 7.0 — 本地数学建模知识库

资料根目录：

`D:\作业\竞赛\大学生数学建模\美赛\备赛\资料`

已做只读 inventory：约 9.6GB、211 个目录进入地图。

已落盘：

- `docs/LOCAL_MODELING_KNOWLEDGE_BASE_README.md`
- `config/ref_models/local_knowledge_base_registry.json`

资料被区分为：

```text
Raw Archive
-> Asset Registry
-> Derived Knowledge
-> Skill / Routing Knowledge
-> Runtime Research State
```

教材、课程、Prompt、第三方 Skill 只能作为 advisory prior；SolverRegistry 和真实 accepted evidence 仍是真源。

## Goal 7.1 — C-only Excellent Corpus

正式 primary benchmark 已冻结为 **5 道 C 题 / 21 篇优秀论文**：

- CUMCM 2010 C — 输油管布置 — 3 篇可解析优秀论文
- CUMCM 2018 C — 大型百货商场会员画像 — 3 篇
- CUMCM 2023 C — 蔬菜自动定价与补货 — 4 篇
- MCM 2018 C — Energy Compact — 5 篇 O 奖
- MCM 2023 C — Wordle — 6 篇 O 奖

Primary registry：

`config/ref_models/c_problem_excellent_benchmark_v1.json`

它会拒绝：

- 非 C 题进入正式 benchmark；
- 少于 3 个 CUMCM C；
- 少于 2 个 MCM C；
- paper count 不一致；
- benchmark asset 不存在。

## Goal 7.2 — C-Problem Modeling Knowledge

五题 corpus 已提炼成 7 条 shared priors，并真正进入 ModelingBrain / Validation / Repair：

1. Problem-specific representation before generic model
2. Question chain, not independent model zoo
3. Data / mechanism / constraint driven model choice
4. Quantified answers in high-visibility sections
5. Validation matches claim type
6. Algorithm diversity is normal
7. Decision/deliverable must be evidence-backed

重要边界：corpus **不是第五种 model candidate source**。它只能增加 research/validation obligation，不能把一个方法标成 PASS；SolverRegistry 仍是真源。

## Goal 7.3 — MCM-C / CUMCM-C Paper Profiles

同一个 accepted Research State 已能分流：

```text
accepted Research State
       ↓
  MCM-C profile    CUMCM-C profile
```

研究真源相同；差异只发生在摘要/summary、语言、章节、memo/letter、提交风格等 document layer。

---

# 3. 当前 Goal：7.4 Five Real C-Problem Gates

已有两个 MCM anchor：

- 2018 Energy
- 2023 Wordle

需要继续完成三个 CUMCM C：

1. 2010 C 输油管布置
2. 2018 C 大型百货商场会员画像
3. 2023 C 蔬菜自动定价与补货

## 2010 C 当前状态

2010 C 已跑通真实 Research/Solver/Validation/Paper Gate。

真实结果：

- Q2 objective ≈ 282.6973 万元；station x ≈ 5.449
- Q3 objective ≈ 251.9685 万元
- no-shared objective ≈ 251.9755 万元
- nominal shared-segment advantage ≈ 0.007 万元
- ±10% 城区附加费 sensitivity 已执行

当前真实论文：研究真实性已经较强，但写作呈现还明显不像最终国奖论文。

阶段评价：

- Research truth / evidence lock：8.5/10
- 数值求解：8/10
- Validation / boundary：8/10
- 多问研究链：7.5/10
- 论文结构：7/10
- 自然论文语言：4.5/10
- 国赛优秀论文呈现感：约 5/10
- PDF visual/layout：UNVERIFIED

样稿审阅记录：

`docs/generated_samples/cumcm_2010_current_draft_review.md`

详细阶段总结：

`docs/section-7-stage-summary-2026-08-20.md`

---

# 4. 2010 C 暴露出的真正通用问题

这些问题应先修一轮，再跑 2018C / 2023C。禁止写 2010C 专用 if/else。

## 4.1 Paper Renderer 内部语言泄漏

当前论文仍可能出现：

- `reported values include`
- `accepted Research State`
- `accepted question-level evidence`
- `SolverRegistry`
- `PASS / NEEDS_SOLVER`
- 内部 method id，如 `pipeline layout continuous`

这些对内部 provenance 很好，但不应进入竞赛正文。

需要做一个明确的：

```text
Internal Research Vocabulary
-> Human Paper Vocabulary Adapter
```

要求：

- 不改数值；
- 不改方法事实；
- 不改 validation；
- 只把 provenance/registry 语言翻译成人类学术表达。

## 4.2 Task-aware section suppression

几何优化题不应机械出现“没有预处理，所以本节无更多清洗”的空数据章节。

Paper Profile 应根据 ProblemGraph / EvidenceGraph 决定：

- 是否需要 Data Preprocessing；
- 是否需要 Feature Engineering；
- 是否需要 Assumptions；
- 是否需要 separate Sensitivity；
- 是否需要 deliverable section。

必须是 evidence-aware suppression，不是删掉固定章节。

## 4.3 Figure semantic contamination

2010 pipeline 题曾出现图 caption：`Optimized compact target levels`，明显来自 Energy 语义残留。

图的 title/caption/purpose 应来自：

```text
subproblem semantics
+ result schema
+ figure semantic_kind
```

禁止从 solver family 共享一个业务 caption。

## 4.4 Table humanization + dedup

目前可能出现：

- duplicate `objective value`
- internal metric key
- `accepted question-level evidence`

需要：

```text
Metric Schema
-> dedup
-> unit-aware label
-> question-aware interpretation
```

## 4.5 Alternative feasibility 仍过宽

当前错误倾向：

```text
Solver exists
=> PASS alternative
=> 要求 head-to-head comparison
```

下一版应该是：

```text
Solver exists
+ input compatible
+ representation compatible
+ constraint compatible
+ protocol comparable
= executable comparable alternative
```

只有最后这一层才产生 empirical comparison obligation。

## 4.6 ExcellentReadiness truth source 要迁移

2010C readiness 仍混入旧 `excellent_c7 extracted-summary prior`，会错误报告 full-text benchmark UNVERIFIED。

现在已有 C-only full-text benchmark，因此 readiness 要升级到：

`config/ref_models/c_problem_excellent_benchmark_v1.json`

旧 excellent_c7 可保留为 legacy structural prior，但不能再成为 full-text truth source。

## 4.7 Domain bibliography

2010C 当前只有 optimization method bibliography，工程背景参考不足。

下一步 bibliography 需要分：

```text
method source
+ domain/background source
+ data source
```

且不能为了“引用够多”随便补文献。

---

# 5. 下一步执行计划

## Goal 7.4A — 修 2010C 暴露出的通用层

优先级：

P0
- Paper internal-language adapter
- task-aware section suppression
- semantic figure captions
- table dedup / human-readable metrics

P1
- alternative semantic compatibility
- C-only Readiness migration
- domain bibliography split

完成后重新跑 2010C。

目标不是让测试过，而是让当前 draft 从“工程日志式论文”明显靠近真正优秀 CUMCM 论文。

## Goal 7.4B — 跑 2018 C 会员画像

这题用于暴露：

- 大表数据清洗；
- domain-specific member representation；
- RFM/RFMS/FMS；
- lifecycle/state transition；
- association / market basket；
- scoring/classification stability；
- business-facing strategy。

只补真实题暴露的 Solver/Validation gap。

## Goal 7.4C — 跑 2023 C 蔬菜定价补货

重点链路：

```text
EDA
-> demand relation
-> forecasting
-> price-demand relation
-> replenishment
-> constrained pricing/optimization
-> uncertainty / sensitivity
-> item-level portfolio decision
```

这是当前 C题专精最重要的综合 Gate。

## Goal 7.4D — Final Capability Gap Map

三道 CUMCM C 全部跑完后，汇总：

- 哪些 gap 是一次性题目特例；
- 哪些在两题以上重复出现；
- 哪些应该进入 Gold Solver / Validation / Modeling priors；
- 哪些只是 Paper layer；
- 哪些应该留到 external/human review。

## Goal 7.5 — Human Review

只有内部 Gate 修到“值得人看”时才叫用户审。

届时提供固定审阅清单：

- 摘要第一眼是否像优秀竞赛论文；
- 模型链是否自然；
- 有没有为模型而模型；
- 图表是否真正承担论证；
- 哪一部分最像 AI/模板；
- 哪一处最可能被评委扣分；
- 业务/工程解释是否可信。

用户意见进入 issue tracker，再精确路由 Research / Document defect。

## 后续

- PDF visual/layout benchmark
- Competition Delivery / submission package
- 修 Python 3.11 + Tenacity 5.1.5 的历史 collection blocker

---

# 6. GitHub 项目调研（2026-08-20）

调研目标不是寻找“更大的 Agent”替换本项目，而是找当前阶段可移植的局部机制。

## 6.1 USAIL-HKUST / LLM-MM-Agent

Repo: https://github.com/usail-hkust/LLM-MM-Agent

当前公开项目把真实数学建模概括为四步：Problem Analysis -> Mathematical Modeling -> Computational Solving -> Result Reporting，并提供 MM-Bench、端到端 Demo 和真实竞赛实践。

### 值得借

- 继续保持完整真实建模闭环，而不是只做 paper writer；
- 用历史真实题作为系统 benchmark；
- report 是 research 的下游阶段。

### 不建议照搬

我们当前的 ProblemGraph / per-subproblem Solver / Validation / EvidenceGraph / Repair 已更细，因此不值得为了“跟 MM-Agent 一样”重构主链。

**结论：作为外部架构 sanity reference，不作为代码母版。**

---

## 6.2 Technion-Kishony-lab / data-to-paper

Repo: https://github.com/Technion-Kishony-lab/data-to-paper

核心价值：backward-traceable / data-chained manuscript。数值能够一路追溯到生成它的分析和代码；同时提供 human oversight、review、rewind、record/replay。

### 强烈建议借

1. **Paper-side lineage view**
   - 论文里的数值/表/图能点回 Result ID -> Solver execution -> source data。
2. **Rewind as first-class operation**
   - Reviewer 指出问题后，明确回到最早错误节点，而不是只做 rewrite。
3. **Human intervention ledger**
   - 用户修改/接受/拒绝建议应成为可恢复状态。

我们已经有这些概念的底层雏形，下一步应该做轻量 UI/state layer，而不是复制整个框架。

**优先级：★★★★★**

---

## 6.3 Stanford OVAL / STORM + Co-STORM

Repo: https://github.com/stanford-oval/storm

STORM 把长文写作拆成 pre-writing research -> outline -> writing，并通过多视角问题生成提升信息覆盖；Co-STORM 加入 human-AI collaborative knowledge curation。

### 值得借

- 写作前先形成“叙事问题树 / 评委视角问题列表”，而不是 Research State 一出来就逐字段模板化渲染；
- 对背景/讨论部分，可用多视角：数学、工程、决策、可解释性；
- human reviewer 的反馈可以成为下一轮 outline revision 的输入。

### 边界

竞赛期间不能把 STORM 的大规模在线检索习惯直接移植过来；我们的 evidence 必须以题目附件、本地知识库和允许引用的外部源为边界。

**优先级：★★★★☆，主要用于 Narrative/Paper。**

---

## 6.4 SakanaAI / AI-Scientist-v2

Repo: https://github.com/SakanaAI/AI-Scientist-v2

项目把实验探索、writeup、citation、review 分离，并使用 progressive agentic tree search；paper review 还单独检查正文与 image/caption/reference。

### 值得借

1. **Writeup 与 Reviewer 真正分离**
   - Writer 不应自己给自己放行。
2. **有限树搜索，不全局爆炸**
   - 只在某个高不确定节点比较 2–3 个研究分支；
   - branch budget 与 token/compute budget 绑定。
3. **图 + caption + reference 独立 review**
   - 很适合我们的 Goal 7.5/视觉 Gate。
4. **失败路径可以放弃**
   - debug/search 深度应该有限，不为一个低价值 alternative 无限迭代。

### 不建议照搬

AI-Scientist-v2 更适合开放式科研探索，成本/复杂度高。数学建模竞赛时间短、题目约束清晰；整个工作站做 tree search 会违反“轻量化”。

**结论：只借 local branch search + independent review。优先级：★★★★☆。**

---

## 6.5 handsomeZR-netizen / mathmodel-skill

Repo: https://github.com/handsomeZR-netizen/mathmodel-skill

当前版本提供 CUMCM/MCM/电工杯的 10 阶段工作流、4 层反馈、decision log、competition packs、规则基线、论文反模式和 CUMCM 公开样本统计。

### 值得借

- competition-specific compliance pack；
- decision_log 作为跨窗口连续状态；
- final submission doctor；
- per-question review / targeted repair；
- anti-pattern checklist；
- 规则与经验统计明确分层，不把经验当官方 rubric。

### 我们已经比它更深入的地方

- actual SolverRegistry feasibility；
- family-specific Validation；
- Result/Table/Figure/Claim provenance；
- Graph-based evidence chain；
- exact research repair；
- same-problem full-text benchmark。

因此下一步主要借 **delivery/compliance/anti-pattern layer**，不复制它的 10 阶段主流程。

**优先级：★★★★★（Section 8 尤其高）。**

---

## 6.6 Paper2Poster / Paper2Poster

Repo: https://github.com/Paper2Poster/Paper2Poster

它本身是 paper -> poster，但真正有价值的是：top-down、visual-in-the-loop、多模态 evaluation，以及 QA/VLM-as-Judge 对视觉产物做独立检查。

### 强烈建议迁移的思想

我们的 Paper Visual Gate 可以变成：

```text
paper.md / latex
-> render PDF
-> page screenshots
-> visual reviewer
-> issue list
-> document-only repair
-> render again
```

视觉 Reviewer 检查：

- 页面密度；
- 图表是否过小；
- 空白/溢出；
- caption 是否语义正确；
- 图表与正文是否在合理距离；
- 表格是否可读；
- 公式断行；
- 中英文污染；
- 图是否真正承担论证。

不要复制 poster generation，只借 **render -> see -> judge -> revise**。

**优先级：★★★★★（Goal 7.5 后）。**

---

## 6.7 sohan-shingade / paper-reviewer

Repo: https://github.com/sohan-shingade/paper-reviewer

这是一个较小的项目，但其设计非常适合 Goal 7.5：多个独立 reviewer + handling editor + cross-revision `issues.yaml`。

Reviewer 分成 methods/domain/generalist，另有 citation/statistics/visual consultant；issue tracker 记录问题在不同版本中的 open/resolved/regressed。

### 建议借机制，不依赖项目本身

我们的 Goal 7.5 可实现：

```text
Research Reviewer
Paper/Narrative Reviewer
Competition Judge Reviewer
Visual Reviewer
        ↓
Handling Editor / Aggregator
        ↓
review_issues.json
        ↓
RESEARCH -> Section 1–5
DOCUMENT -> Section 6/7
EXTERNAL -> human / rules
```

跨版本必须有 issue identity，不能每轮生成一份全新评论。

**优先级：★★★★☆。**

---

## 6.8 Zhangyanbo / vibe-paper-writing

Repo: https://github.com/Zhangyanbo/vibe-paper-writing

该项目把聊天/笔记中“用户明确认可的想法”转换为学术 prose，并对歧义内容标记而非擅自补写。

### 对我们最有用的不是聊天输入，而是 humanization 原则

可以抽象成：

```text
accepted Research State
-> endorsed facts / claims only
-> scholarly prose transformation
-> ambiguity remains flagged
```

这正好适合修当前 2010C：把内部 provenance 语言变成人类论文语言，同时保持 evidence lock。

**优先级：★★★★☆，用于 Paper Humanization Adapter。**

---

# 7. GitHub 调研后的架构决策

**不新增一个“大而全 Agent 框架”。**

现有主框架继续保留，只增加 6 个窄模块：

```text
1. PaperHumanizationAdapter
   参考 vibe-paper-writing / STORM

2. SemanticAlternativeCompatibility
   项目内部需求驱动

3. ReviewIssueTracker
   参考 paper-reviewer + data-to-paper rewind

4. LimitedResearchBranchSearch
   参考 AI-Scientist-v2，只用于高不确定节点

5. VisualPaperReviewer
   参考 Paper2Poster visual-in-loop + AI-Scientist image/caption review

6. CompetitionDeliveryDoctor
   参考 mathmodel-skill competition packs / final doctor
```

严格遵守用户两条总原则：

### 泛化

- 不能为 2010C 写业务特例；
- 模块由 task family / evidence schema / competition profile 驱动；
- 任何新能力必须至少能解释为什么对另一类 C题也有效。

### 轻量化

- 不全局 tree search；
- 不每个节点都 multi-agent review；
- 只有 Gate 失败或高不确定节点才升级昂贵策略；
- corpus 只提供 prior，不把 21 篇全文塞进运行时 context；
- visual review 只在 final candidate PDF 上执行。

---

# 8. 下一轮建议执行顺序

```text
Step 1  修 2010C PaperHumanization + semantic figures/tables
Step 2  修 AlternativeCompatibility + Readiness truth source
Step 3  重跑 2010C，确认 Paper REVIEW 明显下降
Step 4  跑 2018C，补真实数据挖掘/lifecycle/association gap
Step 5  跑 2023C，补 forecast->decision->optimization gap
Step 6  形成 7.4 Final Gap Map
Step 7  实现 multi-review issue tracker
Step 8  叫用户 Human Review
Step 9  Visual PDF Gate
Step 10 Competition Delivery / submission doctor
```

不要提前进入 Step 7–10，除非 2018C/2023C 已完成真实 Gate。

---

# 9. 当前测试/环境边界

最近阶段组合回归：

- five-corpus map + Modeling priors + Paper profiles + 2010C real gate：24 passed
- 2010C focused real gate：5 passed

历史完整 `python -m pytest -q` 仍有两个 collection blocker：

- Python 3.11
- Tenacity 5.1.5 使用已移除的 `asyncio.coroutine`

这是已有环境债，不是 Section 7 新回归。

进入最终 release / Section 8 前应单独修复。

---

# 10. 技术债与不可虚报项

1. MCM 2018/2023 两个 anchor 仍使用 Section 6 old full-text schema；3 个 CUMCM corpus 是 richer deep schema。问题级 capability map 已统一，但 schema parity 未完全完成。外部 MCM PDF 逐篇重抽受 DevSpace 60–120 秒调用窗口限制。
2. PDF visual/layout 仍 UNVERIFIED。
3. blind/human review 仍 UNVERIFIED。
4. 2018C / 2023C 还未完成真实 end-to-end Gate。
5. 当前 internal PASS 绝不能写成“国奖/O奖水平认证”。

---

# 11. Protected WIP

禁止 reset/clean 覆盖。重点保护至少：

- `prompts/internal/paper_refinement.json`
- `src/mathworkstation/agents/modeling.py`
- `src/mathworkstation/auto_pipeline.py`
- `src/mathworkstation/paper_contracts.py`
- `src/mathworkstation/refinement.py`
- `src/mathworkstation/task_executors.py`
- `src/mathworkstation/recurrent_workstation.py`
- `src/mathworkstation/problem_graph.py`
- `src/mathworkstation/modeling_brain.py`
- `src/mathworkstation/solver_engine.py`
- `src/mathworkstation/validation_protocol.py`
- `src/mathworkstation/subproblem_engine.py`
- `src/mathworkstation/subproblem_comparison.py`
- `src/mathworkstation/narrative_graph.py`
- `src/mathworkstation/research_state_graphs.py`
- `src/mathworkstation/research_state_paper.py`
- `src/mathworkstation/competition_paper_auditor.py`
- `src/mathworkstation/evidence_locked_writer.py`
- `src/mathworkstation/excellent_readiness.py`
- `src/mathworkstation/same_problem_benchmark.py`
- `src/mathworkstation/c_problem_benchmark.py`
- `src/mathworkstation/c_problem_modeling_priors.py`
- `src/mathworkstation/c_problem_paper_profiles.py`
- `src/mathworkstation/cumcm_2010_gate.py`
- 对应 tests / config / docs

---

# 12. 给新对话 Agent 的一句话

**不要再扩“大框架”。现在的任务是：利用 2010C 暴露的问题把研究真相转换成自然优秀论文，再用 2018C 和 2023C 真实 Gate 逼出 C题通用 Solver/Validation 缺口；只有三道 CUMCM C 全部跑完，才进入 Human/Visual/Delivery。**

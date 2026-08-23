# V6 — Meta-Benchmark-Driven Reconstruction

日期：2026-08-23  
状态：**设计冻结，下一阶段按本协议执行**  
范围：`math_model_ai_process` 数学建模端到端论文工作站  
当前优先级：**能力架构 > UI；评价可信度 > 新功能数量；因果诊断 > 局部补丁**

---

## 0. 为什么现在必须换研发方法

当前项目已经不是“让一个 LLM 写一篇数学建模论文”的初级系统。现有真实主线已经包括：

```text
ProblemGraph
-> ModelingBrain
-> Solver / Validation
-> Evidence
-> ModelGraph / EvidenceGraph
-> NarrativeGraph
-> Research-State Paper
-> CompetitionPaperAuditor
-> Excellent-paper / same-problem benchmark
-> DOCUMENT / RESEARCH defect routing
-> recurrent repair
```

同时已有 Model Spine、Model Structure、Evidence Expression、Model Story、图表注册与视觉链路、证据锁定、artifact provenance、真实赛题 gate、优秀论文 corpus 等能力。

问题已经发生变化：

> **当前主要风险不是“少一个模块”，而是系统越来越完整、测试越来越多、内部 Gate 越来越高，但真实最终论文与 O/F/国奖优秀论文之间的主观和结构差距没有同比缩小。**

这意味着后续不能再采用：

```text
用户指出一个症状
-> GPT 搜资料 / GitHub
-> 新增一个类或 planner
-> 补测试
-> 测试 PASS
-> 重新生成论文
-> 仍然不满意
-> 再新增一层
```

这种开发方式会造成：

- architecture sedimentation：旧层不退出，新层持续叠加；
- test gravity：为了不破坏旧测试，新架构只能成为 adapter，而不是主导系统；
- generator/evaluator co-adaptation：生成器和自建 evaluator 一起演化，内部越来越高分但未必更接近真实奖级；
- local-optimum patching：每次修改局部正确，却无法推翻错误的高层假设；
- feature completion illusion：`xxx.py` 存在、测试通过被误认为“能力已经具备”；
- importance allocation failure：AI 会做很多正确工作，但资源未投入真正决定论文质量的环节。

因此 V6 的第一目标不是再扩展 Paper Engine，而是建立：

# **“科学地研发这个数学建模 Agent”本身的机制。**

也就是说，我们需要同时研究两个对象：

```text
Object Agent A：数学建模工作站
Meta Agent B：负责改造 A 的 GPT-5.6 Sol / 代码智能体
```

以后 B 的每一次修改都必须被当成一次可验证实验，而不是一次“开发任务”。

---

# 1. V6 的核心结论

## 1.1 当前工作站最值得保留的部分

以下能力不是当前主要矛盾，不应因为重构而推倒：

- Evidence-first / provenance；
- ProblemGraph / Subproblem state；
- solver 实际执行与 validation；
- 数据泄漏防护；
- claim / table / figure evidence linkage；
- research defect 与 document defect 分流；
- recurrent repair / checkpoint / recovery；
- same-problem excellent-paper calibration；
- artifact registry；
- competition profiles；
- human review 保持 `UNVERIFIED` 的诚实边界；
- Web shell 现有基础，但本轮不继续做 UI。

这些属于 **Governor / Verifier / Infrastructure**，当前总体较强。

## 1.2 当前最可疑的能力瓶颈

按优先级列为 4 个待验证假设，而不是直接宣布结论：

### H1 — Judge Validity Bottleneck

内部 evaluator / corpus detector / deterministic quality gate 能够检查完整性、证据和基本结构，但未必能可靠预测真实 O/F/国奖级偏好。

可能表现：

- 内部 90+ 的稿件仍明显不如优秀论文；
- evaluator 更容易奖励“结构齐全”而不是“scientific core / modeling insight / narrative elegance”；
- generator 学会满足 detector，而非产生真正优秀论文。

### H2 — Paper Compiler Bottleneck

上游 Research State 可能已经足够好，但固定 Story Grammar / renderer / frozen outline 把强模型的结构设计自由压缩掉。

可能表现：

- 论文出现稳定的字段感：研究目标、建模动机、模型与方法、变量、构造、数学模型、求解、检验、结论、局限；
- 不同题生成出相似的“优秀论文语法”；
- `ModelStoryPlanner` 存在，但对最终 PDF 的因果影响有限；
- 自由结构 LLM 在相同 evidence 下能够写出明显更自然的论文。

### H3 — Research Creator Bottleneck

ProblemGraph / ModelStructure / ModelingBrain 对问题的安全结构化很强，但候选建模结构仍可能偏规则化、关键词驱动、历史 pipeline 约束过强，缺少真正高质量的“scientific core”。

可能表现：

- 模型选择正确、稳健、可解释，但不惊艳；
- 新的 `ModelStructurePlan` 已谈状态/机制/约束，但实际执行仍受旧 regression/classification `ModelPlan` 或既有 solver 集限制；
- 整篇论文可以做到“无明显错”，但缺少真正让评委眼前一亮的统一建模思想。

### H4 — Meta-Agent Development Bottleneck

GPT-5.6 Sol 作为项目共同开发者，容易把用户反馈转译成局部功能需求，而不是先验证根因。

可能表现：

- 用户说“建模叙事不自然” -> 新建 ModelStoryPlanner；
- 用户说“图片不够好” -> 新建 Figure Director；
- 用户说“优秀论文差距大” -> 新增 comparator；
- 但没有证明这些模块是最终差距的主要因果来源。

V6 不允许先假设 H1-H4 哪一个一定正确。先实验，后重构。

---

# 2. V6 总体架构：Creator 与 Governor 分离

工作站长期目标采用“双系统 + 双闭环”：

```text
                    ┌──────────────────────────────┐
                    │   CREATIVE RESEARCH SYSTEM   │
                    │                              │
Problem / Data ---> │ Route Search / Hypotheses    │
                    │ Model Architecture Search    │
                    │ Experiment Proposal          │
                    │ Story Discovery              │
                    │ Visual / Expression Design   │
                    └──────────────┬───────────────┘
                                   │ candidates
                                   v
                    ┌──────────────────────────────┐
                    │   GOVERNANCE / EVIDENCE      │
                    │                              │
                    │ Solver Execution             │
                    │ Validation / Leakage         │
                    │ Evidence / Provenance        │
                    │ Claim Calibration            │
                    │ Artifact Integrity           │
                    │ Competition Hard Rules       │
                    └──────────────┬───────────────┘
                                   │ accepted state
                                   v
                    ┌──────────────────────────────┐
                    │  PAPER SEARCH + COMPILATION  │
                    │                              │
                    │ Story candidates             │
                    │ Claim-evidence map           │
                    │ Layout / figure plan         │
                    │ Section writer               │
                    │ Full-paper critic            │
                    └──────────────┬───────────────┘
                                   │
                                   v
                    EXTERNAL / FROZEN EVALUATION
```

核心原则：

> **规则负责守底线；强模型负责搜索；真实实验负责决定；独立 evaluator 负责评价。**

不再让规则层承担“创造优秀研究”的职责，也不让自由模型绕过 evidence / validation。

---

# 3. 首要建设：MathModel Meta-Benchmark v1

## 3.1 为什么它比新功能更优先

当前已有 Paper Benchmark，但缺少：

> **“一次工作站代码改造是否真的提升了整个工作站能力”的 Meta-Benchmark。**

以后任何 Vx -> Vx+1 必须回答：

```text
修改了什么高层假设？
在哪些真实问题上更好？
在哪些问题上退化？
改善是 research state 还是只是 prose？
held-out 是否仍然提高？
不同重复运行的方差有没有恶化？
```

没有这些证据，不得使用“能力已升级”“解决”“接近 O/F”等措辞。

---

## 3.2 Benchmark 分层保持现有 L0-L4，但增加 Meta 层

保留现有：

```text
L0 Unit / Regression
L1 Historical Functional Gate
L2 Cross-Problem Historical Benchmark
L3 Excellent Paper Corpus
L4 Blind / Human Competition Review
```

新增：

```text
M0 Judge Calibration
M1 Generator / Compiler Ablation
M2 Creator / Research Architecture Benchmark
M3 Workstation Version Tournament
M4 Sealed Held-out Generalization
```

### M0 — Judge Calibration

验证“谁有资格评价论文”。

### M1 — Generator / Compiler Ablation

验证是否是固定 Paper Compiler 压制最终表达。

### M2 — Creator Benchmark

验证上游 ModelingBrain / ModelStructure 是否产生足够强的研究结构。

### M3 — Version Tournament

V5 vs V6-x 在相同题、相同预算下匿名对打。

### M4 — Sealed Held-out

开发 Agent 不知道具体 target paper / hidden expected solution，在最终版本冻结后才评价。

---

# 4. Benchmark 数据必须分离：DEV / VALIDATION / SEALED HOLDOUT

## 4.1 DEV

开发 Agent 可以看到：

- 完整题面；
- 数据；
- 生成论文；
- evaluator feedback；
- 参考优秀论文（如果该实验允许）；
- traces。

可以多次迭代。

## 4.2 VALIDATION

用于阶段性验证是否过拟合当前 DEV 题。

规则：

- 可以知道题目身份；
- 不能针对其写题号/年份专用逻辑；
- 只能通过通用组件修复；
- 每次大架构修改最多跑有限轮，避免反复调到 validation set。

## 4.3 SEALED HOLDOUT

**真正用于宣告工作站升级。**

必须满足：

- 题目身份/参考优秀论文在版本冻结前尽可能不暴露给实现 Agent；
- evaluator 独立；
- 生成配置冻结；
- 无人工针对该题修补；
- 最终只运行少量次数；
- 结果不允许反向用来继续调本版本后再重新报告同一 holdout。

### 重要：holdout 不应把具体答案写入当前 repo

因为负责开发的 GPT 可以读取 repo。

建议：

- 由“分析员窗口 / 用户”管理 held-out manifest；
- 或放在实现 Agent 无法读取的 evaluator 环境；
- repo 只保存公开的 benchmark interface 和最终匿名结果。

这借鉴 Meta-Agent Challenge 的 dev/test 隔离思想，但不必复制其容器实现。

---

# 5. Evaluator 冻结制度

## 5.1 开发期间禁止 Generator 与 Judge 同时变化

每个实验周期分为两类 branch：

### E-branch：Evaluator Research

只允许修改 evaluator / rubric / judge protocol。

Generator 固定。

### G-branch：Generator Research

只允许修改 Modeling / Research / Paper pipeline。

Evaluator 固定只读。

禁止：

```text
为了让新稿 PASS
-> 同时修改 detector
-> 新稿 PASS
-> 宣称生成器提升
```

---

## 5.2 Judge 本身也要有 JudgeEval

借鉴 PaperBench：评价 Agent 的 Judge 也必须被评价。

### Judge Calibration Set

建立匿名 pair：

```text
真实 O/F/国奖论文 vs 工作站论文
真实优秀论文 A vs 较弱论文 B
工作站 Before vs After
同一 Research State 的不同 writer 输出
```

至少记录：

- human preference；
- judge preference；
- 置信度；
- 主要理由；
- 是否受论文长度/格式/文件名影响。

### Judge 指标

```text
pairwise_accuracy_vs_human
Kendall_tau / Spearman rank correlation
position_swap_consistency
anonymization_consistency
self-generated-paper bias
length/style bias
cross-model agreement
```

只有 Judge 与人类/O-F真实排序具有足够一致性，才能让它成为 V6 优化主奖励。

---

# 6. 第一个必须执行的诊断实验：Experiment 0 — Judge Validity Test

## 目标

判断当前内部评价系统是否是主要瓶颈。

## 输入

至少准备：

- 5–10 篇真实 O/F/国奖 C 题论文；
- 5–10 篇当前工作站代表性论文；
- 若有明显较早版本，再加入 3–5 篇旧稿形成质量梯度。

不要求一次就非常大，但必须覆盖：

- MCM C；
- CUMCM C；
- 不同任务结构。

## 匿名化

删除/替换：

- 文件名中的奖项；
- `Outstanding` / `O Award` / `国一` 等标签；
- 作者、学校、队号（如不影响正文）；
- 任何会泄露系统身份的 metadata。

保留正文、图表、公式、排版本身。

## Judge 组

至少三路：

1. 当前内部 evaluator；
2. 独立强模型 Judge A；
3. 独立强模型 Judge B 或第二配置；

再以用户/人工评审为 anchor。

## 评分维度

必须包括但不限于：

```text
problem insight
scientific / modeling core
modeling appropriateness
mathematical structure
problem-to-problem inheritance
experimental / validation rigor
evidence credibility
innovation / non-obviousness
story discovery / narrative progression
figure argumentative value
page / visual composition
abstract information density
contest usefulness / decision value
writing naturalness
overall award preference
```

特别要求：

> 不得把“有 sensitivity、有公式、有图、有 strengths/weaknesses”本身当成高分原因；这些只能是必要性证据，不能代替 scientific core。

## 成功标准

如果当前 evaluator：

- 无法稳定把真实 O/F/国奖论文排在当前系统论文前；或
- 与人工排序相关性低；或
- 对同一 pair 交换位置后结果明显不稳定；

则结论：

> **先修 Judge，不允许继续大规模 Generator 重构。**

## 输出

```text
artifacts/meta_benchmark/judge_v1/
  manifest.json
  anonymized/
  pairwise_results.jsonl
  ranking.csv
  judge_validity_report.md
```

---

# 7. Experiment 1 — Compiler Freedom Ablation

## 要回答的问题

> **同一份 Research State，如果减少 deterministic Paper Compiler 约束，强模型能否明显写得更像优秀竞赛论文？**

这是定位 Paper Engine / Renderer 是否压制模型能力的最关键实验。

## 控制变量

同一题：

- 相同 ProblemGraph；
- 相同 accepted solver outputs；
- 相同 EvidenceGraph；
- 相同 claims；
- 相同可用 figures；
- 相同 citation sources；
- 不允许任何路线新增未经执行的数字或实验。

只改变“从 Research State 到论文”的生成方式。

## 三条路线

### Route A — Current Compiler

```text
Research State
-> ModelStoryPlanner
-> current ResearchStatePaper renderer
-> EvidenceLockedWriter polish
```

这是 baseline。

### Route B — Free Structure Writer

给强模型：

- ProblemGraph；
- ModelGraph / EvidenceGraph；
- accepted results；
- constraints；
- available figures；
- competition profile；
- evidence rules。

但**不提供固定 section grammar**。

任务：

> 自主设计整篇论文结构和叙事，只受 evidence / competition hard rules 限制。

### Route C — Search-Based Paper Architecture

```text
Research State
-> 3 independent Story Discovery proposals
-> blind Story Judge
-> winning storyboard
-> claim-evidence matrix
-> section-by-section writer
-> whole-paper critic
-> one targeted rewrite
```

## Judge

用 Experiment 0 验证过的 frozen evaluator。

## 主要指标

```text
pairwise win rate
storyline score
modeling progression
non-template naturalness
scientific-core visibility
figure/equation rhetorical placement
human preference
```

## 判定

### 若 C > B > A 显著

说明：

> 当前 deterministic compiler / story grammar 是主要瓶颈之一。

下一步不是继续给 renderer 加规则，而是让 Story Search 成为主导层，deterministic renderer 降级为 evidence/compliance guard。

### 若 A ≈ B ≈ C

说明：

> 上游 Research State 本身不够强，Paper Engine 不是主矛盾。

进入 Experiment 2。

---

# 8. Experiment 2 — Research Architecture Diversity Test

## 要回答的问题

> 当前 ModelingBrain / ModelStructure 的研究结构是否只是“正确、完整、安全”，但缺少真正强的 scientific core？

## 原则

同一赛题，当前工作站不得先给候选答案，避免 anchoring。

建立 4–6 个独立提案者：

```text
A — Mechanistic / mathematical modeler
B — Optimization / decision researcher
C — Statistical inference researcher
D — Dynamical / probabilistic systems researcher
E — Cross-domain analogical researcher
F — Current Workstation ModelingBrain
```

注意：角色不是为了固定使用某类算法，而是强制不同建模视角。

## 每个提案必须输出统一 Contract

```text
problem interpretation
central modeling tension
unified modeling object
state / mechanism / relation / objective
subproblem inheritance
candidate mathematical structures
what the simplest model is
what evidence would justify extra complexity
required experiments
validation obligations
expected failure modes
why this architecture may be award-worthy
what would falsify it
```

禁止只列：

```text
XGBoost
LSTM
Random Forest
AHP
```

## 两阶段评审

### Stage 1 — Proposal Blind Review

不运行实验，仅评：

- problem fit；
- mathematical necessity；
- unification；
- elegance；
- non-obvious insight；
- executability；
- falsifiability。

### Stage 2 — Top-k Pilot

只对前 2–3 个架构执行最便宜的 discriminative pilot。

不允许一开始把所有路线完整做完。

## 结果

如果 Workstation 提案长期：

- 正确但排名中游；
- 模板化；
- 多题趋向相似 archetype；

则进入 Creator 重构。

---

# 9. Experiment 3 — Component Influence / Causal Ablation

以后任何“重大模块已经实现”的结论都必须回答：

> **它到底改变了最终结果多少？**

## 测试对象示例

- ModelSpine；
- ModelStructurePlanner；
- ModelStoryPlanner；
- EvidenceExpressionPlanner；
- ExcellentPaperComparator；
- FigureArtDirector；
- recurrent refinement；
- candidate consensus。

## 做法

固定题目和随机性，运行：

```text
WITH module
WITHOUT module / legacy fallback
```

比较的不只是文本 diff，而是：

```text
selected research architecture
solver choice / experiment plan
story structure
section order
figure demand
formula roles
blind paper preference
quality dimensions
```

定义概念性 influence：

```text
Influence(M) = meaningful downstream decision change
             + blind preference gain
             - regression cost
```

如果某模块：

- 代码很多；
- 测试很多；
- 但 influence 近零；

则应考虑：

> 删除、合并或降级，而不是继续维护。

V6 明确允许“删功能”。

---

# 10. Experiment 4 — Meta-Agent Development Benchmark

这是专门约束负责开发工作站的 GPT-5.6 Sol。

以后每次大改前必须先创建 `Change Hypothesis Card`。

## 10.1 Change Hypothesis Card

```yaml
id: HYP-YYYYMMDD-xxx
symptom: 用户/benchmark 观察到的实际问题
root_cause_hypothesis: 假设的最早因果节点
mechanism: 为什么该节点会产生这个症状
intervention: 本轮只改变什么
non_goals: 明确不改什么
expected_dev_effect: DEV 上具体应该出现什么变化
expected_holdout_effect: 泛化时应该出现什么变化
falsification: 什么结果出现时证明该假设不成立
metrics: 用什么指标判断
rollback: 失败后如何恢复
```

没有 Card，不得开始高层架构 coding。

---

## 10.2 一轮只允许一个 primary causal hypothesis

可以有必要的配套改动，但必须只有一个主要研究假设。

禁止：

```text
同时重写 ModelingBrain
+ Paper Engine
+ Judge
+ Figure system
+ layout
然后发现论文更好
```

因为无法知道是谁造成提升。

---

## 10.3 Feature completion != Goal completion

项目窗口禁止以下验收方式：

```text
新增文件完成
单测通过
全测通过
文档写了
Gate PASS
```

这些只能证明“工程实现完成”。

真正 Goal PASS 必须：

```text
工程测试通过
+
目标实验结果支持 hypothesis
+
blind / frozen evaluator 显示能力改善
+
没有明显 cross-problem regression
```

---

## 10.4 每次实验必须允许 REVERT

如果 falsification 条件触发：

> 不得继续围绕该模块再加 3 个补丁，试图证明方向仍然正确。

先记录：

```text
HYPOTHESIS REJECTED
```

恢复 baseline，再选择新的根因假设。

这是 V6 防止局部最优的核心纪律。

---

# 11. Experiment 5 — Version Tournament + Variance

单次生成变好不足以证明工作站提升。

## 对每个候选版本

至少在代表性题上运行多次（视成本 2–3 次），记录：

```text
mean score
pairwise win rate
variance
failure rate
run-to-run architecture diversity
paper structural diversity
```

因为 Agent 开发存在高方差。

如果：

```text
V6 mean > V5
但 variance 大幅上升
```

则不能直接 Promote。

长期目标：

> 更高的能力 + 可接受稳定性，而不是偶尔抽到一篇非常好。

---

# 12. Scientific Core 专项评价

ResearchClawBench 的重要经验是：端到端研究系统的失败不仅来自执行和 evidence，还来自 **missing scientific core**。

因此增加独立维度：

## Scientific Core Questions

每篇研究必须回答：

1. 这篇论文最核心的“建模发现/建模结构”是什么？
2. 如果删除所有图表和排版，它是否仍然有一个值得记住的思想？
3. 核心模型为什么不是教科书默认模型？
4. 哪一个观察或约束逼迫我们设计当前结构？
5. 模型复杂度的每次增加是否由实际失败证据触发？
6. 多个小问是否真的属于同一个 modeling worldview？
7. 最重要结论是否在不依赖模板字段的情况下仍可清楚讲出？
8. 与一个普通优秀本科生方案相比，非显然价值在哪里？

输出：

```text
scientific_core_summary
core_strength
core_weakness
core_evidence
core_originality
core_falsifiability
```

该维度不能用关键词 detector 作为主判据。

---

# 13. Story Discovery，而不仅是 Story Grammar

当前 `ModelStoryPlanner` 的 StoryMove 设计可以保留为 guard/prior，但 V6 必须区分：

```text
Story Grammar：优秀论文常见的叙事行为
Story Discovery：这道题、这组结果最值得讲的故事到底是什么
```

Story Discovery 应由强模型搜索 2–4 个候选，而不是 deterministic 规则一次决定。

每个 Story Proposal 包括：

```text
central tension
opening hook
model progression
where the paper intentionally slows down
where it accelerates
which result becomes the visual anchor
which equation is the conceptual centerpiece
what is inherited between questions
what is omitted from main text
ending / decision arc
```

之后由 frozen story judge 选择，再交给 evidence guard。

---

# 14. Creator 重构方向（只在 Experiment 2 证明需要后启动）

如果 Creator 是瓶颈，目标不是继续增加关键词 taxonomy，而是建立：

## 14.1 Research Route Portfolio

```text
ProblemGraph
-> N independent structural hypotheses
-> critique
-> merge / keep diverse
-> cheap pilot
-> evidence-based promotion
```

默认不追求 30 个算法，而追求 3–5 个真正不同的 mathematical worldview。

## 14.2 Architecture Before Solver

必须强制：

```text
modeling object
state / variables
mechanism / relation
objective / estimand
constraints
uncertainty
identifiability
validation obligation
```

通过后才允许选择 solver。

## 14.3 Solver 是执行器，不是模型本体

旧 `ModelPlan(regression/classification)` 不应继续作为全局研究抽象的最高层。

长期应：

```text
ModelStructure
-> Mathematical Family
-> Solver / Estimator
```

旧 ModelPlan 可以保留兼容层，但不能反向限制高层结构。

## 14.4 Search 必须包含“推翻当前 worldview”的能力

当连续 improvement 小或 critic 指出 scientific core 弱时：

禁止只做参数/表达微调。

触发：

```text
RETHINK_MODELING_WORLDVIEW
```

要求至少提出一个：

- 不同 modeled object；
- 不同 state representation；
- 不同 mechanism；
- 不同 objective；
- 不同 cross-question inheritance。

---

# 15. Paper 重构方向（只在 Experiment 1 证明需要后启动）

如果 Compiler 是瓶颈：

## 15.1 Research-State Paper 不再等于最终论文结构

Research State 是事实层。

Final Paper 是解释层。

二者关系：

```text
Research State = database / truth
Final Paper = search-selected view over truth
```

不要求每个事实字段都在固定槽位出现。

## 15.2 Outline 必须可变

competition hard rules 只规定：

- 必须交什么；
- 禁止什么；
- 页面/格式硬约束。

不规定每道题都必须出现统一子标题。

## 15.3 EvidenceLockedWriter 从“固定 canonical prose”改为“固定 canonical facts”

锁：

- 数字；
- 结论边界；
- evidence；
- citation；
- solver outcome。

不锁：

- 叙事顺序；
- 标题风格；
- 段落组织；
- 哪个结果先讲；
- 是否合并某些小节。

---

# 16. 外部研究经验，迁移原则

以下不是“照搬项目”，而是 V6 的方法论来源。

## PaperBench (OpenAI, 2025)

关键迁移：

- 复杂研究目标拆成层级 rubric；
- rubric 由真实领域专家参与设计；
- Judge 自己也有 JudgeEval；
- 不把 LLM Judge 当天然真值。

参考：arXiv:2504.01848。

## Meta-Agent Challenge (2026)

关键迁移：

- 评价“AI 开发 Agent”的能力，而非只评价目标 Agent；
- dev/test 分离；
- meta-agent 不能看到 final test；
- 防 reward hacking；
- 高方差意味着必须多次运行和 held-out 验证。

参考：arXiv:2606.04455。

## ResearchClawBench (2026)

关键迁移：

- 真实论文级 end-to-end task；
- target paper 在研究阶段隐藏；
- 专家多模态 rubric；
- 重点诊断 protocol mismatch、evidence mismatch、missing scientific core。

参考：arXiv:2606.07591。

## AARRI-Bench (2026)

关键迁移：

- 不只测宏观“有没有完成”；
- 测研究人员会注意的细微但关键判断；
- 强 scaffold 不等于真正 researcher-like behavior。

参考：arXiv:2606.07462。

## AutoResearchEval (2026)

关键迁移：

- 不只看 final score；
- 看完整轨迹；
- 建 failure taxonomy；
- 特别关注 metacognitive self-correction。

参考：arXiv:2608.14905。

## AutoResearch: Insight In, Hallucination Out (2026)

关键迁移：

- Idea Generation 与 Idea Execution 分离；
- 多模型生成 + cross-review；
- 独立 evidence review 决定 continue / revise / terminate；
- 先保证 insight grounded，再让实验接受结论。

参考：arXiv:2608.17906。

## Karpathy autoresearch

关键迁移：

- frozen evaluation environment；
- mutable research target；
- keep / discard 明确；
- program / research-org instructions 本身也是待优化对象。

不迁移：

- 单一 scalar reward 不能直接用于竞赛论文，因为 O/F 质量是多维且 reward 难以完整定义。

---

# 17. V6 执行顺序

## Phase 0 — Freeze & Snapshot

**禁止新功能开发。**

必须完成：

- 当前 git / dirty state 记录；
- 当前代表性论文归档；
- 当前 evaluator 版本 hash / config 冻结；
- 当前关键 pipeline 架构快照；
- 当前 L0/L1/L2 基线结果；
- 当前 known gaps；
- 建 `meta_benchmark/` 目录契约。

Gate：能够完全回答“V5 现在是什么”。

---

## Phase 1 — Judge Validity

执行 Experiment 0。

**在 Judge 未验证前，禁止用内部 90/100 作为 V6 reward。**

Gate：得到可用的 frozen evaluator v1，或者明确证明当前 evaluator 不可靠并进入 E-branch 修复。

---

## Phase 2 — Compiler Diagnosis

执行 Experiment 1。

Gate：明确 Paper Compiler 是否主要瓶颈。

不要先重写 Paper Engine。

---

## Phase 3 — Creator Diagnosis

执行 Experiment 2。

Gate：明确 ModelingBrain / ModelStructure 是否主要瓶颈。

不要先增加 solver 数量。

---

## Phase 4 — Influence Audit

执行 Experiment 3。

目标：识别：

- truly causal modules；
- low-influence complexity；
- legacy abstraction that should be retired。

允许删除代码。

---

## Phase 5 — Targeted Reconstruction

只根据 Phase 1–4 结果选择：

```text
Judge reconstruction
or
Creator reconstruction
or
Paper search/compiler reconstruction
or
combination in separately measurable stages
```

每个 stage 都必须有 Change Hypothesis Card。

---

## Phase 6 — Cross-Problem Version Tournament

在 DEV + VALIDATION 上：

```text
V5 baseline
vs
V6 candidate
```

同预算、多次运行、盲评。

---

## Phase 7 — Sealed Holdout

冻结 V6。

由项目实现 Agent 之外的 evaluator / 分析员触发 held-out。

只有这一阶段通过，才能说：

> “工作站整体能力得到可泛化提升。”

---

# 18. 每一轮开发的固定输出格式

项目 GPT 每轮必须生成：

```text
1. Symptom
2. Root-cause hypothesis
3. Evidence supporting the hypothesis
4. Alternative explanations considered
5. Intervention
6. Files changed
7. Engineering tests
8. DEV experiment result
9. VALIDATION result
10. Blind evaluator result
11. Regression / variance
12. Hypothesis: SUPPORTED / REJECTED / INCONCLUSIVE
13. Promote / Revert / Next experiment
```

禁止只有：

```text
做了什么
测试通过
下一步继续
```

---

# 19. 强制停止条件

出现以下任一情况，停止继续堆功能：

### Stop A — No causal evidence

新模块存在，但没有 blind / downstream improvement。

### Stop B — Dev-only improvement

DEV 上明显提高，VALIDATION 不提高或下降。

### Stop C — Evaluator drift

为了让新版本通过而需要同时放松 evaluator。

### Stop D — Patch chain

同一 hypothesis 连续两次失败后，又准备增加第三个修补模块。

此时必须：

```text
REJECT hypothesis
```

### Stop E — Architecture accumulation

新增 abstraction 与旧 abstraction 重叠，但没有 migration / deprecation plan。

### Stop F — Scientific core unchanged

论文排版、图表、语言提高，但 blind reviewer 仍认为核心建模无提升。

---

# 20. 当前阶段明确不做的事情

在 Phase 0–3 前：

- 不继续做 UI；
- 不为了“丰富能力”新增大批 solver；
- 不继续按优秀论文表面特征增加 quota；
- 不把更多关键词 detector 当成 award evaluator；
- 不为单一 2023C/Wordle 继续硬编码规则；
- 不把“最新 PDF 更漂亮”当成工作站能力提升；
- 不追求所有旧测试无条件保持旧语义，如果实验已经证明旧 abstraction 是主要瓶颈，可以设计迁移；
- 不允许 GPT 用“改动很多”替代实验结果。

---

# 21. V6 最终成功标准

真正成功不是：

- 1000 个测试；
- 20 个 planner；
- 20 张图；
- evaluator 95；
- PDF 编译成功。

而是同时满足：

## Capability

- 多种 C 题能自主产生明显不同且题意驱动的研究结构；
- scientific core 质量上升；
- Story 不再是固定槽位；
- 论文与真实 O/F/国奖的盲评差距显著缩小。

## Generalization

- DEV 改善；
- VALIDATION 改善；
- SEALED HOLDOUT 改善。

## Reliability

- 多次运行方差可接受；
- evidence / leakage / provenance 不退化；
- 不依赖题号专用规则。

## Meta-development

- GPT-5.6 Sol 的每次大改都可用 hypothesis + experiment 解释；
- 失败方向会被明确放弃，而不是无限补丁；
- evaluator 与 generator 的演化被隔离；
- 能说明“为什么这次升级有效”，而不仅是“做了哪些文件”。

---

# 22. 第一轮真正执行任务

**不要一次执行整份 V6。**

项目窗口下一步只做：

```text
Phase 0 — Freeze & Snapshot
+
Phase 1 — Judge Validity Test 的完整设计与最小可运行实现
```

暂时禁止重写 ModelingBrain / Paper Engine。

理由：

> 如果评价坐标系本身不可信，后续所有自动优化都可能继续朝错误方向收敛。

第一轮结束后，把：

- baseline snapshot；
- judge calibration set；
- judge protocol；
- pairwise result；
- validity report；
- 对 H1 的结论；

交回分析员窗口，再决定进入 Compiler Diagnosis 还是先修 Judge。

---

# 23. 给项目窗口 GPT-5.6 Sol 的核心工作原则

> **你不是被要求“继续优化项目”。你被要求像研究员一样验证：当前工作站为什么没有达到用户看到的 O/F/国奖论文水平。**
>
> 每次看到一个症状，不要立刻新增模块。先定位最早可能的因果节点，提出可证伪假设，设计只改变一个主要变量的实验，再决定是否改代码。
>
> 你的成功标准不是代码量、文件数、测试数或内部 Gate，而是 frozen external evaluation 下的真实能力提升。
>
> 如果实验否定你的方案，明确记录失败并回退。这不是失败，而是正确的研发过程。

---

# 24. 参考资料

- OpenAI PaperBench — arXiv:2504.01848
- The Meta-Agent Challenge — arXiv:2606.04455
- ResearchClawBench — arXiv:2606.07591
- AARRI-Bench — arXiv:2606.07462
- AutoResearchEval — arXiv:2608.14905
- AutoResearch: Insight In, Hallucination Out — arXiv:2608.17906
- Karpathy autoresearch — `karpathy/autoresearch`

本文件引用这些工作的**评估与研发原则**，不表示直接复制其 agent architecture。

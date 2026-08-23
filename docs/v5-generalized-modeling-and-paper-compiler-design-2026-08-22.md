# V5 设计：通用 C 题建模与论文编译器

日期：2026-08-22

## 目标

本轮优化不再围绕“2024 MCM C 怎么写得更像优秀论文”做题目级特化，而是把工作站升级为一个能够覆盖国赛、高教杯/校赛体系、华数杯、MCM/ICM 等不同竞赛 C 题的通用研究与论文编译系统。

核心目标不是追逐分类/预测准确率，而是保证：

- 题型识别正确；
- 建模对象、状态、机制、约束、概率关系和目标函数定义完整；
- 小问之间形成统一模型主线，而不是模型动物园；
- 算法是求解器，不是建模本体；
- 图、表、公式、文字按论证需要自主分配；
- 论文叙事具有优秀竞赛论文的层层推进感，同时所有复杂度增加都有证据支持；
- 正式比赛时允许工作人员在少量关键节点做方向裁决，但当前重构阶段不强制启用人工 loop。

---

## 1. 先拆开两个当前混在一起的概念

### 1.1 Competition Profile：只决定“比赛怎么交”

Competition Profile 负责：

- 语言；
- 页面尺寸与页边距；
- 摘要 / Summary Sheet；
- 目录；
- Memo / Letter；
- 参考文献格式；
- AI Use Report；
- 页数上限；
- 官方格式硬约束。

它不决定模型。

当前 `CProblemPaperProfileRegistry` 只区分 `MCM_C / CUMCM_C`，V5 应扩展为可注册的 competition profile，而不是把其它杯赛硬塞进 CUMCM profile。

建议接口：

```text
CompetitionProfile
- competition_id
- language
- page_size
- hard_format_rules
- required_front_matter
- required_back_matter
- deliverable_rules
- official_source
```

### 1.2 Modeling Profile：决定“这道题本质上是什么”

Modeling Profile 与比赛名称无关，按题目语义和数据/约束结构识别。

例如同样是 C 题，可能是：

- 描述与规律发现；
- 机制解释；
- 动态系统 / 状态演化；
- 概率图 / 隐状态；
- 预测；
- 优化决策；
- 排序评价；
- 仿真；
- 网络 / 图模型；
- 空间 / 几何；
- 组合调度；
- 风险 / 生存 / hazard；
- 多阶段混合题。

建模 profile 决定 research obligations、候选模型结构、验证协议与论文表达义务。

---

## 2. 新增 Problem Type Analyzer：题型必须先识别，再建模

新增逻辑层：

```text
Problem PDF / Statement / Data Dictionary
        ↓
Problem Semantic Analyzer
        ↓
Problem Type Analyzer
        ↓
ProblemGraph + ModelingProfile per node
```

不要单标签分类。每个 subproblem 可有多个 modeling facets，例如：

```text
SP3:
primary = dynamic_state_prediction
secondary = probabilistic_graphical_model
constraints = real_time_observability
validation = grouped_temporal_transfer
```

### 建议的第一版 taxonomy

```text
DESCRIPTIVE_STRUCTURE
EXPLANATORY_MECHANISM
PROBABILISTIC_STATE
DYNAMIC_SYSTEM
CHANGE_POINT_REGIME
FORECASTING
HAZARD_SURVIVAL
OPTIMIZATION
SIMULATION
RANKING_EVALUATION
NETWORK_GRAPH
SPATIAL_GEOMETRIC
COMBINATORIAL_SCHEDULING
UNCERTAINTY_DECISION
SYNTHESIS_DELIVERABLE
```

这套 taxonomy 不能决定具体算法，只定义“研究对象是什么”。

---

## 3. ModelingBrain V2：从“模型名选择器”改成“结构建模器”

### 当前根本问题

当前 `ModelPlan` 主要是：

```text
regression / classification
→ linear / ridge / random forest / gradient boosting
→ metric
```

这会天然把数学建模压扁成监督学习。

### V5 的 Model Structure Contract

在选择算法之前，ModelingBrain 必须产出一个 `ModelStructurePlan`：

```text
ModelStructurePlan
- modeled_entities        # 建模对象
- state_variables         # 状态变量
- observed_variables      # 可观测变量
- latent_variables        # 隐变量
- control_variables       # 决策变量
- parameters              # 参数
- mechanisms              # 关系 / 转移 / 作用机制
- constraints             # 约束
- uncertainty_sources     # 不确定性
- objective               # 目标 / 解释目标
- temporal_structure      # 时间结构
- spatial_structure       # 空间结构
- dependency_structure    # 变量依赖
- inheritance             # 从前问继承什么
- identifiability_notes   # 哪些量能否从数据识别
- solver_requirements     # 最后才映射求解器
- validation_obligations
```

只有这个结构通过检查，才进入：

```text
Model Structure
→ candidate mathematical families
→ executable solver / algorithm
```

### 算法与模型的关系

例如 2024 MCM C：

```text
模型本体：
Serve-conditioned stochastic flow
+ latent performance state
+ temporal transition / swing hazard

求解器可以是：
Bayesian network / HMM / filtering / RF / optimization / MCMC
```

因此 RF 不应该成为论文主角；它最多是某一个估计器或对照求解器。

---

## 4. 统一框架优先：各小问应是同一系统的不同投影

用户偏好：

> 先搭建统一框架，各问只是框架的不同使用方式。

因此 V5 新增 `UnifiedModelFrameworkPlanner`。

它在 ProblemGraph 上方建立一个全题 Modeling System：

```text
Domain / Entities
        ↓
State Representation
        ↓
Mechanism / Transition Law
        ↓
Observation Layer
        ↓
Inference / Estimation
        ↓
Decision / Prediction Layer
        ↓
Validation / Sensitivity
```

之后每个 subproblem 只回答：

```text
本问使用框架中的哪一层？
新增什么？
继承什么？
验证什么？
输出什么？
```

### 理想例子：2024 MCM C

不是：

```text
Q1 rolling mean
Q2 hypothesis test
Q3 random forest
Q4 generalization
```

而是：

```text
Unified Probabilistic Flow Framework

Serve-adjusted observation layer
        ↓
Latent / probabilistic performance state
        ↓
State transition / regime change
        ↓
Swing-risk inference
        ↓
Transfer/generalization
```

Q1 定义观察层与状态；
Q2 检验状态是否具有超出 serve baseline 的依赖；
Q3 对状态转移建概率模型；
Q4 检查同一框架跨比赛/场景是否成立。

2024 可以优先探索 Bayesian / probabilistic graphical structure，但这是由题目结构推导出的候选，不应写成全局硬规则。

---

## 5. 建模深度评分不能再奖励“模型数量”

建议新增 `ModelingDepthReviewer`，评估：

### 5.1 Structure completeness

是否明确：

- 对象；
- 状态；
- 输入；
- 输出；
- 参数；
- 机制；
- 约束；
- 不确定性。

### 5.2 Mathematical necessity

每一个公式是否回答以下至少一个问题：

- 定义状态；
- 定义机制；
- 定义概率；
- 定义约束；
- 定义目标；
- 定义转移；
- 定义估计；
- 定义验证。

禁止为了“公式多”把普通数字包装成公式。

### 5.3 Progressive modeling

是否存在：

```text
simple baseline
→ evidence of insufficiency / new requirement
→ necessary structural extension
→ validation
```

复杂度不能因为“优秀论文看起来复杂”而增加。

### 5.4 Unified inheritance

后问是否显式继承前问模型、参数、状态或证据。

### 5.5 Claim calibration

模型结论强度是否超过验证证据。

---

## 6. Evidence Expression Planner：图、表、公式、文字不再独立规划

当前缺陷之一是图表系统主要在“已有图中做美化”，而不是先判断“这一段应该用什么媒介表达”。

V5 新增统一表达规划器：

```text
Argument / Evidence
        ↓
EvidenceExpressionPlanner
        ↓
TEXT | EQUATION | FIGURE | TABLE | PANEL | ALGORITHM | DEFINITION
```

### 6.1 选择图的条件

优先 Figure：

- 趋势 / 时间变化；
- 分布；
- 多变量关系；
- 状态变化；
- 模型结构；
- 流程；
- 空间关系；
- 网络；
- 敏感性；
- 对比形态；
- 不确定性范围；
- 需要“一眼理解”的复杂关系。

### 6.2 选择表的条件

优先 Table：

- 需要逐项复核的精确数值；
- 参数估计；
- 最终方案；
- 多对象精确比较；
- 决策清单；
- 约束汇总；
- 模型假设和符号（视比赛风格决定）。

### 6.3 选择公式的条件

优先 Equation：

- 新定义；
- 状态转移；
- 概率分解；
- 目标函数；
- 约束；
- 估计量；
- 机制关系。

### 6.4 选择纯文字的条件

优先 Text：

- 解释动机；
- 解释为什么不用更复杂模型；
- 解释限制；
- 解释结果含义；
- 桥接前后小问。

### 6.5 Panel 规则

不是每张图都全宽。

如果两张图：

- 同一证据问题；
- 共享尺度；
- 需要并列比较；

则优先形成 multi-panel。

如果两个图承担完全不同论证，不强制拼图。

### 禁止图数量 quota

不得出现：

```text
min_figures = 10
ideal_figures = 20
```

系统只能根据“未被充分表达的 argument/evidence”产生 figure demand。

优秀论文 10–20 图只作为结果分布先验，不是目标函数。

---

## 7. Figure Demand Planner：解决“图少、种类少、没有流程图”

建议 Figure Demand 类型：

### Orientation

- background/context reality visual
- Our Work / research workflow
- unified model framework

### Model explanation

- mechanism diagram
- probabilistic graphical model
- state-transition diagram
- optimization structure
- simulation architecture

### Data understanding

- distribution
- temporal evolution
- spatial map
- correlation / dependence
- cluster / regime view

### Evidence

- main result curve
- scenario comparison
- residual diagnostics
- null distribution
- uncertainty interval
- sensitivity
- robustness

### Decision

- policy map
- decision frontier
- trade-off/Pareto
- ranked recommendation

### Validation

- transfer/generalization
- calibration
- error structure
- stability across parameters

系统按 Story/ModelStructure 产生“需求”，FigureArtDirector 才负责画法、配色、布局。

当前 MCM 配色保留为正向资产，不回退。

---

## 8. 数学表达与排版：解决 `0.6731` 这种裸数字

裸数字本身不是错误，问题是：数字在论文中的语义角色没有被识别。

V5 增加 `MathematicalExpressionPlanner`。

### 数字角色

#### MODEL_PARAMETER

如 server win probability：

应呈现：

```text
\hat p_s = \frac{N_{server\ wins}}{N_{points}} = 0.6731.
```

随后一句解释：

> Thus, nearly two thirds of points are structurally advantaged by service, so raw winning streaks cannot be interpreted as momentum directly.

#### RESULT_SCALAR

如 AUC、objective value：

若是单个结果，写入结果句；若多个模型/场景并列，进入表格。

#### THRESHOLD

应在定义式中出现，并解释选择依据。

#### INPUT_CONSTANT

若来自题目/文献，必须有来源；不应单独成为“大公式”。

### 公式密度规则

公式数量不设 quota。

但每个核心模型 section 至少应回答：

- What is the state?
- What is the governing relation?
- What is being estimated / optimized / inferred?
- What constraints or probability law apply?

如果一个“模型章节”完全回答不了这些问题，说明建模结构不够完整，而不是简单地“再塞公式”。

---

## 9. PaperLayoutIR V2

当前 IR 已能区分 heading / paragraph / figure / table / display math。

V5 建议增加：

```text
DefinitionBlock
ModelBlock
EquationGroup
AlgorithmBlock
FigurePanel
ResultBlock
AssumptionBlock
RemarkBlock
MemoBlock
```

并允许 Expression Planner 为每个 block 附：

```text
importance
argument_role
preferred_width
keep_with_next
keep_with_evidence
pair_group
page_break_penalty
```

这样 PDF reviewer 的 repair 可以定位到 block，而不是只告诉 renderer “第 8 页太空”。

---

## 10. 工作人员偏好问卷：正式生成论文前先问几个问题

这是一个新的 `ResearchPreferenceInterview`，但不是每次固定问 8 个问题。

### 原则

系统先自行分析题目，然后只对真正影响研究方向的歧义提问。

例如：

```text
1. 更偏机制解释 / 决策 / 预测 / 综合？
2. 结论风险偏好：保守 / 适度增强 / 激进？
3. 是否偏好统一框架还是多模型比较？
4. 在性能、可解释性、数学结构感之间更重视什么？
5. 泛化分析是否需要重点展开？
6. 哪种优秀论文观感更符合团队偏好？
```

### 当前默认偏好（来自本轮设计讨论）

```text
conclusion_posture = MODERATELY_STRONG
modeling_priority = MATHEMATICAL_STRUCTURE
framework_preference = UNIFIED_FRAMEWORK
paper_style = OUTSTANDING_PAPER_WITH_RIGOR
visual_priority = HIGH
重点 = 模型结构图 + 图表丰富度 + 小问继承 + robustness/sensitivity
prediction_metric_priority = LOW_TO_MEDIUM
```

这些是“用户/团队偏好”，不得突破 Evidence Gate。

---

## 11. Human-in-the-loop：现在预留，正式比赛再开启

当前重构阶段：

```text
human_loop_mode = OFF
```

但接口提前存在。

建议四个可选 checkpoint：

### H1 — Problem Interpretation Review

检查：题型、ProblemGraph、小问依赖是否理解正确。

### H2 — Modeling Direction Review

展示 2–4 个不同“结构建模路线”，工作人员选择倾向。

注意：不是问“用 RF 还是 XGBoost”，而是：

```text
概率状态模型
vs
动力系统/变化点
vs
机制 + 优化
```

### H3 — Evidence / Story Review

展示模型主线、关键结论、图表规划，人工决定是否更强调某个论证方向。

### H4 — Final Paper Review

基于 PDF contact sheet 和 reviewer findings 做最后排版/叙事裁决。

正式比赛建议每个 checkpoint 最多一次，不把工作站变成人工问答机。

### 裁决规则

Human preference 可以：

- 调整 candidate priority；
- 调整 exposition emphasis；
- 调整 figure/story priority。

Human preference 不能：

- 把未执行模型写成已执行；
- 修改 Solver 数值；
- 绕过 leakage/validation gate；
- 让无来源图片进入正式论文。

---

## 12. 2024 MCM C 下一版应该怎么变

2024 仅作为 V5 第一个验证实例，不做专用规则。

### 保留

- serve-adjusted baseline；
- 保守但有力的统计结论；
- 当前配色；
- grouped match holdout；
- Whole-PDF reviewer。

### 升级

#### Unified probabilistic framework

从当前：

```text
Flow Score
→ tests
→ RF hazard
```

升级为候选结构：

```text
Observed point outcome
        ↓
Serve-conditioned baseline
        ↓
Latent / probabilistic performance state
        ↓
State transition / swing probability
        ↓
Observed tactical/physical factors
        ↓
Coach-facing risk inference
```

Bayesian graphical model / dynamic Bayesian network 可进入 ModelingBrain 候选，并与 simpler state-transition model 比较结构必要性。

### 图表需求预期（不是 quota）

V5 planner 很可能自主产生：

- Background / Wimbledon context visual（如来源许可安全）；
- Our Work flowchart；
- unified probabilistic framework diagram；
- final match flow；
- set-level flow comparison；
- null simulation distribution；
- per-match test overview；
- latent/state transition diagram；
- swing-risk factor relation；
- feature/parameter effect figure；
- transfer/holdout diagnostic；
- sensitivity/robustness；
- coach decision schematic。

是否全部生成取决于 evidence demand；不强制数量。

---

## 13. 推荐实施顺序

### V5-A — Research Preference + Problem Type

新增：

```text
research_preferences.py
problem_type_analyzer.py
modeling_profile.py
```

先让系统知道“题是什么、团队偏好什么”。

### V5-B — Model Structure Layer

新增：

```text
model_structure.py
unified_model_framework.py
modeling_depth_review.py
```

这是优先级最高的建模升级。

### V5-C — Expression Planning

新增：

```text
evidence_expression.py
figure_demand.py
mathematical_expression.py
```

解决图少、类型少、表/图/公式选择僵硬和裸数字问题。

### V5-D — PaperLayoutIR V2

扩展 block 类型和页面 repair target。

### V5-E — Human Loop Contract

只实现 contract/state，不默认启动：

```text
human_review_checkpoint.py
human_loop_policy.py
```

### V5-F — Validation

至少用不同类型 C 题做跨题回归：

```text
2024 MCM C         概率/动态/预测
2023 CUMCM C       统计关系 + 优化决策
2010 CUMCM C       几何/优化
2023 MCM C Wordle  离散/概率/评价/交付
再补一个华数杯/其它杯赛 C 题
```

只有不同题型仍能产生不同 ModelStructure、不同图表需求和不同论文叙事，才算泛化成功。

---

## 14. V5 成功标准

不使用“图不少于 N 张”“公式不少于 N 个”“模型不少于 N 个”作为成功标准。

真正的 Gate：

1. **Problem-Type Gate**：每个 subproblem 的 modeling facets 能解释题意。
2. **Model-Structure Gate**：核心模型具有完整对象、状态、机制、约束/概率/目标定义。
3. **Unified-Framework Gate**：小问继承关系真实存在，不是模型动物园。
4. **Evidence Gate**：论文中的每个定量结论均可追溯。
5. **Expression Gate**：关键 argument 选择了合适的 text/equation/figure/table 载体。
6. **Figure Gate**：没有装饰性 quota 图；每张图有明确论证作用。
7. **Mathematical Writing Gate**：核心参数、状态和关系在数学语境中定义，不出现突兀裸数字或“只有算法没有模型”。
8. **Validation Gate**：验证协议与模型 claim 类型匹配。
9. **Layout Gate**：PDF 整页布局无空洞页、图表失衡、孤立标题、突兀公式/数字。
10. **Human Preference Gate（正式比赛可选）**：工作人员偏好已记录，但没有覆盖研究硬门。

---

## 最终设计原则

一句话：

> **先理解题，再设计数学结构；先设计数学结构，再选算法；先决定论证需要什么表达，再决定画多少图、做多少表、写多少公式。**

优秀论文的“图多、公式多、模型丰富”应当是完整研究结构自然产生的结果，而不是目标本身。

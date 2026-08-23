# Section 7 阶段总结 — C题专精能力地图与首个国赛真实 Gate

日期：2026-08-20

## 当前结论

项目已经从“搭研究/论文框架”进入“用真实 C 题和优秀论文反向审判工作站”的阶段。

当前正式 benchmark 已冻结为 **5 道 C 题 / 21 篇优秀论文**：

- CUMCM 2010 C — 输油管布置 — 3 篇可解析优秀论文
- CUMCM 2018 C — 大型百货商场会员画像 — 3 篇
- CUMCM 2023 C — 蔬菜自动定价与补货 — 4 篇
- MCM 2018 C — Energy Compact — 5 篇 O 奖
- MCM 2023 C — Wordle — 6 篇 O 奖

Goal 7.0–7.3 已完成：本地资料库地图、C-only excellent corpus、C-Problem Modeling Priors、MCM-C/CUMCM-C 双 Paper Profile 已进入运行时。

Goal 7.4 已开始，CUMCM 2010 C 的真实研究 Gate 已跑通；2018 C 与 2023 C 尚未完成端到端 Gate。

---

## 五题能力地图：当前可以安全泛化的 7 条 C-Problem Priors

### 1. 先做题意专属表示，再选通用算法

优秀 C 题首先定义真正属于问题的变量、状态、指标、几何对象或领域构造：

- 2010 C：几何点、管段、区域费用与共享段；
- 2018 C：RFM/RFMS/FMS、会员状态、生命周期；
- 2023 C：需求/价格/补货/损耗/组合约束；
- Energy：energy profile；
- Wordle：词特征、游戏/热度机制。

因此 ModelingBrain 不应从“模型名列表”开始，而应先问：赛题真正需要什么状态表示。

### 2. 小问必须形成 Research State 链，不是独立 model zoo

有依赖的后续小问应复用、扩展或质疑前问结果。

当前系统已经把这一点做成 ProblemGraph dependency + ModelingBrain obligation，而不是只写在提示词里。

### 3. 模型选择必须由数据、机理或约束驱动

五题优秀论文里的具体算法高度分散。同题也可能分别使用 ARIMA、LSTM、VAR、Grey、MCMC、SA、PSO、TOPSIS、GPR 等。

因此 corpus 频率只能给候选线索，不能成为模型 PASS 或 selected 的理由；SolverRegistry 仍是可执行性真源。

### 4. 高可见位置必须给真正答案

摘要、结论、表格等高可见位置应出现真实数值/策略结果，而不是只讲“建立了某模型、效果良好”。

### 5. Validation 必须与 claim family 对齐

预测、分类、排序、优化、解释、仿真使用不同验证协议；不能统一塞一个 RMSE/准确率段落。

### 6. 算法多样性本身是正常现象

优秀论文的稳定共性是研究行为，而不是同一个算法。当前系统明确禁止“优秀论文常用 X，所以我们必须用 X”。

### 7. 决策与交付物必须处于 evidence 下游

路线、补货、定价、目标、memo、letter 都只能综合 accepted evidence；Paper Engine 不得在写作阶段补造数字或政策目标。

机器定义：`config/ref_models/c_problem_excellent_benchmark_v1.json`

---

## 当前主要能力在哪里

### A. Research architecture 已经比较强

现有主链：

ProblemGraph -> ModelingBrain -> SolverRegistry -> ValidationProtocol -> Evidence -> ModelGraph/EvidenceGraph/NarrativeGraph -> Paper -> Auditor -> Repair Router

真实能力包括：

- 多小问依赖关系；
- per-subproblem solver / validation；
- accepted evidence 才能进入论文；
- research defect 可回到精确 subproblem / phase；
- recurrent repair 不会因为 aggregate score 不涨就误判；
- MCM/CUMCM 共享研究真源、分离文档 profile。

### B. Solver/Validation 已经能支撑多类真实 C题，但覆盖面还不完整

已真实验证：

- Wordle：temporal forecasting / distribution / classification / feature ablation / comparison；
- Energy：panel profile / MCDM / panel trend / Holt forecast / LP targets；
- 2010 C：continuous geometric pipeline-layout optimization + constraint feasibility + surcharge sensitivity + no-shared scenario comparison。

2010 C 实际结果复现到约：

- Q2 objective = 282.6973 万元；station x ≈ 5.449；
- Q3 objective = 251.9685 万元；
- no-shared objective ≈ 251.9755 万元；
- shared segment nominal advantage 仅约 0.007 万元。

### C. Paper provenance 比旧系统强很多

当前论文的公式、表、数值、validation、limitation 都来自 accepted Research State；不会再为了“论文像论文”直接补造实验结果。

MCM-C / CUMCM-C 已有独立标题、摘要/summary 与文档结构 profile。

---

## 当前问题在哪里

### 1. 最大问题已经从“能不能做题”转成“能不能写得像优秀论文”

2010 C 当前真实 draft 没有 BLOCK，但 CompetitionPaperAuditor = REVIEW。

最明显的问题：

- 摘要仍有程序语言，如 `reported values include`、`accepted Research State`；
- 方法名 `pipeline layout continuous` 直接暴露内部 registry 命名，不像论文方法名称；
- 中文正文混有大量英文 assumptions / metric labels；
- “候选方案审查”把 SolverRegistry capability 直接写给读者，这是内部研究记录，不应原样进入竞赛正文；
- 数据章节对本题这种几何题显得机械，出现“当前 Solver 证据未登记更多预处理步骤”这种系统说明；
- 图标题出现错误语义污染，例如 pipeline 题的图 caption 仍叫 `Optimized compact target levels`；
- 表格中 `objective value` 重复；解释列仍是 `accepted question-level evidence`，属于内部 provenance 语言；
- 结果解释过于通用，离“工程设计论文”的自然分析还有明显距离；
- 现实背景/动机、模型之间的自然过渡、工程含义不足；
- 领域参考文献仍薄，目前 2010 C 只有优化方法论文，没有油管/工程背景文献。

### 2. ExcellentReadiness 仍混着旧 excellent_c7 summary prior

当前 2010 C readiness 仍同时读取早期 extracted-summary prior，因此报告：

- `full_text_excellent_paper_benchmark = UNVERIFIED`

但 Section 7.1 已经建立新的 C-only full-text registry。后续应把 readiness 的 excellent-paper truth source 升级到新的 C-problem benchmark，避免新旧 benchmark 双轨造成错误状态。

### 3. Alternative comparison 语义仍可能过宽

2010 C 当前 ModelingBrain 把 generic linear/integer programming 记为 PASS alternative，并因此触发 empirical comparison obligation。

这说明“Solver 有插件”仍不等于“对当前几何问题是语义上可比较的 executable alternative”。下一步需要增加 **input/representation/protocol compatibility**，不能只按 task family + alias 判断。

### 4. Solver Gold set 仍明显不够

2010 C 已暴露 nonlinear/dynamic 相关 solver depth；2018 C 和 2023 C 很可能继续暴露：

- lifecycle/state-transition；
- association/market-basket；
- richer time-series forecasting；
- constrained replenishment/pricing optimization；
- multi-objective / stochastic / robust optimization；
- clustering/scoring stability 等。

正确做法仍是由真实 C题 Gate 暴露再补，不提前堆算法。

### 5. Visual / PDF / human review 还没有完成

目前只完成 text/document profile separation。

尚未完成：

- PDF 页级排版/图表视觉 benchmark；
- blind/human competition review；
- 最终 submission package。

### 6. MCM deep-schema parity 还有技术债

五题已经在问题级 registry 中统一，但 3 个 CUMCM corpus 使用 richer deep schema，2 个 MCM anchor 仍沿用 Section 6 的旧 full-text schema。尝试逐篇重抽 MCM 时，外部 PDF 解析超过 DevSpace 60–120 秒调用窗口。

该问题不影响当前 7 条 shared priors，但在进入最终 corpus analytics 前应完成 schema migration/cache，避免长期维护两套派生格式。

---

## 对当前 2010 C 论文的阶段评价

研究真实性/证据锁：8.5/10

题目求解与数值复现：8/10

验证与边界意识：8/10

论文结构完整性：7/10

自然论文语言：4.5/10

国赛优秀论文呈现感：约 5/10

视觉/排版：尚未验证

结论：它已经从“AI 模板论文”进化成“研究证据真实、结构正确的工程化草稿”，但**还不是值得直接交给评委的国奖论文**。目前最明显短板已从 research truth 转向 narrative/presentation + solver coverage。

---

## 下一步计划

### 7.4A — 先利用 2010 C 暴露的问题修一轮通用层

优先修：

1. Paper renderer internal-language leakage；
2. task-aware section suppression（没有数据预处理就不机械生成空数据章节）；
3. semantic figure captions；
4. table dedup / human-readable metric labels；
5. domain bibliography；
6. alternative feasibility = solver availability + semantic compatibility；
7. readiness 切换到 C-only full-text benchmark truth source。

这些都是通用修复，不为 2010 C 写特例。

### 7.4B — 再跑 CUMCM 2018 C

重点检验：数据预处理、会员领域表示、状态/lifecycle、关联、评价/分类、业务决策。

### 7.4C — 再跑 CUMCM 2023 C

重点检验：EDA -> forecast -> pricing/replenishment -> constrained optimization 全链路，以及 uncertainty/sensitivity。

三道 CUMCM C 全部完成后，再形成 Goal 7.4 final capability gap map。

### 7.5 — Human Review

等内部修到“值得人看”的版本，再由用户实际审一篇。届时提供专门审阅清单，不让用户检查内部代码问题。

之后才进入视觉/PDF和 Competition Delivery。

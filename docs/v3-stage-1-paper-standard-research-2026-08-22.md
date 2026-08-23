# V3 第一阶段：比赛论文标准重建与持续调研基线

日期：2026-08-22  
状态：第一轮调研完成，作为 V3 后续图表、版式、建模重构的基线；后续每个阶段必须再次刷新本文件中的外部依据与本地优秀论文先验。

## 1. 为什么先重建“标准”

当前工作站已经能够从真实 C 题研究状态生成 LaTeX/PDF，但最近一次人工审阅暴露出的核心问题并不是“缺少一个图表模板”，而是系统缺少稳定的比赛论文判断标准：

- 图形会画，但图形语言单一，容易退化为科研蓝 + 柱状图/折线图；
- 流程图已从简单 Graphviz 盒图进步，但还没有达到优秀建模论文中“技术路线图 / 问题链图 / 机理图”的层级；
- 论文版式已经明显变整齐，但不能把“习惯模板”误写成“官方强制标准”；
- 建模部分仍有 AI 常见倾向：每一问都尝试新模型，导致核心建模点出现太晚、公式过多、模型主线不够醒目；
- 当前优秀论文 comparator 统计很多，但需要明确区分：官方硬规则、优秀论文软先验、任务特定证据，三者不能混为一个分数。

V3 第一阶段的目标因此不是增加功能，而是先形成一份可执行的 `Competition Paper Standard`。

---

## 2. 本阶段采用“三源循环”，以后每个阶段重复一次

每一个 V3 阶段都必须执行下面的研究刷新，而不是一次性调研后永久沿用：

```text
A. 本地资料库 / 优秀论文派生先验
        ↓
B. 当年官方规则 / 评阅规则刷新
        ↓
C. GitHub 成熟科研智能体 / 论文自动化系统代码机制调研
        ↓
D. 写“偏差备忘录”：现有工作站哪里与新证据冲突
        ↓
E. 微调下一阶段设计
        ↓
F. 实现 + 真实赛题 Gate
        ↓
G. 再回到 A/B/C
```

这意味着后续不会出现“计划一旦写完就机械执行到底”的模式。

### 每阶段至少保留三类来源

1. **Primary / Hard**：CUMCM / COMAP 当年官方规则、提交要求、AI 使用规定；
2. **Empirical / Soft**：用户本地优秀 C 题论文库及派生统计；
3. **Engineering / Borrow**：成熟 GitHub 研究智能体、自动实验、论文生成系统中的可复用机制。

任何一个来源单独都不能决定系统设计。

---

## 3. 2026 官方规则：先纠正一个重要误区

### 3.1 CUMCM 2026 是“硬约束少、自由排版多”

2026 年《全国大学生数学建模竞赛论文格式规范》明确：

- A4；上下左右页边距至少 2.5 cm；
- 摘要专用页原则上不超过 1 页，含标题和关键词；
- 纸质版第一页为承诺书、第二页为编号专用页、第三页为摘要专用页，正文从第四页开始，**不要目录**，正文不超过 30 页；
- 电子版不包含承诺书和编号专用页，因此电子论文第一页必须直接是摘要专用页，正文紧随摘要页之后；
- 正文之后附录页数不限；
- 附录应包含支撑材料文件列表、完整可运行源程序等；
- 正文/摘要/附录不能出现队员、学校、赛区身份信息；
- 公开资料必须规范引用；
- 电子论文 PDF 或 Word，建议 PDF，不超过 20 MB；支撑材料压缩包不超过 20 MB；
- **字号、字体、行距、颜色等，官方没有统一要求。**

这直接修正此前“国赛官方统一字体”的错误方向。

### 第一阶段设计修正

以后 `CUMCM_C` 不再把某个字体、某个标题字号冒充成“官方硬标准”。

我们把标准拆成两层：

```text
CUMCM HARD RULES
= A4 / margin / page / no TOC / anonymity / references / support files / runnable code

CUMCM STYLE PROFILE
= 从优秀论文与保守中文科技论文习惯中学习的字体、字号、图表、留白、标题层级
```

后者可以优化，前者不能违反。

### 3.2 CUMCM 2026 AI 使用规则必须进入工作站交付层

2026 试行规则已经明确覆盖大模型、生成式 AI、代码辅助工具和 AI agents：

- 可以使用 AI，但核心建模分析应主要由队伍主导；
- AI 生成内容需要人工逐项审核、验证；
- 参考文献前加入“AI 工具使用声明”；
- 使用 AI 时，支撑材料必须附 `Details of AI Tool Usage.pdf`；
- 记录工具名称/版本、使用阶段、主要提示方式、采用/人工修改/验证情况；
- 隐瞒 AI 使用，或把未经人工核验的 AI 内容作为核心建模结果，会产生严重竞赛风险。

因此工作站的 AI ledger 不能只是工程日志，最终应能自动生成官方要求的声明和使用说明草稿，并保留人工确认 Gate。

### 3.3 MCM/ICM 2026 与 CUMCM 必须分开处理

COMAP 2026 要求：

- 仅提交英文 PDF；
- 至少 12-point 可读字体；
- 总页数上限 25 页；
- 25 页包含 Summary Sheet、正文、参考文献、目录、附录、代码和题目特定要求；
- Summary Sheet 是第一页；
- PDF 小于 25 MB；
- 不能出现队员/学校身份信息；
- COMAP 明确强调 Summary 对评委很重要；
- 使用生成式 AI 时需要按 COMAP AI policy 提交 AI Use Report（规则说明中注明 AI report 不计入题面指定的 25 页上限时，应以当年具体 problem PDF / policy 为准）。

结论：`MCM_C` 和 `CUMCM_C` 必须继续作为两个独立 paper profile，不能统一为一个“比赛模板”。

---

## 4. 本地优秀 C 题资料：这次真正改变了什么

当前仓库保存的是外部资料库的 derived priors，原始资产仍位于：

`D:\作业\竞赛\大学生数学建模\美赛\备赛\资料`

知识库登记快照中包括约 867 个“论文”类文件，MCM O 奖全文、CUMCM 优秀论文、历年题目、课程资料、数学建模模型库和 Skill 包均已登记。当前仓库 distilled bank 已对大量本地论文进行文本/视觉派生分析。

### 4.1 现代 MCM C：图不是“装饰”，而是论证链

`competition:MCM:modern` 当前覆盖 217 篇，144 篇有可用文本，73 篇为 visual-only。派生先验显示现代 MCM 论文中常见的 figure purpose 包括：

- data distribution：约 52%；
- sensitivity / uncertainty：约 37%；
- result comparison：约 32%；
- time series / trend：约 31%；
- workflow / framework：约 22%。

因此第二阶段不会再使用“柱状图 + 折线图满足图数量”的思路，而要以 **figure purpose router** 选择热力图、分布图、残差图、等高线、响应面、灵敏度图、方案比较图、结构/机理图等。

### 4.2 现代 CUMCM：当前视觉统计不能被机械当作硬阈值

`competition:CUMCM:modern` 当前登记 37 篇，但只有 14 篇文本解析较好，23 篇依赖视觉/扫描页路径。已有 `modern_competition_paper_prior_v1.json` 已明确指出 2024–2025 一批国赛优秀论文文本层不可靠。

因此：

- “多少张图 / 多少页 / 多少参考文献”不作为硬门槛；
- scanned PDF 提取出的页数、图片数量等不稳定统计不能直接驱动评分；
- 用户刚提供的优秀流程图截图作为 Stage 2 的高价值视觉参考，由人工定义布局模式，不让 OCR/文本统计替代视觉判断。

### 4.3 2023 C 题的关键不是算法多，而是链条统一

本地 2023 C 四篇优秀论文的算法序列差异非常大，包括 Spearman、拟合、时间序列、ARIMA、模拟退火、动态规划、VAR、Monte Carlo、PSO、非线性规划、LSTM、Apriori 等。

但现有深度 profile 的共同结论是：

> 四篇论文都把统计需求分析连接到预测，再连接到有约束的定价/补货决策；真正重复出现的是研究链，而不是某个固定算法。

这与本轮人工反馈完全一致：以后不以“更多复杂模型”作为强度，而以模型链是否清楚、前后问题是否继承、核心模型是否醒目作为强度。

---

## 5. 建模标准 V3：从“每题一个模型”改为“核心模型 + 继承式扩展”

这一条从现在起升为高优先级规则。

### 5.1 新的默认结构

对 3–4 问的典型 C 题，默认先尝试：

```text
Q1  数据结构 / 规律 / 指标 / 关系识别
       ↓ evidence
Q2  核心数学模型
       ↓ accepted model state
Q3  在 Q2 上加约束 / 改场景 / 改粒度 / 改目标
       ↓
Q4  决策 / 鲁棒性 / 灵敏度 / 建议 / 交付物
```

这只是优先结构，不是死模板；如果题目语义证明各问独立，ProblemGraph 仍允许分支。

### 5.2 新增“新模型举证责任”

后续小问如果想引入全新算法，必须回答至少一个问题：

- 前一模型在哪个数据特性上明确失效？
- 新小问新增了什么前一模型无法表达的状态/变量/约束？
- 新模型是否只是为了“显得高级”？
- 能不能通过参数更新、约束扩展、目标函数变化、情景分支解决？

如果后三者可以解决，则优先沿用核心模型。

### 5.3 传统模型优先，不做复杂度竞赛

工作站默认候选排序从“模型新颖度”改为：

```text
题意匹配
> 数据支持
> 可解释 / 可验证
> 约束表达能力
> 稳健性
> 计算成本
> 复杂度 / 新颖度
```

典型线性/非线性回归、相关/统计检验、聚类、PCA、ARIMA/指数平滑、LP/MILP/NLP、图模型、Markov、Monte Carlo、层次分析/评价、差分/微分模型等都应该能作为核心方案；只有任务证据需要时才升级复杂度。

---

## 6. 公式标准 V3：从“会推导”改成“十秒看见建模点”

后续 Paper Engine 使用 `Formula Budget`：

### A 级：核心建模公式，正文必须出现

- 关键变量定义；
- 目标函数；
- 核心关系式 / 状态转移；
- 关键约束；
- 必要的核心估计/求解规则。

### B 级：标准方法公式，按解释需要决定

例如 RMSE、普通 z-score、Pearson/Spearman 定义、常见标准化等，不再默认逐项展开。

### C 级：中间推导 / 冗长矩阵 / 求解细节

优先移入附录或只保留算法步骤。

目标：评委进入核心建模章节 10 秒内可以回答：

1. 这个模型叫什么；
2. 输入/状态/决策变量是什么；
3. 核心方程/目标是什么；
4. 约束是什么；
5. 怎么求；
6. 结果如何验证。

---

## 7. GitHub 调研：这轮明确“借什么，不借什么”

### 7.1 MM-Agent / LLM-MM-Agent

可借：

- Problem Analysis → Mathematical Modeling → Computational Solving → Solution Reporting 的显式阶段分离；
- HMML 三层方法库（domain / subdomain / method schema）理念；
- problem-aware + solution-aware 方法检索；
- actor-critic 式模型方案反思，而不是一次提示词直接决定算法；
- 真实数学建模 benchmark 作为验证对象。

不直接借：

- 把“结构化报告生成”当成最终论文质量保证；
- 任何固定算法频率先验；
- 与我们 EvidenceGraph / accepted research state 冲突的整套运行架构。

### 7.2 AI-Scientist v1 / v2

可借：

- `experiment.py` 与 `plot.py` 分离：实验数据和图形渲染职责分开；
- 独立 review 阶段，支持 reflection + review ensemble；
- v2 的 experiment manager 与树搜索机制可用于“候选方案探索”，而不是用于全文自由生成；
- writeup / citation / review / aggregated plots 使用不同角色/模型的职责分工。

特别重要的反向证据：AI-Scientist-v2 自己明确说明，**在目标清楚且有强模板时，v1 的模板化流程成功率更高；v2 更适合开放探索且成功率更低。**

这与数学建模比赛非常吻合：我们的目标不是开放科学发现，而是 72/96 小时内解决一个规则明确的赛题。因此不应为了“智能体感”把工作站改造成完全开放式树搜索。

### 7.3 Agent Laboratory

可借：

- Literature Review → Experimentation → Report Writing 三阶段；
- 每阶段专门 agent，而不是一个万能 writer；
- Copilot / 人类介入模式；
- checkpoint / state save；
- task notes 把资源、图表偏好、实验约束长期传给 agent。

与本项目对应：用户的人工意见（例如“前两问为核心”“公式要做减法”“流程图参考这些优秀样例”）不应只留在聊天里，应进入持久 paper/modeling preference state。

### 7.4 data-to-paper

可借：

- backward traceability：论文数字追到代码/数据；
- data-chained manuscript；
- human-verifiable；
- rewind / replay；
- coding guardrails。

本项目 Evidence-Locked / ArtifactRegistry 已经走在同一方向，因此这里重点不是复制框架，而是继续强化“论文可见数字 → accepted evidence → experiment → code/data”的回链。

### 7.5 STORM

可借：

- 写作前先检索与形成 outline；
- 多视角问题提出，而不是直接开始写长文；
- user-provided documents 与 web research 同时作为 grounding。

对应本项目：每次进入新的设计阶段，应先做本地优秀论文 + 官方规则 + GitHub 的 research refresh，再进入实现。

### 7.6 SciencePlots

Stage 2 优先调研并可能吸收：

- `science` 样式与 publication-oriented 默认参数；
- IEEE/Nature 等覆盖式 style layering；
- colorblind-safe color cycles；
- 黑白打印仍可区分的线型/marker 设计；
- 600 DPI / 列宽意识。

但不直接套 IEEE 风格到 CUMCM/MCM；只借其“样式配置层”设计和科研图可读性原则。

---

## 8. 第一阶段形成的 Competition Paper Standard 分层

后续 auditor / renderer / benchmark 必须显式区分：

### Level A — Official Hard Constraints

违反即提交风险：页数、纸张、边距、匿名、文件格式/大小、目录规则、AI disclosure、支撑材料等。

### Level B — Competition Structural Priors

来自优秀 C 题：问题链、核心模型位置、摘要信息密度、图形目的、模型验证、决策输出等。

可以作为 soft gate / reviewer finding，但不能因为某篇优秀论文这么做就强制所有题这么做。

### Level C — Task-Specific Evidence

当前赛题数据决定：什么模型、什么图、什么验证、什么公式。

Level C 优先于“论文里常见某算法”。

### Level D — Visual / Human Preference

用户提供的优秀论文截图、人工审美反馈、流程图样例、图表密度与布局偏好。

这一层应形成可调 profile，而不是散落在 prompt 中。

---

## 9. 第一阶段 Gate

第一阶段不是“写完一份调研文档”就算结束，Gate 定义如下：

- [x] 2026 CUMCM 官方格式规则已重新核验；
- [x] 2026 CUMCM AI 使用规则已重新核验；
- [x] 2026 COMAP MCM/ICM 提交与页数规则已重新核验；
- [x] 本地 C 题 distilled priors 已重新读取，不引用聊天印象；
- [x] 2023 CUMCM C 深度 profile 已重新读取；
- [x] AI-Scientist v1/v2、Agent Laboratory、data-to-paper、MM-Agent、STORM 已完成机制级对比；
- [x] SciencePlots 已进入第二阶段候选借鉴清单；
- [x] 建模重心规则已从“各问模型平铺”改为“核心模型 + 继承扩展优先”；
- [x] 官方硬规则与优秀论文软先验已分层；
- [ ] 下一步把这些标准接入可执行的 paper/profile/auditor 配置，并用真实 2023C 新旧论文做第一次结构对照 Gate。

最后一项是第一阶段进入实现收口的任务，不应直接跳到图表系统大改。

---

## 10. 进入下一小步前的计划微调

原计划原本是“调研完 → 直接做 Figure Router”。经过本轮官方 + 本地 corpus + GitHub 研究后，顺序调整为：

```text
Stage 1A  标准研究（本文件）
    ↓
Stage 1B  把 Hard/Soft/Task/Visual 四层标准做成可执行 profile
    ↓
Real Gate：2023 C 当前 PDF 做结构审计
    ↓
Research Refresh #2
    ↓
Stage 2  Figure Router + Academic Plot System + Flowchart V2
```

原因：如果不先把标准层做成机器可消费的结构，第二阶段图表很容易再次退化成“多加几个好看的模板”，而不是由论文论证目标驱动。

---

## 11. Stage 1 收口后的 Research Refresh #2：对 Stage 2 再次微调

在 Stage 1 标准与真实 2023C Gate 完成后，又做了一轮 GitHub + 本地代码现场刷新，而不是直接照原计划进入画图。

### 11.1 MatPlotAgent：Stage 2 不能只有“图表模板库”，还要有视觉反馈闭环

MatPlotAgent 的核心不是多几个 Matplotlib chart，而是：

```text
Query / Intent Understanding
-> Code Generation + Iterative Debugging
-> Visual Feedback
-> Correction
```

并用 100 个 human-verified 可视化任务建立 MatPlotBench。

对本项目的启发：Figure Router 负责“为什么画这张图 / 想证明什么”，Figure Factory 负责“怎么画”，Visual Reviewer 负责最后看：遮挡、字号、图例、留白、信息密度、颜色区分、黑白可读性、子图平衡。三者不能混成一个 render 函数。

自动视觉评分仍只能作为 reviewer signal，不能替代真实人类审阅。

### 11.2 SciencePlots + SSCI-Plots：配色问题应解决为 Style Layer，不是每个 renderer 手调颜色

SciencePlots 已验证成熟的设计是：

- base science style；
- publication/profile override；
- color cycle 单独组合；
- CJK 兼容；
- black-and-white / colorblind readability；
- 600 DPI / paper-width aware export。

SSCI-Plots 进一步展示了：

- 大量 color-blind-safe palette；
- sequential / diverging colormap；
- multi-panel composition；
- chart catalog；
- caption 与图像本体分离。

因此 Stage 2 不应在每个 `plot_*` 函数里硬编码“蓝、橙、绿”。应扩展当前 `publication_context()` 为：

```text
Competition Profile
+ Figure Role
+ Palette Role
+ Output Context
```

例如 correlation heatmap 需要 diverging map；category comparison 需要 muted categorical cycle；sensitivity 需要主参数强调色 + 其它曲线中性化。颜色由“语义角色”决定，不由图编号决定。

### 11.3 本地代码现场发现：我们其实已经有不少图型，真正缺的是 Router

当前 `ScientificFigureFactory.ChartType` 已经包含：

- line
- scatter
- heatmap
- boxplot
- radar
- state_transition
- association_network
- ranking
- uncertainty

因此用户看到的最终论文仍以少数柱状/折线类图为主，根因不只是“chart type 没实现”，而是上游 evidence bridge 没有根据论证目的主动选择不同视觉语法。

Stage 2 优先级因此从：

`先补 20 个 chart renderer`

调整为：

`先做 Figure Purpose Router -> 复用已有 renderer -> 只补当前证据真正需要的图型 -> visual feedback`

### 11.4 发现一个会反向制造当前问题的 legacy 规则：M2 quantity quota

CodeGraph 现场确认 `src/mathworkstation/m2/rubric.py` 仍把下面这些写成评分项：

- 至少 12 个公式；
- 至少 8 张图；
- 至少 5 个表；
- 至少 3 类候选模型。

`m2/agents.py` 与 `m2/benchmark.py` 还有对应生成/验收目标。

这正好解释了为什么旧系统会天然朝“公式更多、图表更多、候选更多”方向优化，与本轮人工反馈完全相反。

该 M2 benchmark 已依据 D002 被降级为 regression evidence，因此 Stage 2/3 必须继续切断这种 quantity quota 对主 Paper Engine 的影响，并在后续改成：

- evidence coverage；
- figure-purpose coverage；
- traceability；
- model clarity；
- constraint/validation closure；
- visual readability。

### 11.5 Stage 2 最终顺序再次调整

Research Refresh #2 后，下一阶段不再是笼统的“图表美化”，而是：

```text
2A Figure Purpose Router
   ↓
2B Academic Style Layer（SciencePlots 思路 + 本地比赛 profile）
   ↓
2C 补齐高价值 chart grammar（distribution / heatmap / residual / contour / sensitivity / comparison / small multiples）
   ↓
2D Flowchart Grammar（technical route / question-oriented / model architecture / mechanism）
   ↓
2E Visual Feedback Gate（代码正确 ≠ 图好看）
   ↓
2023C 重新生成 + 人工验图
```

其中 2D 会直接吸收本轮用户提供的七张优秀流程图的共同结构特征：分区、层级、主次、模块大小不等、低饱和多色、图标/小示意图辅助、连线只服务信息结构，而不再以 Graphviz 节点网络作为最终视觉答案。

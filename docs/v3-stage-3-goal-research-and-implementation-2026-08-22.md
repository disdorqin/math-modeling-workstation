# V3.5 Goal：建模主线重构 + 视觉表达升级（2026-08-22）

本轮不是继续堆模块，而是围绕用户明确的三个问题实施：

- 论文图表不能长期退化成统一科研蓝；
- 数学建模必须形成“基础分析—核心模型—继承扩展—综合输出”的连贯主线，公式做减法；
- 技术路线图应由视觉智能体/生成模型参与设计，最终再转为可编辑载体，而不是依赖固定 Mermaid/Graphviz 盒子。

## Research refresh

### 自动科研系统

**Agent Laboratory**

值得借鉴：把 Literature Review / Experimentation / Report Writing 分成专业角色，并允许 copilot/human intervention。我们的映射是：Research Refresh 不直接改 Research State，而是产出可审查的计划；真正实验仍由 Solver / Validation 执行。

**AI Scientist v2**

值得借鉴：去掉强模板依赖、用 experiment-manager + tree-search 管理开放研究。但其 README 也明确说明：有强起点模板时 v1 反而可能更稳定。对数学建模工作站的启发是“不硬编码论文结构”不等于“完全开放探索”，应保留比赛规则、证据边界和可执行 solver 的硬门。

**autonomous-researcher / research-autopilot**

值得借鉴：把研究目标拆成实验、保存 experiment summary/context bridge，再进入 paper writer。我们的 ModelSpine / EvidenceGraph 正好可以成为这种 context bridge，避免论文层读取全部原始实验日志。

### 科研图与流程图

**LiveFigure (ICML 2026)**

采用其三阶段思想：Visual Planning → editable PowerPoint generation → rendered visual diagnostics/refinement。工作站现已输出 visual brief、AI-image candidate 路由和 PPT-MCP handoff；后续只缺外部 MCP 真正执行和视觉复核。

**MatPlotAgent / paper-figures**

采用“先理解图要证明什么，再绘图，再看生成图”的思想。数值图继续保持 deterministic evidence；流程/机理图允许生成模型作为候选。

### 科研配色

**ggsci / SSCI-Plots / CMasher / Crameri**

采用两点：

1. 分类图不应所有 figure 固定第一种蓝色，而应有可复用 publication palette family；
2. 连续/相关矩阵应使用适合语义的 sequential/diverging colormap，而不是为好看随意 rainbow。

因此新增 `figure_palette_bank_v1.json` 与 `FigureColorDirector`，按 figure semantic intent 选择 palette family，并允许同一篇论文的不同图使用不同但协调的方案。

## 本轮已经落地

### Model Spine

新增：

- `config/ref_models/modeling_narrative_policy_v1.json`
- `src/mathworkstation/model_spine.py`

不硬编码“第二问一定是核心”。核心节点由执行任务类型、下游复用范围和依赖结构推断。

2023C 实际识别为：

`SP1 FOUNDATION → SP2 CORE_MODEL → SP3 EXTENSION → SP4 SYNTHESIS`

### Formula Budget

`ModelEquation` 新增 paper priority；正文通过 `select_equations_for_paper()` 按 ModelSpine role 控制公式数量。完整公式注册仍保留用于审计，不等于全部塞入正文。

2023C Q2 从 5 个登记公式压到 3 个正文核心公式，并把需求响应式压缩为：

`价格响应 + 可选二次项 + s_c(t) 时间结构`

不再把周周期、年周期、趋势全部展开成一整行长公式。

### 通用依赖推断

`ProblemGraphBuilder` 现在能从子问题 contract 中的强信号自动识别：

- `SP1 / SP2` 等显式引用；
- `问题1 / Question 1`；
- `上一问 / 在此基础上 / previous result`。

只有高置信文本证据才建立依赖；“两个问题 task family 相同”本身不会自动连边。

因此 ModelSpine 不再依赖每一道历史题单独写 `link_xxx_dependencies()` 才能工作。

### Adaptive Figure Color

新增：

- `config/ref_models/figure_palette_bank_v1.json`
- `src/mathworkstation/figure_color_director.py`

2023C 当前真实 palette routing 已出现：

- correlation heatmap → `purple_green` diverging
- exploratory diagnostics → `muted_botanical`
- category replenishment → `jama`
- sensitivity → `jama`
- price-demand panel → `muted_botanical`
- item replenishment → `muted_botanical`
- assortment counts → `npg`

颜色不由某一道题的名称硬编码，而由 semantic kind + stable figure identity 决定。

## 下一刀

1. 让 workflow/technical roadmap 的 AI candidate 真正进入外部 GPT Image → PPT MCP → render → visual review 环路；当前本机没有可用 image/ppt MCP backend 时继续保留 deterministic fallback。
2. 将 ModelSpine 的 role/emphasis 进一步反馈到正文篇幅与 ArgumentLayout，让 CORE_MODEL 在页面上获得更高叙事权重，EXTENSION 自动减少重复公式/表格。
3. 从优秀论文 corpus 继续抽取“模型链”而不是算法频率：统计核心模型出现位置、后问复用形式、公式密度与图表承担的论证任务。

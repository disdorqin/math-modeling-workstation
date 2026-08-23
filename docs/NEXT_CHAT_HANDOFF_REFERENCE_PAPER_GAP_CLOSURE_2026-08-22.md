# 下一窗口接任：优秀论文差距收敛阶段（Reference Paper Gap Closure）

## 一、项目现场

主项目：

`D:\computer learning\vibe_coding\math_model_ai_process`

参考论文目录（只读，不要修改）：

`D:\作业\竞赛\大学生数学建模\美赛\备赛\资料\论文\直接参考论文`

当前目录内至少包含：

- `2211240_2022_ICM_F_AMS.pdf`
- `2211922.pdf`
- `2307336_2023_ICM_E_AMS.pdf`
- `2311517_2023_ICM_F_Vilfredo_Pareto.pdf`
- `2318036_2023_MCM_C_Outstanding.pdf`
- `2330610_2023_ICM_Z_AMS.pdf`
- `2409404_2024_MCM_C_Outstanding.pdf`
- `2417340_2024_ICM_F_Outstanding.pdf`
- `2422054_2024_ICM_F_Vilfredo_Pareto.pdf`

最新可靠展示案例：

`20260822-CUMCM-0018-RQ4P`

PDF：

`D:\computer learning\vibe_coding\math_model_ai_process\docs\generated_samples\cumcm_2023_c_showcase\workspace\20260822-CUMCM-0018-RQ4P\paper\submission\cumcm-2023-c-showcase.pdf`

最新真实结果：19页，A4，8 figures，6 tables，Competition Audit=PASS，Visual Quality=REVIEW:91。Visual REVIEW 的主要原因是 workflow diagram 尚未完成真正 rendered-image vision/human review。

---

## 二、接任时必须先做

1. 用 DevSpace 打开主项目。
2. 第一件事读取根目录 `AGENTS.md`，遵守 CodeGraph-first，不要一上来全仓 grep/read。
3. `codegraph status`，然后围绕当前任务使用 explore/query/callers/callees/impact。
4. 所有“文件存在、代码状态、测试通过”等事实必须重新验证，不得只相信本提示词。
5. 再用 DevSpace 单独以只读方式打开参考论文目录，确认论文清单并认真审阅。不要修改该目录。
6. 先收掉上一轮最后的 WIP：`visual_intent.py` / `research_flowchart.py` 中 AI visual master -> editable redraw job 的最新接线，先跑对应回归测试，确认没有半截代码。

建议优先读取：

- `docs/reconstruction-master-plan-2026-08-19.md`
- `docs/DECISION_LOG.md`
- `docs/KNOWN_ISSUES.md`
- `docs/v3-stage-3-goal-research-and-implementation-2026-08-22.md`
- 本文档

---

## 三、当前已经做成的能力

### 1. Model Spine

已有 `model_spine.py`。工作站不再默认“每问一个独立模型”，而会推断：

`FOUNDATION -> CORE_MODEL -> EXTENSION -> SYNTHESIS`

真实 2023C 当前为：

- SP1 = FOUNDATION
- SP2 = CORE_MODEL
- SP3 = EXTENSION / CONSTRAINT
- SP4 = SYNTHESIS

### 2. 简单模型优先已经进入真实 Solver

2023C 问题2的需求响应已从二级候选改为：

`简约加价响应 -> 时间校正线性响应 -> 时间校正二次响应`

只有后一层在同一时间留出集上带来足够 RMSE 改进才升级复杂度。最新真实结果中 6 个品类有 4 个选择简约线性、2 个选择时间校正线性、0 个需要二次模型；平均时间留出 RMSE 约 46.420 kg，7日登记模型预期收益约 8162.37 元。

### 3. Formula Budget

正文不再把所有登记公式都堆进去；核心模型只保留最能表达建模思想的公式，其余估计细节留在 Research State / 附录。

### 4. Figure Color Director

已有 `figure_color_director.py` 和 `figure_palette_bank_v1.json`。相关性热力图已经固定为红-白-蓝发散色；其它图按语义和 figure identity 使用不同 publication palette family，避免全篇科研蓝。

### 5. 流程图路线

当前 CUMCM deterministic fallback 已不再以 Graphviz 作为最终图，已存在 model-spine-oriented roadmap renderer；Graphviz / Mermaid 只保留为结构和可编辑源。

正式方向是：

`NarrativeGraph / ModelSpine -> Visual Brief -> GPT Image / scientific visual master -> PPT MCP / unflatten editable redraw -> render -> vision review -> promote`

### 6. Model Candidate Consensus

已有 `model_candidate_consensus.py` 与配置。目标是让 baseline modeler / alternative modeler / critic / adjudicator 围绕同一任务讨论，但 consensus 只能决定“哪个候选值得真实实验”，不能直接替代 Solver/Validation 宣布论文模型。

旧的全局 `_COMPLEXITY_RANK` 已逐步删除，简单性应该来自实际模型结构与任务语义，而不是维护一张模型复杂度人工排名表。

---

## 四、这批“直接参考论文”带来的关键新认识

不要过多学习它们具体做了什么题、用了哪个算法；真正要抽取的是“优秀论文是怎样被组织和呈现出来的”。

### A. 排版差距不是字体问题，而是“页面构图能力”差距

这些论文的共同点不是统一模板，而是：

- 页面有明显的视觉节奏：正文、留白、图、表、公式不是平均密铺；
- 图像经常成为一页的视觉锚点，而不是正文中的附件；
- 标题层级、caption、表格、粗体关键词、段落宽度与页面边界整体协调；
- 开头几页尤其讲究“读者进入论文”的体验；
- 论文整体像经过人工排版设计，而不是 Markdown 结构被机械翻译成 LaTeX。

当前工作站即使已经 A4/字体/图表清晰，仍然主要是“结构正确的自动排版”；距离优秀论文的“页面构图”还有明显差距。

### B. 优秀论文会用现实图片完成“入题”

例如参考论文会在 Introduction / Problem Background 直接插入与题目强相关的网页真实图片，并在 caption/脚注中标注来源。它不是装饰，而是把抽象赛题快速落到现实情境。

因此下一阶段应新增 `Context Visual` 能力：

`题目现实语境 -> 搜索可信网页图片 -> 选择1~2张真正有入题价值的图片 -> 保存来源/引用/许可信息 -> 进入 Background 页面布局`

注意：

- 背景现实图片优先搜索真实来源，而不是 GPT Image 伪造新闻/现实照片；
- AI生成更适合流程图、机理图、方法图，而不是伪造现实背景事实；
- 不是每题都强制插图，必须由语境价值决定。

### C. 数据图真正的差距在“每张图被单独雕刻”

优秀论文并不是换一套 palette 就结束。它们往往针对每一张图分别选择：

- 图型；
- 颜色；
- 线型/marker；
- 是否多 panel；
- 是否加局部标注、箭头、关键区间；
- 图例摆放；
- 哪些信息弱化、哪些信息强调。

因此继续发展 `Figure Purpose Router + Figure Art Director`，不要硬编码“某 semantic_kind 永远一个模板”。

数值必须由真实数据/solver绘制，但“怎样表达这些数值”应允许 agent/visual planner 提供设计建议，再由 deterministic plotting 实现。

### D. 最大差距仍然是“建模叙事”

优秀论文不是按固定字段反复输出：

`研究目标 -> 模型与方法 -> 变量与符号 -> 模型构造 -> 数学模型 -> 求解 -> 检验`

它们更像：

`现实矛盾/上一问结论 -> 为什么需要这个模型 -> 先建立最简单关系 -> 增加必要机制 -> 得到完整模型 -> 求解 -> 解释结果 -> 下一问在此基础上扩展`

也就是“娓娓道来、层层叠加、循序渐进”。

例如优秀论文常直接把章节命名成模型本身：

- Establish the D&E Model
- Develop Asteroid Mining Model
- Momentum Quantization Model Based on Sliding Windows
- Method / Model / Mould / Movement

而不是所有小问都长成相同模板。

这意味着下一阶段需要一个真正的 `Model Story Planner`，它应消费 ProblemGraph + ModelSpine + Solver Evidence，生成 narrative stages，而不是只给每一问填相同槽位。

### E. “Our Work”只是整篇论文叙事的缩影

优秀流程图之所以好，不只是画得漂亮，而是因为整篇论文先有清楚的研究故事，所以一张图可以浓缩全文。

工作站未来顺序必须是：

`先规划整篇建模故事 -> 再生成技术路线图`

而不是先把 QuestionGraph 画出来，再希望流程图替论文建立逻辑。

---

## 五、下一阶段建议命名

`V4 - Reference Paper Gap Closure / 优秀论文差距收敛阶段`

优先级必须是：

### P0：Model Story Planner

把 Model Spine 真正升级成“逐层建模叙事”。

目标结构示例：

`问题洞察 -> 基础关系 -> 核心模型 -> 必要修正 -> 约束/场景扩展 -> 验证 -> 决策`

要求：

- 后问尽可能复用上游模型；
- 简单模型先行；
- 公式跟着叙事出现，不要一次堆满；
- section title 应允许按模型/机制命名，不要固定“问题X：…”；
- 每个新增复杂模块都必须有“为什么前一个模型不够”的证据。

### P1：Page Composition / Paper Art Direction

建立“论文页面构图层”，重点学习参考论文：

- Background 开篇页面；
- Our Work 页面；
- 模型建立页面；
- 多图/图表混排；
- 公式与文字的节奏；
- figure/table 的浮动位置；
- 不同页面密度。

不要写死某篇优秀论文的坐标模板。应提取 layout grammar / soft priors，让 planner 根据当前内容选择。

### P1：Context Visual Retrieval

为真正需要现实背景的题目增加：

`background image search -> source verification -> attribution -> paper insertion`

建议优先插入 1~2 张，而不是把论文做成杂志。

### P1：Figure Art Director V2

让每张图有自己的设计任务：

`claim/evidence -> chart family -> emphasis -> palette -> annotation -> composition`

数据仍 deterministic；设计允许 agent 参与。

### P1：AI/PPT Scientific Illustration Chain

真正跑通：

`semantic brief -> GPT Image/scientific-image master -> editable PPT redraw -> rendered preview -> VLM semantic/aesthetic review -> accepted figure`

流程图只是第一种应用，后续还应支持 mechanism / architecture / model illustration。

### P2：Whole-PDF Visual Reviewer

不能再只审 figure metadata。应把最终 PDF 页面实际 render 后交给 vision reviewer，从页面层面检查：

- 页面是否太空或太挤；
- 图/表是否抢占正文；
- caption 是否割裂；
- 章节切换是否难看；
- 是否存在大面积连续纯文本；
- 颜色是否协调；
- 关键模型是否在前半部分得到足够视觉强调。

最终与参考论文页进行视觉对照，不是像素复制，而是比较 hierarchy / density / visual rhythm / storytelling。

---

## 六、下一窗口 Goal 提示词

请直接复制下面内容作为新窗口起始词。

---

请继续我之前的数学建模工作站重构任务，不要从头重新设计。

主项目：

`D:\computer learning\vibe_coding\math_model_ai_process`

新加入的优秀论文参考目录（只读）：

`D:\作业\竞赛\大学生数学建模\美赛\备赛\资料\论文\直接参考论文`

这轮 Goal 是：**V4 - Reference Paper Gap Closure / 优秀论文差距收敛阶段**。

第一件事请恢复现场：

1. DevSpace 打开主项目，读取根目录 `AGENTS.md`。
2. 必须遵守 CodeGraph-first；先 `codegraph status`，再用 explore/query/callers/callees/impact 理解当前代码，不要全仓 grep/read。
3. 读取：
   - `docs/reconstruction-master-plan-2026-08-19.md`
   - `docs/DECISION_LOG.md`
   - `docs/KNOWN_ISSUES.md`
   - `docs/v3-stage-3-goal-research-and-implementation-2026-08-22.md`
   - `docs/NEXT_CHAT_HANDOFF_REFERENCE_PAPER_GAP_CLOSURE_2026-08-22.md`
4. 重新验证当前代码和测试状态，不允许只相信聊天记忆。
5. 单独以只读方式打开：
   `D:\作业\竞赛\大学生数学建模\美赛\备赛\资料\论文\直接参考论文`
   系统分析里面所有优秀论文。不要过多关注题目内容和具体算法，而重点研究：
   - 页面排版与视觉节奏；
   - Background / Our Work / Model Establishment 页面构图；
   - 每张数据图为什么看起来不一样、颜色/图型/标注如何服务论证；
   - 现实网页图片如何用于开篇引入以及来源标注；
   - 模型如何从直觉到简单关系、再到必要修正、再到后续小问扩展；
   - section title 和 narrative 如何让评委一路读懂，而不是每问重复固定模板。

当前最新可靠案例：

`20260822-CUMCM-0018-RQ4P`

PDF：

`D:\computer learning\vibe_coding\math_model_ai_process\docs\generated_samples\cumcm_2023_c_showcase\workspace\20260822-CUMCM-0018-RQ4P\paper\submission\cumcm-2023-c-showcase.pdf`

已经完成的重要能力包括：Model Spine、简单模型优先需求 Solver、Formula Budget、Figure Color Director、红蓝相关热力图、CUMCM model-spine roadmap fallback、Model Candidate Consensus、AI Visual Brief/PPT handoff、Visual Review gate。

但不要因为这些已经完成就认为论文接近优秀论文。用户最新人工审阅认为，**我们与这些 Outstanding / AMS / Vilfredo Pareto 论文仍有巨大差距**，主要在三方面：

1. **排版**：我们目前只是“规范、清楚”，优秀论文是“页面经过设计”；需要建立 page composition / paper art direction，而不是继续调字体和边距。
2. **图片**：优秀论文的每张数据图都像单独设计过，而且会在 Background 用与题目高度相关的真实网页图片优雅入题；需要 Context Visual Retrieval + Figure Art Director V2。
3. **建模**：这是最高优先级。优秀论文是娓娓道来、层层叠加、循序渐进。我们虽然有 Model Spine，但正文仍有模板化槽位感。需要真正实现 `Model Story Planner`：
   `问题洞察 -> 基础关系 -> 核心模型 -> 必要修正 -> 扩展约束/场景 -> 验证 -> 决策`。
   简单模型先行，只有实际证据说明不够时才增加复杂度；后续小问优先继承上游模型而不是另起炉灶。

执行优先级：

**P0：Model Story Planner**
- 先研究参考论文的建模叙事；
- 再设计通用 story schema，不要硬编码“Q2一定是核心模型”；
- section title 应允许按照模型/机制命名；
- 公式按叙事逐步出现；
- 新复杂模块必须有 burden of proof；
- 把这个能力真正接入 ResearchStatePaperService，并在 2023C 上验证。

**P1：Page Composition / Paper Art Direction**
- 从参考论文抽取 layout grammar 与 soft priors；
- 解决页面密度、留白、图文比例、model section 的视觉重心；
- 不要复制固定坐标模板。

**P1：Context Visual Retrieval**
- 题目需要时，从可信网站搜索 1~2 张真实背景图；
- 保存 URL/来源/引用；
- 不允许用 AI 图片冒充现实证据。

**P1：Figure Art Director V2**
- 每张图基于 claim/evidence 单独规划 chart type、palette、annotation、multi-panel composition；
- 数值必须 deterministic；设计可由 agent 辅助。

**P1：AI/PPT Scientific Illustration Chain**
- 收掉上一轮 `visual_intent.py` / `research_flowchart.py` 的 WIP；
- 真正形成 `visual master -> editable redraw job -> PPT MCP/unflatten -> render -> vision review -> promote`；
- 流程图只是第一种，后续支持 mechanism/model architecture。

**P2：Whole-PDF Visual Reviewer**
- render 最终 PDF 页面，用 vision reviewer 审真正页面，不再只审 metadata；
- 与优秀论文比较 hierarchy / density / visual rhythm / storytelling，不做像素模仿。

继续遵守既定开发原则：

- 每推进完一个阶段，都必须重新检索本地优秀论文和网上/GitHub成熟科研智能体，调研结果要允许改变原计划；
- 优先借鉴成熟开源项目，不重复造轮子；
- 不硬编码某一道题、某一个优秀论文的算法/颜色/版式；
- Evidence-Locked：不伪造数值、实验、模型和引用；
- 复杂图可交给 GPT Image / scientific-image / PPT MCP，但数值数据图必须由真实数据生成；
- 不要以“新增多少模块”作为完成标准，最终标准是新 PDF 与参考优秀论文的差距是否明显缩小。

执行方式：不要每一步都停下来问我。你可以自主连续推进，关键里程碑再汇报；等生成新的完整 2023C PDF 后再让我人工审阅。

---

# Local Modeling Knowledge Base — 数学建模本地资料库地图

Last updated: 2026-08-20

External source root:

`D:\作业\竞赛\大学生数学建模\美赛\备赛\资料`

> 本文件是外部资料库的**只读索引与使用说明**。原始约 9.6 GB 资料不复制进项目仓库；项目只保存路径、标签、统计、派生 profile / corpus knowledge。当前 DevSpace 写权限仅覆盖 `D:\computer learning\vibe_coding`，所以 README 先保存在本项目；外部资料目录保持原样。

---

## 0. 当前总原则：只专精 C 题

当前工作站不追求覆盖所有 A/B/C/D/E/F 题型。

正式研发、优秀论文 benchmark、Paper Gate 只围绕：

- **MCM / ICM 中的 MCM C 题**；
- **CUMCM / 高教社杯 C 题**。

A/B/D/E/F 资料仍保留为通用方法知识或回归旁证，但不进入近期主 Gate。

目标分层：

```text
数学建模通用 Research Infrastructure
        ↓
C-Problem Generic Research Profile
        ↓
├─ MCM C Profile
└─ CUMCM C Profile
```

其它比赛未来优先复用这两个 profile，而不是现在另起完整体系。

---

## 1. 资料库规模快照

2026-08-20 只读扫描：

| 一级目录 | 目录数 | 文件数 | 约大小 | 主要文件类型 | 角色 |
|---|---:|---:|---:|---|---|
| `mcmthesis-master` | 2 | 17 | 0.8 MB | tex/cls/pdf/code | MCM/ICM LaTeX 排版模板 |
| `杂项` | 0 | 2 | 38.3 MB | zip | 重复压缩包/课程归档 |
| `论文` | 180 | 867 | 9124.3 MB | 506 PDF / 110 xlsx / 66 doc / 44 rar / 36 mp4 | **核心：赛题、优秀论文、方法资料、Skills** |
| `课程课件` | 24 | 209 | 476.4 MB | 92 PDF / 24 zip / 15 m / 9 pptx / 6 py | **核心：课程、方法、代码、赛题解析** |

根目录另有：

- `参考提示词.docx`：建模讲师式 prompt 经验稿；**advisory prior，不是研究真源**。

---

# 2. 根目录逐分支说明

## 2.1 `mcmthesis-master/`

**标签**：`[MCM] [模板] [排版] [高优先级-交付阶段]`

内容：

- `mcmthesis.cls`
- `mcmthesis-demo.tex / pdf`
- `figures/`
- `code/`
- 示例 Matlab / C++ 文件
- `README.md`

用途：

- MCM/ICM 最终论文 LaTeX 版式；
- Section 8 Submission Package；
- 不参与选模与研究结论。

注意：根目录、`杂项/`、`课程课件/` 中还存在 `mcmthesis-master.zip` / `mcmthesis-master(1).zip`，属于重复副本，优先使用已解压根目录版本。

---

## 2.2 `杂项/`

**标签**：`[归档] [低优先级]`

当前只有：

- `mcmthesis-master.zip`
- `课程34：2023、2024年赛题深析 附件.zip`

用途：备份/归档。运行时不直接检索，优先使用已经解压的对应目录。

---

# 3. `论文/` — 核心知识与 Benchmark 区

总规模约 9.1 GB，是整个资料库的主资产。

## 3.1 `论文/.workbuddy/`

**标签**：`[历史工作日志] [非建模知识] [默认忽略]`

- `memory/2026-08-05.md`

内容主要是百度网盘 / aria2 / 油猴下载排错记录，与数学建模研究无直接关系。

规则：**不进入 ModelingBrain / Paper benchmark / Skill 检索。**

---

## 3.2 `论文/skill/`

**标签**：`[Skill] [通用] [C题高价值] [高优先级]`

当前资产：

`数学建模全流程AI-Skills出售版.zip`

压缩包约 100 个 entry，已确认包括：

### Orchestrator / workflow

- `math-modeling-orchestrator`
- `mm-problem-decomposer`
- `mm-model-selector`
- `mm-variable-assumption-builder`

### Data / modeling

- `mm-data-eda-cleaning`
- `mm-evaluation-models`
- `mm-prediction-models`
- `mm-classification-clustering`
- `mm-optimization-models`
- `mm-simulation-models`

### Paper / review

- `mm-abstract-polisher`
- `mm-paper-structure-writer`
- `mm-paper-reviewer`

### Shared model cards

包含 AHP、TOPSIS、熵权、灰色关联、GM(1,1)、聚类、分类、回归、时间序列、LP、整数规划、非线性优化、Monte Carlo、排队等。

### Shared checklists

- academic integrity
- code quality
- competition boundary
- paper logic
- result validation

### Scripts / examples

有 baseline / template Python 脚本和 end-to-end 示例。

**使用规则**：

Skill 只作为：

```text
Advisory knowledge / workflow prior
```

是否真的可执行，仍必须由本项目 `SolverRegistry` 判定；不能因为 Skill 里写了某算法就宣称 Solver 已实现。

当前项目已经有一份 extracted skill 供 ModelingBrain 使用，后续应与本 zip 做版本一致性检查，避免出现两套漂移资产。

---

## 3.3 `论文/数学建模/`

### 3.3.1 `【000】清风数学建模/`

**标签**：`[方法论] [教程] [经验] [通用] [C题高价值]`

#### `000000建模/`

已确认包含约 19 个直接文件 + 子目录，核心包括：

- `Matlab数学建模算法全收录...pdf`
- `[数学模型].姜启源.文字版.pdf`
- `五步法建模.txt`
- `历年题型分类.pdf`
- `清风建模课程笔记（75页）.pdf`
- `数学建模数据库汇总.pdf`
- `数学建模算法分支最终版.pdf`
- `学习路线.md`
- `models.txt`
- 模型大全 / 常见模型 / 技能图谱 URL
- `A018（最新版）按模型算法分类的优秀论文.zip`
- `1.数学建模算法资料大全.../`

用途：

- 建模方法导航；
- 题型 → 方法候选 prior；
- 学习材料与知识卡来源；
- **不能代替同题优秀论文与真实实验。**

#### `清风：数学建模视频全套【已完结！】/`

视频课程类资产。对 AI runtime 价值低于文本/PDF，主要用于人工学习；默认不优先解析视频。

---

## 3.4 `论文/网盘资料/美赛O奖真题+优秀论文/`

**标签**：`[MCM] [C题核心] [原题] [O奖全文] [最高优先级]`

分两大主支：

### 3.4.1 `2000-2024年美赛赛题汇总.../`

当前实际可见主要年份目录：

- `2018_MCM-ICM_Problems`
- `2019_MCM-ICM_Problems`
- `2020_MCM-ICM_Problems`
- `2021_MCM_ICM/...`
- `2022_MCM_ICM_Problems/...`
- `2023_MCM_ICM_Problems`
- `2024_MCM-ICM_Problems`

这是原题 / 官方附件 archive。

C题用途：

- ProblemGraph real gate；
- official data；
- same-problem benchmark problem context。

### 3.4.2 `2006-2025年美赛优秀论文汇总.../`

当前已确认年份包：

- 2018 O奖论文集
- 2019 O奖论文集
- 2021 O奖论文集
- 2022 O奖论文集
- 2023 O奖论文集
- 2024 O奖论文集
- 2025 O奖论文集

当前已直接索引的 **C题 O奖 PDF**：

| 年份 | 已确认 C题 O奖全文 |
|---:|---:|
| 2018 | 5 |
| 2022 | 10 |
| 2023 | 12 |
| 2024 | 11 |
| 2025 | 18 |

2019 / 2021 年包当前存在，但目录命名并非直接 `C题...`，后续 C题 corpus 扩充时再做深层索引。

**运行时策略**：

- Raw PDF 保留外部；
- 项目只保存 derived full-text profile；
- 同题 benchmark 不强制模仿算法，只抽 recurring capability。

当前已实际用于系统 Gate：

- **2018 MCM C Energy**：5 篇 O奖全文；
- **2023 MCM C Wordle**：6 篇首批 O奖全文（原目录实际还有更多）。

---

## 3.5 `论文/高教社论文/`

**标签**：`[CUMCM] [C题核心] [优秀论文] [原题] [方法教材] [最高优先级]`

主目录：

`I953高教社杯全国大学生数学建模竞赛题目及优秀论文/`

分三大支。

### 3.5.1 `各类常用数学模型/`

35 个 PDF，主体 30 章：

1. 线性规划
2. 整数规划
3. 非线性规划
4. 动态规划
5. 图与网络
6. 排队论
7. 对策论
8. 层次分析法
9. 插值与拟合
10. 数据统计描述与分析
11. 方差分析
12. 回归分析
13. 微分方程建模
14. 稳定状态模型
15. 常微分方程
16. 差分方程模型
17. 马氏链
18. 变分法
19. 神经网络
20. 偏微分方程数值解
21. 目标规划
22. 模糊数学
23. 现代优化算法
24. 时间序列
25. 存贮论
26. 经济金融优化
27. 生产与服务运作优化
28. 灰色系统
29. 多元分析
30. 偏最小二乘回归

附录包含 Matlab / LINGO / 判别分析等。

这是传统数学建模知识卡的重要来源。

### 3.5.2 `高教社杯全国大学生数学建模竞赛优秀论文/`

当前 264 个文件，其中 219 个 PDF。

年份目录：

- 2003
- 2010–2025（逐年目录）
- `_analysis/`（当前空）

当前快速索引到的 **C题优秀论文**：

| 年份 | 已确认 C题优秀论文 |
|---:|---:|
| 2010 | 4 |
| 2018 | 3 |
| 2019 | 3 |
| 2020 | 4 |
| 2021 | 4 |
| 2022 | 1 |
| 2023 | 4 |
| 2024 | 3 |
| 2025 | 2 |

这不是“其它年份一定没有 C题”，只是当前按文件命名规则快速识别出的显式 C题集合；Section 7 扩 corpus 时继续深索引。

**CUMCM C 的正式 Excellent Corpus 应优先从这里取。**

### 3.5.3 `高教社杯全国大学生数学建模竞赛往届题目/`

当前 323 个文件，其中约 134 个 xls/xlsx、33 个 PDF，说明大量题目附件数据也在本地。

年份目录：

- 2003
- 2010–2025

用途：

- CUMCM C real problem gate；
- official / original attachments；
- ResearchDataCoverage；
- 同题优秀论文研究时的 ground truth problem context。

---

## 3.6 `论文/美赛备赛+速成+历年真题海量学习资料.docx.docx`

**标签**：`[MCM] [经验合集] [advisory]`

用途：备赛经验 / 速成资料入口。后续可抽取章节索引，但优先级低于官方赛题、O奖论文和结构化课程。

---

## 3.7 `论文/美赛资格赛论文.pdf`

**标签**：`[论文样本] [非优秀论文基准]`

可作为普通/资格赛论文负样本或风格对照，不应混入 O奖 corpus。

---

# 4. `课程课件/` — 方法、写作与实战课程

总计约 209 个文件 / 476 MB。

## 4.1 赛制 / 流程 / 写作

- `课程1：数模入门及美赛全知解读`
- `课程2：数模美赛解题流程启蒙`
- `课程3：美赛各版块高分写作套路`
- `课程4：ChatGPT美赛教程`
- `课程5：SPSSPRO美赛教程`
- `课程10：美赛优秀论文绘图教学`
- `课程11：美赛高分写作&排版速成`
- `课程12：基础阶段真题初析`
- `课程31：赛题分析`
- `第17节课：2023、2024年赛题深析`

用途：

- MCM profile / Paper profile / Figure purpose prior；
- 只能作为经验先验，不能替代优秀论文全文 benchmark。

## 4.2 评价 / 统计 / 数据分析

- `课程13：评价模型基础`
- `课程14：描述性统计`
- `课程15：特征工程`
- `课程16：假设检验与分布拟合`
- `课程18：回归分析综合`
- `第23节课：聚类分析`
- `第24节课：模型的解释与评价方法`

其中：

`课程13配套资料/课程13算法文档（熵权+topsis+层次分析）/`

是 C题常见综合评价方法的重要知识卡源。

## 4.3 预测 / 分类

- `课程19：时间序列预测`
- `课程20：短期预测`
- `课程21：短期预测实战`
- `课程22：贝叶斯与分类模型`

对于数据驱动型 C题属于高优先级课程组。

## 4.4 规划 / 优化 / 图论

- `课程25：常见规划`
- `课程26：图论优化`
- `课程27：贝叶斯优化`
- `课程28：智能优化算法`
- `课程29：网络优化`
- `课程30：TSP旅行商问题`

附带 Matlab / Python / Markdown 代码与 zip 附件，可作为 Solver candidate / implementation reference，但必须重新经过本项目 Solver/Validation contract。

## 4.5 机理模型

- `课程32：微分方程`
- `课程33：差分方程模型+案例讲解`

近期 C题专精下不是每题都优先，但若 C题出现传播、增长、资源动态或系统演化，可进入 ModelingBrain 候选。

## 4.6 编程基础

- `课程6：MATLAB 基础（一）`
- `课程7：MATLAB 进阶（二）`
- `课程8：Python 基础（一）`
- `课程9：Python 进阶（二）`

对当前 AI workstation runtime 优先级较低；保留作为人工学习/代码参考。

## 4.7 `美赛历年题目/`

### `16-24年美赛题目合集/`

已确认包含 2016–2024 各年 MCM/ICM problem 文件，且 **C题及附件连续性很好**：

- 2016 C + `ProblemCDATA.zip`
- 2017 C + `2017_MCM_Problem_C_Data.xlsx`
- 2018 C + `ProblemCData.xlsx`
- 2019 C + C data zip
- 2020 C data zip
- 2021 C + C data zip
- 2022 C + C data zip
- 2023 C Wordle + `Problem_C_Data_Wordle.xlsx`
- 2024 C + `data_dictionary.csv` 等数据

这是当前最方便的 **MCM C 连续历年题库入口**。

## 4.8 `课程34：2023、2024年赛题深析 附件/`

当前解压内容主要是：

- `美赛/2023A/` Matlab 代码
- `美赛/2024A/` Matlab 代码

对当前 C题主线不是核心 benchmark，归为其它题型方法旁证；zip 备份位于 `杂项/`。

## 4.9 `课程10配套资料/`

包含绘图案例 / 图片素材；Section 7.2 visual figure-purpose calibration 可参考。

## 4.10 `课程18：回归分析综合（课程附件）/`

含 `回归分析综合/` 多个文件及 `__MACOSX/` 元数据目录。

规则：`__MACOSX` 默认忽略；真实附件可用于回归知识卡和代码示例。

## 4.11 `课程30附录代码/`

TSP / 图优化类代码。当前 C题不是默认重点，按题目需要再加载。

---

# 5. 根目录单文件

## `参考提示词.docx`

**标签**：`[Prompt] [经验] [advisory] [C题可借鉴]`

已抽样读取，其核心观点包括：

- 题型划分：优化 / 预测 / 评价 / 数理统计 / 机理分析；
- 每问选择最匹配的方法；
- 后续问题与前问逻辑递进；
- 没有真实量化结果时不要伪造模型比较；
- 模型评估、灵敏度、鲁棒性；
- 摘要、写作、图片生成提示词。

这些理念与当前 Workstation 多项设计方向一致，但仍有部分旧式 prompt 风格，例如“公式尽可能多”。

使用原则：

> 作为历史经验与写作 prior，不作为硬 Gate。硬 Gate 来自真实赛题、Research State、Validation 和优秀论文 corpus。

---

# 6. C题核心资产索引

## 6.1 MCM C

### 原题 / 附件

优先级：

1. `课程课件/美赛历年题目/16-24年美赛题目合集/`
2. `论文/网盘资料/.../2000-2024年美赛赛题汇总.../`

### O奖全文

优先：

`论文/网盘资料/.../2006-2025年美赛优秀论文汇总.../`

当前重点年份：2018、2022、2023、2024、2025。

### 已进入真实 Gate

- 2018 C Energy Compact
- 2023 C Wordle

## 6.2 CUMCM C

### 原题 / 附件

`论文/高教社论文/.../高教社杯全国大学生数学建模竞赛往届题目/`

### 优秀论文

`论文/高教社论文/.../高教社杯全国大学生数学建模竞赛优秀论文/`

当前 C题 corpus 候选优先年份：

- 2018 C：会员画像 / 数据挖掘
- 2020 C：中小微企业信贷决策
- 2023 C：蔬菜自动定价与补货
- 2024 C：3 篇显式 C题优秀论文
- 2025 C：2 篇显式 C题优秀论文

正式 Section 7 benchmark 只选任务结构互补的 C题，不以年份数量为完成标准。

---

# 7. 知识库分层：避免把所有资料混成一个向量库

```text
L0 RAW ARCHIVE
PDF / DOCX / XLSX / ZIP / code / video
        ↓
L1 ASSET REGISTRY
比赛 / 年份 / 题号 / C题 / 类型 / 可解析性 / 路径 / 优先级
        ↓
L2 DERIVED KNOWLEDGE
model cards / excellent-paper profiles / question families / failure patterns
        ↓
L3 SKILL / ROUTING KNOWLEDGE
when-to-use / when-not-to-use / validation / solver requirements
        ↓
L4 RUNTIME RESEARCH STATE
ProblemGraph -> ModelingBrain -> Solver -> Validation -> Evidence -> Paper
```

## 严格边界

- 教材说“某模型适合” ≠ Solver 已实现；
- Skill 写了某算法 ≠ 真实实验已执行；
- 课程老师推荐某套路 ≠ 优秀论文 recurring standard；
- 优秀论文用了某算法 ≠ 我们必须模仿；
- 同题优秀论文反复出现的**能力**才可进入 benchmark prior；
- 最终数值只能来自当前 case 的 accepted Research State。

---

# 8. C题 Router 建议

## MCM C 请求

```text
MCM C prompt
→ MCM C 原题 archive
→ same-year / same-problem O-award corpus
→ generic C model cards / Skills
→ MCM writing/profile assets
→ Solver + Validation truth
```

## CUMCM C 请求

```text
CUMCM C prompt
→ 高教社 C 原题 + 附件
→ same-year C 优秀论文 corpus
→ 各类常用数学模型 + 课程知识
→ generic C model cards / Skills
→ CUMCM writing/profile assets
→ Solver + Validation truth
```

这样可以避免把 MCM 的 memo / page style / discussion 写法直接污染 CUMCM，也避免把国赛模板反向污染 MCM。

---

# 9. PDF / 文档读取策略

已实际发现：部分 CUMCM PDF 使用特殊中文字库，Poppler `pdftotext` 会丢失中文，但 PDF 本身并不是扫描件。

读取优先级：

```text
PyMuPDF
→ pypdf
→ Poppler / pdftotext fallback
→ OCR only when no usable text layer exists
```

OCR 是最后手段，不应把“pdftotext 失败”误判成“必须 OCR”。

超长论文含大量附录时，Section 7 deep profile 优先分析 submission main body；代码附录不应该把模型序列 / figure density 人为放大。

---

# 10. 低价值 / 重复 / 清理提示

以下资产**当前不删除**，但 Registry 应默认降权：

- `杂项/` 中已解压内容的 zip 副本；
- `mcmthesis-master.zip` / `mcmthesis-master(1).zip`；
- `__MACOSX/`；
- `.DS_Store`；
- `.downloading` 未完成文件；
- `.workbuddy` 下载工具工作日志；
- 视频课程（AI runtime 默认不解析）；
- 非 C题优秀论文（保留但不进入近期 benchmark）。

原则：**先索引、后去重；当前不物理删除用户资料。**

---

# 11. Goal 7.0 / 7.1 当前完成度

## Goal 7.0 — Local Modeling Knowledge Base：PASS

2026-08-20 已对资料根目录执行全量只读目录扫描：**211 个目录**进入 inventory 范围；README 对所有高价值一级/二级/三级分支做语义分类，其余年份/附件目录按同一 Registry 规则归档，不依赖聊天记忆。

已完成：

- 根目录四大分支真实扫描；
- 文件规模 / 类型统计；
- 211 个目录全量 inventory 覆盖；
- 关键二级/三级目录语义分类；
- Skill zip 100-entry 内容索引；
- 高教社 30 类常用模型确认；
- MCM C 历年题库入口确认；
- MCM C O奖 corpus 主入口及年份数量确认；
- CUMCM C 原题/附件与优秀论文入口确认；
- 课程 1–35 方法/写作/优化/预测分类；
- `参考提示词.docx` 经验内容抽样；
- PDF 非 OCR Unicode 恢复路线确认；
- 机器入口：`config/ref_models/local_knowledge_base_registry.json`。

仍可后续增量补充，但不阻塞主线：

- 2019 / 2021 MCM C O奖包更细文件映射；
- 早年 CUMCM 文件名不统一年份的逐文件题号 metadata；
- 课程/清风教材的章节级 model-card 抽取；
- 外部资料根目录 README 镜像（当前 DevSpace 只写项目 root）；
- visual/layout 资产索引。

## Goal 7.1 — C-Problem Excellent Corpus：PASS（text/full-text layer）

正式 primary benchmark 已锁定为 **5 道 C题 / 21 篇优秀论文**：

| 赛制 | 年份 | C题 | 优秀论文数 | 主要研究链 |
|---|---:|---|---:|---|
| CUMCM | 2010 | 输油管布置 | 3 | 几何/最短路径 → 约束优化 → 决策 |
| CUMCM | 2018 | 大型百货商场会员画像 | 3 | 数据挖掘 → 会员表示/生命周期 → 营销决策 |
| CUMCM | 2023 | 蔬菜定价与补货 | 4 | EDA → 预测 → 定价/补货约束优化 |
| MCM | 2018 | Energy Compact | 5 | profile/evaluation → forecast → targets/actions → memo |
| MCM | 2023 | Wordle | 6 | forecast/explanation/distribution/classification → letter |

统一派生层包含：Question type、Model sequence、Why this model、Model transition、Validation type、Figure purpose、Innovation pattern、Abstract structure、Failure patterns。

机器 Gate：`config/ref_models/c_problem_excellent_benchmark_v1.json` + `src/mathworkstation/c_problem_benchmark.py`。任何非 C题进入 primary benchmark、少于 3 道 CUMCM C 或少于 2 道 MCM C 都会失败。

当前边界：**PDF visual/layout = UNVERIFIED；blind/human competition review = UNVERIFIED。** 文本 corpus PASS 不能被解释成获奖认证。

---

# 12. 下一步

## Goal 7.2 — C-Problem Modeling Knowledge

把五题优秀论文的 recurring research behavior 转成 ModelingBrain / validation / repair prior。

## Goal 7.3 — MCM C vs CUMCM C Paper Profiles

分别建立写作、图表、摘要、公式、交付规范。

## Goal 7.4 — Five Real C Problem Gates

工作站完整跑 5 道真实 C题，按 gap 回退 Section 1–6。

## Goal 7.5 — Human Review

内部 Gate 到值得人工查看的阶段后，再邀请用户审阅；不在开发中间频繁打断。

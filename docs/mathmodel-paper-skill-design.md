# 数学建模论文写作层设计(Math-Model Paper Skill)

**状态:** 设计定稿 v1.0 — 用户已确认 5 项决策(2026-08-04)
**日期:** 2026-08-04
**核心观点:** 数模论文 ≠ 学术论文。数模看重:①完整性(摘要/问题/假设/模型/结果/评价全流程)②**图表是灵魂**(图表好看 > 模型涨几个点)③**连贯性**(从摘要到结论一条主线,而非学术式严谨论证)④格式规范(三线表、摘要页、图题表题位置)。

---

## 0. 已确认的设计决策(用户拍板)

| # | 决策 | 选择 |
|---|---|---|
| 1 | 数据图如何进论文 | **自动晋升所有图**(paper_ready 后 DRAFT 图自动晋升进对应章节) |
| 2 | 无证据不进论文对叙述性文字 | **数字硬+叙述松**(数字/结论/图表引用仍硬约束;叙述性文字放宽,保证连贯) |
| 3 | 隐藏状态打磨默认 Stage 数 | **5 个 Stage**(coherence→humanize→figures→notation→final_polish) |
| 4 | 数模格式规范优先哪个竞赛 | **两套都做**(CUMCM 中文 + MCM 英文) |
| 5 | 帮手分工 | **帮手全做**(opencode + 另一帮手实现,Claude 验收) |

---

## 0. 现状诊断(基于代码实测)

| 维度 | 现状 | 与数模论文的差距 |
|---|---|---|
| 结构 | 已有 12 节(摘要/问题重述/假设/符号/数据/模型建立/求解/结果/敏感性/优缺点/结论/参考文献) | ✅ 基本符合数模框架 |
| 绘图 | matplotlib,dpi=180,**无统一风格**;6 张图只有 1 张(流程图)进论文,5 张 DRAFT 卡住 | ❌ **绘图是数模灵魂,却最弱** |
| 格式 | markdown→LaTeX,`documentclass` 用默认,无三线表/摘要页/页边距规范 | ❌ **不符合数模格式规范** |
| 连贯性 | 无专门检查;REVIEW 项(未归属数字)与学术式"无证据不进论文"严格门 | ⚠️ 过度学术化,可能拖累数模连贯性 |
| 打磨 | refinement 存在但 0 次触发(consistency REVIEW→CONVERGED) | ❌ **RNN 多 Stage 打磨没真正落地** |

---

## 1. 三个"数模 skill"设计

### Skill A:数模论文格式规范(`mathmodel-format`)

**目标:** 产出的论文符合国赛/MCM 格式硬性规定。

**A1 格式规范包**(`config/mathmodel-format.json`):
- 摘要:单独成页、≤1页、含"模型归类/建模思想/算法思想/模型特色/主要结果"5要素、3-5关键词、**不写公式/表/图**
- 三线表:顶线/栏目线/底线 1.5磅,无竖线,表题在上、编号表1表2
- 图:图题在下、编号图1图2、600dpi PNG、**黑白可区分(线型+图例,非颜色)**
- 公式:居中、右对齐编号、后文引用才编号
- 参考文献:5-10篇、[J][M][D][EB/OL]、英文标点+空格
- 附录:单独成页、含全部可运行代码

**A2 格式检查器**(`PaperFormatChecker`):对 markdown+latex 做确定性检查:
- 摘要是否含禁止元素(公式/表/图)、是否超页
- 表格是否三线表、表题位置
- 图片是否全部引用、图题位置
- 参考文献格式
- 输出 BLOCK/REVIEW 发现(与 consistency 机制一致)

**A3 LaTeX 模板升级**:数模专用 documentclass(`cumcmthesis` 风格 / 自建),含三线表样式、摘要页、页边距 2.5cm、正文≤20页。

### Skill B:绘图风格规范(`mathmodel-plot`)

**目标:** 图好看、数模风格、自动晋升进论文。

**B1 绘图风格包**(`config/plot-style.json` / 一个 `plot_style.py`):
- 统一 matplotlib `rcParams`:字体(中文 SimHei + 数学 Times)、配色(数模常用:蓝/橙/绿/红)、网格、线型循环(实/虚/点/点划,保证黑白可区分)
- 统一尺寸(dpi=600,figsize 规范)、图题字号、坐标轴标签
- 常用图模板:分布直方图、相关性热力图、模型对比柱状/箱线、敏感性折线、工作流/流程图

**B2 图表自动晋升机制**(关键缺口):
- 现状:数据图注册为 DRAFT,**只有流程图为 final**;`promote-figure` 需人工
- 设计:流水线在 paper_ready 通过后,**自动把符合证据门的 DRAFT 图晋升为 final 并嵌入对应章节**(数据分布→data_analysis、对比图→results、敏感性图→sensitivity)
- 晋升条件 = 已有 `paper_ready_approval`(人工已审),即"人工审证据链 + 系统自动嵌图",不增加人工负担

### Skill C:数模连贯性打磨(`mathmodel-coherence`)

**目标:** 从摘要到结论一条主线,符合数模"连贯 > 严谨"。

**C1 连贯性检查器**(`PaperCoherenceChecker`):
- 摘要是否覆盖 5 要素、是否与结论呼应
- 问题重述→假设→模型→结果→结论 是否逐层衔接(问题里提的目标是否都被回答)
- 每节是否有承上启下(节首不突兀、节尾不悬空)
- 符号是否在符号说明中统一定义、全文一致
- 图表是否在正文被引用(而非孤立存在)

**C2 与 RNN 打磨整合**:把 coherence 发现作为 refinement 的 OPEN issue 输入,触发多 Stage 焦点课程:
- Stage 1 coherence(完整/衔接)→ Stage 2 humanize(更像人写)→ Stage 3 figures(嵌图美化)→ Stage 4 notation/latex(公式符号)→ Stage 5 final_polish(降AI痕迹/流程图)
- **修复当前"0 次打磨"缺陷**:consistency/coherence 的 REVIEW 项必须成为 refinement 的 issue,否则 Stage 不启动

---

## 2. 后端流水线集成(改动点)

```
_generate_sections → PaperFormatChecker(软检) → complete_paper_draft
→ PaperCoherenceChecker(生成issue) → consistency(BLOCK才硬停,REVIEW进refinement)
→ refinement(多Stage: coherence→humanize→figures→notation→final_polish)
→ 图表自动晋升 → complete_paper(硬门) → final_review → 数模LaTeX模板 → 投稿
```

关键改动:
1. `_ensure_model_formula` / `_sanitize_internal_refs`(已做)保留
2. 新增 `mathmodel-format` / `mathmodel-plot` / `mathmodel-coherence` 三个模块(纯新增,不破坏既有)
3. `promote-figure` 在 paper_ready 后自动调用(嵌 DRAFT 图)
4. refinement 的 issue 来源:consistency + coherence 合并
5. LaTeX 模板换成数模 documentclass + 三线表 + 摘要页

---

## 3. 多智能体实施分工(帮手全做,Claude 验收)

**分工原则(用户确认):** 帮手全做实现,Claude 管内核保证(证据门/状态机)与验收。实施阶段经 AI Memory 邮箱 + 心跳 + 任务单派单。

| 任务 | 负责人 | 验收标准 |
|---|---|---|
| A 格式规范包(CUMCM 中文 + MCM 英文两套)+ 检查器 + LaTeX模板 | 帮手 1 | 两套格式检查全过、可编译 PDF |
| B 绘图风格 + 图表自动晋升 | opencode | 图好看、6张图全进论文、黑白可区分 |
| C 连贯性检查 + refinement 5-Stage 整合 | 帮手 2(或 opencode) | 多Stage真打磨、摘要到结论连贯 |
| 端到端验收 | Claude | 网页对话→论文→PDF,格式规范、图表齐全 |

**实施顺序建议:** B(绘图,影响最大)→ A(格式)→ C(连贯性打磨)。

---

## 4. 后续实施清单(帮手开工前)

1. 建 `config/mathmodel-format.json`(两套格式规范包)
2. 建 `config/plot-style.json` + `plot_style.py`(统一绘图风格)
3. 新增 `PaperFormatChecker` / `PaperCoherenceChecker`
4. `promote-figure` 在 paper_ready 后自动调用(嵌全部 DRAFT 图)
5. refinement 的 issue 来源合并 consistency + coherence;5-Stage 焦点课程触发
6. LaTeX 模板换成数模 documentclass(CUMCM 中文 + MCM 英文)

---

*设计者: claude_code;参考国赛官方格式规范、math-modeling-skills 的三线表/DOCX、MM-Agent 的 HMML、mathmodel-skill 的竞赛包。*

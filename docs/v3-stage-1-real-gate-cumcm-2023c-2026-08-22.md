# V3 Stage 1 Real Gate — 2023 CUMCM C 当前论文对 2026 标准的基线审计

日期：2026-08-22  
对象：`20260822-CUMCM-0010-K32X`  
论文：`docs/generated_samples/cumcm_2023_c_showcase/workspace/20260822-CUMCM-0010-K32X/paper/submission/cumcm-2023-c-showcase.pdf`

## 结论

Stage 1 的标准重建揭示了一个此前没有被内部 `visual_quality=PASS` 捕获的问题：**当前 PDF 的视觉/论文结构已经能跑通，但“官方提交合规”还不能标 PASS。**

当前状态建议记为：

`FORMAT BASELINE = REVIEW`

不是因为 A4、页数或边距，而是因为官方 2026 CUMCM 对附录源程序和 AI 使用披露提出了明确要求，而当前展示论文尚未把这两类交付物接入最终 submission package。

---

## 已通过的硬项

通过 `pdfinfo` 与当前 XeLaTeX 源配置重新检查：

- PDF 共 19 页，小于 30 页正文上限的风险区间；
- 页面尺寸为 A4（595.28 × 841.89 pt）；
- 文件约 2.67 MB，低于电子论文 20 MB 上限；
- CUMCM exporter 使用 16.0 cm 正文宽度，A4 左右边距约 2.5 cm；顶部配置也按至少 2.5 cm 设计；
- 中文 CUMCM 输出不写 Team Control Number / 学校 / 参赛者身份；
- 当前稿没有目录；
- 电子论文第一页为标题 + 摘要页，正文在摘要之后开始。这与 2026 电子版规则一致：电子论文排除纸质版承诺书与编号页，因此电子版第一页必须是摘要专用页。

这里特别纠正一个容易误判的点：纸质版正文“从第四页开始”是因为第一页承诺书、第二页编号页、第三页摘要页；电子版明确不包含前两页，所以不能机械要求电子 PDF 也空出三页。

---

## 当前 BLOCK / REVIEW 项

### 1. 附录未包含完整可运行源程序与支撑材料文件列表

当前附录主要是完整决策表，没有把本题建模使用的全部可运行源程序代码作为论文附录输出。

2026 CUMCM 官方规范要求附录包括：

- 支撑材料文件列表；
- 建模用到的全部完整、可运行源程序代码；
- 若确实没有使用程序，也应明确说明。

因此当前展示 PDF 如果直接作为正式国赛提交稿，**这一项不能通过。**

后续处理：不要把整个仓库源代码粗暴塞进论文；应建立 `Competition Support Material Builder`，只收集本案例真正参与求解的可复现脚本、配置、数据处理入口和运行说明，并由 provenance / Artifact lineage 自动生成附录文件清单。

### 2. 2026 AI 使用声明尚未进入正式论文

当前稿参考文献前没有 `AI 工具使用声明`。

对于实际比赛使用本工作站的场景，AI 使用是显式存在的，因此不能默认走“未使用 AI”分支。应由 AI ledger 自动生成声明草稿，并在提交前经过人工确认。

### 3. `Details of AI Tool Usage.pdf` 尚未进入支撑材料生成链

项目其实已经存在 `AILedger`，而且字段已经覆盖官方要求的：

- 工具/模型；
- 用途与阶段；
- prompt / interaction；
- 是否采用；
- 是否人工审核；
- 审核说明。

这说明不用重造第二套日志。Stage 1 的正确实现方向是：**从唯一 AI ledger 投影生成官方使用说明，而不是另外维护一个 disclosure 日志。**

### 4. 当前 preflight 仍偏“Markdown/内部占位符检查”，没有真正消费 2026 official standard

旧 `SubmissionService.preflight()` 主要检查 required sections、内部引用泄漏、figure missing 等工程项；它并不知道：

- CUMCM 无目录；
- A4 / margin；
- 电子首页摘要；
- 30 页；
- 20 MB；
- 附录代码与支撑材料列表；
- 2026 AI declaration / details PDF；
- MCM 的 12 pt、25 页、Summary Sheet、header/control number 等。

因此 Stage 1B 新增的 `CompetitionPaperStandardRegistry` 只是第一步；下一次 submission preflight 必须以该 registry 为真源。

---

## 对用户这轮“建模重心”反馈的结构基线

当前稿已经有一个值得保留的进步：Q3 明确写出“继承问题2得到的品类需求和最优加价率”，说明研究状态层已经开始从“每问独立模型”转向“上游模型下沉”。

但人工反馈仍然成立：

- Q1 的核心是 Spearman + 稳健异常/变化扫描，正文较轻；
- Q2 才是核心的需求响应—定价补货联合优化；
- Q3 虽然继承 Q2，但仍用了完整的“变量—模型构造—多条公式—求解—验证—图—表—稳健性”的同规格章节模板，视觉上仍接近“又建立了一个完整模型”；
- 因此“逻辑已继承”与“论文视觉重心已继承”还不是一回事。

这会直接进入下一阶段的 Paper / Model Narrative 规则：后续问若只是核心模型的扩展，默认渲染为 `模型扩展 / 新增约束 / 求解调整 / 结果`，不再重复一套完整核心建模模板。

---

## Stage 1 Gate 判定

### 已完成

- 官方 hard rule 与优秀论文 soft prior 分层；
- 2026 CUMCM / MCM 规则刷新；
- 本地 C 题优秀论文派生 prior 重新读取；
- GitHub 科研智能体机制调研；
- `competition_paper_standard_v2.json` 落盘；
- `CompetitionPaperStandardRegistry` 落盘并接入 `CProblemPaperProfileRegistry`；
- 新标准单测通过；
- 当前 2023C 真实 PDF 重新做官方合规基线审计。

### Stage 1 收口后进入 Stage 2 前必须保留的四个任务

这些不是继续扩大 Stage 1，而是作为后续实现 Gate：

1. submission preflight 消费 official standard；
2. AI ledger → AI 使用声明 / Details PDF；
3. solver/artifact lineage → 可运行源码附录与支撑材料清单；
4. 视觉/建模重心进入 Stage 2/3，不再由“每问同规格模板”决定。

本阶段的最大收获不是新加了多少规则，而是把“看起来像比赛论文”和“真的符合当年比赛提交要求”彻底分开了。

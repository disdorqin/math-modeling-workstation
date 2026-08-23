# 数学建模智能体生态对比报告(2026-08)

**对比对象:** 本仓库 `disdorqin/math-modeling-workstation`(数学建模辅助工作站)
**调研日期:** 2026-08-04
**调研范围:** GitHub 开源数学建模智能体 + 互联网/商业数学建模 AI 产品 + 2026 竞赛官方 AI 规则
**对比性质:** 情报盘点,非基准测试。本文外部项目的功能描述来自其 README / 论文 / 官网,不代表本项目实测结论。

---

## 0. 一句话结论

本仓库在"**证据可追溯、过程可恢复、确定性可复现**"这一维度上是当前开源数模智能体里**机制最硬**的——它把"无证据不进论文"做成了代码约束而非提示词承诺;但在**竞赛规则合规自动化、商用化、社区生态、题型覆盖深度**上落后于一批 2025–2026 年快速迭代的开源项目和商业平台。2026 年国赛 AI 新规(2026-09-01 试行)与 COMAP 的 AI 披露要求,恰好是把本仓库"审计优先"的优势转化为刚需的场景——前提是补上"AI 使用台账与披露材料自动生成"这一环。

---

## 1. 本项目定位快照

| 项 | 值 |
|---|---|
| 仓库 | [`disdorqin/math-modeling-workstation`](https://github.com/disdorqin/math-modeling-workstation) |
| 描述 | Evidence-first, recoverable mathematical modeling workstation |
| 建立 / 最近推送 | 2026-07-21 / 2026-07-28 |
| Star / Fork | 0 / 0(公开但未被社区发现) |
| License | GitHub 未标注 |
| 核心原则 | **No Evidence, No Claim(无证据,不进论文结论)** |
| 已冻结里程碑 | M1(4 智能体建模工作站,`m1-verified-2026-07-28`)、M2(`mathworkstation.m2` B1–B11 竞赛级论文层) |
| 已开放 PR | #2(公开 AI 可读审计网关)、#3(M2 论文层)——均未合并 |
| 架构 | Case/Session/Run 三层隔离 → DAG 状态机 + 人工审批 → Claim/Figure/结果注册表 → 12 节论文 → 一致性门 → 投稿预检 |
| 智能体模型 | 智能体只提「提案」,唯一有写权限的 Adjudicator 复用既有注册表裁决(机制性证据门,不靠提示词自律) |
| 确定性 | 全链路可离线运行(`FakeProvider` 为纯函数);LangGraph 仅作为可选适配器 |
| 测试 | 60+ 测试文件;pytest 全绿(本地) |
| Benchmark | `test_m2_benchmark`(rubric 0–100,阈值 75,实测 100;9 figs / 5 tbls / 12 eqs / 3 candidates) |

---

## 2. 开源数学建模智能体盘点

> 以下 Star/数据为 2026-08-04 调研时点。按社区热度排序。

### 2.1 [jihe520/MathModelAgent](https://github.com/jihe520/MathModelAgent) — 3.2k★ 热度第一

- **定位:** "3 天比赛变 1 小时",自动产出可直接提交的论文。多 Agent(建模手 / 代码手 / 论文手等)+ 多 LLM(litellm 支持所有模型)。
- **执行:** 本地 Jupyter 解释器 + 云端 E2B/daytona;Web Search(Tavily);RAG 知识库(ChromaDB + Rerank);HIL 人机协作(6 种决策:confirm/edit/regenerate/ask/skip/abort);四层容错(有限重试 → Fallback Hand Off → Evaluator Shadow Mode → Feedback Rerun)。
- **现状:** 2026 年中起**从"自研 Web 平台"转向纯 SKILLS 形态**(不再维护 harness),17 套 Typst 论文模板,9 步自动验收,作者声明"实验探索阶段,直接拿它国赛获奖不可能"。
- **License:** 自定义——**个人免费,禁止商业用途**(商业需联系作者)。
- **运营:** 作者托管在线版 [`mathmodel.top`](https://mathmodel.top/home)。
- **与本项目关系:** 既有 docs 里的评估已把它列为借鉴对象(角色契约);它的 HIL 6 决策动作 ≈ 本项目的审批门,但它的"证据保证"更多依赖提示词。

### 2.2 [usail-hkust/LLM-MM-Agent(MM-Agent)](https://github.com/usail-hkust/LLM-MM-Agent) — 625★ 最接近科研对标

- **定位:** 港科广 usail 实验室,**NeurIPS 2025** 论文(arXiv 2505.14148)。模拟人类真实建模全流程,四阶段:问题分析 → 数学建模 → 计算求解 → 报告生成。
- **创新点:** **HMML(层级数学建模方法库)**——Domain/Subdomain/98 个 method node 三级知识库 + actor-critic 检索;"MLE-Solver" 自主生成并迭代代码。
- **竞赛实证:** 辅助 2 支本科生队在 **MCM/ICM 2025 获 Finalist**(Top 2.0% / 27,456 队)。
- **Benchmark:** 自带 **MM-Bench**——111 道 MCM/ICM(2000–2025)题目 + 数据集 + LLM 判分脚本。这是目前开源数模智能体里唯一成规模的公共 benchmark。
- **产品形态:** HuggingFace Space 在线体验;2026-05 开源本地 Demo(Next.js + FastAPI + BYOK + E2B 沙盒),保留了生产级 Web 结构(曾托管 `cdn.mmagent.top`,服务器到期已下线)。
- **License:** README 徽章 CC BY-NC 4.0,仓库侧栏标 GPL-3.0(不一致,需注意)。
- **对比:** 与本项目最相似——都强调"过程"而非"一次生成";但它把保证放在方法库和 LLM 判分,本项目把保证放在确定性证据门与可复现测试。

### 2.3 [handsomeZR-netizen/mathmodel-skill](https://github.com/handsomeZR-netizen/mathmodel-skill) — 173★ 最贴合 2026 新规

- **定位:** harness-agnostic 的**结构化建模工作流**(Claude Code 与 Codex 均可),10 阶段主流程 + 4 层反馈(L1–L4),核心是 `state/decision_log.json` 共享决策日志(跨工具接力)。
- **合规能力(独有):** **AI 使用台账 + `render_ai_usage.py` 披露生成器**——CUMCM 自动生成"AI 工具使用声明/支撑材料 PDF",MCM 报告自动接入主模板。**直接命中 2026-09-01 生效的国赛 AI 新规。**
- **竞赛包:** CUMCM(91 篇 2023–2025 获奖论文蒸馏,59 篇有效,42 项反模式检查)/ MCM(COMAP 2027 页数与 AI 披露基线)/ 电工杯;经验分位只作参照,明示不预测奖项。
- **工程质量:** 显式 section marker 防漏引用、fail-closed 渲染、per-Qi 加权评分(最低分不被均分掩盖)、`doctor.py` 环境预检、CI + 单测。
- **License:** MIT。
- **对比:** 与本项目哲学高度重合("能自动验证的不依赖记得检查""局部错误局部修复"),并且比本项目更早、更完整地解决了"AI 披露合规"。这是本项目**最值得吸收的对手**。

### 2.4 [xuec699-sudo/math-modeling-skills](https://github.com/xuec699-sudo/math-modeling-skills) — 116★ 工业级 Codex skill

- **定位:** "工业级数学建模竞赛 Agent",支持国赛/五一赛/美赛。双模式(Autopilot 全自动 / Manual 人工强制检查点)+ Friendly Mode(编号选项推进,不敲命令)。
- **质量门:** 六维选题评估、模型依赖 DAG、**G1–G6 gate 契约**(enter_condition / pass_criteria / fail_fallback)、**frozen_numbers 冻结数字 + 3 步 refreeze 协议 + 过期检测**、5 人评审团(≥65 放行)、7 类学术诚信阻断检查、9000 实质字下限、`build_docx.py`(LaTeX→OMML 原生 Word 公式、国赛三线表)。
- **License:** MIT。吸收自 `mathmodel-skill` 与 `XiaoMaColtAI/math-modeling-skill` 的思路(未复制文本)。
- **对比:** "frozen_numbers + G4 过期检测 + P1 变更传播规则"与本项目"论文一致性门 + SHA-256 冻结"目标一致,但实现为脚本纪律(仍需 LLM 自觉执行),本项目则是状态机机制强制。

### 2.5 其他参考

- **XiaoMaColtAI/math-modeling-skill** — 三角色协作、Figure Contract、Claim-Evidence 写作(被 2.4 借鉴)。
- **MathModelPilot**(Trae 论坛):六阶段(读题/建模/编码/图表/论文/审计)五 Agent,适用于国赛/美赛/校内赛。
- **MathHub**(React+Express 社区平台):数学模型库 + 竞赛信息 + AI 建模助手(接入通义/Gemini)。

---

## 3. 商业 / 互联网数学建模 AI 盘点

> 现状判断:2026 年**尚不存在**真正成熟的"数模竞赛专用 SaaS",商业价值主要落在四个形态。这本身是一个值得观察的窗口期。

### 3.1 消费级数学智能体(垂直 Agent 商业化样板)

- **华为小艺 IMO 2026 满分智能体**([报道](https://www.geekpark.net/news/367849)):2026-07-21 受邀参加 IMO 2026,以 **42/42 满分**夺得金牌,是首个全题满分攻克 IMO 的 AI 智能体。
  - 架构:**"通用基座模型 + 垂直场景 Agent"**,多 Agent 扮演策略提出者 / 对手 / 裁判;闭环为"提出猜想 → 环境执行 → 反例攻击 → 策略修正";几何证明同时探索纯几何 / 复数 / 坐标多路线并由 Verifier 交叉验证;长程证明用"证明状态图"记录引理与失败路径。
  - 商业化:2026-07 底面向消费者开放,应用于小艺智慧大脑 / 小艺 Claw。
  - **对本项目的启示:** IMO 是纯数学竞赛,数模是应用数学——但"多路线探索 + 交叉验证 + 状态图"的 Agentic 架构,与本项目"候选模型 fan-out + 证据验证 + DAG 状态"同构,说明这条技术路线是行业共识。

### 3.2 开源 Agent 的托管在线版

- **MathModelAgent → mathmodel.top**:作者自托管在线版(邀请制体验)。
- **MM-Agent**:曾托管 `cdn.mmagent.top`(服务器到期下线),现 HF Space 体验 + 开源 Demo。
- 特征:开源引流 → 托管变现(邀请码 / 服务账号)是当前主流路径;服务器成本与合规(数据出境、竞赛规则)是硬约束。

### 3.3 数模流水线里被广泛使用的商业分析 SaaS

- **SPSSAU / SPSSPRO**:在线统计分析平台,国内数模参赛者高频使用(问卷、检验、回归"点几下出结果+文字解释")。它们不是端到端 Agent,而是承担"数据分析层"的商业组件。
- 定位关系:此类工具解决"分析怎么做",本项目和开源 Agent 解决"从题到论文的流程怎么组织"。

### 3.4 企业级赛事/平台

- 满帮首届 Agent 算法大赛(2026-06 南京,1284 人 / 963 队,物流智能体建模);第六届国际供应链建模设计大赛首设"智能体建模专项赛道"——数学建模 + Agent 正在成为产业赛事本身的内容,说明该能力有真实商用需求。

---

## 4. 政策背景:为什么"审计优先"现在是刚需

### 4.1 2026 国赛 AI 新规(全国大学生数学建模竞赛,2026-09-01 试行)

来源:[全国大学生数学建模竞赛人工智能工具使用规定(2026 年试行)](https://www.cmathc.org.cn/mcm/tz/602.html)。要点:

1. 适用范围:大语言模型、生成式 AI、代码辅助工具、**AI 智能体**。
2. 核心建模与分析**必须由参赛队主导**;AI 参与内容须**逐项人工审查核实**。
3. 论文参考文献前须设"**AI 工具使用声明**"(使用/未使用二选一)。
4. 使用 AI 须在支撑材料附"**AI工具使用详情.pdf**":工具名称/版本、使用目的与环节、提示方式与交互示例、采纳与人工修改核验情况。
5. **故意隐瞒、虚假声明、把未人工审查的 AI 生成内容直接当核心成果 → 取消评奖资格。**

### 4.2 COMAP MCM/ICM AI 政策

- 使用 AI 的队伍须在 25 页正文后追加"**Report on Use of AI Tools**"(无页数限制、不计入 25 页),须说明用了什么模型、什么用途、典型 query 与完整输出;未披露使用 AI 可能被判定抄袭/取消资格。
- 官网政策按届更新(2027 指令已纳入 mathmodel-skill 的竞赛包基线)。

### 4.3 对本项目的影响

这两条规则把"可追溯"从锦上添花变成了**参赛资格前提**。而本项目恰恰以审计为核心资产:

- Case 目录里已有 `decisions.jsonl`、JSONL 日志、审批人/理由、产物 SHA-256 —— 天然是"AI 使用详情.pdf"的内容来源;
- **但当前缺口明确:** 没有"AI 使用台账"命令,没有 `render_ai_usage` 这类披露生成器,也没有在提交门里强制校验披露。mathmodel-skill(v6.1)已经做了,这是本项目最直接可补的 feature。

---

## 5. 关键维度对比表

| 维度 | **本项目(workstation)** | MathModelAgent | MM-Agent | mathmodel-skill | math-modeling-skills |
|---|---|---|---|---|---|
| 热度 | 0★(未推广) | 3.2k★ | 625★ | 173★ | 116★ |
| License | 未标注 ⚠️ | 自定义(禁商用) | CC BY-NC/GPL ⚠️ | MIT ✅ | MIT ✅ |
| 形态 | CLI + Streamlit + Docker | Web + SKILL | Web 平台 + 开源 Demo | Codex/Claude Code skill | Codex skill |
| 证据保证方式 | **机制强制**(Adjudicator 唯一写权限 + 注册表 + SHA-256) | 提示词 + 四层容错 | HMML 方法库 + LLM 判分 | decision_log + 脚本重算评分 | frozen_numbers + 脚本门控 |
| 无 Key 离线可复现 | **✅ 全链路 FakeProvider 确定性** | ❌ 需 LLM | ❌ 需 LLM(判分也需 Key) | ❌ 需 LLM | ❌ 需 LLM |
| 端到端测试套件 | **60+ 测试文件 + CI + 非回归** | 少量 | 有(判分为主) | CI + 单测 | test_gate.py 等 |
| 竞赛 Benchmark | 自建 rubric benchmark(实测 100) | 无 | **MM-Bench 111 题** ✅ | 经验分位(非官方) | 无 |
| 竞赛格式深度 | 12 节通用结构 + 五类题型插件 | 17 套 Typst 模板 | 一般 | **CUMCM/MCM/电工杯模板 + 页数/匿名/AI 披露门** | **国赛三线表 + 9000 字门 + DOCX** |
| **2026 国赛 AI 合规** | **缺披露生成器** ❌ | 无 | 无 | **✅ AI 台账 + 披露 PDF** | 学术诚信门(部分覆盖) |
| 商业化 | 无(个人/研究) | 托管在线版 | 曾托管(已下线) | 无 | 无 |
| 最大短板 | 社区冷、无竞赛格式/合规闭环 | 实验阶段、证据靠提示词 | 许可证混乱、需 Key | 依赖外部 harness | 依赖 Codex |

---

## 6. 本项目的相对优势(在生态里的不可替代位置)

1. **机制级证据门是唯一一家。** 其他项目(包括评分最像的 math-modeling-skills)都依赖"脚本 + 提示词纪律"来保证数字可追溯;本项目把"任何写操作必须经 Adjudicator 且背后要有 paper_eligible 证据"做进状态机,编造数字在机制上进不了论文。这是可从 CI 里证明、且可对外声称的硬差异。
2. **确定性离线可复现领先。** `FakeProvider` 纯函数 + 60+ 测试 + 端到端 smoke,意味着本项目是唯一能声称"无 API Key、无网络、可复现全链路"的数模智能体——这对 CI、审计、教学、以及"AI 使用详情"举证都是直接优势。
3. **与 2026 AI 新规天然契合但未落地。** 审计记录已存在,缺的只是"披露生成"这一层胶水。

## 7. 差距与可借鉴项(按优先级)

| 优先级 | 差距 | 借鉴来源 | 建议 |
|---|---|---|---|
| P0 | 无 AI 使用台账/披露生成器 | mathmodel-skill `render_ai_usage.py` + COMAP/CUMCM 规则 | 在 `mathworkstation.m2` 增加 `ai-usage-ledger` 命令,从 decisions.jsonl/审批记录生成"AI工具使用详情.pdf"与声明段,并纳入提交门校验 |
| P1 | 竞赛格式深度不足(三线表/页数/匿名门) | math-modeling-skills `build_docx.py` + mathmodel-skill competition packs | 把 M2 的 profile 机制扩充为国赛/美赛级模板 + 格式门(页数、匿名、图表规范) |
| P2 | 无成规模公共 Benchmark | MM-Agent **MM-Bench(111 题)** | 建立跨题型 benchmark(仓库 roadmap 已列为优先),并发布基于 MMBench 的对比结果 |
| P2 | License 未标注 | 各 MIT 项目 | 尽快选择并声明(当前 0★ + 无 License 会挡住合作/引用) |
| P3 | 社区冷、无托管体验 | MathModelAgent mathmodel.top | 复用 Track A 的 `public-site` 网关做 AI 可读落地页,或发布 Docker 一键体验 |

## 8. 结论

2025–2026 年,数模智能体从"prompt 拼盘"进化为"带证据门的工程流水线"(MathModelAgent → mathmodel-skill/math-modeling-skills 的门控与台账),而 MM-Agent 证明这条路能产出 Finalist,华为小艺证明 Agentic 架构在极限数学上能满分。**本仓库走的是同一条路,但把保证层做得比谁都硬(机制化、确定性、可复现),代价是竞赛格式与合规闭环落后一拍。**

2026-09-01 国赛 AI 新规是本项目的顺风局:规则要求的正是本项目最擅长的"逐项人工审查 + 可追溯 + 披露"。补齐 AI 使用台账/披露生成(P0)后,本仓库在"合规 + 可复现"象限内没有直接对手,且天然适合作为参赛队必须公开提交的"AI 使用详情"的生成基础设施。

---

## 9. 主要来源

- 项目自身:README.md、docs/M2_FINAL_REPORT.md、docs/multi-agent-architecture.md、docs/open-source-evaluation.md、docs/open-source-pattern-synthesis.md
- [jihe520/MathModelAgent](https://github.com/jihe520/MathModelAgent)(含 mathmodel.top)
- [usail-hkust/LLM-MM-Agent](https://github.com/usail-hkust/LLM-MM-Agent) + [MM-Bench](https://github.com/usail-hkust/LLM-MM-Agent/tree/main/MMBench) + [arXiv 2505.14148](https://arxiv.org/abs/2505.14148)
- [handsomeZR-netizen/mathmodel-skill](https://github.com/handsomeZR-netizen/mathmodel-skill)
- [xuec699-sudo/math-modeling-skills](https://github.com/xuec699-sudo/math-modeling-skills)
- [全国大学生数学建模竞赛人工智能工具使用规定(2026 年试行)](https://www.cmathc.org.cn/mcm/tz/602.html)
- [COMAP 美赛 AI 政策解读(中文)](https://mcmicm.org.cn/news/913.html)
- [华为小艺 IMO 2026 满分(极客公园)](https://www.geekpark.net/news/367849)、[IT168](https://digital.it168.com/a2026/0722/6942/000006942517.shtml)
- [MathModelAgent 解析(百度开发者)](https://developer.baidu.com/article/detail.html?id=6021945)
- [满帮 Agent 算法大赛(金陵晚报)](http://jlwb.njdaily.cn/html/2026-06/30/content_550_271046.htm)、[澳科大智能体专项赛](https://msb.must.edu.mo/news/article/view/id-41319.html)

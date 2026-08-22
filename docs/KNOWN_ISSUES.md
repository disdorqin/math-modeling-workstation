# KNOWN_ISSUES

## KI-001 — P0：多个 subproblem 被单一 ModelPlan / best model 压扁

状态：RESOLVED IN NEW RESEARCH-STATE PATH  
影响：Competition quality / correctness  
首修 Section：1

症状：ProblemAnalysis 能识别多个子问题，但后续主链仍主要围绕一个模型计划与比较，`SubproblemAnswerRecord` 容易共享同一 best model / primary metric。

真实证据：2023 MCM Wordle 的 SP1-SP6 在最终论文中没有形成六条独立研究链。

---

## KI-002 — P0：Wordle 任务类型与验证协议不匹配

状态：RESOLVED FOR CURRENT SOLVER/VALIDATION PATH

论文数据分析明确发现日序列存在显著自相关/结构变化，但主模型仍采用 random split；说明 validation 当前主要跟随通用 ModelPlan，而不是 subproblem task family。

计划：Section 4 ValidationProtocol Registry；Section 1 先让 task family 独立化。

---

## KI-003 — P0：Paper Engine generic template pollution

状态：RESOLVED FOR WORDLE RESEARCH-STATE PAPER / OPEN FOR GENERALIZATION

2023 Wordle final.md 出现 `x_t/y_t/z_t`、`A_t/B_t`、状态转移方程、kWh/kW/CNY 等题目无关模板。

计划：Section 6 从 accepted Research State 构造符号/公式/单位，禁止无来源模板注入。

---

## KI-004 — P1：内部 registry ID 泄漏到最终论文

状态：RESOLVED IN NEW RESEARCH-STATE PAPER / LEGACY PAPER PATH STILL EXISTS

Wordle final.md 中可见 `claim-*`、`result-*`、`table-*` 等内部 ID。

计划：Paper Engine / export sanitation hard gate。

---

## KI-005 — P1：References 质量不足

状态：PARTIAL — VERIFIED METHOD BIBLIOGRAPHY SEEDED / DOMAIN COVERAGE OPEN

此前审计发现真实论文 References 缺少具体、可核验的高质量来源，甚至用方法论框架替代正式文献。

计划：Section 6/7 建真实 source registry 与 bibliography gate。

---

## KI-006 — P1：完整 pytest 被旧 Tenacity 阻塞

状态：OPEN / ENVIRONMENT

当前：Python 3.11.9 + Tenacity 5.1.5。`tenacity._asyncio` 仍使用已移除的 `asyncio.coroutine`，导致 LangGraph 相关测试 collection error。

当前 full pytest：2 collection errors。  
当前 Section 1–6 核心定向组：49 passed；受保护 legacy WIP 回归组：31 passed。

处理原则：独立修复依赖，不在 Section 1 混入大范围环境升级。

---

## KI-007 — P1：CodeGraph 当前存在 pending changes

状态：OPEN / OPERATIONAL

`codegraph status` 当前存在大量 Added/Modified pending changes。图谱仍可用于定位，但对本轮新/dirty 文件必须核验 current on-disk source。大改后再考虑 sync/index。

---

## KI-008 — P1：大量受保护未提交 WIP

状态：OPEN / OPERATIONAL

`auto_pipeline.py`、`paper_contracts.py`、`refinement.py`、`agents/modeling.py` 与对应 tests 已修改；excellent comparator / recurrent workstation / model decision 等存在 untracked WIP。

禁止 reset/clean/restore-all/checkout overwrite。

---

## KI-009 — P2：优秀论文 comparator 存在历史 self-validation 风险

状态：MITIGATED FOR SECTION 6 / FULL-TEXT CORPUS STILL OPEN

此前并未真正读取本地优秀 PDF 全文，却产生过“接近优秀论文”的对比结论。

计划：Section 7 真实全文 corpus + external benchmark。

---

## KI-010 — P2：旧 benchmark 100/100 容易被误解

状态：DOCUMENTED

M2 100/100 是 synthetic + FakeProvider + deterministic rubric，只可用作 regression baseline。已在 benchmark spec 中正式降级。

---

## KI-011 — P1：当前优秀论文资料仍是提炼稿，不是全文 external corpus

状态：OPEN

`config/ref_models/excellent_c7/` 的 11 份资料已在 Section 6 用作跨年份结构/叙事先验，并加入中英语义代理降低假阳性；但文件本身明确是“提炼稿”。

真实全文资料仍位于：

`D:\作业\竞赛\大学生数学建模\美赛\备赛\资料`

当前 DevSpace allowed root 不能直接读取。没有解决全文访问前，不允许把当前 0 BLOCK / 0 REVIEW internal Gate 宣称为 O/F 级认证。

---

## KI-012 — P2：替代方案比较主要仍是 feasibility comparison

状态：OPEN

Section 6 已把 ProblemGraph / ModelingBrain 的 alternative candidates 投影进论文，并明确 PASS / NEEDS_SOLVER / REJECT / PLANNED；未执行候选不再伪造性能指标。

但并非每个 subproblem 都已有多个可执行方案的 head-to-head experiment。优秀论文常见的“多方案对比”下一阶段应在确有研究价值时回 Section 2–4 补实验，而不能靠 Paper Engine 造数。

---

## KI-013 — P2：Research-State paper prose 仍偏 deterministic

状态：OPEN

当前 renderer 已解决结构、证据边界、公式、假设、图表目的、references P0，但语言成熟度仍主要由确定性模板拼装。下一步需要 evidence-locked prose writer / reviewer，在不允许新增数字、模型、引用的前提下提升摘要压缩、段落过渡、叙事自然度与竞赛论文语气。

---

## KI-014 — P1：legacy M2 rubric 仍用“数量配额”奖励公式、图、表和候选模型

状态：OPEN / CONTRADICTS V3 STANDARD

`src/mathworkstation/m2/rubric.py` 当前仍把 `>=12 equations`、`>=8 figures`、`>=5 tables`、`>=3 candidate families` 写入 deterministic score；`m2/agents.py` 和 `m2/benchmark.py` 也保留同类目标。

这与 2026-08-22 人工审阅和本地优秀论文重新调研后的结论冲突：公式数量不等于建模深度，图数量不等于视觉质量，候选模型数量不等于研究严谨性。继续保留这些目标会反向诱导系统制造“公式臃肿、表格太多、算法动物园”。

处理原则：M2 已按 D002 降级为 regression evidence。V3 后续应把这些 quantity quota 改成 evidence coverage / figure purpose / model clarity / traceability 等能力指标，不能再反馈到主 Paper Engine。

---

## KI-015 — P0：2026 CUMCM official submission support materials 尚未闭环

状态：OPEN / OFFICIAL COMPLIANCE

当前 2023C 展示 PDF 的 A4、电子首页、页数、大小和无目录等基础项通过，但正式提交链尚缺：

- 论文附录中的支撑材料文件列表；
- 本案例实际使用的完整可运行源程序代码；
- 使用 AI 时参考文献前的 `AI 工具使用声明`；
- 由唯一 `AILedger` 投影生成的 `Details of AI Tool Usage.pdf`。

这些属于 2026 CUMCM 官方硬规则，优先级高于优秀论文视觉先验。后续 submission preflight 必须从 `competition_paper_standard_v2.json` 消费规则，而不是只检查 Markdown 内部占位符。

---

## KI-016 — P1：GPT Image → PPT MCP → Render → Vision Review 尚未在本机真实闭环

状态：PARTIAL / BACKEND MISSING

Research workflow 已能生成 Visual Intent、backend-neutral brief、AI-image candidate request 和 PPT MCP handoff，且新增 rendered-image visual review artifact/gate；但当前本地 `config` 只有 image route example，没有已配置可执行 image route，DevSpace 会话也没有 PowerPoint MCP tool。因此真实 2023C 仍以 deterministic SVG/PNG 为 paper-safe fallback。

处理原则：不能因为 handoff/schema 已存在就宣称 AI/PPT 链路已完成。接入可用 image route 和 PPT MCP 后，必须跑一次真实候选 → 可编辑重绘 → render → vision/human PASS 的端到端验收。

---

## KI-017 — P2：ModelSpine 已接入 CUMCM renderer，但 MCM renderer 仍保留旧“各问独立”叙事

状态：OPEN / GENERALIZATION

当前 ModelSpine 已在 ResearchStatePaperService 全局生成并持久化，但 CUMCM renderer 首先消费了 role、inheritance 与 Formula Budget；英文 MCM renderer 仍有历史文案 `each question is solved and validated independently`，尚未完全利用 foundation/core/extension/synthesis 结构。

后续应把同一 ModelSpine 以英文比赛语气投影到 MCM-C，保持 Research State 共用、Paper Profile 分叉的 D032 原则，而不是建立第二套研究逻辑。

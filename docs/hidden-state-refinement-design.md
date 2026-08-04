# 隐藏状态精修设计(Hidden-State Refinement)

**灵感来源:** 用户的 RNN / GRU / LSTM 类比。神经网络按新输入反复更新内部权重以逼近曲线;本项目用 **M 个 Stage 反复打磨同一篇论文**,而非另起炉灶写 M 篇。
**性质:** 设计文档。将现有 `refinement_loop`(src/mathworkstation/refinement.py)从"循环修补"升级为"显式隐藏状态机"。
**状态:** 待评审(2026-08-04,用户出门期间记录)。

---

## 1. 用户的原始想法(记录,不歪曲)

> 像神经网络里的 RNN / GRU / LSTM,它们不断根据新输入反复更新内部权重,达到精准曲线拟合。这个项目也是:
> - 设置 **M 个 stage**,每个 stage 执行的论文流程**一样**(覆盖全流程),但能对论文优化打磨。
> - Stage 1: 完成一篇论文草稿(覆盖全流程各环节)。
> - Stage 2: 对论文一部分更新,让论文更像人写的。
> - Stage 3: 加一些图表。
> - Stage 4: 让文字更贴合,不只是 MD,写成 LaTeX。
> - Stage 5: 最后打磨——语言逻辑问题、更严谨、降低 AI 查重率、绘制最终流程图,形成完整论文。
> - 关键: 这是一个"前后交流"的过程,交流状态叫**隐藏状态**。
>
> 三个问题:
> 1. 如何做到一个完整 Stage 覆盖论文全流程?(不同 Stage 只是同一流程循环几次)
> 2. 如何做到每个 Stage 是"更新"而非"另起炉灶"?(5 个 Stage 不该等于写 5 篇论文;理想是 5 次打磨 1 篇)
> 3. 几个 Stage 之间如何交互?(即隐藏状态;LSTM/GRU 的隐藏状态是原地更新的;设立**专属存储文件夹**放置 Stage 间交流信息,可更新)

---

## 2. 现有代码对照:三个问题的现状

### 问题 1"完整 Stage 覆盖全流程" — ✅ 已部分实现,需强化

现有 `refinement_loop` 的每个 Stage 已执行**全论文审计**(见 `docs/agent-handoff.md`):
> Every refinement Stage must perform a full-paper audit even when the edit
> budget only permits local changes — 检查所有章节、子问题契约、结果/表格/图表/引用记录、模型公式、实验日志,再选择最高价值缺陷做有界修改。

即:每个 Stage **评估整篇论文**(`PaperQualityEvaluator.evaluate` 对全部 section 打分),但**只补丁局部**(1–2 个章节)。这正是"同一流程覆盖全流程"——已成立。

**强化点:** 把"评估整篇 + 修补局部"从隐性约定变为**显式 Stage 合约**,并让每个 Stage 的**聚焦目标**(coherence / figures / notation / language / flowchart)成为可配置的 Stage policy(见第 4 节)。

### 问题 2"更新而非另起炉灶" — ✅ 已实现,需固化为契约

现有机制已经做到:
- 只修改 `paper/current.md`;候选稿只有通过硬门控且改善目标质量维度才成为新 `current.md`(`RefinementService` 接受/回滚);
- 历史完整保留:`paper/versions/`、`paper/patches/`、`refinement/history.jsonl`;
- **冻结已验证内容**:数字 token、Claim ID、Figure ID、章节证据范围、合成数据披露,Stage 内不可变。

即"5 个 Stage = 5 次打磨同一篇论文"已经成立。

**强化点:** 把"同一篇论文"的连续性写进隐藏状态(见第 3 节),让下游 Stage 明确知道"这是第 N 次打磨,不是重写"。

### 问题 3"隐藏状态交流层" — ❌ 未实现,是本次设计的核心新增

现有持久化分散在多个文件(`memory/frozen_facts.json`、`memory/frozen_evidence.json`、`refinement/history.jsonl`、`refinement/stages/stage-NNN/`),**没有一个统一的、可原地更新的"隐藏状态"文件**来承载 Stage 间交流的紧凑摘要。

**本次新增:** 一个专属、可更新的存储文件 `refinement/hidden_state.json`,作为 LSTM 细胞状态 / GRU 隐藏状态的类比。

---

## 3. 核心新增:隐藏状态文件

位置:`<case_root>/refinement/hidden_state.json`(随每个 Stage 原地更新,类似 LSTM 细胞状态 c_t 的更新)。

```json
{
  "schema_version": 1,
  "epoch": 3,
  "paper": {
    "paper_id": "paper-...",
    "current_md_sha256": "...",
    "version_id": "v3",
    "accepted_stages": [1, 2, 3],
    "rejected_stages": []
  },
  "frozen": {
    "number_tokens": {"section_a": ["1.23", "45.6%"]},
    "claim_ids": ["claim-..."],
    "figure_ids": ["figure-..."],
    "evidence_scope": ["..."],
    "synthetic_disclosure": true
  },
  "quality": {
    "problem_coverage": 0.81,
    "evidence_alignment": 1.0,
    "data_reasoning": 0.77,
    "model_logic": 0.85,
    "result_explanation": 0.8,
    "figure_alignment": 0.6,
    "abstract_quality": 0.72,
    "writing_quality": 0.68,
    "total": 0.778
  },
  "issues": {
    "resolved": {"issue-1": "stage=2 fixed", "issue-3": "stage=3 fixed"},
    "open": ["issue-5", "issue-8"]
  },
  "focus": "figures_and_tables",
  "memory": "第3次打磨：已完成完整性与图表补强；下一篇聚焦 notation/LaTeX；已冻结数字与证据，语言维度待提升。",
  "deltas": [
    {"stage": 1, "focus": "coherence", "accepted": true, "total_delta": 0.05},
    {"stage": 2, "focus": "figures_and_tables", "accepted": true, "total_delta": 0.03},
    {"stage": 3, "focus": "notation_and_latex", "accepted": true, "total_delta": 0.02}
  ]
}
```

**更新规则(类似 LSTM 门控):**
- **读**:Stage 启动时读 `hidden_state.json`,获得冻结集、质量向量、未决问题、焦点、记忆摘要;
- **写**:Stage 结束后**原地更新**同一文件(不是新建),记录本次 delta、关闭/新增 issue、更新 quality、追加 memory 摘要;
- **冻结保护**:`frozen.number_tokens/claim_ids/figure_ids` 只增不改;若某 Stage 想改已冻结内容 → 硬门 `VERIFIED_NUMBERS_CHANGED` 拒绝(与现有 `PaperQualityEvaluator` 一致)。

**"记忆"字段的定位:** 它是 LSTM 细胞状态意义上的**紧凑摘要**,不是原始上下文——用一两句话概括"论文现在是什么、改了什么、下一步是什么",避免把整篇论文塞进 context(呼应项目铁律:不把 LLM 上下文当持久记忆)。

---

## 4. Stage 课程(聚焦策略,把用户的 5 阶段显式化)

用户描述的阶段主题 → 固化为 Stage 焦点集合,每个 Stage 从隐藏状态读当前焦点,完成该焦点维度后在隐藏状态更新下一焦点(类似 RNN 逐层逼近):

| Stage 序号 | 焦点 focus | 目标(对应质量维度) |
|---|---|---|
| 1 | `coherence` | 完整性、子问题闭环、章节齐全(problem_coverage / evidence_alignment) |
| 2 | `humanize` | 写作自然度、去模板化空话(writing_quality) |
| 3 | `figures_and_tables` | 图表入文、图表解释(figure_alignment) |
| 4 | `notation_and_latex` | 公式、符号一致性、LaTeX 排版(notation_consistency / model_logic) |
| 5 | `final_polish` | 语言逻辑严谨、降低 AI 痕迹、最终流程图、完整论文(final_review 门) |

焦点轮转可配置;若某个焦点 Stage 无改进(无 delta),允许跳到下一焦点而非卡死(与现有 `patience` / `max_no_progress_attempts` 一致)。

---

## 5. 开源智能体融合点

| 来源 | 吸收点 | 落到本项目 |
|---|---|---|
| mathmodel-skill(handsomeZR) | `decision_log.json` 共享决策日志 + `refine_partial`(局部回修) | 隐藏状态文件即本项目版 decision_log;`refine_partial` 已在 Stage 5 按 Qi 局部修补 |
| math-modeling-skills(xuec699) | G1–G6 门控 + `frozen_numbers` + 3 步 refreeze + P1 变更传播 | 隐藏状态 `frozen` 块即 frozen_numbers;refreeze 协议与现有硬门一致 |
| AI-Scientist(Sakana) | idea→experiment→plots→paper→review 闭环 | 已有 artifact 链;隐藏状态把 review 结果固化进 memory |
| MM-Agent(HKUST) | HMML 方法库 + 代码迭代自改进(MLE-Solver) | Stage 3/4 的"加图表/改 LaTeX"可由 HMML 式方法目录提供合法模板 |
| AgentLaboratory | 分阶段文献/实验/报告 | 与本项目 evidence→paper 链一致 |
| 华为小艺 IMO Agent | 多路线探索 + 反例攻击 + 状态图 | 隐藏状态 = "证明状态图"的数模版:记录每 Stage 的关键结果与失败路径 |

> 设计原则不变:**隐藏状态承载的是"流程记忆与冻结摘要",绝不承载未经证据的数值**;数值永远来自证据注册表,不来自模型或记忆。

---

## 6. 与现有 `refinement.py` 的关系(最小侵入)

- **不重写** `RefinementService` / `PaperQualityEvaluator` / `IssueRegistry`;它们已被 60+ 测试保护。
- 新增:
  1. `HiddenState` 类(`src/mathworkstation/refinement_hidden_state.py`)——读/写/校验 `refinement/hidden_state.json`;
  2. `StageFocusPolicy` —— 把"焦点轮转"变成可配置策略;
  3. `RefinementService` 内一个可选 hook:Stage 开始读隐藏状态、结束写回(默认关,不破坏现有行为与测试);
  4. 一组确定性测试:隐藏状态原地更新、冻结只增不改、焦点轮转、Stage 拒绝不回退隐藏状态。
- **与 Web 对话层联动:** 网页上可看到"当前第 N 次打磨、焦点=图表、质量向量、已冻结证据";审批门(paper_ready/final_review)在隐藏状态进入 final_polish 时触发。

---

## 7. 实施排期(接入 S1/S2/S3 之后)

| 阶段 | 内容 | 前置 |
|---|---|---|
| H1 | `HiddenState` 类 + 读写/校验 + 确定性测试 | 本设计冻结 |
| H2 | `StageFocusPolicy` 焦点轮转 + RefinementService 可选 hook | H1 |
| H3 | 隐藏状态 → Web 展示(质量向量/焦点/已冻结)+ 审批联动 | S2/S3 |
| H4 | HMML 式模型/模板目录辅助 Stage 3/4(可选) | 设计评审 |

---

*设计者: claude_code,记录自用户 2026-08-04 的 RNN/GRU/LSTM 灵感;融合 mathmodel-skill / math-modeling-skills / AI-Scientist / MM-Agent / AgentLaboratory 开源思路。*

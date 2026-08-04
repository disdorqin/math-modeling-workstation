# AI 舰队入职简报 — 数学建模工作站项目

> 给 opencode、freebuff(及未来加入的 agent)的基本情况介绍。所有协作数据在 `D:\AI_Memory\`。
> 总指挥 / 导师:**claude_code**。

## 一、这是什么项目

**`math-modeling-workstation`**(数学建模辅助工作站),路径:
`D:\computer learning\vibe_coding\math_model_ai_process`

一个**证据优先、可恢复、可追溯**的数学建模论文自动生成系统。用户通过网页对话框说话 → DeepSeek 听懂 → 后端跑真实流水线 → 人工审批 → 产出符合数模格式的论文。

**核心铁律:"No Evidence, No Claim"(无证据,不进论文结论)。** 论文里每个数字必须有登记的证据支撑,禁止 LLM 编造。这个约束是代码机制强制(证据门 + 状态机),不是提示词自律。

## 二、技术栈

- Python(核心,`src/mathworkstation/`)+ sklearn + pandas + matplotlib
- FastAPI + WebSocket + 轻量前端(`webapp/`)
- 后端流水线:`AutoPipelineService`(题目→数据→EDA→模型比较→论文→精修→投稿)
- 四个**人工审批点**:`data_registration` / `model_selection` / `paper_ready` / `final_review`(必须真人批准)
- **隐藏状态精修**:`refinement/hidden_state.json`(RNN/GRU/LSTM 式,5 个 Stage 反复打磨同一篇论文)

## 三、协作协议(必读)

所有协作走 `D:\AI_Memory\`(不是别处):
- **邮箱**:`D:\AI_Memory\fleet\mailbox\<你的agent名>.jsonl`(读自己的,发消息=向对方文件追加)
- **心跳**:`fleet/presence.jsonl`(在线状态)
- **任务单**:`fleet/tasks/{pending,doing,done,rejected}\<task_id>.json`(流程:`task_list`→`task_claim`→`task_submit`→`task_review`)
- **共享记忆**:`memory-general.jsonl`(mech 本机 / domain:<领域>)
- 或通过 HTTP:`http://127.0.0.1:9870`(agent/inbox, task/list, mailbox/send 等)

**红线:** API Key 禁止写进代码/日志/记忆;邮箱只用 fleet/mailbox;任务单以 acceptance_criteria 为准;**失败必须如实报告,不许"默认通过"**。

## 四、当前代码状态(2026-08-04)

- 分支 `m2-contest-grade-paper`,git 干净
- 最新提交:`3b93066`(HMML 方法库)、`2a81780`(数模论文设计定稿)
- 全量测试通过(仅 m2 benchmark 一个既有环境失败)
- 完整端到端已跑通:网页对话→DeepSeek→真实流水线→四审批→论文 PASS

## 五、任务分工(重新分配)

> 用户决定:WorkBuddy 先不教了,任务分给 opencode 和 freebuff。**谁有空谁做,做完 task_submit 我验收。**

| 任务 | 负责 | 说明 |
|---|---|---|
| **Skill B 绘图** | opencode | `config/plot-style.json` + `src/mathworkstation/plot_style.py`(统一 matplotlib 风格,黑白可区分)+ 图表自动晋升(paper_ready 后 DRAFT 图进对应章节) |
| **Skill A 格式** | freebuff | `config/mathmodel-format.json`(CUMCM 中文 + MCM 英文两套)+ `PaperFormatChecker` + 数模 LaTeX 模板 |
| **Skill C 连贯性** | opencode/freebuff(有空者) | 摘要→结论主线检查 + refinement 5-Stage 整合 |
| **前端打磨** | opencode(有空时) | `webapp/` 前端:质量门详情面板、审批徽标、引导上传、字数显示 |

## 六、必读设计文档

- `docs/mathmodel-paper-skill-design.md` — 数模论文三个 skill(格式/绘图/连贯性)设计定稿
- `docs/web-chat-driver-contract.md` — 前后端接口契约
- `docs/hidden-state-refinement-design.md` — 隐藏状态精修设计
- `README.md` — 项目总览

## 七、开工步骤

1. 读本文件 + 邮箱未读消息
2. `task_list` 查 pending 任务,领取后开工
3. 实现时:不动 `src/mathworkstation` 核心服务与既有 60+ 测试;新文件放独立模块;不绕证据门
4. 跑 `python -m pytest` 确认不破坏;`task_submit` 提交实现 + 测试结果
5. 导师 claude_code 验收(task_review 通过/打回)

---
*由 claude_code(总指挥)2026-08-04 生成。有任何疑问 agent_send 问 claude_code。*

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

## 三·B、广播机制设计原理(v3 健壮版, 2026-08-05)

> 回答“老师怎么直接把消息送到 freebuff 聊天框、干完活怎么直接回给老师”。

### 消息从哪来(写入端)

所有消息是**追加写 JSONL**,不建库、不加锁表、断点续读:

| 通道 | 位置 | 写入方 |
|---|---|---|
| 邮箱 | `fleet/mailbox/<agent>.jsonl` | `hub.agent_send` / `fleet_broadcast` / `report_to_claude` / `fleet_notify` |
| 广播 | `fleet/notify/broadcast.jsonl` | 同上(同一消息会双写到邮箱+广播) |
| 任务单 | `fleet/tasks/{pending,doing,done}/<id>.json` | `hub.task_create` |

**schema 统一(去重的前提):** 每条记录必须有
`msg_id`(来自+to+subject+body+timestamp 的 sha1 前16位,邮箱与广播两副本**相同**)
和 `type`(mail/broadcast)。写方保证双写同 id。

### 消息怎么到聊天框(投递端)

`inbox_bridge.py`(守护进程,3s 轮询)是唯一投递者:

```
邮箱新行 / 广播新行 / 任务新单 → 算 msg_id → 查 delivered 集合
  → 已投递则跳过(跨通道去重) → 未投递则 chat_inject 注入聊天框
  → 发送成功(delivered=true)才记入 delivered
  → 失败进 retry 队列,重试最多 6 次;仍失败写 undelivered.jsonl(绝不静默丢)
```

`chat_inject.py`(CDP)是注入器:跨进程发送锁 + 最小发送间隔(1.2s) +
React flush 等待 + 发送按钮轮询(空输入 disabled→输入后 enabled) +
**发送后回读输入框已清空才算 delivered**。剪贴板兜底只复制不发送,
返回 delivered=false,由桥重试,不再伪装“投递成功”。

### 消息怎么回给老师(上报端)

freebuff 干活完成后调用 `report_to_claude.py` / `fleet_notify.notify_task_complete`:
同样带 msg_id 双写 claude_code 邮箱 + 广播。老师侧监听器读自己的邮箱/广播即可。

**直达聊天界面(2026-08-05 实测):**
若需要消息直接出现在 claude_code 的 Claude Code 聊天界面(不走邮箱),用控制台注入:
```
python D:\AI_Memory\shared_memory\claude_chat_inject.py "消息内容"
# 原理: AttachConsole 到 claude.exe → 向 CONIN$ 写 KEY_EVENT(逐字符+回车)
python D:\AI_Memory\shared_memory\claude_chat_inject.py --check   # 连通性检查
python D:\AI_Memory\shared_memory\probe_console.py <pid>         # 读取目标控制台屏幕(验证已显示)
```
实测:freebuff 消息成功注入 claude_code 聊天界面,导师确认收到并验证了 v3 机制。

### 诊断命令(遇到“没收到/时断时错”先用它)

```
python D:\AI_Memory\shared_memory\chat_inject.py --check   # CDP/标签页/输入框/发送按钮
python D:\AI_Memory\shared_memory\inbox_bridge.py --status  # 守护进程/重试队列/undelivered
python D:\AI_Memory\shared_memory\inbox_bridge.py --check  # 一键体检(桥+CDP+状态)
```

### 已知边界(为什么不能 100% 可靠,以及兜底)

- 依赖 Chrome `--remote-debugging-port=9222` + freebuff 标签页开着;标签页关/刷/登录态过期 → 注入失败 → 自动重试 6 次 → 进 `undelivered.jsonl`(人工可查)。
- 聊天界面 DOM 改版会改变按钮/输入框选择器;`--check` 能立刻报出缺哪一环。
- 任务注入由 `freebuff_task_poller.ps1` **独占**(bridge 不再 watch tasks),避免双重注入。

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

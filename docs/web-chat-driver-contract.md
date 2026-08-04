# Chat Driver 接口契约(Frozen Contract,供 Web 外壳对接)

**状态:** Frozen v1.0 — 已冻结(2026-08-04)。后续变更须修订到 v1.1+ 并告知 WorkBuddy。

**v1.1 增补(2026-08-04,用户确认):**
- **真实人工审批节点 = 四个:** `data_registration`、`model_selection`、`paper_ready`、`final_review`。`AutoPipelineService.run()` 到达这些节点时,若配置了 `approval_callback`,会**阻塞等待网页人工批准**(真实身份签名)后才继续;默认 `None` = CLI 现状(自动按传入身份批准),不影响既有测试。
- **对话理解 = 真 LLM 驱动(DeepSeek):** 意图解析优先用 RouterProvider(白名单工具 + JSON schema 约束)理解自由语言;关键词规则作为快速路径/兜底。FakeProvider 保持离线确定性可测。
- **真实流水线执行:** `ChatDriver._schedule_pipeline` 不再只排程,而是真正调用 `AutoPipelineService.run()`(后台工作线程),JobRunner 推送**真实**进度事件(非演练)。
**设计者:** claude_code(证据内核 / Agent 驱动)
**对接方:** WorkBuddy(Web 外壳:FastAPI 后端 + 轻量前端)
**原则:** Web 外壳只调用本契约;不直接触碰 `src/mathworkstation` 内部。证据门与审批永远在驱动层(本契约)以内,外壳无法绕过。

---

## 0. 设计总则

1. **LLM 只能"出主意",不能直接写 Case。** 聊天输入经 Chat Driver 解析为**结构化工具调用(JSON)**,每个工具映射一个既有服务方法;工具经**白名单 + 证据门 + 审批**后才执行。
2. **一切写操作落审计。** 每次工具调用与每次 LLM 调用都写入 **AI 使用台账**(`ledger`),对应 2026 国赛"AI工具使用详情.pdf"的数据源。
3. **长流水线后台跑。** `run_auto_pipeline` 等长任务放入磁盘持久化的 Job 队列,前端通过轮询/WebSocket 看进度,可断点续跑(复用既有 CheckpointManager)。
4. **离线确定性可测。** 驱动层用 `FakeProvider` 可在无 API Key、无网络下全链路测试,不破坏既有 60+ 测试。

---

## 1. 工具白名单(Agent 可调用,每项 = 既有服务方法)

| 工具名 | 对应服务 | 说明 | 需要人工审批 |
|---|---|---|---|
| `list_cases` | `CaseManager.list_cases` | 列出案例 | 否 |
| `get_case` | `CaseManager.show_case` + snapshot | 案例全景(DAG/产物/Claims) | 否 |
| `create_case` | `CaseManager` | 建案例 | 否(审计记录) |
| `upload_inputs` | `ProblemIngestion` / `DatasetRegistry` | 上传题面+数据并注册 | 否(审计记录) |
| `run_auto_pipeline` | `AutoPipelineService.run` | 全自动流水线(后台 Job) | **是**(关键节点停等审批) |
| `run_task_paper` | `AutoPipelineService.run_task_paper_pipeline` | 五类任务论文 | **是**(同上) |
| `approve_node` | `WorkflowService.approve_node` | 批准待审节点 | ——(本身就是审批动作) |
| `retry_node` | `WorkflowService.retry_node` | 重试失败节点 | 是(二次确认) |
| `degrade_node` | `WorkflowService.degrade_node` | 降级可选分支 | 是(记录理由) |
| `read_paper` | `paper/current.md` 读取 | 论文预览 | 否 |
| `export_pdf` | `SubmissionService.prepare_submission` | 生成 PDF / 投稿包 | 否(审计记录) |
| `list_artifacts` / `list_claims` / `list_figures` | 对应 Registry | 只读视图 | 否 |
| `ask_human` | — | Agent 主动向用户澄清(阻塞等待回答) | 是 |

> 新增工具必须满足:①映射到既有服务方法;②有明确的人审边界;③有单测。

---

## 2. HTTP API 契约(WorkBuddy 的 FastAPI 按此实现)

### 2.1 聊天与驱动
```
POST /api/chat
  body: { "case_id": str, "session_id": str|null, "message": str, "context": {...} }
  resp: { "reply": str,            # 给用户的自然语言回复
          "tool_calls": [...],      # 本次触发并执行的结构化工具调用
          "job_id": str|null,       # 若启动了后台任务
          "awaiting_approval": [node_id,...],  # 停等审批的节点
          "ledger": { "entry_id": str, "used_ai": true } }
```

### 2.2 后台任务队列(长流水线)
```
POST /api/jobs
  body: { "case_id": str, "kind": "auto_pipeline"|"task_paper",
          "payload": {...}, "approved_by": str }
  resp: { "job_id": str, "status": "queued" }

GET /api/jobs/{job_id}
  resp: { "job_id", "status": queued|running|waiting_approval|succeeded|failed|resumed,
          "current_node": str|null, "progress": 0.0-1.0,
          "logs": [ {"ts":..., "level":..., "msg":...} ],
          "awaiting_approval": [node_id,...] | null,
          "result": {...} | null }

POST /api/jobs/{job_id}/resume      # 断点续跑
POST /api/jobs/{job_id}/cancel
```

### 2.3 审批
```
POST /api/cases/{case_id}/approve
  body: { "node_id": str, "note": str, "approved_by": str }   # approved_by 不能是 AI,必须是真人标识
POST /api/cases/{case_id}/retry
  body: { "node_id": str, "reason": str, "requested_by": str }
POST /api/cases/{case_id}/degrade
  body: { "node_id": str, "reason": str, "approved_by": str }
```

### 2.4 视图
```
GET  /api/cases                          -> [{case_id, title, competition_type, updated_at}]
GET  /api/cases/{case_id}                -> {manifest, workflow_dag, artifacts, claims, figures, pending_approvals}
GET  /api/cases/{case_id}/paper          -> {markdown, consistency_gate, refinement:{...}}
GET  /api/cases/{case_id}/ledger         -> [AI 使用台账条目]
POST /api/upload                         -> multipart,落盘 input/ 并注册,返回 artifact_id
```

### 2.5 实时进度(WebSocket)
```
WS /ws/jobs/{job_id}
  服务端推送事件(JSON):
  {"type":"progress","node":"eda","status":"RUNNING","progress":0.4}
  {"type":"approval_required","nodes":["model_selection"]}
  {"type":"ledger","entry_id":"..."}          # 每次 AI 调用落账后广播
  {"type":"done","result":{...}}
```

---

## 3. 数据模型(持久化位置)

| 对象 | 位置 |
|---|---|
| Job | `<case_root>/jobs/<job_id>.json`(磁盘持久化,可断点续跑) |
| Ledger | `<case_root>/ai_ledger.jsonl`(AI 使用台账) |
| 审批决策 | 既有 `<case_root>/decisions.jsonl`(不新增,复用) |
| 恢复状态 | 既有 CheckpointManager + MemoryManager(不新增) |

**Ledger 条目 schema(直接对应 2026 国赛 AI 披露要求):**
```json
{
  "entry_id": "led-...",
  "timestamp": "...",
  "tool": "run_auto_pipeline",
  "model": "provider/model",
  "purpose": "自动流水线执行",
  "stage": "problem_analysis",
  "user_input": "题目PDF+数据CSV",
  "prompt_ref": "prompt 文件路径或摘要",
  "output_adopted": true,
  "human_reviewed": false,
  "review_note": null
}
```

---

## 4. 验收标准(给 WorkBuddy 的 Web 外壳)

Web 外壳必须通过以下验收才算完成:
1. `POST /api/chat` 能把一句话驱动起一个真实 Case 的自动流水线,并在模型选择节点**停下等人工审批**;
2. 审批后在网页继续,直到论文生成与 PDF 导出;
3. WebSocket 全程推送进度,断网重连可恢复;
4. 每次 AI 交互后 `GET /api/cases/{id}/ledger` 有对应台账条目;
5. 用 `FakeProvider` 配置时全链路**无需 API Key 可跑通**(CI 可验证)。

---

## 5. 分阶段交付(与派单顺序)

| 阶段 | 内容 | 依赖 |
|---|---|---|
| S1 | Chat Driver 内核(driver/tools/jobs/ledger)+ FakeProvider 离线测试 | 本契约冻结 |
| S2 | WorkBuddy 实现 FastAPI 外壳(S2 起派单) | **契约冻结即可开工,不必等 S1 实现**;后端 handler 先按契约签名预留 driver 导入点 |
| S3 | 集成验收:全链路 pytest + 真实 Case 网页演练 | S1+S2 |
| S4 | AI 台账 → 披露 PDF 生成器(国赛合规) | S1 |

> **S1/S2 并行原则:** S2 依赖的是本契约(HTTP API + 数据模型),不是 S1 的代码。
> WorkBuddy 可先搭 FastAPI 骨架、路由、WebSocket、前端壳;后端 handler 调用 driver 的位置按
> `from mathworkstation.chat.driver import ChatDriver` 预留,待 S1 落地后自动接上。
> 两者通过本契约对接,互不阻塞。

---

*契约由 claude_code 维护;任何变更需回到本文件修订并在派单前告知 WorkBuddy。*

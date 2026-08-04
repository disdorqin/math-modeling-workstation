# Web Shell (`webapp/`)

FastAPI 后端 + 轻量原生前端，作为数学建模工作站的 **Web 外壳**。
外壳不持有任何领域逻辑，只做三件事：

1. **HTTP 适配** —— 把契约 `docs/web-chat-driver-contract.md` (v1.0 冻结) 的接口暴露出来；
2. **实时层** —— 用 WebSocket 把后台任务进度/审批门/台账事件推给浏览器；
3. **边界守卫** —— `approved_by` 必须是真人标识（拒绝 `workbuddy/claude/auto/chat-human` 等 AI 标识），
   所有写入都走既有服务与证据门，绝不绕过。

> 所有 jobs / AI 台账的落盘都来自 S1 的 `mathworkstation.chat.jobs.JobManager` 与 `AILedger`，
> 文件位置与契约一致（`<case_root>/jobs/<job_id>.json`、`<case_root>/ai_ledger.jsonl`）。
> 外壳**不**维护第二套存储，因此不存在“平行账本 / 双重记账”风险。

## 运行

```powershell
# 默认 127.0.0.1:8000，自动探测装有 mathworkstation + fastapi + uvicorn 的 Python
.\webapp\run.ps1

# 自定义
.\webapp\run.ps1 -Port 8080 -OutputRoot "D:\cases" -Reload
```

等效手动命令：

```bash
python -m uvicorn webapp.main:app --host 127.0.0.1 --port 8000
```

打开 <http://127.0.0.1:8000/> 即可使用前端（聊天面板 + DAG 进度 + 图表/论文预览 + 审批 + 下载 + 台账）。

## 驱动接入点

`webapp/driver.py` 通过 `from mathworkstation.chat.driver import ChatDriver` 接入 S1 的真实驱动；
若该包不存在则自动降级为 `StubChatDriver`（返回 `NotImplemented`，仅保证路由/前端可跑）。
当前环境已接入 **真实驱动**（`/api/health` 显示 `real_driver_available: true`，默认 `fake` provider，离线确定性、无需 API Key）。

## 关键设计

| 关注点 | 做法 |
| --- | --- |
| 服务复用 | `services.py` 复用 S1 的 `build_services()` 产出的 service bag，外壳不重建第二套 |
| 证据门 | `approve_node` 的 `approved_by` 必须是真人；AI 标识一律 HTTP 400 |
| 双重记账防护 | `/api/chat` 中驱动已记账（`result.ledger_entry_id` 非空）则外壳**不**重复记账 |
| 审批门释放 | 演练任务的审批门用模拟节点名（如 `model_selection`），`/api/cases/{id}/approve` 会先释放匹配的等待中任务，再尝试真实工作流审批 |
| 脱敏 | `ledger.py` 写入前对 `user_input/purpose/review_note` 做 `_redact`（密钥模式脱敏） |
| 密钥 | `run.ps1` 不读取/打印/写入任何 API Key；`MATHWS_ROUTER_CONFIG` 只存**路径**不存 key |

## 端点速查

- `GET  /api/health` — 健康检查 + 工具表
- `POST /api/chat` — 对话驱动（`case_id` / `session_id` / `message` / `context`）
- `POST /api/jobs` — 创建后台任务（需真人 `approved_by`）
- `GET  /api/jobs/{job_id}` — 任务状态/进度/事件历史
- `POST /api/jobs/{job_id}/resume|cancel` — 续跑 / 取消
- `GET  /api/cases` — 案例列表
- `GET  /api/cases/{id}` — 案例 manifest / DAG / artifacts（读既有服务）
- `GET  /api/cases/{id}/paper|ledger` — 论文 / AI 台账
- `GET  /api/cases/{id}/figures/{i}` — 图表文件
- `POST /api/cases/{id}/export` — 生成投稿包（审计）
- `POST /api/cases/{id}/approve|retry|degrade` — 审批 / 重试 / 降级（均需真人署名）
- `POST /api/upload` — 上传并注册输入文件
- `WS   /ws/jobs/{job_id}` — 实时事件流

## 已知限制

- **演练模式（rehearsal）**：S1 的 `ChatDriver._schedule_pipeline` 当前只“排程”不“执行”（真实执行待 S1.1/S3）。
  因此外壳的 `JobRunner` 以 10 节点的演练 DAG 推进，**事件序列与审批门是真实的，但不会写入任何 Case 证据**；
  每个演练任务在 payload/日志/result 中都明确标注 `mode: "rehearsal"`，绝不会被误认为真实流水线运行。
- 真实驱动默认 `fake` provider（离线、确定性）。接入需要 API Key 的 provider 时，key 走既有
  `.env.local` 机制，外壳与 `run.ps1` 不接触密钥。
- 前端为原生 JS 单页，WebSocket 断线采用指数退避重连，并回退 REST 轮询。

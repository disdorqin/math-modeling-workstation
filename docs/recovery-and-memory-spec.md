# 恢复与记忆规范

系统恢复不依赖完整聊天记录，而使用受控记忆：

- `memory/project_facts.md`：已确认事实；
- `memory/decisions.md`：已批准决策；
- `memory/current_state.md`：当前进度；
- `memory/evidence_index.json`：结论与证据映射；
- `.internal/resume_brief.md`：下次会话的最小恢复摘要；
- `.internal/checkpoints/current.json`：最新 DAG 状态。

恢复流程：验证案例结构、校验产物哈希、读取 Checkpoint、识别中断运行、将遗留 `RUNNING` 节点改为 `NEEDS_REVIEW`、生成恢复报告和 Resume Brief。

Resume Brief 明确 Case ID、当前阶段、成功/失败/阻塞节点、受管产物和控制规则，防止模型自由扫描和跨案例串线。


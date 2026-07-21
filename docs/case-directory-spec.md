# 案例目录规范

每个案例位于 `output/{case_id}/`，不得访问其他案例目录。

关键目录：

- `input/`：用户原始输入，只允许首次写入；
- `evidence/`：外部来源、原始响应和快照；
- `data/`：raw、intermediate、cleaned、features 和 splits；
- `analysis/`：中文阶段报告；
- `code/`：可执行分析与模型代码；
- `experiments/`：每次实验的完整快照；
- `figures/`、`tables/`、`results/`：程序产生的证据；
- `paper/`：论文提纲、章节、草稿和最终稿；
- `memory/`：事实、决策、当前状态和证据索引；
- `sessions/`：对话和会话摘要；
- `runs/`：节点执行日志；
- `.internal/`：Checkpoint、恢复摘要和结构化状态；
- `export/`：最终提交包。

`input/`、`data/raw/` 和 `evidence/raw_responses/` 中的已注册文件不可覆盖。版本更新必须创建新文件和新 Artifact ID。


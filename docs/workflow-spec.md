# 工作流与异常规范

工作流使用 DAG，而不是不可恢复的线性流水线。每个节点声明依赖、关键性、重试预算、是否允许降级和是否需要人工审批。

## 节点状态

`PENDING`、`RUNNING`、`RETRYING`、`SUCCEEDED`、`FAILED`、`BLOCKED`、`NEEDS_REVIEW`、`DEGRADED`、`STALE`、`SKIPPED`、`CANCELLED`。

## 异常策略

- `TRANSIENT`、`SCHEMA`：在预算内重试；
- `DATA_QUALITY`、`MODEL_ASSUMPTION`：进入人工复核并阻塞下游；
- `OPTIONAL_ARTIFACT`：节点允许时受控降级，失败产物禁止进入论文；
- `CRITICAL`：暂停并阻塞依赖节点。

自动跳过被禁止。人工跳过必须记录批准人、原因和影响。上游结果变化后，已完成下游自动转为 `STALE`，待重新执行。

`WorkflowService` 保证 Run、节点状态、Checkpoint 和 Resume Brief 同步更新。


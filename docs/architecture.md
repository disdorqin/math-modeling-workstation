# 系统架构

数学建模辅助工作站采用三个相互隔离的平面：

1. **Control Plane**：案例、会话、运行、DAG、Checkpoint、审批和异常策略；
2. **Reasoning Plane**：后续接入的 LLM、Prompt 和结构化输出；
3. **Evidence Plane**：原始数据、代码、实验、指标、图表和论文证据。

核心内核不依赖具体 Agent 框架。LangGraph、PydanticAI 等只能通过适配器接入，不能绕过案例隔离、产物注册和审批策略。

## 标识层级

- Case ID：一篇论文或一个建模项目；
- Session ID：一次连续对话；
- Run ID：一个节点的一次执行。

所有文件操作必须先解析 Case Root，再经过路径守卫；模型节点通过 `NodeAccessPolicy` 获取最小读写权限。

## 第一阶段边界

第一阶段只实现可恢复底座，不包含 LLM、爬虫、EDA、建模和论文生成。后续模块必须复用现有 Case、Artifact、Workflow 和 Recovery 接口。


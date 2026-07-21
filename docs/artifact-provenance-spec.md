# 产物与证据链规范

每个受管文件在 `artifact_registry.jsonl` 中登记：

- Artifact ID；
- Case ID；
- 相对路径；
- 类型和创建者；
- Run ID；
- 上游 Artifact ID；
- SHA-256 和字节数；
- 是否允许进入论文；
- 当前状态。

原始输入采用复制后登记，禁止覆盖。验证时重新计算哈希，发现缺失或变化即报告异常。

后续论文 Claim 必须引用 Artifact ID，形成：

`Claim → Result → Experiment Run → Code → Dataset → External Source`

没有完整证据链的数值、图表和结论不能标记为 `paper_eligible`。


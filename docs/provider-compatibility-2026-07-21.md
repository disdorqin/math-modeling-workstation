# 中转站兼容性实测（2026-07-21）

测试只发送 `Reply with exactly OK` 和一张无项目内容的白底黑点图片，不包含 Case、论文或数据。Key 未写入仓库。

| 路由 | `/models` | Chat | 延迟 | 结论 |
|---|---:|---:|---:|---|
| seekai 三账号 | 200 | ReadTimeout | 超过 45 秒 | 仅作低优先级备用 |
| testvideo | 200 | 200 / OK | 约 1.8 秒 | Chat 首选 |
| codexplus chat 账号一 | 200 | 200 / OK | 约 7.8 秒 | 可用，但观察到 5,136 prompt tokens 异常 |
| codexplus chat 账号二 | 200 | 200 / OK | 约 37.7 秒 | 可用，慢速备用 |
| codexplus image | 200 | 200 / Base64 | 约 33.8 秒 | `gpt-image-2` 可用 |

中转站属于第三方基础设施。正式使用前应轮换聊天中暴露的 Key，并避免向未经信任审查的路由发送敏感数据、个人信息或未公开论文。


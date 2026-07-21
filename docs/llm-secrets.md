# LLM 密钥与中转站配置

真实 Key 只能放在本机 `.env.local` 或操作系统环境变量中，不得进入 Git、Case、Session、Run、Prompt、错误报告和测试 Fixture。

路由配置只保存环境变量名：

```json
[
  {
    "name": "primary",
    "base_url": "https://example.com/v1",
    "api_key_env": "MMW_LLM_PRIMARY_KEY",
    "models": ["gpt-5.1"]
  }
]
```

运行日志仅允许记录路由名、Base URL、模型、延迟、状态码、错误分类和重试次数。禁止记录 Authorization Header、Key、完整请求正文或包含敏感材料的完整响应。


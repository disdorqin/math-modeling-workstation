# 公开出售版检查清单

## 根目录

- [ ] 根目录只包含 `数学建模全流程AI-Skills包介绍.md` 和 `skills/`。
- [ ] 不出现 `.pytest_cache`、`__pycache__`、`.DS_Store`、`outputs/`、`dist/`。

## skills 文件夹

- [ ] 13 个真实 Skill 都在 `skills/` 下。
- [ ] 每个 Skill 都有 `SKILL.md`、`agents/openai.yaml` 和 `references/`。
- [ ] 有脚本的 Skill 保留自己的 `scripts/`。
- [ ] `skills/_shared/` 包含模板、模型卡和检查清单。
- [ ] `skills/_examples/` 包含样例题、样例数据和端到端案例。
- [ ] `skills/_release/` 只放购买者文档、依赖、许可证和验证脚本。

## 验证命令

在出售版根目录运行：

```bash
python3 skills/_release/scripts/validate_public_package.py
```

通过后才建议交付给买家。


# 高教社《各类常用数学模型》方法库融入 model-catalog 报告

日期:2026-08-05 · 执行者:opencode(任务单 tff3f1fa6) · 分支:m2-contest-grade-paper

## 1. 背景与任务

把高教社《各类常用数学模型》教材中的国赛经典方法提炼成 HMML 式方法卡片,融入 `config/model-catalog.json`,至少新增 3-5 个国赛方法,不干扰主线(C 题 ML 管线),并产出分析报告。

## 2. 现状核对(commit 7f64ed9 之后)

- catalog 已由 helper 会话(AI-Skills 融合)升级为 schema_version 2,`methods` 27 个,含 linear_programming / integer_programming / ahp / gm11 / grey_relation 等国赛方法。
- 权威集锁测试已放宽为 **superset 契约**:`core = REGRESSION_MODELS | CLASSIFICATION_MODELS`,要求 `core ⊆ catalog.names`(而非严格相等),且每条 method 需非空 `description` 与 `task_types`。
- 运行时安全性已核实:即使 LLM 从 catalog 选出目录内但无构造器的方法,`auto_pipeline.py:674` 的 `supported` 白名单会在归一化阶段直接丢弃(`if name not in supported: continue`),不会让不支持的方法进入训练;测试全绿。

## 3. 本次新增(5 个国赛方法,全部以教材原文为蓝本)

| 方法 | 章节来源 | 任务类型 | 关键内容 |
|------|----------|----------|----------|
| `dynamic_programming` | 第04章 动态规划 | optimization | Bellman 最优性原理、逆序递推 f_k(s_k)=opt{v_k+f_{k+1}} |
| `interpolation` | 第09章 插值与拟合 | interpolation | 拉格朗日/牛顿/分段线性/Hermite/三次样条;拟合为最小二乘 |
| `markov_chain` | 第17章 马氏链模型 | stochastic_process | 无后效性、转移矩阵 π^(n+1)=π^(n)P、稳态 πP=π |
| `graph_network` | 第05章 图与网络 | graph_optimization | 最短路/最小生成树/最大流/最小费用流/中国邮递员/TSP |
| `ode_modeling` | 第13章 微分方程建模 | differential_equation | 直接列方程/微元分析法/模拟近似;初值问题 + 龙格-库塔 |

同时为 4 个新任务类型新增 `task_types` 顶层键(interpolation / stochastic_process / graph_optimization / differential_equation),并把 `dynamic_programming` 挂入已有 `optimization.allowed_models`。

**新增后 catalog 规模**:methods 27 → 32;task_types 10 → 14。

## 4. 不干扰主线的验证

1. 权威集锁测试 `test_model_catalog_matches_authority_supported_set` 通过(新增方法在 core 之外,不破坏 superset)。
2. `config/model-catalog.json` JSON 合法,全部 32 条 method 元数据非空。
3. 全量 pytest 107 项通过。
4. 运行时:新增方法不在 `baseline.py::build_candidate_model` 构造器集合内,但 `auto_pipeline.py:674` 白名单保证 LLM 误选也不会进入训练。
5. 新增方法均标注了 when_to_use / when_not_to_use,与已有卡片风格一致。

## 5. 素材来源与许可说明

- 方法内容提炼自高教社《各类常用数学模型》(姜启源 等)相关章节,仅作为方法卡片说明文字,不含教材原文大段引用。
- 既有 27 条 method 沿用 AI-Skills(MIT License, Copyright 2026)归属,已在 `attribution` 字段声明。
- 本次新增条目建议视为在 HMML 目录结构下对公共数学方法卡片的扩充,不改变原许可归属声明。

## 6. 遗留观察(未在本任务范围)

- `catalog.task_types.classification.allowed_models` 含 `svm`,但 `model_plan.py` 权威集与 `baseline.py` 分类构造器均无 svm —— 因锁测试已是 superset 契约且管线有白名单兜底,不会炸管线,但目录与"可运行模型"存在轻微信息差,建议后续任务决定是补 svm 构造器还是从目录移除。

# 知识库卡片接入 model_plan 管线 (t554eae27)

## 交付内容

### 1. 检索模块 `src/mathworkstation/knowledge_cards.py`(新增)
仿照 `hmml.py` 的 `MethodRetriever` 接入模式,实现确定性卡片检索(非 RAG):

- `KnowledgeCardRetriever`:加载 `config/knowledge/index.json` + `cards/*.md`(32 张)。
- `retrieve(problem_text, task_types=None, top_k=4)`:先按推断的 task_type 过滤候选池,再按
  **问题文本与卡片内容的 CJK 二元组 + 拉丁词重叠(Dice 系数)** 排序取 top-k。
- `infer_task_types(problem_text)`:确定性关键词表(中文为主,兼收英文)推断任务类型。
- `format_cards(cards)`:把卡片渲染成 6 字段注入块(适用场景/核心公式/建模步骤/C题适用性/论文佐证/易错点)。
- 非阻塞:索引/卡片缺失或不可读 → `loaded=False`、`retrieve` 返回 `[]`、`format_cards` 返回 `""`。

### 2. 管线接线 `src/mathworkstation/auto_pipeline.py`
- 新增 `_load_knowledge_cards(analysis)`:按问题 objectives 检索并格式化卡片,
  按 query 进程内缓存;任何异常返回 `""`(建议层,永不阻塞)。
- `_run_model_plan`:在 `model_plan_context` 注入 `knowledge_cards`(主路径 + LLM 格式化失败回退路径都注入)。

### 3. Prompt `prompts/internal/model_plan.json`
- `user_template` 新增 `{knowledge_cards}` 变量与说明:
  「C-layer essential model cards(…;use them to write concrete, evidence-grounded rationale)」,
  并明确「never to select a model outside the Method Catalog」——与 HMML 相同的约束措辞。

## 共存原则
- **catalog**(`config/model-catalog.json`):约束「能用哪些模型」,是唯一权威约束。
- **HMML**(`config/hmml.json`):告诉 LLM 分层方法库里的候选方法。
- **知识卡片**(`config/knowledge/`):告诉 LLM「怎么做」——建模步骤/核心公式/易错点/C 题适用性/论文佐证。
  三者互补不重复;卡片和 HMML 都不能让 LLM 选 catalog 之外的模型。

## 验证结果

### 2023 / 2024 C 题检索
- 2024 C 题 objectives → 推断 task_type `[prediction, evaluation, differential_equation]` → 命中
  `gm11 / time_series_arima / exponential_smoothing / moving_average`(预测族)。
- 2023 C 题 objectives → 推断 `[prediction, differential_equation, classification]` → 命中
  `gm11 / holt_winters / gradient_boosting / svm`。
- 两块注入块均含 `###` 卡标题 + 核心公式/建模步骤/C题适用性等字段(详见测试)。

### 测试
- 新增 `tests/test_knowledge_cards_retriever.py`(18 项):加载/检索排序/task_type 过滤/非阻塞/6 字段/2023/2024 验证等。
- 更新 `tests/test_hmml.py` 的 model_plan prompt 渲染用例(补 `knowledge_cards` 变量)。
- `tests/test_knowledge_cards_retriever.py` + `test_hmml.py` + `test_prompt_registry.py` + `test_knowledge_cards.py` 全过;
  全量 pytest(除 cline 在改的 e2e 用例)exit=0。

## 与 cline 的边界
- `test_auto_pipeline_e2e.py::test_auto_pipeline_produces_traceable_refined_export` 当前失败,
  位于 refinement 阶段(非本任务改动);已将本任务对 `auto_pipeline.py` / `model_plan.json` 的改动整体回退后
  该用例仍失败,证明非本任务引起,是 cline 的端到端验证(并入 Comparator 后)在改的环节。

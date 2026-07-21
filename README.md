# 数学建模辅助工作站

这是一个本地运行、案例隔离、过程可恢复、结果可追溯的数学建模辅助工作站。

当前版本实现第一阶段底座：

- Case / Session / Run 三层标识；
- 标准案例目录与路径隔离；
- Manifest、状态、Checkpoint 和 JSONL 日志；
- 文件产物注册及 SHA-256；
- 案例记忆与恢复摘要；
- DAG 节点依赖、失败分类、阻塞、降级和过期传播；
- 命令行创建、检查、恢复和归档案例。

核心原则：**No Evidence, No Claim（无证据，不进论文结论）**。

## 快速开始

```powershell
python -m pip install -e .
mathworkstation create-case --competition SM --title "测试案例"
mathworkstation list-cases
mathworkstation create-session --case-id <CASE_ID>
mathworkstation start-node --case-id <CASE_ID> --node-id input_validation
mathworkstation succeed-node --case-id <CASE_ID> --node-id input_validation
mathworkstation show-workflow --case-id <CASE_ID>
mathworkstation validate-case --case-id <CASE_ID>
mathworkstation resume-case --case-id <CASE_ID>
```

数据登记和质量画像：

```powershell
mathworkstation register-dataset --case-id <CASE_ID> --source data.csv --name "原始数据" --kind OBSERVED
mathworkstation complete-data-registration --case-id <CASE_ID>
mathworkstation approve-node --case-id <CASE_ID> --node-id data_registration --approved-by human
mathworkstation profile-dataset --case-id <CASE_ID> --dataset-id <DATASET_ID> --target-column target
mathworkstation list-datasets --case-id <CASE_ID>
```

题目材料摄取：

```powershell
mathworkstation ingest-problem --case-id <CASE_ID> --source problem.pdf
```

支持 TXT、Markdown，以及安装可选解析依赖后的 PDF/DOCX。原始文件保存于 `input/problem/original`，抽取文本保存于 `input/problem/extracted`，两者分别注册并保留上下游关系。

网页/API 数据先保存来源快照，再登记：

```powershell
mathworkstation collect-url --case-id <CASE_ID> --url https://example.org/data.csv
mathworkstation register-artifact-dataset --case-id <CASE_ID> --artifact-id <ARTIFACT_ID> --name "公开数据" --kind OBSERVED --source-type web --source-uri https://example.org/data.csv
```

EDA 和 Baseline：

```powershell
mathworkstation run-eda --case-id <CASE_ID> --dataset-id <DATASET_ID> --target-column target
mathworkstation run-baseline --case-id <CASE_ID> --dataset-id <DATASET_ID> --target-column target --task-type regression
mathworkstation list-figures --case-id <CASE_ID>
mathworkstation list-experiments --case-id <CASE_ID>
```

Baseline 必须等待题目分析和模型方案通过人工审批，不允许绕过依赖直接运行。

正式模型比较与论文就绪门：

```powershell
mathworkstation validate-model-plan --case-id <CASE_ID> --source model_plan.json
mathworkstation run-model-comparison --case-id <CASE_ID> --plan-artifact-id <PLAN_ARTIFACT_ID>
mathworkstation select-model --case-id <CASE_ID> --experiment-id <EXPERIMENT_ID> --selected-model ridge --comparison-artifact-id <ARTIFACT_ID> --selected-by human --rationale "交叉验证表现稳定"
mathworkstation run-sensitivity --case-id <CASE_ID> --experiment-id <EXPERIMENT_ID> --plan-artifact-id <PLAN_ARTIFACT_ID>
mathworkstation assess-paper-ready --case-id <CASE_ID> --experiment-id <EXPERIMENT_ID> --selection-artifact-id <SELECTION_ID> --sensitivity-artifact-id <SENSITIVITY_ID>
```

`select-model` 同时记录人工选择并完成 `model_selection` 审批，不需要再调用通用 `approve-node`。

论文证据和分章节工作区：

```powershell
mathworkstation create-claim --case-id <CASE_ID> --text "模型交叉验证表现稳定" --claim-type model_result --evidence-artifact-id <ARTIFACT_ID>
mathworkstation create-default-outline --case-id <CASE_ID> --title "论文标题" --competition-type SM --output outline.json
mathworkstation validate-outline --case-id <CASE_ID> --source outline.json
mathworkstation init-paper-sections --case-id <CASE_ID> --outline-artifact-id <OUTLINE_ID>
mathworkstation update-section --case-id <CASE_ID> --section-id results --source results.md
mathworkstation check-paper-consistency --case-id <CASE_ID>
```

文献检索和引用验证：

```powershell
mathworkstation search-literature --case-id <CASE_ID> --query "mathematical modeling sensitivity analysis" --rows 5
mathworkstation export-bibtex --case-id <CASE_ID>
mathworkstation verify-citations --case-id <CASE_ID>
```

检索结果先保存 Crossref 原始快照，再进入独立引用注册表。BibTeX 不会自动变成论文结论；论文一致性检查发现未验证引用时会阻断 `PASS`。

受控 LLM 和生图调用：

```powershell
mathworkstation llm-chat --case-id <CASE_ID> --session-id <SESSION_ID> --node-id problem_analysis --routes config/llm-routes.example.json --message-file request.md --input-artifact-id <PROBLEM_ARTIFACT_ID>
mathworkstation generate-illustration --case-id <CASE_ID> --routes config/image-routes.example.json --title "机制示意图" --prompt-file image_prompt.md
mathworkstation list-prompts
```

一次性自动论文流水线：

```powershell
mathworkstation create-case --competition SM --title "自动论文案例"
mathworkstation create-session --case-id <CASE_ID>
mathworkstation run-auto-pipeline --case-id <CASE_ID> --session-id <SESSION_ID> `
  --problem-source problem.md --data-source data.csv --dataset-name "原始数据" `
  --target-column target --competition-type SM `
  --routes config/llm-routes.example.json --approved-by pipeline-human --kind OBSERVED `
  --source-uri https://data.example.org/source --license "CC BY 4.0"
```

该入口会依次执行结构化题目分析、数据质量、EDA、模型方案、确定性实验、证据 Claim、12 节论文草稿、一致性检查和 ZIP 导出。`--approved-by` 是显式的关键节点审批身份，不允许模型自行绕过审批。

自动论文使用严格研究质量门：会检查章节完整性、模型公式、图表引用、内部证据 ID 泄漏、模板化空话、数据真实性声明和证据完整性。详细规则见 [`docs/research-quality-gate.md`](docs/research-quality-gate.md)。

真实 Key 必须通过路由配置中的 `api_key_env` 对应环境变量提供，禁止写入 JSON。

本地 Streamlit 控制台：

```powershell
python -m pip install -e ".[ui]"
$env:PYTHONPATH="src"
python -m streamlit run src/mathworkstation/ui_app.py --server.headless true
```

控制台提供 Case 选择、DAG 状态、审批/重试、产物和论文浏览，以及绑定当前 Case、Session 和节点的受控 LLM 对话。详细说明见 `docs/ui-runbook.md`。

不安装包也可以直接运行：

```powershell
$env:PYTHONPATH="src"
python -m mathworkstation.cli create-case --competition SM --title "测试案例"
```

## 测试

```powershell
python -m pytest
```

详细规范见 `docs/`。

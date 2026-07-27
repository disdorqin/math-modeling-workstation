# 数学建模辅助工作站

这是一个本地运行、案例隔离、过程可恢复、结果可追溯的数学建模辅助工作站。

发布与复现入口：[`docs/reproducibility.md`](docs/reproducibility.md) ·
协作规范：[`CONTRIBUTING.md`](CONTRIBUTING.md) ·
架构交接：[`docs/agent-handoff.md`](docs/agent-handoff.md)

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

证据晋升与可降级分支：

```powershell
mathworkstation promote-figure --case-id <CASE_ID> --figure-id <FIGURE_ID> `
  --approval-artifact-id <PAPER_READY_APPROVAL_ID> --approved-by human --note "与已批准实验证据一致"
mathworkstation approve-paper-ready --case-id <CASE_ID> --experiment-id <EXPERIMENT_ID> `
  --selection-artifact-id <SELECTION_ID> --sensitivity-artifact-id <SENSITIVITY_ID> `
  --approved-by human --note "证据链完整" `
  --additional-artifact-id <PROFILE_ID> --additional-artifact-id <EDA_SUMMARY_ID>
mathworkstation degrade-node --case-id <CASE_ID> --node-id refinement_loop `
  --approved-by human --reason "本次不执行 LLM 循环精修"
```

EDA、Baseline、模型比较和敏感性产出的图形一律注册为 `DRAFT`，不会自动成为论文证据。
`promote-figure` 要求挂靠一个已存在的 `paper_ready_approval` 产物并填写审批人与理由，
晋升后图形才可写入提纲的 `figure_ids`，并由 `complete-paper-draft` 编号插入最终稿、
由 `prepare-submission` 转成 LaTeX `figure` 环境。

`degrade-node` 用于记录"有意不执行某个可选分支"的人工决策：节点转为 `DEGRADED`，
下游解除阻塞，审批人与理由写入 `decisions.jsonl`。与 `skip` 不同，它不阻断下游。
不使用 API 时可据此降级 `refinement_loop`，使确定性链路能够走到 `export`。

完整的无 API 实跑记录、九项已修复缺陷与复现脚本见
[`docs/端到端实跑报告-2026-07-26.md`](docs/端到端实跑报告-2026-07-26.md) 与
`scripts/run-deterministic-end-to-end.ps1`。

多智能体切片（Agent 提案，工作流裁决）：

```powershell
mathworkstation run-agent-pipeline --case-id <CASE_ID> --session-id <SESSION_ID> `
  --dataset-id <DATASET_ID> --target-column <TARGET> --runtime builtin
```

四个确定性智能体（`data_steward` → `eda_analyst` → `evidence_verifier` →
`quality_assurance`）依次提出提案，唯一有写权限的 `Adjudicator` 复用既有的
`ClaimRegistry`、`FigureRegistry` 与 DAG 状态机来裁决，因此智能体链路与手工 CLI
链路产生同一套审计记录。任何数值断言若缺少 `paper_eligible` 证据会被机制性拒绝，
不依赖提示词自律。`--runtime` 支持 `auto`（默认，检测到 LangGraph 时使用）、
`langgraph`、`builtin`（零依赖回退，语义与 LangGraph 路径一致）。

架构设计、智能体名册、裁决规则、编排拓扑与迁移路径见
[`docs/multi-agent-architecture.md`](docs/multi-agent-architecture.md)。

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
  --source-uri https://data.example.org/source --license "CC BY 4.0" `
  --image-routes config/image-routes.example.json
```

该入口会依次执行结构化题目分析、数据质量、EDA、模型方案、确定性实验、证据 Claim、12 节论文草稿、一致性检查和 ZIP 导出。`--approved-by` 是显式的关键节点审批身份，不允许模型自行绕过审批。

自动流水线还建立 typed evidence-to-narrative 链：`SubproblemContract` 记录子问题责任与完成状态，`ResultRecord` / `TableRecord` 保存实验指标及来源，`SectionEvidencePack` 只向对应章节投影证据。确定性 renderer 将精确指标和结果表写入中文 Claim 与章节；`CompletePaperContract` 在 final review/export 前检查子问题闭环、指标入文和表格引用。

一致性检查通过后，流水线会进入受控的 `refinement_loop`：同一个 Refinement Cell 在 2--10 个有限 Stage 内重复执行“评估 → 选择缺陷 → 局部补丁 → 验证 → 接受或回滚”。每个补丁最多修改两个章节，必须回显原章节 SHA-256；已验证的数字、Claim、Figure、数据披露和章节证据范围被冻结。候选稿只有通过硬门控且改善目标质量维度后才会成为新的 `paper/current.md`。循环状态、问题账本和每轮 decision 均写入 Case 目录，可断点续跑。

控制默认值：`--refinement-max-stages 10 --refinement-patience 2 --refinement-min-delta 0.015`。对已有初稿可单独执行：

```powershell
mathworkstation run-refinement --case-id <CASE_ID> --session-id <SESSION_ID> `
  --routes config/llm-routes.example.json --max-stages 6
```

已完成循环需要重新开启时追加 `--restart`；该操作会标记后续 `final_review/export` 为 stale，保留旧版本和完整历史。

自动论文使用严格研究质量门：会检查章节完整性、模型公式、图表引用、内部证据 ID 泄漏、模板化空话、数据真实性声明和证据完整性。详细规则见 [`docs/research-quality-gate.md`](docs/research-quality-gate.md)。

剩余开发按 [`docs/remaining-work-optimized-roadmap.md`](docs/remaining-work-optimized-roadmap.md) 执行：当前优先是发布级 API 兼容性、跨题型 benchmark 和 PDF 环境验收。增加 refinement 次数不会替代缺失证据或题型插件。

当前版本已落地 Phase A-D 的基础能力：回归案例可生成假设、数据语义、诊断、子问题答案和故事线记录；final review 会执行确定性审查并生成上游修复请求；审批、预算和 provenance policy 已持久化；分类、预测、优化、仿真、排序已有统一协议插件、非法协议阻断、deterministic 执行器和 12 节论文编排，结果会由 `TaskExecutionService` 注册并投影到 Claims、表格和图形。

仓库的稳定性不依赖“语言数量”。核心编排保持 Python 单一实现，以减少跨语言环境差异；稳定性由受控依赖、CI 矩阵、确定性 fixture、案例级 SHA-256、事务日志、断点恢复和端到端 smoke test 保证。需要 GPU、PDF 引擎或外部 API 的能力均作为显式可检查的可选依赖，不作为隐藏前置条件。

投稿预检与清洁稿：

```powershell
mathworkstation prepare-submission --case-id <CASE_ID> --profile SM
mathworkstation prepare-submission --case-id <CASE_ID> --profile SM --compile-pdf
```

该命令生成 `paper/markdown/submission.md`、`paper/latex/main.tex` 和持久化预检报告，清除用户稿中的内部证据锚点。安装 `latexmk` 或 `pdflatex` 后才会编译 PDF；缺少引擎时记录可恢复的阻断结果，不伪造 PDF。完整审计 ZIP 与清洁投稿 ZIP 分离保存。

五类任务统一论文入口：

```powershell
mathworkstation run-task-paper --case-id <CASE_ID> --family optimization --plan optimization.json --title "优化任务论文"
mathworkstation run-task-paper --case-id <CASE_ID> --family forecasting --plan forecast.json --frame data.csv
```

该入口复用原 DAG 和状态审批，依次完成任务协议、确定性执行、Claims/Table/Figure、12 节论文、完整论文合同、一致性检查和投稿预检。支持 `classification`、`forecasting`、`optimization`、`simulation`、`ranking`；非法协议在进入论文阶段前阻断。

`--image-routes` 是可选的流程图视觉参考分支。它只在主流水线末端调用 OpenAI-compatible Images API，生成供 Draw.io Scientific Illustrator 重绘的参考图，同时输出 `workflow-design.json` 和 `drawio-flowchart-prompt.md`。数据图和模型实验图始终由本地 Python 确定性生成。

真实 Key 必须通过路由配置中的 `api_key_env` 对应环境变量提供，禁止写入 JSON。

本地 Streamlit 控制台：

```powershell
python -m pip install -e ".[ui]"
$env:PYTHONPATH="src"
python -m streamlit run src/mathworkstation/ui_app.py --server.headless true
```

控制台提供 Case 选择、DAG 状态、审批/重试、产物和论文浏览，以及绑定当前 Case、Session 和节点的受控 LLM 对话。详细说明见 `docs/ui-runbook.md`。
论文页优先显示最后一个 accepted 的 `paper/current.md`，并展示循环精修轮次、接受/拒绝计数、停止原因和质量向量。

不安装包也可以直接运行：

```powershell
$env:PYTHONPATH="src"
python -m mathworkstation.cli create-case --competition SM --title "测试案例"
```

也可以脱离 Codex 使用 Docker 运行 CLI。密钥保留在宿主机 `.env.local`，
不会写入镜像：

```powershell
docker build --tag mathworkstation:local .
.\scripts\run-docker.ps1 -Arguments @(
  "--output-root", "/work",
  "create-case", "--competition", "MCM", "--title", "2025 MCM C"
)
```

完整 API 流水线使用同一个包装脚本，把 `run-auto-pipeline` 的参数放入
`-Arguments`。详细说明见 [`docs/reproducibility.md`](docs/reproducibility.md)。

## 测试

```powershell
python -m pytest
```

详细规范见 `docs/`。

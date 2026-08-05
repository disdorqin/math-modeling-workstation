# 数学建模全流程 AI Skills 包

## 一句话介绍

这是一套面向学习、科研、业务分析和工程决策的数学建模 AI Skills 包。它把“复杂现实问题”拆成可执行的建模流程：问题拆解、变量假设、数据处理、模型选择、代码模板、结果验证、报告结构和审稿检查。

它不是代写论文、代赛、保奖或伪造结果工具。它更像一套数学建模工作流工具箱，帮助用户更快地把问题说清楚、把模型选对、把代码跑通、把结论核验清楚。

## 适合谁

| 人群 | 可以用来做什么 |
|---|---|
| 大学生、研究生、建模竞赛团队 | 课程作业、国赛/美赛/校赛训练、赛题拆解、模型复盘、论文结构自查 |
| 科研人员、课题组 | 变量假设设计、数据预处理、指标评价、预测建模、结果核验、论文/报告逻辑审查 |
| 数据分析师、商业分析人员 | 多指标评分、方案排序、趋势预测、用户分群、风险分层、报告结构化 |
| 产品、运营、管理人员 | 指标体系设计、方案优选、业务预测、实验复盘、资源配置 |
| 供应链、物流、制造、工程人员 | 库存/需求预测、产能分配、排班调度、路径优化、排队分析、仿真模拟 |
| 金融、风控、城市规划、公共管理、医疗公卫 | 风险评分、综合评价、政策情景模拟、资源分配、敏感性分析 |
| 教师、培训机构、咨询顾问 | 教学案例拆解、训练营流程设计、作业审阅、方案论证、客户报告审查 |

## 适合解决的问题

| 问题类型 | 典型场景 | 对应 Skill |
|---|---|---|
| 问题拆解 | 题目很长、目标混乱、分问题不清楚 | `mm-problem-decomposer` |
| 模型选型 | 不知道该用评价、预测、优化、分类还是仿真 | `mm-model-selector` |
| 变量假设 | 需要把现实问题转成变量、参数、假设、约束 | `mm-variable-assumption-builder` |
| 数据处理 | CSV 数据需要检查缺失、异常、重复、相关性 | `mm-data-eda-cleaning` |
| 综合评价 | 多指标打分、排序、优选、风险评分 | `mm-evaluation-models` |
| 数值预测 | 需求、销量、流量、风险、成本等趋势预测 | `mm-prediction-models` |
| 资源优化 | 预算、人力、产能、库存、路线、排班优化 | `mm-optimization-models` |
| 分类聚类 | 用户分群、样本分类、风险分层、模式识别 | `mm-classification-clustering` |
| 仿真模拟 | 随机风险、排队等待、服务能力、政策情景模拟 | `mm-simulation-models` |
| 报告结构 | 建模论文、业务报告、研究报告结构整理 | `mm-paper-structure-writer` |
| 摘要优化 | 摘要缺模型、缺结果、结论空泛或夸大 | `mm-abstract-polisher` |
| 审稿查错 | 模型错配、假设过强、结果无支撑、图表不清 | `mm-paper-reviewer` |

## 这个包包含什么

| 模块 | 内容 |
|---|---|
| 13 个 Agent Skill | 覆盖数学建模从拆题到审稿的完整流程 |
| Python 脚本 | EDA、熵权、TOPSIS、AHP、灰色关联、GM(1,1)、回归、时间序列、优化、分类聚类、仿真等脚本 |
| 共享模板 | 拆题模板、变量表、假设表、选模输出、数据报告、论文结构、摘要、审稿报告 |
| 模型卡 | AHP、熵权法、TOPSIS、灰色关联、PCA、回归、GM(1,1)、时间序列、线性规划、整数规划、聚类、分类、蒙特卡洛、排队模型等 |
| 检查清单 | 学术诚信、结果验证、代码质量、论文逻辑、竞赛边界 |
| 示例材料 | 样例题、样例数据、分类样例、端到端资源分配案例 |
| 发布辅助 | 依赖文件、脚本命令索引、公开版验证脚本 |

## 目录结构

出售版根目录只保留一个综合介绍文件和一个 `skills/` 文件夹，买家打开后不会看到复杂的工程目录。

```text
数学建模全流程AI-Skills出售版/
├── 数学建模全流程AI-Skills包介绍.md
└── skills/
    ├── math-modeling-orchestrator/
    ├── mm-problem-decomposer/
    ├── mm-model-selector/
    ├── mm-variable-assumption-builder/
    ├── mm-data-eda-cleaning/
    ├── mm-evaluation-models/
    ├── mm-prediction-models/
    ├── mm-optimization-models/
    ├── mm-classification-clustering/
    ├── mm-simulation-models/
    ├── mm-paper-structure-writer/
    ├── mm-abstract-polisher/
    ├── mm-paper-reviewer/
    ├── _shared/
    ├── _examples/
    └── _release/
```

说明：

- `skills/` 下 13 个不以下划线开头的目录是真正的 Agent Skill。
- `skills/_shared/` 是共享模板、模型卡和检查清单。
- `skills/_examples/` 是样例题、样例数据和端到端案例。
- `skills/_release/` 是购买者文档、依赖、许可证和公开版验证脚本。

## 13 个 Skill 说明

| Skill | 核心用途 | 典型输出 |
|---|---|---|
| `math-modeling-orchestrator` | 总控调度，判断任务类型并推荐后续 Skill | 推荐工作流、缺失信息、下一步 |
| `mm-problem-decomposer` | 拆解题目、背景、目标、输入、输出、约束和难点 | 分问题表、已知条件、隐含约束、数据需求 |
| `mm-model-selector` | 根据问题类型、数据条件和约束推荐候选模型 | 候选模型比较、主模型、备选模型、不建议模型 |
| `mm-variable-assumption-builder` | 生成变量、参数、假设、目标函数和约束草案 | 变量表、假设表、约束条件、风险提示 |
| `mm-data-eda-cleaning` | 数据清洗、缺失值、异常值、描述统计、相关性和 EDA 报告 | summary、missing values、correlation、基础图表 |
| `mm-evaluation-models` | TOPSIS、熵权法、AHP、灰色关联、PCA 综合评价 | 权重、得分、排名、敏感性分析建议 |
| `mm-prediction-models` | 回归、时间序列、GM(1,1) 和预测基线 | 预测结果、误差指标、外推风险说明 |
| `mm-optimization-models` | 线性规划、整数规划、多目标优化和资源分配模板 | 目标函数、约束、最优解、不可行处理 |
| `mm-classification-clustering` | 分类、聚类、用户分群、模式识别和特征建模 | 分类指标、混淆矩阵、聚类标签、PCA 可视化 |
| `mm-simulation-models` | 蒙特卡洛、排队模型、情景模拟和敏感性分析 | 仿真样本、均值方差、置信区间、队列指标 |
| `mm-paper-structure-writer` | 建模论文或报告结构、章节骨架和结果占位 | 论文结构、每节写作要点、需补充结果 |
| `mm-abstract-polisher` | 摘要诊断、结果表达优化、压缩版本和核验提醒 | 改写版摘要、修改理由、需核验数据 |
| `mm-paper-reviewer` | 审查模型逻辑、假设、公式、结果、图表和诚信风险 | 风险等级、逐节审稿、优先修改清单 |

## 如何在 Codex 中使用

推荐显式点名 Skill，这样触发更稳定。

### 总控判断

```text
请使用 $math-modeling-orchestrator 判断这个数学建模任务应该怎么推进：……
```

### 赛题/问题拆解

```text
请使用 $mm-problem-decomposer 分析下面的题目，列出每一问的输入、输出、变量、约束和难点：……
```

### 模型选型

```text
请使用 $mm-model-selector 根据题目拆解和数据条件推荐 2-4 个候选模型，并说明主模型和备选模型：……
```

### 数据分析

```text
请使用 $mm-data-eda-cleaning 检查这个 CSV 数据，重点看缺失值、异常值、相关性和对建模的影响：……
```

### 论文/报告审查

```text
请使用 $mm-paper-reviewer 审查这段建模报告草稿，优先指出高风险逻辑问题、模型错配和无法核验的结果：……
```

## 如何运行脚本

如果只使用 Skill 文本工作流，不一定需要安装 Python 依赖。若要运行内置脚本，需要先在出售版根目录安装依赖：

```bash
python3 -m pip install -r skills/_release/requirements.txt
```

完整脚本命令索引在：

```text
skills/_release/docs/SCRIPT_INDEX.md
```

示例：

```bash
python3 skills/mm-data-eda-cleaning/scripts/eda_report.py --input skills/_examples/sample_data_prediction.csv --output outputs/eda
```

```bash
python3 skills/mm-evaluation-models/scripts/topsis.py --input skills/_examples/sample_data_evaluation.csv --output outputs/topsis --columns x1,x2,x3 --weights 0.3,0.4,0.3 --directions positive,negative,positive
```

```bash
python3 skills/mm-prediction-models/scripts/gm11.py --input skills/_examples/sample_data_prediction.csv --output outputs/gm11 --column usage --periods 3
```

## 示例应用路线

### 路线 1：数学建模题目训练

1. 用 `math-modeling-orchestrator` 判断流程。
2. 用 `mm-problem-decomposer` 拆题。
3. 用 `mm-model-selector` 选模型。
4. 用 `mm-variable-assumption-builder` 设计变量和假设。
5. 根据题型调用评价、预测、优化、分类聚类或仿真 Skill。
6. 用 `mm-paper-structure-writer` 组织论文结构。
7. 用 `mm-paper-reviewer` 做最后审查。

### 路线 2：业务分析/工程决策

1. 明确业务目标，例如评分、预测、分群、资源分配或服务能力评估。
2. 用 `mm-model-selector` 判断模型方向。
3. 用 `mm-data-eda-cleaning` 检查数据质量。
4. 调用对应模型 Skill 和脚本。
5. 用 `mm-paper-reviewer` 检查结论是否被数据支持。

### 路线 3：科研建模辅助

1. 用 `mm-variable-assumption-builder` 把研究问题抽象为变量、假设和约束。
2. 用 `mm-model-selector` 比较候选模型。
3. 用 `mm-data-eda-cleaning` 检查数据可用性。
4. 用模型 Skill 生成代码模板和验证建议。
5. 用 `mm-paper-reviewer` 检查逻辑、结论和可验证性。

## 示例材料在哪里

| 路径 | 内容 |
|---|---|
| `skills/_examples/sample_problem_01_resource_allocation.md` | 资源分配样例题 |
| `skills/_examples/sample_problem_02_evaluation_ranking.md` | 综合评价排序样例题 |
| `skills/_examples/sample_problem_03_prediction.md` | 趋势预测样例题 |
| `skills/_examples/sample_data_evaluation.csv` | 多指标评价样例数据 |
| `skills/_examples/sample_data_prediction.csv` | 预测样例数据 |
| `skills/_examples/classification_sample.csv` | 分类样例数据 |
| `skills/_examples/end_to_end/resource_allocation_workflow.md` | 端到端资源分配建模案例 |

## 质量验证

出售版附带公开包验证工具。进入出售版根目录后运行：

```bash
python3 skills/_release/scripts/validate_public_package.py
```

通过后会看到：

```text
Public package validation passed.
```

这个验证会检查：

- 根目录是否只有介绍 MD 和 `skills/`；
- 13 个 Skill 是否都存在；
- 每个 Skill 是否有 `SKILL.md`、`agents/openai.yaml` 和 `references/`；
- 共享模板、模型卡、检查清单数量是否完整；
- 15 个模型脚本是否支持 `--help`；
- 样例数据能否跑通基础 demo；
- 是否存在 `.pytest_cache`、`__pycache__`、`.pyc`、`.DS_Store` 等发布污染物。

## 学术诚信和使用边界

可以使用本包做：

- 建模学习和训练；
- 课程作业辅助；
- 赛前准备；
- 科研建模辅助；
- 业务分析和工程决策支持；
- 数据清洗和代码模板；
- 报告结构化和审稿自查。

不应使用本包做：

- 代写完整参赛论文；
- 代替用户参赛；
- 承诺获奖或保奖；
- 编造数据、图表、实验结果或参考文献；
- 输出未经用户核验的可提交终稿。

所有模型结果、业务结论、科研结论和竞赛提交内容都需要用户自行核验。正在进行的正式竞赛、课程项目、研究项目或商业报告，应先确认对应规则是否允许使用 AI 辅助。

## 常见问题

### 这套包能不能直接生成完整论文？

不建议，也不应这样使用。它可以帮助拆题、选模型、整理结构、生成代码模板、检查摘要和审稿查错，但最终论文、报告和提交内容需要用户自己理解、核验和完成。

### 没有编程基础能用吗？

可以使用 Skill 的文字工作流，例如拆题、选模型、变量假设、论文结构和审稿。如果要运行 Python 脚本，需要基本命令行环境和依赖安装。

### 业务场景能用吗？

可以。它适合多指标评价、方案优选、趋势预测、用户分群、资源配置、排队仿真等工作场景。但业务结论必须结合实际口径和数据来源核验。

### 科研场景能用吗？

可以。它适合变量假设、模型选择、数据清洗、预测/评价/优化建模和论文逻辑审查。但不能替代真实实验、真实数据和研究伦理审查。

### 脚本结果能直接写进报告吗？

不能直接照搬。脚本输出需要用户核验数据字段、参数设置、模型前提和结果含义，再决定如何写入报告。

### 为什么没有承诺获奖或保证效果？

数学建模质量取决于题目理解、数据质量、模型适配、验证过程和表达能力。任何“保证获奖”“直接可提交”的承诺都不负责任。

## 建议使用顺序

首次使用建议从总控开始：

```text
请使用 $math-modeling-orchestrator 帮我判断这个任务应该调用哪些数学建模 Skill，并列出需要补充的信息。
```

如果已经知道任务类型，可以直接调用对应 Skill，例如：

```text
请使用 $mm-evaluation-models 帮我建立多指标评价模型。
```

```text
请使用 $mm-optimization-models 帮我把资源分配问题写成目标函数和约束。
```

```text
请使用 $mm-abstract-polisher 优化这段数学建模摘要，但不要编造结果。
```


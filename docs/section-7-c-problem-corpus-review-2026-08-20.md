# Section 7.0–7.1 Review — C-Problem Knowledge Base + Excellent Corpus

Date: 2026-08-20

## Gate result

**PASS for local-knowledge inventory + full-text C-problem corpus.**

Not certified:

- PDF visual/layout quality: **UNVERIFIED**
- blind/human competition review: **UNVERIFIED**
- three CUMCM C end-to-end workstation gates: **NOT YET RUN**

The text corpus is a research prior and benchmark source, not award proof.

---

## 1. 原来具体有什么问题？

Section 6 已经证明工作站能够在 2023 MCM C Wordle 和 2018 MCM C Energy Compact 上形成 Research State -> Paper -> Auditor 闭环，但存在两个阶段性问题：

1. 优秀论文标准仍主要来自 MCM C，同一赛制偏置较大；
2. 用户本地约 9.6 GB 数学建模资料此前只是“文件夹”，没有稳定的知识地图与运行时边界；
3. 早期 Section 7 计划曾把 A/B/C 等不同题混入 benchmark，与当前“只专精 C题”的目标冲突；
4. CUMCM PDF 的中文字体映射不统一，单纯依赖 Poppler 会把可解析文本误判成扫描件；
5. 旧 profiler 对中文方法、MCM Summary Sheet、RFM/RFMS、Fermat/shortest-path 等 C题常见构造识别不足；
6. 如果直接统计“优秀论文最常用什么算法”，会产生错误的算法模仿压力，而不是学习研究行为。

---

## 2. 成熟做法应该是什么？

本节没有把优秀论文当模板库，而是采用 corpus / evidence prior 的思路：

```text
Raw archive
-> asset inventory
-> copyright-safe derived full-text profile
-> same-problem / cross-problem recurring behavior
-> Modeling / Validation / Paper priors
-> real-problem gate
```

重要原则：

- 原文与附件保持外部只读；仓库只保存路径、manifest 和派生信号；
- 同题论文比较 recurring capability，不要求复制某一个算法；
- CUMCM C 与 MCM C 分别保留赛制 profile；
- 只有真实数据/真实 solver/真实 validation 能关闭 Research gap；
- visual/layout 与 human review 必须单独验证，不能从文本 parser 自证。

---

## 3. 本节具体改了什么？

### Local Knowledge Base

对：

`D:\作业\竞赛\大学生数学建模\美赛\备赛\资料`

完成只读 inventory：

- 4 个一级分支；
- **211 个目录**进入 inventory 范围；
- `论文`：约 180 目录 / 867 文件 / 9.1 GB；
- `课程课件`：约 24 目录 / 209 文件 / 476 MB；
- 识别 Skill、题库、优秀论文、方法教材、课程、代码、模板、经验 prompt、归档副本等角色。

新增：

- `docs/LOCAL_MODELING_KNOWLEDGE_BASE_README.md`
- `config/ref_models/local_knowledge_base_registry.json`

### PDF / full-text extraction

新增：

- `src/mathworkstation/excellent_pdf_text.py`

策略：PyMuPDF -> pypdf -> Poppler fallback；OCR 只在无可用 Unicode 文本层时考虑。

这一步证明：很多 CUMCM PDF 不是扫描件，只是 Poppler 无法恢复中文字库映射。

### Rich full-text corpus

新增：

- `src/mathworkstation/excellent_fulltext_corpus.py`
- `tests/test_excellent_fulltext_corpus.py`

派生 schema：

- Question type
- Model sequence
- Why this model
- Model transition
- Validation type
- Figure purpose
- Innovation pattern
- Abstract structure
- Failure pattern

补充双语/领域方法词典：

- Fermat point / geometric construction
- shortest path
- RFM/RFMT/RFMS/FMS member-value models
- member lifecycle state model
- 以及已有时间序列、优化、分类、评价、仿真等方法。

MCM Summary Sheet parser 也修复，`Team Control Number` 不再错误截断摘要。

### C-only primary benchmark

正式 benchmark：**3 CUMCM C + 2 MCM C，21 篇优秀论文**。

1. CUMCM 2010 C — Oil Pipeline Layout — 3篇可解析优秀论文
2. CUMCM 2018 C — Retail Member Profiling — 3篇
3. CUMCM 2023 C — Vegetable Pricing/Replenishment — 4篇
4. MCM 2018 C — Energy Compact — 5篇 O奖
5. MCM 2023 C — Wordle — 6篇 O奖

新增：

- `config/ref_models/cumcm_2010_c_oil_pipeline_excellent_deep.json`
- `config/ref_models/cumcm_2018_c_retail_member_excellent_deep.json`
- `config/ref_models/cumcm_2023_c_vegetable_excellent_deep.json`
- `config/ref_models/c_problem_excellent_benchmark_v1.json`
- `src/mathworkstation/c_problem_benchmark.py`
- `tests/test_c_problem_benchmark.py`

Primary Gate 强制：

- `scope == C_PROBLEM_ONLY`
- 所有 `problem_letter == C`
- 至少 3 道 CUMCM C
- 至少 2 道 MCM C
- reference paper count 一致且不少于 15
- benchmark asset 必须真实存在

因此之前用于架构泛化的 2018B RGV / 2023A heliostat 等资料可以继续作为 archive/regression，但不会污染 primary excellent benchmark。

---

## 4. 真实优秀论文告诉了我们什么？

### CUMCM 2010 C

重复能力不是“必须用某个求解器”，而是：

- 3/3 optimization / decision strategy
- 3/3 constraint-structure-driven modeling
- 3/3 scenario branching
- 2/3 model comparison
- 2/3 algorithmic / constraint-aware improvement
- 3/3 abstract contains quantified results

几何构造、Fermat、shortest-path 是服务题意的工具。

### CUMCM 2018 C

- 3/3 statistical analysis + classification/scoring + decision
- 3/3 data-characteristic-driven selection
- 3/3 constraint-structure-driven selection
- 3/3 domain-specific member/state representation
- 2/3 refine previous model / hybrid progression

高水平点在于“会员价值/状态表示 + 生命周期链”，而不是 K-means/AHP 本身。

### CUMCM 2023 C

- 4/4 forecasting
- 4/4 statistical analysis
- 4/4 optimization/resource allocation/decision
- 4/4 data + constraint driven model choice
- 3/4 hybrid model transition
- 3/4 sensitivity/robustness
- 3/4 uncertainty interval
- 4/4 quantified + validation-aware conclusion language in abstract

具体算法高度分散：ARIMA、Prophet、VAR、LSTM、Grey、SA、PSO、MCMC 等都存在，因此算法频率不能成为强制模型选择。

### MCM C 已验证规律

Wordle 与 Energy 的 Section 6 same-problem corpus继续作为两道 MCM C anchor：

- domain-specific representation / mechanism
- uncertainty / validation
- high-information Summary Sheet
- prompt-specific letter/memo
- evidence-backed synthesis

---

## 5. 五题共同 C-Problem Priors

当前可以安全进入下一阶段的 shared priors：

1. **Problem-specific representation before generic model**：先构造真正对应赛题语义的变量/状态/指标/几何对象，再选算法。
2. **Question chain, not independent model zoo**：有关联的后续小问应复用/扩展/挑战前问 Research State。
3. **Data / mechanism / constraint driven model choice**：不能按“优秀论文常用模型”选模。
4. **Quantified answers in high-visibility sections**：有 evidence 时，摘要/结论必须给真实答案与关键量，不只报模型名。
5. **Validation matches claim type**：预测、评价、优化、分类、解释必须使用各自协议。
6. **Algorithm diversity is normal**：同题优秀论文算法高度分散；corpus 只提供候选 prior，不提供答案。
7. **Decision/deliverable is downstream evidence**：策略、目标、路线、补货、memo/letter 都不得由写作层补造。

机器定义见：

`config/ref_models/c_problem_excellent_benchmark_v1.json`

---

## 6. 验证

Section 7 新增 corpus / registry：

```text
16 passed
```

关键 Section 6 compatibility checks：

```text
2 passed  # Wordle same-problem + readiness
11 passed # Energy/Wordle real gate + Validation
```

一次性大型 pytest 组合在 DevSpace connector 层出现 502 / timeout，因此未把连接错误算作测试失败。此前 Section 6 已验证的 47-test gate 仍是历史基线；本节实际修改集中在 corpus/parser/registry，不宣称重新完成了完整 47-test 单次运行。

已知全仓历史环境 blocker 仍是 Python 3.11 + Tenacity 5.1.5 的 `asyncio.coroutine` collection incompatibility，与本节无关。

---

## 7. 下一 Gate

**Goal 7.2 — C-Problem Modeling Knowledge**

不再继续扩论文数量作为主要工作。下一步把上述 shared priors 转成机器可执行的：

```text
CProblem benchmark
-> ModelingBrain prior
-> Validation obligations
-> Research Repair signals
```

要求：

- priors 只能影响候选生成/审查，不能直接替代 Solver feasibility；
- “优秀论文用了 X”不能成为方法强制理由；
- Research gap 必须回 Section 1–5；
- Paper gap 才留 Section 6；
- 之后再跑 3 道真实 CUMCM C end-to-end gate。

Human review 仍放在 Goal 7.5：内部 Gate 做到值得人工审阅后，再请用户集中审一版。

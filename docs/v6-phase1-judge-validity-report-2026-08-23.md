# V6 Phase 1 — Judge Validity Report

日期：2026-08-23  
状态：**MVP COMPLETE / FINAL H1 STILL INCONCLUSIVE**  
当前分支基线：`m2-contest-grade-paper @ 63f6459688cad47ee09323f1d1b93404eb106032`

---

## 1. 本轮问题

V6 Phase 1 只回答：

> 当前内部 Judge / Benchmark 能不能可靠地区分真实优秀论文与当前工作站论文，并作为后续 Generator 优化的 award-quality reward？

本轮没有修改：

- ModelingBrain；
- ModelStructure；
- solver selection；
- ModelStoryPlanner；
- ResearchStatePaper 主生成逻辑；
- Figure planner；
- 为当前稿件服务的 generator 逻辑。

即：**Generator frozen，研究 Judge。**

---

## 2. Calibration MVP

本轮建立：

```text
artifacts/meta_benchmark/judge_v1/
  manifest.json
  anonymization_manifest.json
  anonymized/README.md
  pairwise_pairs.jsonl
  judge_results/internal_current.jsonl
  aggregate.json
  judge_validity_report.md
```

其中 `artifacts/` 按仓库既有 `.gitignore` 策略为本地运行产物，不默认进入 Git；可复现协议、结果摘要与实现代码通过本报告和下述源码进入版本控制。本轮不修改全局 artifact policy。

以及通用基础设施：

```text
src/mathworkstation/judge_validity.py
scripts/run_v6_judge_validity.py
tests/test_judge_validity.py
```

### 当前 paper set

优先采用 C题，且把 2024 same-problem pair 放在最高优先级：

1. `2409404_2024_MCM_C_Outstanding.pdf` — real excellent；
2. `20260823-MCM-0004-D97D` — current workstation MCM 2024 C；
3. `20260822-MCM-0005-H7E2` — older workstation MCM 2024 C；
4. `2318036_2023_MCM_C_Outstanding.pdf` — real excellent。

本轮没有为了凑数量加入 ICM E/F/Z，因为这会弱化 C-only calibration 的解释力。

---

## 3. 匿名化状态

已实现：

```text
anonymize_paper_text()
```

会掩盖常见：

- Outstanding / Finalist / O Award 等奖项词；
- Team / Control Number；
- standalone 6–7 digit team ID；
- 明示 Author / School / University / Institution 行。

并新增 position-swapped pair generator。

但当前没有把 raw reference full text 复制进 repo。原因：

1. 现有项目政策要求 raw papers 保持在外部只读资料库；
2. regex 不能保证去掉所有作者/学校身份；
3. 真实 blind run 前仍需要 manual leakage review；
4. PDF visual anonymization 仍未完成。

所以当前状态是：

```text
text anonymization machinery = READY
blind material manual review = PENDING
visual/page blind package = UNVERIFIED
```

没有把“自动脱敏函数存在”冒充成“盲评已经完成”。

---

## 4. Internal Judge 1 — CompetitionPaperAuditor raw-text calibration

为了尽量对称，本轮没有把 generator-side NarrativeGraph 只喂给工作站稿，而是双方都采用：

```text
PDF -> pdftotext -> CompetitionPaperAuditor.audit(text, narrative=None, competition="MCM")
```

排序探针只使用现有输出：

```text
gate severity -> block_count -> review_count
```

这不是新建 award evaluator，只是检验“若现有 Auditor 被误用为质量排序信号，会发生什么”。

### 2024 same-problem pair

真实 Outstanding：

```text
2409404_2024_MCM_C_Outstanding.pdf
BLOCK = 1
REVIEW = 6
```

当前工作站：

```text
20260823-MCM-0004-D97D
BLOCK = 1
REVIEW = 4
```

因此按 defect-count 排序：

```text
WORKSTATION_CURRENT > REAL_OUTSTANDING
```

这与真实奖项 provenance、以及用户此前对优秀论文和当前稿件的质量判断方向冲突。

重要：用户此前反馈不是本轮正式 blind human vote，所以只能作为非盲 prior，不能计入 H1 ground truth。

### current vs older workstation

旧稿：

```text
20260822-MCM-0005-H7E2
BLOCK = 1
REVIEW = 8
```

当前稿：

```text
20260823-MCM-0004-D97D
BLOCK = 1
REVIEW = 4
```

这里 Auditor 能识别：

```text
CURRENT > OLDER
```

因此结论不是“CompetitionPaperAuditor 没用”。更准确地说：

> 它对 document/hard-gate regression 有价值，但 defect-count 不能未经校准直接升级成 award-quality reward。

---

## 5. Internal Judge 2 — PaperQualityBenchmark raw-text calibration

同样采用双方对称输入：

```text
PDF -> pdftotext
figures = []
profile = MCM_C
```

这样不会给工作站稿额外注入内部 FigureRegistry，而真实论文没有相同 privileged metadata。

结果：

### 2024 real vs current

```text
REAL_OUTSTANDING = 66.25
WORKSTATION_CURRENT = 55.0
```

因此该 detector 在这对上排序正确：

```text
REAL_OUTSTANDING > WORKSTATION_CURRENT
```

但分数来源主要仍是：

- abstract density；
- abstract numeric density；
- figure density；
- table density。

双方都没有通过完整 award-quality 维度。

### current vs older

```text
WORKSTATION_CURRENT = 55.0
WORKSTATION_OLDER = 55.0
```

即：

```text
TIE
```

它无法识别 Auditor 已能看出的 current-vs-old document regression improvement。

### real 2023 vs real 2024

```text
REAL_2023 = 66.25
REAL_2024 = 66.25
```

也是 TIE。

这再次说明该服务更像 density calibration，而不是能细粒度排序 award papers 的 Judge。

---

## 6. 当前两个内部 Judge 的冲突

对最关键的 2024 same-problem pair：

| Judge | preference |
|---|---|
| CompetitionPaperAuditor raw-text probe | workstation current |
| PaperQualityBenchmark raw-text | real Outstanding |

因此：

```text
cross_judge_agreement = 0.0
```

而 position swap：

```text
position_swap_consistency = 1.0
```

这说明冲突不是简单 A/B 位置偏差，而是 **两个内部 evaluator 奖励的东西不同**。

---

## 7. Aggregate

`artifacts/meta_benchmark/judge_v1/aggregate.json`：

```text
paper_count = 4
pair_count = 6
vote_count = 12
human_vote_count = 0
independent_model_vote_count = 0
internal_vote_count = 12
position_swap_consistency = 1.0
cross_judge_agreement = 0.0
```

当前 discrimination：

```text
competition-paper-auditor-raw:
  checked = 2
  correct vs provenance prior = 1
  accuracy = 0.5

paper-quality-benchmark-raw:
  checked = 1
  correct vs provenance prior = 1
  accuracy = 1.0
```

注意：`accuracy_vs_provenance_prior` 不是 human-ground-truth accuracy。

---

## 8. JudgeEval 基础设施

新增 `judge_validity.py`，实现：

- private calibration manifest；
- blind IDs；
- common identity/award text masking；
- order-swapped pair construction；
- judge vote schema；
- preferred paper normalization（避免 LEFT/RIGHT 与 paper identity 混淆）；
- position-swap consistency；
- cross-judge agreement；
- real-vs-current / current-vs-older discrimination probe；
- H1 conservative verdict。

最重要的 guard：

> **没有 blind HUMAN vote 时，H1 永远不能自动变成 SUPPORTED/REJECTED。**

因为 known award label、用户非盲反馈、internal score 都不等价于 JudgeEval human anchor。

测试：

```text
PYTHONPATH=src python -m pytest -q tests/test_judge_validity.py
5 passed
```

---

# 9. 对 Phase 1 五个问题的回答

## Q1 — 当前内部 evaluator 是否能可靠区分真实优秀论文和工作站论文？

### 当前答案

**不能证明可靠，且已发现实质冲突。**

证据：

- 同一个 2024 same-problem real-vs-current pair；
- `CompetitionPaperAuditor` 若按 defect count 排序，会选工作站；
- `PaperQualityBenchmark` 会选真实 Outstanding；
- 两者 cross-judge agreement = 0；
- 目前没有 blind human / independent judge 来决定哪类内部 signal 与真实竞赛偏好一致。

因此当前 evaluator ensemble **没有资格作为 V6 Generator 的统一 award reward**。

---

## Q2 — 哪些 evaluator 只能作为 hard gate，不能作为 award-quality reward？

目前至少：

### 主要作为 hard/regression gate

- `PaperQualityEvaluator` 的 evidence/claim/number preservation 与 section contract；
- `CompetitionPaperAuditor` 的 internal-ID、reference、pollution、Research State coverage、competition-profile hard rules；
- provenance / artifact integrity / leakage / validation invariants。

### 主要作为 calibration/prior，而非 award reward

- `PaperQualityBenchmarkService`；
- `ExcellentCorpusBenchmarkService` recurring-pattern detectors；
- same-problem recurring-pattern gap detector。

它们可以说：

> “某个结构、密度、evidence obligation 是否缺失”。

它们目前不能可靠说：

> “A 比 B 更像 O/F/国奖论文”。

---

## Q3 — internal score 与真实质量差异最大的维度是什么？

当前最明显缺口不是 formula/figure/table 数量，而是现有 Judge 尚没有经过校准的：

```text
scientific/modeling core
problem insight
non-obviousness
unified mathematical worldview
model progression necessity
story discovery
figure argumentative value
whole-paper award preference
```

当前多个 detector 更擅长：

```text
presence / count / structure / traceability / recurring patterns
```

这正是 V6 所担心的 Goodhart 区域。

---

## Q4 — H1 Judge Validity Bottleneck

正式状态：

```text
INCONCLUSIVE
```

原因不是“没有问题”，而是 V6 明确要求 human anchor。

当前已经存在 **strong preliminary evidence toward SUPPORTED**：

1. same-problem 2024 pair 上一个内部 Judge 反向排序；
2. 两个内部 Judge 对该关键 pair 完全冲突；
3. 当前高内部指标（如最新 MCM 2024 `PaperQualityBenchmark=88.75`、Visual=91、Audit=PASS）仍不能替代真实 award preference；
4. evaluator 维度明显偏 completeness/density/structure，scientific core 缺少已校准判据。

但：

```text
blind human votes = 0
independent model votes = 0
visual blind judge = UNVERIFIED
```

因此不能把 H1 偷偷写成 SUPPORTED。

---

## Q5 — 下一步

选择：

```text
C. 数据不足，先补 calibration
```

而不是：

```text
B. 直接进入 Compiler Freedom Ablation
```

也不应立刻大规模：

```text
A. 重写 Judge
```

因为我们还需要先知道：

- 哪些维度与 human preference 真正一致；
- 当前 internal Judge 到底在哪些 pair/维度系统性失败；
- 独立强模型 Judge 与人工是否一致。

下一步只补：

1. materialize anonymized text pair；
2. 至少 1 个 blind human anchor；
3. 至少 1 个真正独立强模型 Judge；
4. 同一 pair 做 AB/BA；
5. 加入更多 real-vs-current C题 pair；
6. 视觉维度必须通过实际 PDF page review 单独验证。

在这批 calibration 完成前：

> **禁止进入 Phase 2 大规模 Paper Compiler 重构。**

---

## 10. 本轮没有做的事情

- 没改 ModelingBrain；
- 没改 ModelStory；
- 没改 Paper Engine；
- 没为了让结果 PASS 调 evaluator threshold；
- 没用 known award label 冒充 blind human vote；
- 没把 PDF 视觉质量伪装成已验证；
- 没因为旧 test assertion 漂移而顺手改 Judge 本体。

---

## 11. Phase 1 当前停止点

Phase 1 的**最小可运行实现与内部校准探针已完成**。

但 V6 Phase 1 的最终 Judge certification 尚未完成。

当前项目必须停在：

```text
Phase 1 — CALIBRATION REQUIRED
H1 = INCONCLUSIVE (strong preliminary evidence toward SUPPORTED)
```

除非 blind human / independent judge calibration 被补齐，否则不得宣称 evaluator 已冻结为可信 `frozen evaluator v1`。

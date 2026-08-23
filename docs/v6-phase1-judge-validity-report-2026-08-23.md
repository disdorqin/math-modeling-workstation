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
scripts/run_v6_internal_judges.py
scripts/materialize_v6_judge_packets.py
scripts/run_v6_independent_judge.py
scripts/build_v6_human_review_html.py
scripts/record_v6_human_vote.py
tests/test_judge_validity.py
```

### 当前 paper set

只采用 C题，并优先构造 same-problem 对照。当前 calibration set 已扩展为 9 篇：

MCM 2024 C：

1. `2409404_2024_MCM_C_Outstanding.pdf` — real excellent；
2. `20260823-MCM-0004-D97D` — current workstation；
3. `20260822-MCM-0005-H7E2` — older workstation。

MCM 2023 C：

4. `2318036_2023_MCM_C_Outstanding.pdf` — real excellent。

CUMCM 2023 C：

5. `20260822-CUMCM-0031-SRTA` — current workstation；
6. `C050.pdf` — real excellent corpus；
7. `C126.pdf` — real excellent corpus；
8. `C228.pdf` — real excellent corpus；
9. `C235.pdf` — real excellent corpus。

因此当前含 5 组 real-vs-current same-problem 逻辑比较（1 组 MCM 2024 + 4 组 CUMCM 2023），另有 current-vs-older 与 real-vs-real calibration。仍未为了凑数量加入 ICM E/F/Z。

---

## 3. 匿名化状态

已实现：

```text
anonymize_paper_text()
```

会掩盖常见：

- Outstanding / Finalist / O Award 等英文奖项词；
- 一/二/三等奖、国一/国二/国三、优秀论文等中文奖项词；
- Team / Control Number / 参赛队号 / 队号；
- standalone 6–7 digit team ID；
- 明示 Author / School / University / Institution；
- 学校 / 作者 / 单位 / 指导教师等中文身份行。

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
PDF -> pdftotext -> CompetitionPaperAuditor.audit(text, narrative=None, competition=<MCM|CUMCM>)
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

### 2023 CUMCM C same-problem expansion

当前工作站 2023 国赛 C：

```text
BLOCK = 1
REVIEW = 3
```

四篇同题真实优秀论文分别为：

```text
C050: BLOCK = 1, REVIEW = 5
C126: BLOCK = 1, REVIEW = 6
C228: BLOCK = 1, REVIEW = 9
C235: BLOCK = 1, REVIEW = 4
```

所以按当前 defect-count 排序，Auditor 对四组 real-vs-current **全部偏向工作站稿**。结合 MCM 2024 real-vs-current 与 current-vs-older，总体 provenance probe 为：

```text
checked = 6
correct = 1
accuracy = 16.7%
```

更重要的是失败模式具有明显 generator-coupling：真实优秀论文经常触发 `COMPETITION_PROFILE_REQUIRED_SECTION_MISSING`、`COMPETITION_PROFILE_SUMMARY_HEADING_MISSING`、`EXCELLENT_PRIOR_*` 等 detector，而工作站正是按这些内部 profile / lexical convention 生成，因此天然更容易通过。

因此结论不是“CompetitionPaperAuditor 没用”。更准确地说：

> 它对 document/hard-gate regression 有价值，但 defect-count 不能未经校准直接升级成 award-quality reward；在跨赛制 real-vs-current calibration 中已观察到强烈 generator-coupling。

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

### 2023 CUMCM C expansion

当前工作站 raw-text benchmark：

```text
55.0
```

真实优秀论文：

```text
C050 = 66.25
C126 = 66.25
C228 = 55.0
C235 = 66.25
```

因此 3 组给出 real > current，1 组 TIE。连同 MCM 2024，在它做出非平手判断的 4 组 real-vs-current 上 provenance probe 为 4/4。

但检查 per-dimension 后发现，这个“正确”高度脆弱：当前对称 raw-text 模式下 abstract extractor 对这些 PDF 文本多数返回 0，`figures=[]` 又使 figure density 必然为 0，所以主要分离信号实际上来自 **table count 是否跨过阈值**。这不是我们要寻找的 scientific/modeling-core award signal。

这再次说明该服务更像 density calibration，而不是能细粒度排序 award papers 的 Judge；表面 100% provenance accuracy 不能升级为 Judge validity 证明。

---

## 6. 当前两个内部 Judge 的冲突

最关键的 2024 MCM same-problem pair 已出现方向相反：

| Judge | preference |
|---|---|
| CompetitionPaperAuditor raw-text probe | workstation current |
| PaperQualityBenchmark raw-text | real Outstanding |

扩展到 CUMCM 2023 后，在两个 Judge 都能形成唯一 logical preference 的 4 个 swap group 上：

```text
cross_judge_agreement = 0.0
cross_judge_pairs_checked = 4
```

而所有可检查的 AB/BA：

```text
position_swap_consistency = 1.0
position_swap_groups_checked = 11
```

这说明冲突不是简单 A/B 位置偏差，而是 **两个内部 evaluator 奖励的东西不同**；同时其中一个明显偏向 generator profile，另一个主要依赖粗密度计数。

---

## 7. Aggregate

`artifacts/meta_benchmark/judge_v1/aggregate.json`：

```text
paper_count = 9
pair_count = 14
vote_count = 28
human_vote_count = 0
blind_human_vote_count = 0
independent_model_vote_count = 0
internal_vote_count = 28
position_swap_consistency = 1.0
position_swap_groups_checked = 11
cross_judge_agreement = 0.0
cross_judge_pairs_checked = 4
```

当前 discrimination：

```text
competition-paper-auditor-raw:
  checked = 6
  correct vs provenance prior = 1
  accuracy = 0.166667

paper-quality-benchmark-raw:
  checked = 4
  correct vs provenance prior = 4
  accuracy = 1.0
```

注意：`accuracy_vs_provenance_prior` 不是 human-ground-truth accuracy。尤其 `PaperQualityBenchmark` 的 1.0 不能被解释为“Judge 已可靠”：在当前 raw-text 对称模式下，9 篇论文的 abstract density / numeric density / figure density 多数都被 extractor 读成 0，real-vs-current 的分离主要来自 table count 是否跨过阈值。因此它更像一个偶然与 provenance 同向的粗密度 detector，而不是 scientific-core judge。

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

> **H1 只允许由真实 blind-human preference 校准，不再允许 provenance label 参与正式判决；且至少需要 2 个不同 logical pair 的 blind-human anchor。**

因此：

- known award label 只能做 provenance diagnostic；
- 用户看过来源后的非盲反馈只能做 prior；
- 只有 1 个 blind logical pair 时仍强制 `INCONCLUSIVE`；
- `SUPPORTED` 必须来自多个 pair 上 internal Judge 与 blind-human preference 的实际低一致率；
- `REJECTED` 还额外要求独立模型与 blind human 同向，避免只靠同一套内部 Judge 自证。

测试：

```text
PYTHONPATH=src python -m pytest -q tests/test_judge_validity.py
10 passed
```

---

# 9. 对 Phase 1 五个问题的回答

## Q1 — 当前内部 evaluator 是否能可靠区分真实优秀论文和工作站论文？

### 当前答案

**不能证明可靠，且已发现实质冲突。**

证据：

- calibration 已覆盖 MCM 2024 C 与 CUMCM 2023 C 两个 same-problem 场景，共 5 组 real-vs-current；
- `CompetitionPaperAuditor` 的 provenance probe 仅 1/6=16.7%，且 4 篇 CUMCM 同题优秀论文全部被它排在当前工作站之后；
- Auditor 的主要失败码与工作站自身 profile/section convention 高度耦合，存在明显 reward co-adaptation 风险；
- `PaperQualityBenchmark` 在非平手的 4 组 real-vs-current 上方向为 4/4，但 raw-text 下 abstract/figure 信号大面积为 0，主要靠 table count 区分，属于脆弱的偶然正确；
- 两个内部 Judge 在可共同比较的 4 个 swap group 上 cross-judge agreement = 0；
- 目前没有 blind human / 成功返回的 independent-model vote 来决定哪类内部 signal 与真实竞赛偏好一致。

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

1. 不是单一样本：MCM 2024 + CUMCM 2023 共 5 组 real-vs-current same-problem calibration；
2. `CompetitionPaperAuditor` 的 provenance probe 只有 16.7%，并系统性偏爱符合自身 section/profile detector 的工作站稿；
3. 两个内部 Judge 在 4 个可共同判定的 swap group 上 agreement=0，同时 AB/BA position consistency=1.0，说明冲突来自 reward definition 而不是位置噪声；
4. `PaperQualityBenchmark` 的表面 4/4 主要由 table count 驱动，abstract/figure raw-text 信号大量失效，因此其正确方向不能证明 award validity；
5. 当前高内部指标（如最新 MCM 2024 `PaperQualityBenchmark=88.75`、Visual=91、Audit=PASS）仍不能替代真实 award preference；
6. evaluator 维度明显偏 completeness/density/structure，scientific core 缺少已校准判据。

但：

```text
human votes = 0
blind-verified human votes = 0
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

---

## 12. Phase 1 continuation — blind materialization 与 external Judge route probe

随后继续补齐 calibration 基础设施，没有进入 Phase 2。

### 12.1 真正 materialize 匿名全文 pair

新增：

```text
scripts/materialize_v6_judge_packets.py
```

它执行：

```text
private manifest
-> pdftotext
-> award/team/case identity redaction
-> source team-number literal redaction
-> identity leakage scan
-> anonymized/<blind_id>.txt
-> packets/<pair_id>.json
-> materialization_report.json
```

在实现过程中抓到并修复了三个真实 blind-eval bug：

1. `blind_pair_rows()` 原本会暴露私有 `kind=REAL_VS_CURRENT`，现已禁止 blind payload 包含 `kind`；
2. 第一版 literal redaction 错把短奖项代码 `O` 当成全局 literal，会污染所有英文 `o/O`。现已只允许 case ID / 文件中 6–7 位队号等安全 literal 做全局替换，并新增回归测试；
3. 原 descriptive pair ID `m24-real-current-ab` 自身泄漏 comparison provenance。现所有运行时 pair/swap group 均迁移为 opaque ID（例如 `G-A91F-1`），旧审阅页已作废。

最终 materialization：

```text
paper_count = 9
pair_count = 14
ready_for_automatic_blind_judge = true
identity_leakage_findings = 0 for all 9 papers
```

自动扫描通过不等于真人 blind 已完成；真人投票前仍需 reviewer 自己确认页面没有意外身份提示。

### 12.2 真人 blind review 页面已生成

新增：

```text
scripts/build_v6_human_review_html.py
scripts/record_v6_human_vote.py
```

当前用于形成最小跨赛制 blind-human anchor 的两份本地匿名审阅页：

```text
artifacts/meta_benchmark/judge_v1/human_review/G-A91F-1.html
artifacts/meta_benchmark/judge_v1/human_review/G-H31M-1.html
```

两者属于不同 logical pair；同一个 AB/BA swap group 的两页不能冒充两个独立 human anchors。

该页面：

- 不显示 source / award / origin / case ID；
- 左右并排展示完整匿名 text extraction；
- 逐项评价 V6 14 个维度；
- 明确 visual_dimension=UNVERIFIED_TEXT_ONLY；
- 可导出 vote JSON；
- `record_v6_human_vote.py` 只接受真实 human reviewer ID，拒绝 AI/model 占位身份；
- 页面必须勾选 `content_only_before_provenance_reveal` blind-review attestation 才能导出有效票；
- `JudgeVote` 新增 `blind_verified`，只有 blind-verified HUMAN vote 才会进入 human anchor；
- aggregate 直接计算每个 internal Judge 的 `accuracy_vs_blind_human`，正式 H1 不再使用 `accuracy_vs_provenance_prior`；
- 至少需要两个不同 logical pair 的一致 blind-human anchor 才允许 `SUPPORTED/REJECTED`，普通非盲人工反馈只能作为 prior。

针对该 HTML 再执行泄露扫描，未发现：

```text
real-current
REAL_VS_CURRENT
WORKSTATION_CURRENT
REAL_EXCELLENT
20260823-MCM-0004-D97D
2409404
Outstanding
O Award
Team #
```

### 12.3 Independent model Judge 已真实尝试，但被外部服务阻塞

新增通用 runner：

```text
scripts/run_v6_independent_judge.py
```

它强制每次只加载指定一个 route + model，禁止失败时 fallback 到其他模型，从而保证 Judge identity 可追溯。

真实调用当前 opaque group 对应的最高价值 MCM 2024 same-problem pair（运行中迁移后 ID 为 `G-A91F-1`）：

| route/model | result |
|---|---|
| DeepSeek `deepseek-reasoner` | HTTP 402 / insufficient balance |
| SeekAI Grok `grok-4.5` | HTTP 503 / provider memory overloaded |
| TestVideo GPT-5.4 | HTTP 403 / insufficient account balance |
| SeekAI GPT-5.4 | HTTP 503 / provider memory overloaded |
| CodexPlus-2 GPT-5.4 | HTTP 401 / invalid token |
| CodexPlus-3 GPT-5.4 | HTTP 503 / service unavailable |
| CodexPlus-4 GPT-5.4 | HTTP 403 / model-group access denied |

详细、不含 secret 的记录保存在：

```text
artifacts/meta_benchmark/judge_v1/independent_model_attempts.json
```

这些失败**不能计为 Judge vote**，也不能作为 H1 的支持/反对证据。

### 12.4 更新后的真实停止点

现在 Phase 1 状态更精确地是：

```text
anonymous text calibration package = READY
AB/BA package generation = READY
automatic identity leakage scan = PASS
human blind review UI = READY
human vote = PENDING
blind-verified human anchor groups = 0 / minimum 2
independent-model runner = READY
independent-model valid vote = BLOCKED_BY_EXTERNAL_PROVIDER
PDF/page visual blind review = UNVERIFIED
H1 = INCONCLUSIVE (strong preliminary evidence toward SUPPORTED)
```

所以仍然：

> **禁止进入 Phase 2。**

下一项真正能改变 H1 状态的证据，不是继续写 evaluator，而是**至少两个不同 logical pair 的有效 blind-human preference**；成功返回的独立模型 blind vote 会进一步增强 calibration，并且是未来 `REJECTED` Judge-bottleneck 假设所要求的独立证据。

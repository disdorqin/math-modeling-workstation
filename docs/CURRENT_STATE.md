# CURRENT_STATE

Last updated: 2026-08-20 — Goal 7.4A CUMCM 2010 C first real national-competition gate + Section 7 stage review

## Current Section

**Section 6 — Paper Engine: INTERNAL GATE PASS.**

Next active section: **Section 7 — C-Problem Excellent Corpus + External Benchmark. Current Goal: 7.4 Five Real C-Problem Gates.**

Passed / frozen infrastructure:

- Section 0 — baseline / benchmark / persistent memory
- Section 1 — ProblemGraph / Subproblem Engine
- Section 2 — Modeling Brain
- Section 3 — Solver Engine first Gold set
- Section 4 — ValidationProtocol Registry
- Section 5 — M-Round Research Refinement (PASS; frozen except when Paper/Reviewer routes a real Research defect upstream)
- Section 6.1 — Research-State Paper Architecture (PASS)
- **Section 6.2A — 2023 Wordle same-problem O-award full-text gap-driven refinement (PASS for text/structure/research calibration)**
- **Section 6.2B — 2018 MCM C Energy Compact cross-problem Paper Gate + 5 same-problem O-award full-text calibration (PASS)**
- **Goal 7.0 — Local Modeling Knowledge Base inventory (PASS; 211 directories covered)**
- **Goal 7.1 — C-only Excellent Corpus (PASS for text/full-text layer; 5 C problems / 21 excellent papers)**
- **Goal 7.2 — C-Problem Modeling Knowledge (PASS; corpus priors enter ModelingBrain/Validation/Repair without overriding Solver feasibility)**
- **Goal 7.3 — MCM-C vs CUMCM-C Paper Profiles (PASS for text/document separation)**

Section 6 is now **internally complete**: two materially different historical MCM C problems pass the Research State -> Paper -> Auditor path, and the 2018 cross-problem paper has no internal Readiness REVIEW/BLOCK other than the deliberately external `blind_human_competition_review=UNVERIFIED`.

This is not award certification. PDF visual/layout calibration, independent/blind review, and the larger **C-problem** corpus belong to Section 7. Scope is now frozen to C problems: 3 CUMCM C + 2 MCM C for the formal benchmark.

## Current production research-to-paper path

```text
ProblemGraph
-> ModelingBrain (HMML + Cards + Skills)
-> SolverRegistry / SolverPlugin
-> ValidationProtocol Registry
-> node evidence
-> Result / Table / Figure / Claim
-> ModelGraph
-> EvidenceGraph
-> NarrativeGraph
-> Research-State Paper
-> CompetitionPaperAuditor
-> excellent-summary prior
-> same-problem full-text O-award assessor (when available)
-> ExcellentReadiness
-> DOCUMENT defect -> Paper Engine
-> RESEARCH defect -> Section 5 exact subproblem repair
```

## Section 5 final status

Section 5 is PASS and frozen as infrastructure.

Important final fix: recurrent Round acceptance now recognizes resolution of this Round's `selected_issue_ids` as material progress even if aggregate quality score is flat because unrelated P2 standards were added later.

Verified:

```text
python -m pytest -q tests/test_research_recurrent_router.py tests/test_recurrent_workstation.py
20 passed
```

## Section 6.1 status

Already completed before Goal 6.2A:

- ProblemGraph -> ModelGraph -> EvidenceGraph -> NarrativeGraph -> Paper
- answer-first subproblem narrative
- method-specific formulas; no generic equation filler
- solver/validation-derived assumptions
- semantic per-question figures
- real candidate considerations without invented performance
- evidence-bounded practical recommendations
- verified method/domain bibliography seed
- EvidenceLockedWriter restrictions
- ExcellentReadiness: internal PASS is never award proof
- old Wordle final remains BLOCK under the new Auditor; 6.1 Research-State draft removed known P0 template/id/unit/reference pollution

## Goal 6.2A — same-problem O-award full-text calibration

### Original reference corpus now accessible

DevSpace has re-verified read-only access to:

`D:\作业\竞赛\大学生数学建模\美赛\备赛\资料`

The corpus includes many CUMCM national-award papers and MCM/ICM O-award papers. Critically, it includes at least 12 original **2023 MCM C Wordle O-award PDFs**, allowing same-question calibration instead of self-validation.

Current first full-text calibration set (6 papers):

- 2307166
- 2309397
- 2311717
- 2314151
- 2318036
- 2322645

Only derived profiles are persisted in repo:

`config/ref_models/mcm_2023_c_wordle_oaward_fulltext.json`

Raw reference-paper text is NOT copied into the project.

PDF tooling currently available locally:

- `pdftotext.exe`
- `pdfinfo.exe`
- `pdftoppm.exe`

Visual/page-layout verification is still NOT claimed because current DevSpace path does not yet provide a direct image-view workflow for those external PDFs.

### Same-problem recurring signals from the 6 O-award papers

Prevalence (descriptive calibration, not mandatory recipe):

- Wordle/word feature engineering: 100%
- Wordle game semantics: 100%
- explicit uncertainty / interval: 100%
- data preprocessing: 100%
- editor letter: 100%
- custom domain construct: 83%
- player/popularity mechanism: 83%
- workflow/model-framework figure signal: 83%
- strengths/weaknesses: 83%
- cross-validation/holdout: 100%

Medians (not quotas): ~25 pages, 483 abstract words, 19 abstract numeric tokens, 5 abstract method families, 7 whole-paper method families, 15 numbered figure mentions, 8 table mentions, 9 references.

### New full-text calibration implementation

`src/mathworkstation/same_problem_benchmark.py`

Key rule: no algorithm becomes required because one O-award paper used it. Only recurring same-problem capabilities become gaps. Gaps are typed DOCUMENT / RESEARCH with repair phases and subproblem IDs.

Paper Engine automatically resolves a matching derived full-text benchmark via `SameProblemBenchmarkRegistry` and persists:

`review/competition/same_problem_oaward_gap.json`

Artifact type: `same_problem_excellent_gap_assessment`.

ExcellentReadiness now includes:

- `same_problem_fulltext_document_alignment`
- `same_problem_fulltext_research_alignment`

### First trusted 6.1 -> O-award gap report

Initial reliable gaps after parser false-positive fixes:

DOCUMENT:
- explicit Data Preprocessing narrative
- explicit Strengths/Weaknesses
- actual editor letter

RESEARCH:
- SP2/SP3/SP4 stronger Wordle-specific construct
- SP1 popularity/player-dynamics mechanism alternative

### DOCUMENT gaps fixed

Research-State Paper now contains:

- `Data Preprocessing and Feature Construction`, derived only from accepted solver plan/input schema
- `Model Evaluation: Strengths, Weaknesses, and Robustness`, with weaknesses derived from node limitations
- a prompt-specific deliverable renderer: Wordle produces an actual editor letter from accepted dependencies; other problems render their registered memo/letter/synthesis without Wordle hard-coding

Same-problem DOCUMENT alignment is now PASS.

### Wordle-specific feature gap fixed through real ablation

New contest-data-only constructs:

- `positional_letter_surprisal`
- `letter_transition_surprisal`

They use smoothed statistics from the supplied contest word corpus only; no external familiarity/popularity labels are smuggled in.

Real multi-holdout ablation:

- SP2: positional surprisal retained; MAE improves at all tested temporal holdouts, RMSE degrades only ~0.04–0.14%, bootstrap coefficient interval excludes zero in 3/4 splits.
- SP3: both surprisal features retained; RMSE and MAE improve at 15/20/25/30% temporal holdouts; at 20% RMSE ~4.798 -> 4.723 and MAE ~3.576 -> 3.505.
- SP4: added surprisal features are not robust across random seeds, therefore classification keeps base8 features.

`wordle_task_feature_sets()` makes feature selection subproblem-specific instead of forcing one feature set onto all questions.

### SP1 modeling depth improved and mechanism alternative honestly rejected

A new solver plugin exists:

`gold.popularity_lifecycle`

It is a two-phase piecewise exponential popularity lifecycle with training-only change-point selection and residual-bootstrap interval. It explicitly does NOT claim latent player compartments, because the observed dataset does not identify SIR-like compartments.

Multi-horizon real Wordle RMSE:

| temporal holdout | Ridge | Holt | Popularity lifecycle |
|---:|---:|---:|---:|
| 15% | 8792 | 6541 | 3608 |
| 20% | 9900 | 6005 | 3145 |
| 25% | 11106 | 4676 | 12755 |
| 30% | 12037 | 4542 | 14394 |

Decision:

- Lifecycle wins only 2/4 horizons and collapses on longer horizons -> rejected as accepted model.
- Holt beats old Ridge on 4/4 horizons -> **Wordle SP1 accepted solver is now damped Holt exponential smoothing**.

Holt has method-specific assumptions/equations and bibliography support in the Paper Engine.

### Stress-aware alternative comparison

`SubproblemAlternativeComparisonService.compare()` now accepts temporal stress split grids for forecasting.

An alternative is considered robustly better only if:

- at least 3 stress splits exist;
- it is >1% better on at least 75% of splits;
- median relative improvement >1%;
- validation does not FAIL.

Single-split winner no longer overrides robust decision. When stress says KEEP_ACCEPTED, `best_method` is forced back to the accepted method.

AutoPipeline now exposes:

`compare_subproblem_alternatives(...)`

NarrativeGraph / Paper Engine project only **executed** head-to-head evidence, including stress split list, median/worst metric, win rate, and robust decision.

### Current same-question Gate

For a real Wordle case with accepted Holt and executed alternatives Ridge + Popularity Lifecycle under 15/20/25/30% stress splits:

```text
same-problem DOCUMENT gaps = 0
same-problem RESEARCH gaps = 0
same-problem Gate = PASS
empirical alternative comparison = PASS
```

This means the currently encoded recurring capability gaps from the six same-question O-award full texts are closed by actual Research State evidence.

It does **NOT** mean O/F certification.

## Goal 6.2B — 2018 Energy Compact cross-problem Gate

A second, materially different historical problem now passes the complete Research-State Paper path: **2018 MCM Problem C — Energy Production / four-state energy compact**.

### Official data and same-problem O-award corpus

Verified local official attachment:

`D:\作业\竞赛\大学生数学建模\美赛\备赛\资料\课程课件\美赛历年题目\16-24年美赛题目合集\2018_MCM-ICM_Problems\ProblemCData.xlsx`

- `seseds`: 105,744 long-format observations
- `msncodes`: 605 variable definitions
- target states present: AZ / CA / NM / TX
- historical horizon used by the problem: 1960–2009

Five original same-problem O-award PDFs were profiled (72969, 73767, 78577, 80560, 82150). Derived corpus profile only:

`config/ref_models/mcm_2018_c_energy_oaward_fulltext.json`

Across those five papers, the **capability** recurrence is much stronger than any single algorithm recurrence:

- explicit energy-profile construct: 5/5
- multi-criteria state evaluation: 5/5
- 2025/2050 long-horizon prediction: 5/5
- compact targets/actions: 5/5
- Governors memo: 5/5

Specific algorithms are diverse: ARMA appears 3/5; TOPSIS and PCA 2/5; most other methods appear only once. Therefore the benchmark does not prescribe one O-award algorithm.

### New cross-problem solver/validation capabilities

Added general capabilities exposed by the 2018 Gate rather than by Wordle:

- `gold.panel_profile_summary` + `exploration.panel-profile-summary.v1`
- `gold.panel_trend_characterization` + `forecasting.panel-trend-characterization.v1`
- `gold.entropy_topsis` + `ranking.entropy-topsis-stability.v1`
- `gold.panel_holt` + `forecasting.panel-temporal-uncertainty.v1`
- existing exact linear-programming solver used for target setting

Paper projection now supports:

- common-reference multi-entity profile heatmap
- entity/indicator historical trend figure
- multi-entity future forecast intervals
- MCDM ranking scores
- optimization decision-variable targets

### Minimal transparent 2018 profile

The accepted common profile uses directly documented SEDS quantities and transparent derived ratios:

- renewable consumption share = RETCB / TETCB
- renewable production share = REPRB / TEPRB
- renewable consumption per capita = RETCB / TPOPP
- total energy per capita = TETPB

The selected six source series are complete over all 4 states × 50 years = 200 state-years, avoiding needless imputation solely to make the profile look richer.

### Real 2009 MCDM result

Entropy-TOPSIS on the four-state 2009 profile gives:

```text
CA > AZ > NM > TX
winner = CA
winner retention under leave-one-criterion-out = 1.0
mean rank Spearman under criterion deletion = 1.0
```

This stability evidence is treated as genuine sensitivity/stability evidence; the Auditor no longer accepts the word “sensitivity” in prose as proof that sensitivity analysis was executed.

### Real 2025/2050 panel forecast and compact targets

Panel Holt validates 8 entity-target series (4 states × 2 renewable-share variables) under entity-wise temporal holdout and emits 16 future point/interval forecasts for 2025/2050.

Aggregate holdout metrics in the current Gate are approximately:

```text
RMSE = 0.0174
MAE  = 0.0132
```

II-A target optimization distinguishes **no-policy forecasts** from **historically bounded stretch targets**. Target lower bounds come from no-policy forecasts; stretch upper bounds are limited by historically observed same-horizon renewable-share improvement and made non-decreasing from 2025 to 2050.

Accepted renewable-consumption-share stretch targets in the current Gate:

```text
AZ  2025 0.15697   2050 0.15697
CA  2025 0.15487   2050 0.15487
NM  2025 0.10528   2050 0.10726
TX  2025 0.09010   2050 0.09472
```

They are decision targets under the registered envelope, **not claims that policy causally produces those values**.

### Paper Engine generalization bugs found and repaired

The second problem exposed Wordle-specific pollution that a one-problem test could not reveal:

- generic data section was hard-coded to “Wordle dataset”
- background citation prose was hard-coded to “underlying puzzle / Wordle”
- Section 8 always rendered “Letter to the Puzzle Editor of The New York Times”
- only the first synthesis node was rendered, losing 2018's separate actions/memo deliverables

Current renderer is prompt/dependency aware:

- all synthesis nodes are rendered
- editor-letter objectives render an editor letter
- memo/governor objectives render a real Governors' Memo
- unrelated problems do not inherit Wordle language

### Readiness inference tightened

A generic ProblemGraph candidate is no longer promoted to “executable alternative” just because its method name happens to match a SolverRegistry alias. `empirical_alternative_comparison` and `alternative_solver_depth` now require explicit candidate feasibility (`PASS` / `NEEDS_SOLVER`). This prevents scalar Ridge or IR-ranking plugins from being incorrectly treated as ready alternatives to panel forecasting / MCDM.

Formula/assumption schemas were added for panel Holt, panel trend, Entropy-TOPSIS, and linear programming, so document equations describe the solver actually executed.

Energy-domain bibliography now includes verified pre-2018 SEDS/NREL background in addition to method references.

### 2018 final internal Gate

Latest real official-data case:

```text
ProblemGraph / ModelGraph / EvidenceGraph / NarrativeGraph = PASS
CompetitionPaperAuditor BLOCK = 0
2018 same-problem O-award DOCUMENT gaps = 0
2018 same-problem O-award RESEARCH gaps = 0
cross_problem_generalization = PASS (2 historical problems)
domain bibliography = PASS
structured excellent-summary standards = PASS
ExcellentReadiness internal_pass = true
```

The **only non-PASS Readiness dimension** is intentionally:

```text
blind_human_competition_review = UNVERIFIED
```

That dimension cannot be self-certified by more code.

Still explicitly external / Section-7 work:

- blind/human competition review
- full PDF visual/layout/figure-purpose calibration
- larger excellent-paper sample across multiple CUMCM years/problems
- deeper claim-to-citation coverage beyond the currently verified method/domain bibliography

## Current verified tests

Latest Section-6 wide group across both real historical problems and shared paper/research infrastructure:

```text
python -m pytest -q \
  tests/test_energy_2018_research_gate.py \
  tests/test_excellent_corpus_benchmark.py \
  tests/test_research_state_paper.py \
  tests/test_same_problem_benchmark.py \
  tests/test_solver_engine.py \
  tests/test_validation_protocol.py \
  tests/test_subproblem_paper_bridge.py \
  tests/test_subproblem_comparison.py \
  tests/test_narrative_graph.py \
  tests/test_wordle_2023_problem_graph_gate.py

47 passed
```

Section 5 recurrent close-out group remains 20 passed.

Full `python -m pytest -q` still has the pre-existing Python 3.11 + Tenacity 5.1.5 collection incompatibility (`asyncio.coroutine` removed) in two runtime tests; do not report that as a Goal 6.2 regression.

## Section 7.0 / 7.1 status

**Goal 7.0 — Local Modeling Knowledge Base: PASS.**

User scope is frozen to **C problems only**. A/B/D/E/F assets remain archive/method references, not primary excellent-paper benchmarks.

Knowledge-base source:

`D:\\作业\\竞赛\\大学生数学建模\\美赛\\备赛\\资料`

Persisted assets:

- `docs/LOCAL_MODELING_KNOWLEDGE_BASE_README.md`
- `config/ref_models/local_knowledge_base_registry.json`

Read-only inventory covered **211 directories**. Major snapshot: `论文` 180 directories / 867 files / ~9.1 GB; `课程课件` 24 directories / 209 files / ~476 MB. Knowledge layers are separated as RAW archive -> Asset Registry -> Derived Knowledge -> Skill/Routing Knowledge -> Runtime Research State. Tutorials/Skills remain advisory; SolverRegistry and accepted case evidence remain truth.

**Goal 7.1 — C-Problem Excellent Corpus: PASS for the text/full-text layer.**

Formal primary benchmark is now locked to **5 C problems / 21 excellent papers**:

1. CUMCM 2010 C — Oil Pipeline Layout — 3 readable excellent papers;
2. CUMCM 2018 C — Retail Member Profiling — 3;
3. CUMCM 2023 C — Vegetable Pricing/Replenishment — 4;
4. MCM 2018 C — Energy Compact — 5 O-award papers;
5. MCM 2023 C — Wordle — 6 O-award papers.

New machine assets:

- `config/ref_models/cumcm_2010_c_oil_pipeline_excellent_deep.json`
- `config/ref_models/cumcm_2018_c_retail_member_excellent_deep.json`
- `config/ref_models/cumcm_2023_c_vegetable_excellent_deep.json`
- `config/ref_models/c_problem_excellent_benchmark_v1.json`
- `src/mathworkstation/c_problem_benchmark.py`
- `tests/test_c_problem_benchmark.py`
- `docs/section-7-c-problem-corpus-review-2026-08-20.md`

Primary benchmark code now rejects any non-C problem, fewer than 3 CUMCM C problems, fewer than 2 MCM C problems, paper-count mismatch, or missing benchmark assets.

Section 7 corpus/parser regression: **16 passed**. Key Section 6 compatibility checks additionally verified **2 passed** for Wordle same-problem/readiness and **11 passed** for Energy/Wordle real gates + Validation. Large combined pytest commands hit DevSpace connector 502/timeouts, so connector failures are not reported as pytest failures.

Remaining external boundaries: PDF visual/layout = **UNVERIFIED**; blind/human competition review = **UNVERIFIED**.

## Goal 7.2 status

**PASS.** Five-corpus priors are now embedded in ModelingBrain decisions as research/validation obligations, never as model candidates. `WorkstationGlobalAuditor` checks completed C-problem nodes for missing or wrong-family validation and routes defects to the exact `subproblem / validation` repair target. Real Wordle mismatch injection verified the route; a correct validation family emits no benchmark finding.

Focused 7.2 regression: **15 passed**. Combined Section 7 corpus + priors + recurrent routing: **27 passed**.

## Goal 7.3 status

**PASS for text/document separation.** `ResearchStatePaperService` now resolves an explicit competition profile and dispatches the same accepted NarrativeGraph to separate MCM-C or CUMCM-C renderers. `CompetitionPaperAuditor` can apply profile-specific DOCUMENT checks; cross-profile heading contamination is BLOCK, while research state remains shared and unchanged.

Profile/auditor regression: **8 passed**. Three critical real Wordle Paper Gate tests were re-run individually and all passed after the MCM top section changed from `Abstract` to `Summary`.

## Goal 7.4 current status

**IN PROGRESS.** The first CUMCM real gate, **2010 C Oil Pipeline Layout**, now passes the real ProblemGraph -> ModelingBrain -> Solver -> Validation -> Evidence -> Chinese CUMCM paper path. Focused pipeline + research-gate tests: **5 passed**. Section-7 map/priors/profiles + 2010C combined regression: **24 passed**.

The real generated 2010C draft has no CompetitionPaperAuditor BLOCK, but remains REVIEW-level as a competition paper. It correctly reproduces the main Q2/Q3 optimum values and preserves limitations, yet exposes general issues that must be fixed before continuing blindly: internal registry language leaks into prose, task-insensitive empty sections, semantic figure-caption pollution, machine-oriented table labels, weak domain bibliography, and over-broad executable-alternative semantics.

Stage review: `docs/section-7-stage-summary-2026-08-20.md`

Renderer sample review: `docs/generated_samples/cumcm_2010_current_draft_review.md`

### Next

**Goal 7.4A repair pass:** make the 2010C-exposed defects generic fixes, especially semantic alternative compatibility and natural/evidence-grounded CUMCM rendering. Then run **CUMCM 2018 C Retail Member Profiling**, followed by **CUMCM 2023 C Vegetable Pricing/Replenishment**. Do not add broad solver families unless a real C-problem gate proves the need.

After all three CUMCM C gates: Goal 7.5 actual human review. Human/blind review remains UNVERIFIED until the user or another independent reviewer actually reviews the generated paper.

## Protected WIP

Never reset / clean / restore-all / checkout overwrite.

Protect at minimum:

- prompts/internal/paper_refinement.json
- src/mathworkstation/agents/modeling.py
- src/mathworkstation/auto_pipeline.py
- src/mathworkstation/paper_contracts.py
- src/mathworkstation/refinement.py
- src/mathworkstation/task_executors.py
- src/mathworkstation/recurrent_workstation.py
- src/mathworkstation/problem_graph.py
- src/mathworkstation/modeling_brain.py
- src/mathworkstation/solver_engine.py
- src/mathworkstation/validation_protocol.py
- src/mathworkstation/subproblem_engine.py
- src/mathworkstation/subproblem_comparison.py
- src/mathworkstation/narrative_graph.py
- src/mathworkstation/research_state_graphs.py
- src/mathworkstation/research_state_paper.py
- src/mathworkstation/competition_paper_auditor.py
- src/mathworkstation/evidence_locked_writer.py
- src/mathworkstation/excellent_readiness.py
- src/mathworkstation/same_problem_benchmark.py
- src/mathworkstation/word_features.py
- src/mathworkstation/wordle_2023_gate.py
- corresponding tests/config/docs

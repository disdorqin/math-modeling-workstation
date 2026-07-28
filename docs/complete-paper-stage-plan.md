# Complete Paper Stage Plan

Status: implementation plan  
Date: 2026-07-22

## 1. Objective

The workstation must first be able to produce one substantively complete
mathematical-modeling paper from one controlled build pass. Repeating a weak
paper-writing stage cannot create missing evidence, experiments, numerical
results, or argument structure.

The target architecture has two layers:

```text
Bootstrap / Full Paper Build
  -> CompletePaperContract gate
  -> Recurrent Full-Paper Review Cell x N
  -> Submission gate
```

- Bootstrap creates the first complete evidence-backed paper.
- Every recurrent Stage reviews the whole paper across all quality domains.
- One Stage commits only one bounded repair transaction.
- A document Stage never fabricates missing upstream evidence.
- Evidence changes start a new refinement epoch; they do not mutate frozen
  truth inside the current epoch.
- The workflow DAG remains acyclic. Stage iterations remain Runs and Artifacts
  inside the `refinement_loop` meta-node.

## 2. Current Measured Baseline

The deterministic end-to-end acceptance case proves that the current system
can execute from a problem statement and observed CSV through experiments,
paper generation, one accepted refinement, and ZIP export.

Measured output:

- 12 required main sections;
- 3,959 characters and 136 lines;
- strict consistency gate `PASS`;
- one accepted refinement stage;
- valid Artifact hashes and committed stage transaction;
- internal quality score 0.943607.

That paper was not submission quality. Real experiment metrics existed but did
not reach the Claims or manuscript. Generic English Claim sentences appeared
inside the Chinese paper. This demonstrates metric gaming in the current
quality evaluator: keyword and reference coverage can score highly while
substantive reasoning remains weak.

## 3. Complete Paper Capability Matrix

| Domain | Required output | Current state | Main weakness |
|---|---|---|---|
| Problem decomposition | typed subproblems, inputs, outputs, constraints, completion criteria | weak | `ProblemAnalysis` uses broad `Any` fields |
| Assumptions | assumption, source, necessity, risk, validation, affected model | partial | prose-only and no lifecycle |
| Literature/context | verified sources tied to methods and claims | optional | not integrated into auto pipeline |
| Data semantics | schema, units, ranges, leakage, outliers, missingness, split decision | partial | mostly profile heuristics |
| Model design | task-family contract, equations, rationale, alternatives | weak | regression/classification centric |
| Implementation | executable model code, environment, seed, resource record | partial | deterministic built-ins only |
| Experiment design | baseline, CV, ablation, uncertainty, diagnostics, scenarios | partial | no complete protocol by task family |
| Result evidence | typed metrics, tables, comparisons, diagnostics, limitations | weak | metrics are not promoted into Claims |
| Figures/tables | purpose-specific visuals and result tables | partial | generic EDA dominates; table layer thin |
| Storyline/writing | subproblem-to-section narrative with evidence spans | weak | section prompts consume generic Claims |
| Review/refinement | global diagnosis, bounded repair, rollback | partial/strong kernel | evaluator is shallow and paper-only |
| Submission | clean Markdown, LaTeX, PDF, references, precheck | weak | current export is a whole-Case ZIP |

## 4. CompletePaperContract

Bootstrap cannot enter recurrent refinement until all contract groups pass.

### 4.1 Problem contract

Create a `SubproblemRegistry` with one record per subproblem:

```json
{
  "subproblem_id": "subproblem-...",
  "objective": "...",
  "inputs": ["..."],
  "outputs": ["..."],
  "constraints": ["..."],
  "task_family": "prediction|forecasting|optimization|simulation|evaluation|mechanism",
  "candidate_methods": ["..."],
  "required_evidence_types": ["..."],
  "completion_checks": ["..."],
  "section_owner": "results",
  "status": "OPEN|SUPPORTED|BLOCKED"
}
```

No paper can be complete while a required subproblem remains `OPEN`.

### 4.2 Truth contract

Add typed registries for:

- assumptions and their validation status;
- data-field semantics, units, range rules, and identifier decisions;
- split protocol and leakage decisions;
- model equations and parameter definitions;
- experiment protocol and execution environment;
- result metrics, uncertainty, diagnostics, and scenario outputs;
- literature evidence and citation verification.

Each truth record must point to immutable Artifact IDs and carry an explicit
paper eligibility state.

### 4.3 Narrative contract

Every section receives a machine-generated `SectionEvidencePack`:

```text
section purpose
-> owned subproblems
-> approved assumptions
-> exact equations
-> typed metric rows
-> approved figures/tables
-> verified literature contexts
-> mandatory limitations
-> forbidden claims
```

The writer receives this pack rather than raw Case files or generic Claim
sentences. Numerical prose is rendered from typed values before the LLM sees
it. The LLM may explain and connect verified facts, but may not create new
numbers or evidence references.

### 4.4 Submission contract

Before export, require:

- all required sections and subproblems covered;
- all result Claims backed by typed metric records;
- all figures and tables cited and captioned;
- literature references verified;
- no internal IDs or unsupported numerical statements;
- Chinese-language consistency;
- LaTeX compilation and PDF existence;
- page, figure-resolution, font, reference, and package prechecks;
- a clean submission package separated from the internal audit package.

## 5. One Full-Paper Stage

Every Stage uses the same cell but evaluates eleven domains:

```text
1. snapshot accepted paper and frozen truth
2. audit subproblem coverage
3. audit evidence and data semantics
4. audit model rationale and equations
5. audit experiment protocol and diagnostics
6. audit numerical result/table/figure alignment
7. audit storyline and section argument structure
8. audit citations and limitations
9. audit language, compression, and competition style
10. audit reproducibility and submission readiness
11. select one bounded repair -> verify -> accept/rollback
```

The Stage is globally aware but locally mutating. It does not regenerate the
whole paper.

### 5.1 Typed issue taxonomy

Replace keyword-only findings with typed issues:

- `PROBLEM_COVERAGE`
- `ASSUMPTION_SUPPORT`
- `DATA_SEMANTICS`
- `LEAKAGE_OR_SPLIT`
- `MODEL_RATIONALE`
- `EQUATION_COMPLETENESS`
- `EXPERIMENT_PROTOCOL`
- `RESULT_EVIDENCE`
- `DIAGNOSTIC_INTERPRETATION`
- `FIGURE_TABLE_ALIGNMENT`
- `CITATION_SUPPORT`
- `NARRATIVE_LOGIC`
- `LANGUAGE_STYLE`
- `SUBMISSION_FORMAT`
- `REPRODUCIBILITY`

Each issue includes affected subproblems, evidence dependencies, severity,
verification command, repair class, and proof of resolution.

### 5.2 Repair router

```text
DOCUMENT_PATCH
  -> patch at most two sections in the current epoch

FIGURE_TABLE_REPAIR
  -> regenerate from frozen result records, then start a new epoch

CITATION_REPAIR
  -> retrieve/verify sources, update evidence, then start a new epoch

EXPERIMENT_REPAIR
  -> emit UpstreamRepairRequest; execute through experiment services;
     verify results and start a new epoch

MODEL_OR_DATA_REPAIR
  -> BLOCK current paper epoch and require an approved upstream repair

SUBMISSION_REPAIR
  -> modify LaTeX/template/package artifacts without changing truth
```

This preserves the current non-negotiable rule: frozen facts, verified numbers,
Claims, Figures, evidence scope, and section contracts cannot change within an
epoch. A Stage that detects missing truth records the defect instead of hiding
it with prose.

### 5.3 Stage acceptance

Acceptance requires all of the following:

- hard truth and integrity gates pass;
- targeted issue has machine-verifiable resolution evidence;
- no protected dimension regresses;
- changed sections and characters remain within budget;
- subproblem coverage does not decrease;
- exact metric/table/figure references remain valid;
- independent reviewer preference is sufficiently confident;
- reward-hacking checks do not fire.

Reward-hacking checks include:

- keyword repetition without new evidence spans;
- length inflation without issue resolution;
- removing difficult findings from the evaluator input;
- replacing exact results with vague positive language;
- quality-score jumps without changed supporting Artifacts;
- LLM self-review as the sole acceptance signal.

## 6. Hidden State And Artifacts

Extend `memory/refinement_state.json` with projections only:

```text
subproblem_status
truth_contract_digest
section_coverage
quality_vector_by_domain
active_issue_ids
blocked_upstream_issue_ids
repair_request_ids
review_disagreement
submission_readiness
cost/time/token budgets
```

Keep append-only evidence in:

```text
problem/subproblems.jsonl
memory/assumptions.jsonl
evidence/literature_contexts.jsonl
data/dictionaries/semantic_contract.json
experiments/*/protocol.json
experiments/*/result_records.jsonl
results/claim_inputs.jsonl
tables/metadata/*.json
review/domains/*.json
refinement/repair_requests/*.json
refinement/history.jsonl
```

The state projection is updated. Historical truth, experiment results,
reviews, decisions, and accepted paper versions are never overwritten.

## 7. External Project Lessons

Sources were checked on GitHub on 2026-07-22.

### AI-Scientist v1

[SakanaAI/AI-Scientist](https://github.com/SakanaAI/AI-Scientist)

Borrow:

- domain templates with executable `experiment.py` and `plot.py`;
- bounded experiment runs with explicit per-run outputs;
- notes connecting figures and runs to the writeup;
- LaTeX generation, repeated compilation, lint/error repair;
- structured reviewer forms and review-driven improvement.

Do not borrow unrestricted execution of LLM-written code. This workstation
should keep model implementations behind reviewed task-family plugins and run
them with time, filesystem, network, and resource limits.

### AI-Scientist v2

[SakanaAI/AI-Scientist-v2](https://github.com/SakanaAI/AI-Scientist-v2)

Borrow later:

- experiment-manager role;
- bounded candidate branching and comparison;
- VLM review for plot/PDF inspection.

Do not adopt broad tree search before strong contracts exist. Its own README
notes that general exploration can have lower success rates than a strong
template. Mathematical modeling benefits first from task-family templates.

### STORM

[stanford-oval/storm](https://github.com/stanford-oval/storm)

Borrow:

- perspective-guided question generation;
- explicit knowledge-curation -> outline -> article interfaces;
- hierarchical outline coverage;
- source-grounded writing contexts.

Map perspectives to subproblem stakeholders, assumptions, objectives, failure
modes, and evaluation questions instead of generic web-report viewpoints.

### PaperQA2

[Future-House/paper-qa](https://github.com/Future-House/paper-qa)

Borrow:

- search -> gather evidence -> answer separation;
- source metadata, journal quality, retraction and citation checks;
- ranked evidence contexts and relevance thresholds;
- test cassettes for external-source behavior.

### Agent Laboratory

[SamuelSchmidgall/AgentLaboratory](https://github.com/SamuelSchmidgall/AgentLaboratory)

Borrow:

- literature, experimentation, and report-writing phase separation;
- specialized agents with explicit handoff artifacts;
- persisted state saves and human research notes;
- optional LaTeX compilation.

### ARIS

[HaiyangDiiing/aris-cli](https://github.com/HaiyangDiiing/aris-cli)

Borrow:

- baseline before iteration;
- one atomic change per attempt;
- mechanical metric plus guard metric;
- keep/discard/crash/no-op logging;
- multi-sample metrics for noisy evaluation;
- explicit reward-hacking detection.

The current refinement transaction already matches part of this pattern, but
its quality metric needs stronger evidence-aware components.

### PaperSmith

[magicJ1995/PaperSmith](https://github.com/magicJ1995/PaperSmith)

Borrow:

- separate project context, storyline, references, reviews, and outputs;
- explicit evidence-gap markers;
- precheck before export;
- prohibition on invented results, citations, datasets, and conclusions.

### MCM-Agent-Workflow

[yuexi0616/MCM-Agent-Workflow](https://github.com/yuexi0616/MCM-Agent-Workflow)

Borrow cautiously:

- modeling -> independent audit -> code -> audit -> paper -> final audit;
- modeling-specific knowledge catalog;
- dimension, assumption, result-truth, and competition-format checks;
- checkpoint/resume and rejection counts.

This repository is useful as a domain workflow reference, not as proof of
production maturity. Its claims must be validated independently before reuse.

## 8. Security And Control Gaps

### Critical

1. `approved_by` is currently a supplied string; auto pipeline can record an
   approval without a distinct authenticated human action.
2. `final_review` currently marks the node complete without executing a real
   final review suite.
3. Whole-Case ZIP export includes internal state, prompts, responses, and raw
   evidence. A submission package must exclude internal/private material.
4. Keyword-heavy quality dimensions are vulnerable to reward hacking and gave
   a poor paper a 0.94 score.

### High

5. Example LLM routes include third-party providers; provider trust, data
   classification, retention policy, and redaction must be explicit.
6. External literature and source calls need snapshots, request limits,
   provenance, and replayable test cassettes.
7. Future LLM-written experiment code must run in an isolated sandbox with no
   secrets, restricted network, resource quotas, and immutable inputs.
8. Cost, wall-clock, CPU, memory, and experiment-count budgets are not enforced
   uniformly across the full pipeline.

### Medium

9. Semantic reviewer disagreement and confidence are not persisted as first-
   class acceptance evidence.
10. PDF visual inspection, figure-resolution checks, and citation rendering
    checks do not yet exist.

## 9. Implementation Roadmap

### Milestone 0: Acceptance specification

Deliver:

- `CompletePaperContract` schema;
- paper-domain quality matrix;
- machine-readable submission readiness report;
- benchmark fixtures and expected failure codes.

Tests:

- current regression E2E remains green;
- an intentionally generic paper fails substantive readiness;
- missing subproblem/result/table/citation each produces a stable issue code.

### Milestone 1: Problem and truth contracts

Deliver:

- typed `ProblemAnalysis` and `SubproblemRegistry`;
- `AssumptionRegistry` and decision lifecycle;
- data semantic/leakage/split contract;
- section ownership for every subproblem.

Gate: no model plan starts until every required subproblem has an evidence and
completion contract.

### Milestone 2: Task-family model and experiment plugins

Start with:

1. tabular regression/classification;
2. forecasting/time series;
3. constrained optimization;
4. simulation/mechanism modeling;
5. evaluation/ranking.

Each plugin owns schema validation, equations, baseline requirements, split or
scenario protocol, diagnostics, sensitivity, result records, and figures.

Gate: one golden fixture per task family must produce deterministic registered
results and reject an invalid protocol.

### Milestone 3: Evidence-to-narrative compiler

Status: partially implemented for the deterministic tabular pipeline.

Deliver:

- typed `ResultRecord` and `TableRecord`;
- numerical Claim renderer in Chinese;
- `SectionEvidencePack` builder;
- subproblem answer matrix;
- storyline artifact before drafting;
- exact experiment metrics and limitations inserted before LLM explanation.

Gate: every important number in the paper traces to a ResultRecord, and every
required subproblem has an explicit answer paragraph and result table row.

Implemented now: typed contracts, append-only result/table registries,
section projections, Chinese numerical Claim rendering, model-comparison table,
stable substantive issue codes, and an end-to-end gate proving registered
values and table IDs reach the final paper. Remaining: data-profile and
diagnostic records plus a true subproblem answer matrix with one result-table
row per required subproblem.

### Milestone 4: Full-paper reviewer and repair router

Deliver:

- eleven-domain review suite;
- issue taxonomy and dependency graph;
- independent semantic pairwise reviewer with confidence;
- reward-hacking checks;
- `UpstreamRepairRequest` and new-epoch transition;
- document, figure/table, citation, experiment, and submission repair routes.

Gate: a Stage must detect all seeded defects in benchmark papers, repair one
bounded target, and preserve every frozen truth record.

### Milestone 5: Submission pipeline and safety controls

Deliver:

- CUMCM/SM/MCM-ICM LaTeX templates;
- deterministic Markdown -> LaTeX mapping;
- PDF compile/lint/retry;
- PDF page and visual regression checks;
- separate `submission_package` and `audit_package`;
- authenticated approval events;
- provider/data policy and execution sandbox configuration.

Gate: the submission ZIP contains only allowed files and passes format,
integrity, PDF, citation, and privacy prechecks.

### Milestone 6: Benchmark calibration

Run at least:

- one observed regression case;
- one classification case;
- one forecasting case with temporal split;
- one optimization case with constraints;
- one simulation/mechanism case;
- one case with missing evidence that must block safely.

For every case measure:

- pipeline completion and recovery;
- subproblem coverage;
- metric/Claim/paragraph traceability;
- seeded defect recall and false-positive rate;
- accepted/rejected repair quality;
- PDF/submission readiness;
- runtime, token, cost, and resource budgets;
- blinded human score using a stable modeling-paper rubric.

Only after these benchmarks should the project claim parity with a competent
modeling team.

## 10. Recommended Immediate Sequence

Implement in this order:

```text
CompletePaperContract
-> typed SubproblemContract
-> typed ResultRecord/TableRecord
-> SectionEvidencePack
-> substantive readiness evaluator
-> full-paper review domains
-> repair router/new epoch
-> task-family expansion
-> LaTeX/PDF/submission package
```

The first high-value code change is not another refinement iteration. It is the
typed evidence-to-narrative path demonstrated missing by the end-to-end test.

# Remaining Work: Optimized Delivery Roadmap

Status: Phase A-D foundations and deterministic task executors implemented; Phase E submission preflight and clean-package foundation implemented  
Date: 2026-07-22

## 1. Current Judgment

The workstation's large architecture is now stable enough for focused
feature development:

- the bootstrap DAG is acyclic and executable;
- `refinement_loop` is a bounded, resumable, transactional meta-node;
- frozen evidence and accepted paper versions are protected by epoch rules;
- the tabular regression path has typed subproblem/result/table contracts;
- the end-to-end fixture passes the substantive paper gate.

The remaining risk is not architectural absence. It is shallow content:
missing modeling depth, weak subproblem answers, limited diagnostics, weak
review coverage, and no clean submission package. More refinement stages before
these are fixed would mostly polish prose without adding truth.

## 2. Priority Rules

Work follows these rules:

1. Improve one complete paper family before adding several incomplete families.
2. Add deterministic evidence before asking an LLM to explain it.
3. Every new capability gets a golden fixture and a negative fixture.
4. Upstream evidence defects create an `UpstreamRepairRequest` and a new epoch;
   document refinement never fills the gap with prose.
5. Security/control gates are implemented before external providers or broad
   autonomous execution are enabled.
6. A milestone is complete only when its gate passes in the full test suite.

## 3. Execution Order

### Phase A — Make the regression paper substantively useful

Status: implemented for the golden tabular path.

Goal: turn the current deterministic regression path into a credible complete
paper baseline.

Implement:

- subproblem answer matrix: objective -> method -> result -> limitation ->
  answer paragraph;
- typed data-semantic records: units, missingness, outliers, leakage, split,
  target meaning, and feature rationale;
- typed diagnostics: residual summary, calibration/error slices, uncertainty,
  and failure cases;
- model rationale records: baseline purpose, candidate trade-offs, equation,
  parameter meaning, and selection reason;
- result rendering for data profile, diagnostics, sensitivity gate, and model
  limitations;
- deterministic storyline artifact consumed by section drafting.

Gate:

- every declared subproblem has an explicit answer paragraph;
- every material numerical statement maps to a typed record;
- results contain at least one comparison table, one diagnostic artifact, and
  one limitation tied to evidence;
- a seeded missing-diagnostic case blocks final review;
- no generic English claims remain in the Chinese golden paper.

Do not start broad task-family expansion until this gate passes.

### Phase B — Build the real review and repair router

Status: initial deterministic review and upstream-request router implemented;
full eleven-domain repair execution remains.

Goal: make recurrent refinement improve content rather than only structure.

Implement:

- eleven-domain deterministic review suite;
- typed issue taxonomy with severity, affected subproblem, evidence dependency,
  verification command, and repair class;
- reward-hacking checks for vague-result replacement, keyword inflation,
  length-only gains, and score jumps without evidence changes;
- `UpstreamRepairRequest` records for data/model/experiment/citation defects;
- repair routing: document patch, table/figure regeneration, experiment repair,
  evidence repair, and blocked state;
- final review that executes the suite instead of only marking a workflow node.

Gate:

- seeded defects are detected with stable codes;
- document defects can be repaired in one bounded stage;
- upstream defects become blocked/new-epoch requests;
- frozen truth hashes remain unchanged within an epoch;
- rejected patches never replace accepted paper state.

### Phase C — Add control and provenance hardening

Status: approval events, budget state, and provenance policy primitives
implemented; provider adapters and full package separation remain.

Goal: prevent a polished but uncontrolled workstation from being mistaken for
an audited submission system.

Implement:

- distinct approval event records instead of trusting a free-form `approved_by`
  string;
- provider/data classification and redaction policy for external LLM calls;
- source snapshots, request limits, provenance, and replay cassettes for
  literature/source retrieval;
- uniform token, time, CPU, memory, experiment-count, and cost budgets;
- explicit audit-package versus user-facing-package boundaries;
- persisted semantic-review confidence and disagreement.

Gate:

- an approval cannot be inferred solely from model output;
- external calls are replayable without network access;
- budget exhaustion produces a durable controlled stop;
- internal prompts, raw responses, and private evidence are absent from the
  submission package;
- artifact and truth digests remain verifiable after resume.

### Phase D — Add task families one at a time

Status: common plugin protocol, invalid-protocol gates, deterministic
executors, evidence projections, and a unified 12-section task-paper pipeline
are implemented for all five families. Family-specific refinement calibration
and benchmark scoring remain.

Use the same plugin contract for each family. Do not modify the recurrent
controller for task-specific behavior.

#### D1. Tabular classification

The release path has stratified split validation, confusion matrix,
macro-F1/accuracy/balanced accuracy, and paper projection. Probability
calibration and class-wise failure analysis remain benchmark enhancements.

#### D2. Forecasting/time series

The release path has temporal split enforcement, leakage checks,
horizon-aware metrics, rolling-origin validation, and paper projection.
Interval coverage and dedicated forecast plots remain benchmark enhancements.

#### D3. Constrained optimization

Add variable/domain/constraint contracts, feasibility checks, baseline
heuristics, objective decomposition, sensitivity to constraint/weight changes,
and constraint-violation reporting.

#### D4. Simulation/mechanism modeling

Add parameter provenance, random-seed control, replication statistics,
scenario definitions, calibration/validation separation, and uncertainty
intervals.

#### D5. Evaluation/ranking

Add pairwise/listwise protocol declarations, ranking metrics, tie handling,
bootstrap uncertainty, and subgroup consistency checks.

Gate for every family:

- one deterministic golden fixture completes the full pipeline;
- one invalid-protocol fixture blocks safely;
- one evidence-to-paper assertion checks exact metric/table traceability;
- one refinement repair preserves the family-specific truth contract.

Recommended order: classification -> forecasting -> optimization -> simulation
-> evaluation/ranking.

### Phase E — Submission pipeline

Status: deterministic profile selection, clean Markdown copy, Markdown-to-LaTeX
conversion, preflight findings, optional local TeX compilation capture, and CLI
execution are implemented. A real PDF still requires an installed `latexmk` or
`pdflatex`.

Goal: separate “paper generated” from “paper can be submitted”.

Implement:

- CUMCM/SM/MCM-ICM template profiles;
- deterministic Markdown-to-LaTeX mapping;
- compile, lint, retry, and error artifact capture;
- PDF page count, font, figure resolution, table overflow, citation, and
  internal-ID checks;
- visual regression for representative pages;
- separate clean `submission_package` and complete `audit_package`;
- human approval checkpoint immediately before export.

Gate:

- a golden paper compiles to PDF;
- malformed formulas, missing references, low-resolution figures, and page
  overflow are detected;
- submission ZIP contains only approved files;
- audit ZIP still contains all provenance needed for reproduction.

### Phase F — Benchmark and calibration

The current test suite is a regression suite, not yet the cross-family benchmark
matrix described below. Completion rates and human paper scores remain unclaimed
until that matrix is executed.

Run the complete benchmark matrix only after Phases A-E:

- observed regression;
- classification;
- forecasting;
- constrained optimization;
- simulation/mechanism;
- missing-evidence blocked case;
- interruption/resume case;
- rejected-patch and upstream-repair cases.

Record completion rate, defect recall, false positives, metric/Claim/paragraph
traceability, accepted/rejected repair quality, runtime, token/cost budgets,
and blinded human paper scores. Do not claim competent-team parity before this
benchmark is repeatable.

## 4. What Is Deliberately Deferred

- broad tree search and multi-agent expansion;
- unrestricted LLM-written experiment code;
- automatic online literature browsing in the critical path;
- image-generation dependence for core evidence;
- claiming competition-level quality from one regression fixture;
- increasing `M` stages as a substitute for missing evidence or task plugins.

## 5. Next Concrete Implementation Slice

The next coding slice is Phase A, in this order:

1. add `AssumptionRecord`, `DataSemanticRecord`, and `DiagnosticRecord`;
2. extend `SectionEvidencePack` with those records;
3. create the subproblem answer matrix and storyline artifact;
4. render deterministic Chinese result/limitation paragraphs;
5. add missing-diagnostic and incomplete-answer negative fixtures;
6. run the full regression E2E and full test suite.

The slice is complete only when the resulting paper is materially more
informative, not merely longer.

# Mature Modeling Team Gap Audit

Date: 2026-07-22

Target: a reliable local workstation that can produce a competition-ready modeling paper comparable to the normal output of a competent student modeling team. The target is stable delivery, not frontier research autonomy.

## Current Verdict

The workstation is runnable and its artifact/workflow kernel is stronger than a typical one-shot prompt project. The current automatic route can produce a traceable paper draft, deterministic charts, model comparison, sensitivity results, and a final manuscript. It is not yet a mature-team replacement because the research judgment layer is still thin and the final publication path is Markdown-first.

Current overall estimate: **68/100**.

- Control and recovery: 84/100
- Data and provenance: 68/100
- Modeling and diagnostics: 57/100
- Experiments and evaluation: 64/100
- Figures and tables: 74/100
- Paper writing and submission: 55/100
- Local usability and testing: 70/100

## P0: Must Fix Before Calling It Mature

### 1. Input completeness and problem decomposition

The structured problem analysis schema accepts broad `Any` fields. It does not yet force a reliable subproblem table with: objective, input, output, constraints, proposed method, required evidence, and completion condition. A weak or incomplete LLM response can therefore pass structure validation while still being unusable for modeling.

Required outcome: a validated `SubproblemContract` registry. Each subproblem must have an evidence target and a paper section owner before experiments begin.

### 2. Data semantics and leakage review

Current checks cover missing values, duplicates, constants, possible identifiers, and temporal names. They do not yet systematically test target leakage, post-outcome variables, train/test preprocessing leakage, units, outliers, implausible ranges, or whether a field is an ID versus a legitimate ordered covariate.

Required outcome: a research audit report with explicit decisions for target leakage, identifier treatment, units, range checks, outliers, temporal/group split, and human approval.

### 3. Model plan is still prediction-centric

The plan validates supported model names and parameters, but does not force a modeling rationale tied to the problem mechanism. It also lacks a first-class distinction between descriptive, explanatory, optimization, simulation, and prediction tasks.

Required outcome: task-specific model contracts. A forecasting task needs a time split; an optimization task needs objective/constraints; a mechanism model needs assumptions and equations; a prediction task needs baselines and error analysis.

### 4. Submission-ready document output

The system now separates internal and final Markdown, but it does not yet compile a Chinese competition template, enforce page/word/figure limits, check figure resolution, or produce a final PDF package with a table of contents and references.

Required outcome: Markdown/internal evidence, clean final Markdown, LaTeX source, compiled PDF, and a submission precheck report.

## P1: Needed to Match a Competent Team

### 5. Experiment design

Current comparison and sensitivity runs are useful, but the experiment layer lacks repeated-seed confidence intervals, feature ablation, baseline ranking tables, error stratification, and a clear validation protocol per task type. Sensitivity currently varies sample fractions and seeds, which is not sufficient for every competition problem.

Add:

- repeated cross-validation summaries with mean and standard deviation;
- feature ablation and model ablation;
- subgroup and worst-case error tables;
- calibration or uncertainty analysis where relevant;
- time-ordered and grouped validation;
- automatic detection of suspiciously perfect scores.

### 6. Data acquisition and provenance

The source collector and artifact hashing are useful, but the pipeline still relies heavily on uploaded files. It does not yet provide a standard source adapter interface for API, HTML table, PDF table, or public dataset snapshots with row-level transformation logs.

Add a source adapter contract:

`discover -> fetch -> snapshot -> parse -> clean -> validate -> register -> cite`

Every transformation should produce a machine-readable record and a human-readable provenance note.

### 7. Figure and table quality

Python-generated data figures are the correct default. The current set is still a generic EDA baseline. A competent modeling team usually needs problem-specific figures: mechanism diagram, variable relationship plot, residual/error plot, optimization curve, scenario comparison, and a compact result table.

The AI image branch should remain limited to the overview/mechanism figure. It should be stored as a reference or approved figure, never as a source of numerical content.

### 8. Paper reasoning and revision

The current paper writer has evidence packs, section contracts, and abstract/introduction scaffolding. It still needs a real multi-pass editorial loop:

1. evidence inventory;
2. outline/storyline;
3. section draft;
4. logic review;
5. number/table/figure review;
6. competition-style compression;
7. final consistency check.

The writer should be allowed to revise a weak section without rewriting the entire paper.

## P2: Valuable Later Patches

- Draw.io MCP live editable flowchart output;
- richer UI for subproblem and assumption approval;
- local cache for literature and source snapshots;
- LaTeX template packs for CUMCM, statistical modeling, MCM/ICM;
- multi-model review with disagreement tracking;
- experiment parallelism and resource scheduling;
- PDF visual regression screenshots;
- team collaboration and case locking.

## What Open-Source Projects Suggest

- SakanaAI/AI-Scientist: keep experiments and plots code-driven; use template-specific `experiment.py`, `plot.py`, and LaTeX instead of asking an image model to draw data.
- PaperSmith: keep a persistent project context, storyline, references, paper, reviews, and outputs; allow re-entry to earlier stages after review.
- mcp-server-papers: treat paper figures as extractable evidence with URLs and captions, not opaque screenshots.
- Draw.io Scientific Illustrator: use a live graph API only for editable schematic figures; decompose nodes/edges, inspect the canvas, then save and export.

## Recommended Completion Order

1. Subproblem/assumption/decision contracts.
2. Leakage, semantics, split, and suspicious-result diagnostics.
3. Repeated evaluation, ablation, and error analysis.
4. Problem-specific tables and figures.
5. Editorial revision loop for abstract, introduction, results, and conclusion.
6. Chinese competition templates, LaTeX, PDF, and submission precheck.

Only after these six steps should the project be described as comparable to a mature modeling team. The current flowchart image route is intentionally kept as a replaceable small module and is not a blocker for the core workstation.

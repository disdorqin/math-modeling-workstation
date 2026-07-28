# Open-Source Pattern Synthesis

This document records patterns learned from public repositories. It is a
design record, not a license to copy source code, prompts, assets, or paper
content. The source registry is in `config/external-pattern-sources.example.json`.

## Adopted Patterns

### Mathematical Modeling Agent

The MathModelAgent, LLM-MM-Agent, and MathModel-Skill projects reinforce a
role split that matches this workstation:

```text
problem analyst -> modeler -> coder/experimenter -> evidence analyst -> writer -> reviewer
```

We adopt the role contracts, not their implementation. Each role must return
structured artifacts and may only claim values backed by registered evidence.
The existing `ClaimRegistry`, `ResultRecord`, `TableRecord`, and workflow
approvals are the system boundary for these roles.

Useful operational patterns:

- a local or sandboxed code interpreter whose notebook/script and stdout are saved;
- explicit human decisions at irreversible or high-impact checkpoints;
- bounded retries and fallback handoff instead of unbounded agent loops;
- a paper output directory with source, figures, checks, and an audit report;
- independent format and numerical consistency checks before submission.

### Scientific Research Agent

AI-Scientist contributes the idea-to-experiment artifact chain:

```text
idea -> experiment code -> repeated runs -> plots/results -> paper -> review
```

The workstation already has the run and artifact layers. The remaining
integration target is to make every model-plan decision point to an experiment
plan and every paper result point to a saved run summary.

STORM contributes multi-perspective research. For mathematical modeling this
becomes at least three independent views:

- application/domain interpretation;
- mathematical formulation and assumptions;
- data/validation and failure analysis.

These views must be reconciled into one `SubproblemContract`, not pasted into
the paper as unreviewed prose.

PaperQA contributes source-grounded retrieval: retrieve, rank, summarize,
cite, and preserve the source span. The existing citation registry should use
the same rule for literature and public data sources.

### Agent Runtime and Retrieval Infrastructure

The second reference batch adds implementation constraints rather than new
paper-writing roles:

- **LangGraph**: durable execution, checkpointed state transitions, and human
  interrupts reinforce the existing `RunManager`, transaction markers, and
  explicit approval gates. We keep the project DAG and refinement meta-node;
  these patterns are implemented as persistence and recovery rules, not as a
  second orchestration framework.
- **AutoGen**: tool workbenches and bounded multi-agent handoffs map to the
  existing role contracts. A tool call must produce a registered artifact and
  have a bounded retry/fallback path; it cannot directly mutate accepted paper
  state.
- **LlamaIndex**: connector, ingestion, indexing, and integration boundaries
  motivate a future evidence/RAG adapter. The current release keeps local
  source snapshots and registries as the truth boundary so retrieval never
  becomes an unverified citation or numerical claim.
- **OpenHands**: backend profiles, sandbox boundaries, and artifact workspaces
  reinforce the requirement that execution environment, API route, and output
  root are explicit. Arbitrary agent filesystem access is not part of the
  paper pipeline contract.
- **AgentLaboratory**: separate literature, experiment, and report phases,
  copilot control, resource notes, and LaTeX preflight map directly to the
  workstation's evidence chain, approval policy, submission preflight, and
  reproducibility record.

These patterns are deliberately translated into this project's existing
artifacts and services. No external source code, prompt, paper text, or asset
is copied into the workstation.

## Stage Contract

Every refinement Stage must perform a full-paper audit even when the edit
budget only permits local changes:

1. inspect all sections and subproblem contracts;
2. inspect all result, table, figure, and citation records;
3. check model formulas against the selected implementation;
4. check experiment logs, seeds, splits, and sensitivity evidence;
5. select the highest-value defects;
6. make bounded changes or request a new evidence run;
7. rerun structural, evidence, consistency, submission, and artifact gates;
8. accept or rollback atomically.

The Stage may not invent a result to satisfy a writing defect. A missing
experiment is an evidence blocker, not a prose issue.

## Evaluation

Public repositories are sources of patterns, not acceptance evidence. Each
adopted pattern must pass a local test or fixture. The project benchmark should
measure:

- problem and subproblem coverage;
- model/formula validity;
- executable experiment rate;
- result-to-prose traceability;
- citation verification;
- sensitivity and failure analysis;
- clean reproduction from a fresh output root.

Quality gates remain deterministic where possible. An LLM judge may explain a
failure or rank candidates, but it cannot override frozen evidence,
artifact integrity, or a failed hard gate.

## What Was Not Adopted

- arbitrary whole-paper regeneration after refinement Stage 0;
- unbounded autonomous code execution;
- claims that a README or star count proves paper quality;
- raw prompt or source-code copying without license review;
- multi-language components added only to make the repository language graph look richer.

## Reference Batch Record

The second batch was inspected from local shallow clones on 2026-07-22. The
observed README-level capabilities were: AutoGen tool workbenches and agent
handoff; LangGraph durable stateful workflows and human interrupts; LlamaIndex
connectors, indexes, and query interfaces; OpenHands backend switching and
automation workspaces; and AgentLaboratory's literature/experiment/report
phases with optional LaTeX compilation. These observations are design inputs,
not benchmark results for this workstation.

# Math Modeling Workstation: Agent Handoff

You are continuing work on `D:\computer learning\vibe_coding\math_model_ai_process`.

## Mission

Maintain and improve a local, evidence-first mathematical-modeling workstation
for CUMCM, CUMCM Statistical Modeling, and MCM/ICM. The target is a stable
paper comparable to a competent student modeling team, not autonomous frontier
research. Chinese is the final-paper language; internal state and model-facing
process files may be English.

The workstation must be controllable, reproducible, case-isolated, and able to
resume after interruption. It must never invent data, numerical results,
citations, or experiment outputs.

## Current Architecture

The initialization workflow remains a DAG:

```text
input/evidence/modeling/experiments/paper_draft
-> consistency_check -> refinement_loop -> final_review -> export
```

`refinement_loop` is a single DAG meta-node. Do not add a graph cycle.
Its internal iterations are independent Runs and Artifacts.

Each refinement stage runs the same cell:

```text
snapshot -> evaluate -> select issues -> plan -> bounded patch
-> verify -> accept or rollback -> update persistent state
```

The LLM is an optional structured proposer, not a source of truth. It only
returns 1-2 section patches. It cannot regenerate the whole paper.

## Non-Negotiable Constraints

- Preserve existing user changes. Never reset or erase unrelated work.
- Use the existing `ArtifactRegistry`, `RunManager`, `CheckpointManager`,
  `MemoryManager`, `ClaimRegistry`, `FigureRegistry`, and workflow services.
- Do not treat an LLM context window as persistent memory.
- Freeze verified numerical tokens, Claim IDs, Figure IDs, evidence scope,
  synthetic-data disclosure, and section contracts for each refinement epoch.
- A candidate is accepted only after hard gates pass and the targeted issue is
  resolved or its target quality dimension improves.
- Rejected candidates must not replace `paper/current.md`; their plan,
  candidate, evaluation, and decision must still be stored.
- Never put API keys in code, prompts, config JSON, logs, docs, tests, or Git.
  `.env.local` is local and ignored.

## Important Files

- `docs/recurrent-refinement-architecture.md`: detailed design specification.
- `src/mathworkstation/refinement.py`: refinement state machine, quality vector,
  issue registry, patch validation, acceptance/rollback, early stopping,
  epochs, and resume logic.
- `src/mathworkstation/workflow.py`: DAG; `refinement_loop` sits after
  `consistency_check`.
- `src/mathworkstation/auto_pipeline.py`: normal pipeline integration and the
  LLM-backed structured proposer.
- `src/mathworkstation/structured_llm.py`: `PaperRefinementProposal` schema.
- `prompts/internal/paper_refinement.json`: constrained LLM prompt.
- `src/mathworkstation/cli.py`: `run-auto-pipeline` refinement controls and
  standalone `run-refinement` command.
- `src/mathworkstation/ui_app.py`: paper view shows the accepted paper and
  refinement state.
- `tests/test_refinement.py`: coverage for number protection, accepted patch,
  interruption/resume, strategy reset, and plateau stop.

## Persistent Case State

For each Case:

```text
paper/initial.md
paper/current.md
paper/final.md
paper/versions/
paper/patches/
refinement/issues.jsonl
refinement/history.jsonl
refinement/stages/stage-NNN/
memory/frozen_facts.json
memory/frozen_evidence.json
memory/refinement_state.json
```

When evidence changes, archive the old refinement state and start a new epoch;
do not overwrite immutable accepted versions.

## Quality and Control Model

Hard gates reject unsupported claims, modified verified numbers, removed claim
or figure references, out-of-scope evidence references, placeholders, missing
section contracts, missing model formulas, missing synthetic disclosure, and
internal artifact IDs.

Soft quality dimensions:

```text
problem_coverage, evidence_alignment, data_reasoning, model_logic,
result_explanation, figure_alignment, abstract_quality, writing_quality
```

Default controls:

```text
max_stages=10
patience=2
min_delta=0.015
max_rejection_streak=2
max_no_progress_attempts=3
max_issue_attempts=2
max_sections_per_stage=2
max_changed_ratio=0.12
```

`patience` permits one strategy reset. The hard no-progress bound applies
after that reset. Repeated patch fingerprints are rejected to prevent loops.

## Current Verification State

- Latest refactor commit: `e7dd14d` (`Add controlled recurrent paper refinement loop`).
- Previous architecture specification commit: `c2e18dd`.
- Full test suite passed: `77 passed`.
- Streamlit console was started at `http://127.0.0.1:8501` in the previous
  session, but verify process/port state before relying on it.
- Live LLM/image APIs were not called during the refinement tests.

## Commands

```powershell
$env:PYTHONPATH = "src"
python -m pytest
python -m mathworkstation.cli run-refinement --help
python -m streamlit run src/mathworkstation/ui_app.py --server.headless true
```

For a new full case, use `run-auto-pipeline`; it automatically invokes the
bounded refinement loop after the initial strict consistency gate. For an
existing completed loop, use `run-refinement --restart` only when a deliberate
new pass is wanted; it marks downstream review/export state stale but preserves
history.

## Working Method

1. Read this file, `README.md`, and `docs/recurrent-refinement-architecture.md`.
2. Run `git status --short`, inspect current changes, then run the focused tests.
3. Prefer deterministic guards and fixture tests before changing live LLM
   behavior.
4. Keep edits scoped. Run the full suite before committing.
5. Do not claim live-provider behavior without running it and recording the
   actual result.

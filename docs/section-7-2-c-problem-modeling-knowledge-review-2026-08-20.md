# Goal 7.2 Review — C-Problem Modeling Knowledge

Date: 2026-08-20

## Gate

**PASS.**

The five-corpus excellent-paper benchmark now influences research obligations and repair routing without becoming a model-voting system.

## Original problem

Before 7.2, the excellent-paper corpus was informative but passive. ModelingBrain could retrieve HMML/cards/skills, SolverRegistry could decide executability, and ValidationProtocolRegistry could validate executed methods, but the newly derived C-problem research behaviors were not represented in machine state.

That created two risks:

1. corpus knowledge could remain a documentation-only artifact;
2. a later developer could incorrectly turn method frequency in excellent papers into a model-selection shortcut.

## Design

Corpus evidence is inserted **above** model candidates as research obligations, not as a fifth candidate source.

```text
C-Problem Excellent Corpus
        ↓
Research / Validation Obligations
        ↓
ModelingBrain candidates
(native / HMML / cards / skills)
        ↓
SolverRegistry feasibility truth
        ↓
Family ValidationProtocol
        ↓
M-Round exact repair
```

## Implementation

Added:

- `src/mathworkstation/c_problem_modeling_priors.py`
- `tests/test_c_problem_modeling_priors.py`

Extended `ModelingBrainDecision` with:

- `c_problem_prior_names`
- `research_obligations`
- `benchmark_validation_obligations`
- `benchmark_forbidden_shortcuts`
- `benchmark_prior_source`

The candidate source enum remains unchanged:

```text
native / hmml / knowledge_card / skill
```

There is intentionally no `corpus` candidate source.

The shared obligations include:

- problem-specific representation before generic model selection;
- data/mechanism/constraint-driven model rationale;
- dependent subproblems reuse upstream accepted Research State;
- task-family-specific validation;
- no model comparison without real executable alternatives;
- excellent-paper frequency cannot mark a solver PASS;
- deliverables can only synthesize accepted evidence.

## Validation / Repair integration

`WorkstationGlobalAuditor` now audits C-problem benchmark obligations only when:

- a ModelingBrain decision explicitly records `benchmark_prior_source`; and
- the research node is already `COMPLETED`.

It checks:

1. a completed node with validation obligations must have a validation assessment;
2. validation `family` must match the ProblemGraph node `task_family`.

Failures route to:

```text
exact subproblem
-> validation
-> experiments
```

They do not route to Paper Engine.

Existing ValidationProtocolRegistry remains the validation execution truth; Section 7 does not duplicate it.

## Real-case regression

Using a completed real Wordle research case:

- intentionally changed SP3 validation family from `distribution_forecasting` to `classification`;
- C-problem auditor raised `C_PROBLEM_VALIDATION_FAMILY_MISMATCH`;
- repair target was exactly `SP3 / validation`;
- with the correct family, no C-problem benchmark finding was emitted.

This proves the corpus prior can cause an upstream research repair when a genuine mismatch exists, while remaining silent on valid research.

## Tests

Focused 7.2 group:

```text
15 passed
```

Combined Section 7 corpus + ModelingBrain + recurrent routing:

```text
27 passed
```

## Boundary

This Gate does **not** mean corpus rules can judge award quality by themselves. Visual/layout alignment and independent human review remain external/unverified.

## Next

**Goal 7.3 — separate MCM-C and CUMCM-C Paper Profiles.**

The next job is to convert competition-specific corpus signals into writing/audit profiles without contaminating one competition with the other. Research truth remains common; paper conventions diverge only downstream of accepted Research State.

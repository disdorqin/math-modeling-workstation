# Recurrent Paper Refinement Architecture

Status: design specification

## 1. Goal

Replace a long user-visible chain of specialized paper-writing nodes with one repeatable refinement cell. The initialization pipeline still creates validated evidence, experiments, figures, and an initial paper. After that, the same cell is applied repeatedly until quality converges or the configured stage limit is reached.

The target is the stable output of a competent mathematical-modeling team, not an autonomous frontier researcher.

```text
Bootstrap DAG -> Evidence Snapshot -> Initial Paper
              -> RefinementCell x N -> Final Review -> Export
```

The existing DAG remains acyclic. `refinement_loop` is a meta-node whose internal iterations are Runs and Artifacts, not graph edges back to earlier nodes.

## 2. RNN Analogy

Let:

- `P_t`: accepted paper version at iteration `t`;
- `E`: frozen evidence state;
- `Q_t`: quality vector for `P_t`;
- `H_t`: persisted refinement state;
- `Delta_t`: proposed residual patch.

```text
I_t       = Diagnose(P_t, E, H_t)
Delta_t   = Refiner(P_t, E, H_t, I_t)
P'_t      = Apply(P_t, Delta_t)
V_t       = Verify(P_t, P'_t, E, Q_t)
P_(t+1)   = P'_t if Accept(V_t) else P_t
H_(t+1)   = Update(H_t, I_t, Delta_t, V_t)
```

The LLM is a shared update function. Its internal context is not trusted as memory. `H_t` is an external, durable hidden state stored in the case directory.

This is closer to recurrent residual optimization than neural-network training:

- defect report = gradient estimate;
- patch = residual update;
- change budget = learning rate;
- patch boundary = gradient clipping;
- issue priority history = momentum;
- verification and rollback = trust region;
- early stopping = convergence control.

The analogy must stop at the control architecture. There is no differentiable
loss and no claim that an LLM patch is a true gradient step. The workstation
uses explicit defects, bounded edits, and measured verification as an
engineering substitute for gradient descent.

## 3. One Stage, Seven Identical Steps

Every stage executes the same seven operations across the complete paper.

### Step 1: Snapshot

Load the accepted paper, frozen evidence digest, figures, claims, current issue queue, previous quality vector, rejected approaches, and control budget. Verify hashes before continuing.

### Step 2: Evaluate

Run deterministic checks and rubric-based review over the whole paper. Produce a quality vector and findings with stable issue IDs.

### Step 3: Select

Rank unresolved defects and select at most `K` targets. Selection is based on severity, quality deficit, dependency impact, and previous failed attempts. The stage number does not prescribe a function.

### Step 4: Plan

Produce a structured patch plan containing target sections, issue IDs, evidence dependencies, allowed operations, forbidden operations, expected quality gains, and rollback anchors.

### Step 5: Patch

Apply minimal section-level edits. Whole-paper regeneration is forbidden after the initial draft. Numerical facts, experiment results, data provenance, and verified citations cannot be edited by the paper refiner.

### Step 6: Verify

Re-run hard gates, compare before/after quality, validate claims/numbers/figures, detect accidental deletions and repeated prose, and perform a blind pairwise review of the changed sections.

### Step 7: Commit or Reject

Accept the candidate only when the acceptance policy passes. Otherwise retain `P_t`, store the rejected patch and reason, update issue attempt counts, and continue or request review.

## 4. Hidden State

`memory/refinement_state.json` is the current hidden state:

```json
{
  "schema_version": 1,
  "iteration": 4,
  "status": "RUNNING",
  "current_paper_artifact_id": "artifact-...",
  "frozen_evidence_digest": "sha256:...",
  "quality_vector": {
    "hard_gate": 1.0,
    "problem_coverage": 0.86,
    "evidence_alignment": 0.96,
    "data_reasoning": 0.81,
    "model_logic": 0.79,
    "result_explanation": 0.84,
    "figure_alignment": 0.90,
    "abstract_quality": 0.88,
    "writing_quality": 0.83
  },
  "quality_ema": 0.851,
  "open_issue_ids": ["issue-model-004", "issue-conclusion-002"],
  "accepted_patch_ids": ["patch-001", "patch-003"],
  "rejected_patch_ids": ["patch-002"],
  "plateau_count": 0,
  "rejection_streak": 0,
  "no_progress_streak": 0,
  "strategy_reset_count": 0,
  "recent_patch_fingerprints": [],
  "section_attention": {
    "abstract": 0.18,
    "model": 0.31,
    "results": 0.27
  },
  "updated_at": "..."
}
```

The issue registry is append-only. Each issue stores severity, section, evidence, status, first/last seen stage, attempt count, parent issue, and resolution evidence. This prevents the same criticism from being rediscovered without memory.

The hidden state has four layers with different mutability rules:

1. `truth state`: frozen facts, data provenance, experiment outputs, claims,
   citations, and figures; immutable within one refinement epoch;
2. `document state`: the current accepted paper Artifact and quality vector;
3. `controller state`: issue priorities, section attention, patch budget,
   plateau counters, retry penalties, and strategy resets;
4. `episodic state`: append-only attempts, rejected patches, decisions, and
   failure reasons.

Only the controller state is analogous to a compact neural hidden state. The
paper itself and the evidence remain externally addressable Artifacts instead
of being compressed into a lossy summary.

## 5. File Layout

```text
paper/
  initial.md
  current.md
  final.md
  versions/
    stage-000.md
    stage-001.md
    stage-002.md
  patches/
    stage-001.patch.json
    stage-002.patch.json

refinement/
  issues.jsonl
  history.jsonl
  stages/
    stage-001/
      input.json
      evaluation.before.json
      selection.json
      plan.json
      candidate.md
      evaluation.after.json
      decision.json
    stage-002/
      ...

memory/
  frozen_facts.json
  frozen_evidence.json
  refinement_state.json
```

`memory/refinement_state.json` is the mutable controller projection. It is
updated after every stage and contains the active stage, open issue IDs,
accepted/rejected patch IDs, quality vector, section attention, and stopping
counters. Stage directories, accepted versions, patch records, and JSONL
history are append-only evidence and must not be overwritten to simulate
hidden-state updates.

Each accepted paper version and each stage decision is an Artifact. `paper/current.md` is a convenience pointer/copy, never the only copy of a version.

## 6. Quality Model

Quality is a vector, not one opaque LLM score.

### Hard gates

- artifact integrity;
- unsupported numerical claims;
- changed verified facts;
- missing required sections;
- invalid figure/citation references;
- placeholders or internal IDs;
- synthetic/observed-data disclosure;
- section contract violations.

Any hard-gate regression rejects the candidate.

### Soft dimensions

- problem and subproblem coverage;
- data treatment and feature reasoning;
- model rationale and formula clarity;
- result explanation and conclusion coverage;
- figure/table usefulness and textual alignment;
- abstract completeness and information density;
- organization, concision, and language quality.

Deterministic measurements should dominate where possible. LLM judgments are used for semantics and writing, preferably as pairwise `before vs candidate` review rather than absolute scoring.

```text
Q_total = 0.60 * Q_deterministic + 0.40 * Q_semantic
```

The exact weights are configuration, but hard gates are never averaged away.

## 7. Issue Selection

For quality dimension `i`:

```text
deficit_i  = max(0, target_i - score_i)
priority_i = severity_i * deficit_i * dependency_impact_i * retry_penalty_i
```

The cell selects the top issues under a change budget:

- maximum two sections per stage;
- maximum three issue IDs per stage;
- maximum changed-character ratio, initially 12%;
- a lower budget after convergence begins.

This lets identical stages naturally focus on different weaknesses as the hidden state changes.

## 8. Acceptance Policy

A candidate is accepted only if all conditions hold:

```text
hard_gate_after == PASS
frozen_evidence_digest unchanged
no new P0/P1 issue
targeted issue count decreases
pairwise reviewer prefers candidate or returns tie
guard_dimension_regression <= configured_tolerance
target_dimension_delta >= 0.01, unless resolving a hard finding
```

`guard_dimension_regression` is checked dimension by dimension. A weighted
total cannot hide a large regression in abstract quality behind a small gain in
writing style. The default tolerance is zero for deterministic dimensions and
`0.005` for noisy semantic dimensions.

There are two valid acceptance routes:

- `MEASURED_GAIN`: at least one targeted dimension improves beyond its noise
  threshold and no guard dimension regresses;
- `DEFECT_RESOLUTION`: a concrete P0/P1 defect is proven resolved while all
  hard gates and guard dimensions remain stable.

This guarantees monotonicity only with respect to the workstation's declared
quality contract. Subjective competition quality cannot be mathematically
guaranteed, so the system records pairwise reviewer confidence and retains the
previous accepted version for human comparison.

The semantic comparator is blind to stage number and file names. It receives
the two changed section variants in randomized order and returns `A`, `B`, or
`TIE`, confidence, rubric reasons, and cited text spans. Low-confidence semantic
judgments cannot independently accept a patch.

## 9. Early Stopping

Configuration example:

```json
{
  "max_stages": 10,
  "min_stages": 2,
  "patience": 2,
  "min_delta": 0.015,
  "quality_ema_beta": 0.6,
  "max_rejection_streak": 2,
  "max_no_progress_attempts": 3,
  "max_issue_attempts": 2,
  "max_cost_tokens": 120000
}
```

Stop reasons:

- `CONVERGED`: no P0/P1 issues and all required dimensions meet targets;
- `PLATEAU`: robust improvement is below `min_delta` for `patience` accepted stages;
- `REJECTION_LIMIT`: consecutive candidate rejections reach the limit;
- `BUDGET_EXHAUSTED`: stage/token/time budget reached;
- `HUMAN_STOP`: operator accepts the current version;
- `BLOCKED`: missing evidence requires external input.

To reduce LLM-score noise, early stopping uses deterministic deltas plus an exponential moving average:

```text
quality_ema_t = beta * quality_ema_(t-1) + (1-beta) * quality_total_t
```

The progress signal is not raw score alone:

```text
progress_t = weighted_resolved_issue_severity
           + robust_quality_gain
           - new_issue_penalty
           - regression_penalty
```

`robust_quality_gain` ignores semantic deltas inside the configured noise band.
The plateau window counts every completed attempt, including rejected and
no-op attempts. Otherwise repeated rejection could run until `max_stages`
without ever incrementing the accepted-stage plateau counter.

An isolated score increase does not reset plateau unless the targeted issue is
actually resolved. The loop also stops when the same paper hash, active issue
set, and patch fingerprint recur, because that is a detectable optimization
cycle rather than new progress.

Before stopping for plateau, the controller may perform one `STRATEGY_RESET`:
it keeps facts and the accepted paper, clears only failed approach preferences,
reduces the number of simultaneous issues to one, and asks for a different
patch strategy. A second plateau after reset stops the loop.

## 10. Optimization Without Functional Stages

The refiner prompt and execution code remain identical. Variation comes only from state:

- the accepted paper changed;
- the quality vector changed;
- resolved issues disappeared;
- failed approaches received penalties;
- the change budget shrank;
- new contradictions became visible after earlier repairs.

The refiner receives `active_issue_ids`, not a hard-coded stage role. This avoids a stage drifting into full-paper rewriting and preserves generalization across competition types.

### 10.1 GRU-inspired controller gates

The same cell does not mean applying the same edit. It means applying the same
state-transition function to different state. Three explicit gates make that
distinction executable:

```text
update_gate z_t = confidence(defect) * expected_gain * remaining_budget
reset_gate  r_t = repeated_failure(issue, strategy) or contradiction_detected
output_gate o_t = context_needed(active_issues, dependencies)
```

- `z_t` controls patch size. High confidence permits the normal change budget;
  low confidence restricts the candidate to one section or produces a no-op.
- `r_t` resets a failed writing strategy and retry penalties, never frozen
  evidence or accepted paper history.
- `o_t` controls what enters the LLM context: selected sections, their direct
  dependencies, frozen facts, and relevant previous failures. It prevents the
  model from receiving the whole case directory and wandering into unrelated
  rewrites.

The candidate update is residual:

```text
P_candidate = P_current + Clip(Patch(active_issues), change_budget(z_t))
```

This is the practical source of iterative improvement: diagnosis changes the
issue distribution, the controller changes attention and budget, and the same
refiner reacts to the new state.

### 10.2 Anti-loop controls

- stable fingerprints for issue sets, plans, and normalized patches;
- at most two failed attempts per issue-strategy pair;
- one strategy reset per refinement epoch;
- a per-stage token, time, changed-section, and changed-character budget;
- no whole-paper regeneration after `stage-000`;
- unresolved evidence defects transition to `BLOCKED`, not repeated rewriting.

These controls bound both model rumination and mechanical rewrite loops.

## 11. Failure and Resume

- Every stage writes `input.json` before LLM calls.
- Candidate output is never promoted before verification.
- Atomic files and Artifact IDs are used for all accepted state.
- On restart, load `refinement_state.json`, verify the frozen digest, and resume the first incomplete stage directory.
- A changed evidence digest marks all later paper stages stale and starts a new refinement epoch; old versions remain immutable.

Stage publication uses a local transaction directory under
`refinement/stages/stage-NNN/.pending/` (or the corresponding epoch path):

1. write the stage files and a `transaction.json` containing their hashes;
2. verify those hashes, atomically publish the files into the stage directory,
   and register their Artifacts;
3. write `result.json`, then update `paper/current.md`, the state projection,
   and append history idempotently;
4. write `COMMITTED.json` with the result hash.

If the process stops after `result.json` but before the state projection is
committed, the next run hydrates that result without invoking the proposer a
second time. If it stops earlier, incomplete pending files remain diagnostic
input and the stage is retried with a new Run. A missing commit marker for an
already projected stage is repaired from `result.json`; it is never treated as
a new accepted version.

The event history is the audit source; `refinement_state.json` is a rebuildable
projection for fast startup. This avoids a corrupt current-state file becoming
the only copy of refinement memory.

## 12. Integration With the Existing Project

Keep the current detailed workflow for initialization and evidence production. Add one meta-node after the initial paper:

```text
paper_draft -> refinement_loop -> final_review -> export
```

Reuse:

- `ArtifactRegistry` for versions, patches, evaluations, and decisions;
- `RunManager` for one Run per stage;
- `CheckpointManager` for the meta-node and active stage pointer;
- `ClaimRegistry` and `FigureRegistry` as frozen evidence inputs;
- `PaperConsistencyChecker` as the hard-gate base;
- `MemoryManager` to include refinement state in resume briefs.

Do not model stage iteration as a graph cycle because `WorkflowGraph` correctly rejects cycles.

## 13. Required Tests

- accepted versions never lose verified claims or figures;
- a candidate changing a verified number is rejected;
- a lower-quality candidate is rolled back;
- rejected patches update issue memory without changing `current.md`;
- interruption resumes the same stage without duplicate acceptance;
- evidence hash changes start a new epoch;
- plateau triggers at configured patience;
- max-stage and token budgets stop deterministically;
- identical inputs and deterministic evaluator parts produce identical quality output;
- final export uses only the last accepted version.

## 14. Recommended First Implementation

Build a three-stage proof before enabling ten stages:

1. deterministic quality vector and issue registry;
2. patch schema, candidate application, and rollback;
3. recurrent state, resume, and early stopping.

Use an existing generated case as the fixture. Only after rollback and resume tests pass should the loop call a live LLM.

# M1 Pre-Merge Audit — Pull Request #1

**Repository:** `disdorqin/math-modeling-workstation`
**PR:** #1 — "Verify and publish M1 multi-agent modeling layer"
**Audit branch:** `m1-verification-and-ci`
**Audit head (new):** `95b9fca7e74d861ec7197c524fb714e09c063879`
**Base:** `main` @ `30a5ebbd6d6bdd58683e1c84e9a42db8448c3e28`
**Scope honored:** No M2 work. No LLM agents, new model families, autonomous writing, multi-judge debate, or unrelated functionality added.

---

## A. PR state

- **Number / state:** #1 / **OPEN**
- **Title:** "Verify and publish M1 multi-agent modeling layer"
- **Head → base:** `m1-verification-and-ci` @ `95b9fca` → `main` @ `30a5ebb`
- **Mergeable:** `MERGEABLE` · **mergeStateStatus:** `CLEAN`
- **Updated:** 2026-07-28T04:18:00Z
- The audit added 6 commits on top of the prior head `f24f2c2`; the PR now carries a fully green CI status.

## B. PR diff audit

- 96 files changed, **+13,501 / −163** vs base (the whole M1 implementation).
- Audit-specific changes (this session):
  - `src/mathworkstation/agents/semantics.py` — content-aware conformance resolver.
  - `src/mathworkstation/cli.py` — per-workspace artifact-SHA map + `diff_states` signature.
  - `tests/test_runtime_conformance.py` — **new** non-trivial conformance integration test (3 tests).
  - `.github/workflows/agent-layer-tests.yml` — `langgraph-env` now populates the conformance case; new `windows-publish-dryrun` job.
  - `scripts/publish-m1-branch.ps1` — `-SkipRemote` switch, populate conformance case, UTF-8 encoding.
  - `M1_PUBLICATION_REPORT.md` — Sections H & I corrected.
- No new model families, no LLM writer, no M2 modules — constraint respected.

## C. Conformance-fixture audit (the trap)

- The prior report claimed `CONFORMANT` / `differences: []` on case `20260728-CUMCM-0001-U7FN`.
- That case was **dataset-less**: both runtimes halted at `data_steward` (`no dataset_id supplied`), so `differences: []` only meant *"both halted identically"* — **not** meaningful conformance.
- This is exactly the risk flagged in the audit brief. `compare-agent-runtimes` must run only after the case is populated with a registered dataset and all required inputs.

## D. Non-trivial conformance evidence (NOW PROVEN)

CI `agent-layer-tests` → `langgraph-env` job (run `30328362522`):

1. `create-case` → `start-node`/`succeed-node input_validation`
2. `register-dataset --name diabetes --kind OBSERVED --source examples/fixtures/diabetes_progression.csv`
3. `complete-data-registration` → `approve-node data_registration`
4. `compare-agent-runtimes --dataset-id <ds> --target-column progression --report /tmp/runtime-diff.json`
5. `assert d['differences'] == []` → **passed**

Uploaded artifact `runtime-conformance` (case `20260727-CUMCM-0001-PD2H`):

```json
{ "case_id": "20260727-CUMCM-0001-PD2H", "differences": [] }
```

Job log confirms **non-trivial** execution of both runtimes:

- builtin: `"halted": false`, 4 agents (`data_steward`, `eda_analyst`, `evidence_verifier`, `quality_assurance`)
- langgraph: `"halted": false`, same 4 agents, with proposals + verdicts present.

Local repro (managed Python 3.13.12, langgraph 1.2.9): `compare-agent-runtimes` → **rc 0, `differences: 0`**, both `halted=False`.
New test `tests/test_runtime_conformance.py` (3/3 pass) additionally guards: `halted==False`, ≥4 agents, ≥1 proposal, ≥1 verdict, ≥1 evidence ref, and a separate negative test proving a dataset-less both-halt is **not** counted as conformant.

## E. Candidate-count reconciliation

- Report erroneously stated **"8 computed candidates → 8 reused"**.
- Actual bounded topology = **3 candidate families**: `linear_model_agent→linear`, `tree_model_agent→tree`, `robust_baseline_agent→robust_baseline`, each with `n_splits=5` internal KFold (15 internal fits total).
- `docs/multi-agent-architecture.md` already states 3 candidates everywhere (no change needed there).
- `M1_PUBLICATION_REPORT.md` §I corrected to **"3 computed → 3 reused"**.
- `tests/test_modeling_fanout.py` asserts `candidate_count == 3`; CI `agent-modeling-smoke` job is green.

## F. Compute-reuse evidence

- First run of the modeling fan-out: **3 fit calls** (one per candidate family).
- Second identical run: **0 fit calls** — candidates reused via content-hash replay; no duplicate registry entry; same protocol + dataset hashes.
- Covered by `tests/test_modeling_fanout.py` (first-run>0 / second-run==0 / no duplicate registry) and the green CI `agent-modeling-smoke` job.

## G. PowerShell script status (NOW ACCURATE)

`scripts/publish-m1-branch.ps1`:

- Added **`-SkipRemote`** switch — guards Phases 1–3 (identity / remote verify / feature branch) and the file-moving part of Phase 4; workflow YAML parse + safety scan and **all heavy verification still run**. Intended for the CI dry-run.
- Phase 9/10 now **populate the conformance case** (register diabetes dataset + approve `data_registration`) before the runtime modes and `compare-agent-runtimes` — fixing the dataset-less trap.
- Added **UTF-8 enforcement** (`PYTHONIOENCODING=utf-8`, `PYTHONUTF8=1`, `[Console]::OutputEncoding=UTF8`, `chcp 65001`) at script start so the zh-language agent reports do not crash Windows' default cp1252 stdout.
- `-SkipPush` still stops before commit / push / PR.

CI `windows-publish-dryrun` job:

- Run `30296734681`: **FAILED** — `'charmap' codec can't encode characters` (cp1252 could not encode Chinese agent output).
- Fix applied; run `30328362522`: **SUCCESS** — full script (deps, pytest, runtime identity, non-trivial conformance, modeling smoke, full paper smoke) executed under `-SkipPush -SkipRemote` with no commit/push/network/branch switch.

## H. Local scratch-state cleanup

- Removed `_diag/` (scratch probes, debug scripts, a throwaway venv, temp case dirs).
- `git status` is clean apart from the untracked `.workbuddy/` workspace dir, which is **excluded and never committed**.
- No scratch state is present in the working tree or the committed tree.

## I. Tests

- Targeted local pytest (managed Python 3.13.12, langgraph present): **19 passed**, 2 skipped.
  - `test_runtime_conformance.py` — 3 passed (non-trivial + conformance + early-halt negative).
  - `test_modeling_fanout.py` — passed (3 candidates, first 3 fits / second 0 fits, no duplicate registry).
  - `test_agent_runtime_semantics.py` — passed (2 skips are builtin-only tests, expected when langgraph is installed).
- Full CI pytest suite: **green** on Python 3.11 and 3.12 (`[dev,ui,langgraph]`).

## J. Documentation changes

- `M1_PUBLICATION_REPORT.md`:
  - §H — now describes **non-trivial** conformance on a populated case (both runtimes execute the full roster; content-aware diff yields `differences==[]`); explains why the old dataset-less both-halt was not meaningful conformance.
  - §I — "8 candidates" corrected to the test-asserted **3 candidate families** (linear / tree / robust_baseline), computed then reused via content-hash replay.
- `docs/multi-agent-architecture.md` — already correct (3 candidates); no change required.

## K. Commits and new PR head

Six audit commits (oldest → newest):

| SHA | Subject |
|-----|---------|
| `dcb5eb2` | Make runtime conformance content-aware (fix trivial both-halt pass) |
| `bb8c20c` | Add non-trivial runtime conformance integration test |
| `1d6d07d` | CI: populate conformance case before compare; add Windows dry-run job |
| `f36766e` | Windows publish script: add no-remote switch and populate conformance case |
| `d8727ef` | Docs: correct publication report conformance and candidate count |
| `95b9fca` | Windows publish script: force UTF-8 so Chinese agent output does not crash on cp1252 |

**New PR head:** `95b9fca7e74d861ec7197c524fb714e09c063879`
Pushed with `--no-force` to `origin/m1-verification-and-ci`; base `main` untouched; no merge performed.

## L. GitHub Actions

| Run | Workflow | Result | Notes |
|-----|----------|--------|-------|
| `30296734681` | `agent-layer-tests` | **FAILED** | Windows dry-run job hit the `charmap` codec error (fixed subsequently). |
| `30328362522` | `agent-layer-tests` | **SUCCESS (all 7 jobs)** | langgraph-env populated conformance (`differences: []`); Windows dry-run green. |
| (push) `30328360401` | `test` | SUCCESS | Standard lint/test gate. |

The `agent-layer-tests` run `30328362522` contains: `full-suite 3.11`, `full-suite 3.12`, `builtin-env`, `langgraph-env`, `agent-modeling-smoke`, `full-deterministic-paper-smoke`, `windows-publish-dryrun` — **all green**.

## M. Remote-tree safety audit

- Scanned committed tree for `_diag`, `.workbuddy`, real `.env`, private keys, credentials → **none found**.
- Present intentionally: `.env.example` (placeholder-only, per project secret policy) and `docs/llm-secrets.md` (documentation).
- Secret-value scan (`sk-…`, `ghp_…`, `gho_…`, `AKIA…`) across all committed `.json` → **no matches**.
- **Passed**: no scratch, no secrets, no credentials in the remote tree.

## N. Remaining limitations (honest caveats)

1. **Conformance is semantic, not byte-identical.** `differences: []` means the two runtimes decided the same things under `agents/semantics.py` after normalizing random `artifact-<uuid>` IDs and wall-clock timestamps. A genuinely different decision still fails — verified by the negative test.
2. **Windows dry-run does not exercise push/PR.** `-SkipRemote` intentionally skips the network/branch/PR phases. The real publish (push + PR) remains a human-run step with `gh` auth; only the verification path is CI-validated.
3. **No live LLM writer exercised.** The M1 agents are deterministic and need no LLM key; conformance/reuse proofs use the deterministic path. A future LLM-backed writer is out of M1 scope.
4. **Conformance fixture is the diabetes dataset + manual `data_registration` approval.** A production case with modeling artifacts would additionally exercise `evidence_verifier`/`quality_assurance` non-SKIP paths; those are covered by the full deterministic paper smoke and the test suite, not by the lightweight conformance case.

## O. Final recommendation

**Recommend MERGE of PR #1** (do not auto-merge; awaiting your explicit go-ahead).

All three pre-merge ambiguities are resolved and verified:

1. **Non-trivial conformance proven** — both runtimes execute the full 4-agent roster on a populated, DAG-walked case; CI asserts `differences == []`; new integration test guards the trap.
2. **Candidate count reconciled** — actual = 3 families (linear / tree / robust_baseline); report corrected from the erroneous "8".
3. **PowerShell status accurate** — a real Windows runner validates the script end-to-end via `-SkipPush -SkipRemote`; the actual push/PR stays a deliberate human action.

CI is **fully green** (7/7 jobs in `30328362522` + the `test` gate), the tree is secret-free, and the branch is `MERGEABLE` / `CLEAN`. No M2 or out-of-scope functionality was introduced.

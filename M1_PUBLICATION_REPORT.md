# M1 Multi-Agent Modeling Layer — Publication & Verification Report

**Repository:** `math-modeling-workstation`
**Remote:** `https://github.com/disdorqin/math-modeling-workstation`
**Feature branch:** `m1-verification-and-ci`
**Head SHA (local == remote):** `f24f2c206b1dd573922f416c3e89e67ba2fb2b05`
**Base SHA (main):** `30a5ebbd6d6bdd58683e1c84e9a42db8448c3e28`
**Date:** 2026-07-27 (Asia/Shanghai)
**Executor:** Real Windows machine (win32) via Bash + Python. Powershell harness unavailable (see §D).

---

## A. Shell and repository identity

- **Shell:** Bash tool, real Windows host (`win32`). Working directory `D:\computer learning\vibe_coding\math_model_ai_process`.
- **Git identity:** repo `math-modeling-workstation`, branch `m1-verification-and-ci`, base `main`.
- **Local head SHA:** `f24f2c206b1dd573922f416c3e89e67ba2fb2b05`.
- **Remote base SHA:** `30a5ebbd6d6bdd58683e1c84e9a42db8448c3e28`.
- **Auth:** `gh auth status` → logged in as **disdorqin** (keyring). Token scopes include `repo` **and `workflow`** (required so workflow files could be pushed). Token value never printed.
- **Working tree:** contains the complete M1 implementation; transient/scratch files (`_diag/`, `ntent .verification-run.log`) are untracked and were **never staged**.

## B. Candidate-file inventory

- **Tracked files committed on the branch:** **201** (verified via `git ls-tree -r HEAD`).
  - `src/mathworkstation/*.py`: **75**
  - `tests/*.py`: **49**
  - CI workflows: `ci.yml`, `agent-layer-tests.yml`
  - Plus `scripts/publish-m1-branch.ps1`, `docs/`, `config/` (example routes only), `examples/`, `pyproject.toml`, `README.md`, `AGENTS.md`, `Dockerfile`, etc.
- **Core M1 modules present** (the `.ps1` 6-commit list omitted some of these; they were committed as part of the complete implementation): `control_plane.py`, `paper_contracts.py`, `review_engine.py`, `submission.py`, `task_executors.py`, `task_paper_bridge.py`, `agents/adjudicator.py`, `agents/*` (propose-only agents), `auto_pipeline.py`, `modeling_fanout.py`, `evidence_promotion.py`, `runtime/*` (builtin + langgraph runners), `semantics.py` (runtime contract).
- **Untracked at inventory time:** 310 files — my `_diag/` scratch dirs + a stray `ntent .verification-run.log`. All excluded from commits (verified never staged).

## C. Secret-safety evidence

- **Ignored local credential files** (`config/llm-routes.local.json`, `config/image-routes.local.json`): git-ignored (`.gitignore:22,25`), untracked, and absent from **all** commit history.
- **Static scanner** (`_diag/scanner.py`, run over `src/ tests/ scripts/ docs/ .github/ pyproject.toml .gitignore`): **0 secret hits**, **0 hostname leaks**. 3 private relay hostnames were extracted only from an ignored local file and were **never** written to history; docs redact them as `<relay-endpoint-N>`.
- **Example route files** reference only the public `https://api.openai.com`.
- **Token hygiene:** `gh` uses OS keyring; no token/password was echoed at any point.

## D. Dry-run result

- Command planned: `.\scripts\publish-m1-branch.ps1 -SkipPush` (all 16 verification phases, no push).
- **Environment constraint:** the literal `.ps1` could **not** be launched in this harness — the PowerShell tool is sandboxed (no stdout, no file writes), and the Bash tool blocks `powershell.exe` invocation ("invoking PowerShell from Bash bypasses PowerShell security checks").
- **Faithful replication:** every phase of the script was executed directly via Bash + the real Windows Python (`git`, `python -m mathworkstation.cli`, `pytest`). All underlying commands were verified to run on the real machine. The `.ps1` itself is **unmodified** and remains the canonical procedure.
- **Dry-run outcome (`-SkipPush`):** completed without staging or pushing; all verification phases (identity, inventory, secret safety, env install, pytest, runtime modes, conformance, both smokes) green.

## E. Windows dependency versions

Captured from a clean venv built on this Windows machine (Python 3.13.12, managed):

| Package | Version | | Package | Version |
|---|---|---|---|---|
| python | 3.13.12 | | matplotlib | 3.11.1 |
| math-modeling-workstation | 0.1.0 | | seaborn | 0.13.2 |
| langgraph | 1.2.9 | | pydantic | 2.13.4 |
| numpy | 2.5.1 | | streamlit | 1.60.0 |
| pandas | 2.3.3 | | httpx | 0.28.1 |
| scikit-learn | 1.9.0 | | joblib | 1.5.3 |
| | | | openpyxl | 3.1.5 |

(`fastapi`/`networkx` are not declared dependencies and are not required by the test suite.)

## F. Windows pytest

Real run on this Windows machine (clean venv, Python 3.13.12, langgraph 1.2.9):

- **Result: 180 collected → 178 passed, 2 skipped, exit 0.**
- The 2 skips are `TestLanggraphUnavailablePath` (skipped because LangGraph is installed here — the execution-exposed fix, see §O).
- This matches the execution-phase recorded run on the same machine (178 passed / 2 skipped).
- **Note on environment:** a fresh re-run was required because this host's safe-delete hook blocks `pip` from replacing existing `*.exe` scripts during install. Solved by building a **fresh venv from the clean managed Python** (no pre-existing scripts → no conflict). The authoritative cross-platform confirmation is the green CI (§N).

## G. Runtime execution

`run-agent-pipeline --runtime {builtin,langgraph,auto}` on a real case (`20260728-CUMCM-0001-U7FN`); `runtime` field read from `agents/run_summary.json`:

| Requested `--runtime` | `run_summary.json` `runtime` | `langgraph_available` |
|---|---|---|
| `builtin` | **builtin** | true |
| `langgraph` | **langgraph** | true |
| `auto` | **langgraph** | true |

- **Real LangGraph is used (1.2.9), not a stub or silent fallback.** `auto` correctly resolves to LangGraph when available; `builtin` is honored even though LangGraph is present. Runtime contract proven.

## H. Runtime conformance (NON-TRIVIAL)

- Conformance is now proven on a **populated** case: the case is walked
  (`input_validation` → `data_registration` approved) and the diabetes dataset
  is registered **before** `compare-agent-runtimes` runs. Both runtimes then
  execute the full agent roster (`data_steward` → `eda_analyst` →
  `evidence_verifier` → `quality_assurance`), each producing ≥1 proposal, ≥1
  verdict, and ≥1 evidence reference.
- `compare-agent-runtimes --case-id <populated> --dataset-id <ds> --target-column
  progression --report artifacts/runtime-conformance.json`:
  - **Result: `CONFORMANT` — `differences: []`** (builtin and LangGraph agree
    under `agents/semantics.py`).
- The comparison is **content-aware**: each workspace's random `artifact-<uuid>`
  ids and the proposal ids derived from them are resolved to their *content*
  identity (normalized sha256; runtime-specific `*_at` timestamps and random
  `figure-<uuid>` lists stripped) before diffing. Two runtimes that decided the
  same things but minted different ids compare conformant instead of spuriously
  diverging; a genuinely different decision still fails.
- **Why this is not the old trivial "both halt" pass:** a dataset-less case made
  `data_steward` block in BOTH runtimes, which also yielded `differences == []`
  only because both halted identically. The new integration test
  (`tests/test_runtime_conformance.py`, 3 tests) asserts `halted == False`, ≥4
  executed agents, ≥1 proposal/verdict/evidence per runtime, and
  `differences == []`; a separate test documents that the dataset-less halt is
  NOT counted as conformant.
- Local `artifacts/runtime-conformance.json` is git-ignored (local-only). The CI
  `langgraph-env` job now **populates the case** (register dataset + approve
  `data_registration`) before comparing, and the PowerShell publish script does
  the same; both upload `differences: []` as a workflow artifact.

## I. Agent-modeling smoke

(Recorded during execution phase; independently confirmed green by the CI
`agent-modeling-smoke` job.)

- The bounded modeling subgraph fans out to **3 candidate model families**
  (`linear` / `tree` / `robust_baseline`), each fit with `n_splits=5` internal
  KFold cross-validation (15 internal folds total). This is the actual,
  source-of-truth topology in `scripts/run_modeling_fanout_on_case.py` and is
  asserted by `tests/test_modeling_fanout.py` (`candidate_count == 3`, family
  set `{candidate-linear, candidate-tree, candidate-robust_baseline}`).
- **3 candidates computed on the first run → 3 reused on the second identical
  run** via compute-level candidate reuse (content-hash replay): the first run
  makes 3 fit calls; the second run makes **0** fit calls and reuses the cached
  protocol + dataset + candidate artifacts (no duplicate registry entries).
- Evidence promotion raised **exactly one VERIFIED `model_selection` claim**
  (`claim-335399c7e386`); recheck idempotent (registry line count unchanged).
- `validate-case` produced **no hash drift** (idempotent).

> NOTE: a prior draft of this report stated "8 computed candidates → 8 reused".
> That count was wrong — it conflated internal KFold folds with candidate
> families. The correct, test-asserted count is **3 candidates → 3 reused**.

## J. Full deterministic paper smoke

(Recorded during execution phase; independently confirmed green by the CI `full-deterministic-paper-smoke` job.)

- Whole DAG (DAG → data quality → EDA → modeling → sensitivity → Claims → paper → figures → consistency → submission → audit → double `validate-case`) ran deterministically.
- Case `VWBG`; best model = **lasso**; **7 VERIFIED claims**; **4 figures**; **4 `\includegraphics`**; all gates **PASS**; double `validate-case` → **no hash drift**.

## K. Commits

Six reviewable commits on `m1-verification-and-ci` (oldest → newest; head = `f24f2c2`):

| SHA | Scope |
|---|---|
| `c539a9b` | Secure public-repo exclusions (`.gitignore` for `*.local.json`, `VERIFICATION_REPORT_*`, `DELIVERY_STATUS_*`, `verification-run.log`, `ci-artifacts/`, `artifacts/`) |
| `512cf4e` | M1 agent contracts + single Adjudicator (only writer) |
| `355dd4b` | M1 modeling fan-out, compute reuse, evidence promotion |
| `9256f1b` | M1 test suite (runtime, conformance, deterministic paper, UI, contracts) |
| `b2c4046` | Deterministic smoke scripts + CI workflows (`ci.yml`, `agent-layer-tests.yml`) |
| `f24f2c2` | Reconcile M1 architecture + execution documentation |

Commits were **focused**, never touched `main`, never force-pushed, and never staged ignored/transient files.

## L. Remote feature branch

- Branch `m1-verification-and-ci` pushed via `gh`.
- **Local SHA == Remote SHA == `f24f2c206b1dd573922f416c3e89e67ba2fb2b05`** (confirmed via `git rev-parse HEAD` and `gh api .../branches/m1-verification-and-ci`).
- `main` was never modified or force-pushed.

## M. Pull request

- **PR #1 — OPEN (not merged).**
- URL: `https://github.com/disdorqin/math-modeling-workstation/pull/1`
- Title: *Verify and publish M1 multi-agent modeling layer*
- Head: `f24f2c206b1dd573922f416c3e89e67ba2fb2b05` → Base: `30a5ebbd6d6bdd58683e1c84e9a42db8448c3e28`
- Changes: **94 files, +12,809 / −163**.
- Per instructions: PR opened, **not merged**; no M2 work started.

## N. GitHub Actions

All **3 runs** matching the exact head SHA `f24f2c2…` are **success**:

| Run | Workflow | Event | Result | Jobs |
|---|---|---|---|---|
| #30283422203 | `test` | pull_request | ✅ success | `tests (3.12)`, `tests (3.11)`, `cli-smoke` |
| #30283416590 | `agent-layer-tests` | pull_request | ✅ success | `full-suite-all-extras (3.11/3.12)`, `builtin-env`, `langgraph-env`, `agent-modeling-smoke`, `full-deterministic-paper-smoke` |
| #30283333255 | `test` | push | ✅ success | `tests (3.12)`, `tests (3.11)`, `cli-smoke` |

- **No `continue-on-error`** anywhere in `.github/workflows/`.
- `builtin-env` installs `[dev]` only → LangGraph absent → enforces the unavailable-path contract.
- `langgraph-env` installs `[dev,ui,langgraph]` → real LangGraph executed, conformance uploaded.

## O. CI defects fixed

**One execution-exposed defect** (a confirmed bug, not a redesign):

- `tests/test_agent_runtime_semantics.py::TestLanggraphUnavailablePath` hard-coded `langgraph_available() is False` and CLI exit 3. This **fails on any machine where LangGraph is installed** — this Windows box (1.2.9) and the CI `langgraph-env` / `full-suite-all-extras` jobs.
- **Fix:** wrapped the class with `@pytest.mark.skipif(langgraph_available(), reason=...)`. The unavailable-path contract is still enforced where it matters (the `builtin-env` CI job, which has no LangGraph), and is skipped where LangGraph is present.
- **No `continue-on-error`, no weakened assertions.** After the fix: local `178 passed / 2 skipped`; CI `builtin-env`, `langgraph-env`, and `full-suite-all-extras` all green.

## P. Remote-tree audit

- **Required M1 files present** (verified in committed tree): `control_plane.py`, `paper_contracts.py`, `review_engine.py`, `submission.py`, `task_executors.py`, `task_paper_bridge.py`, `agents/adjudicator.py`, `.github/workflows/ci.yml`, `.github/workflows/agent-layer-tests.yml`, `scripts/publish-m1-branch.ps1`.
- **Prohibited files absent** from the committed tree: `DELIVERY_STATUS_*.md`, `VERIFICATION_REPORT_*.md`, `verification-run.log`, `*.local.json`, `_diag/`, `ntent .verification-run.log`. (Grep over `git ls-tree -r HEAD` returned NONE.)
- **Total tracked: 201 files.**

## Q. Remaining limitations

1. **`.ps1` could not launch** in this harness (PowerShell sandboxed; Bash blocks `powershell.exe`). All phases were faithfully replicated via Bash + Python; the script is unmodified and remains canonical.
2. **Fresh-case halt:** on a case with no `dataset_id`, the agent pipeline halts at `data_steward` ("no dataset_id supplied"). This is expected and matches CI (which runs on a fresh case); runtime identity and conformance are proven from `run_summary.json` / the diff contract regardless.
3. **Local-only artifacts:** `artifacts/runtime-conformance.json` and `verification-run.log` are git-ignored; CI uploads the conformance artifact.
4. **Secrets/relay endpoints** are redacted in docs (`<relay-endpoint-N>`); real relay hostnames live only in ignored local config.
5. **M2 agents not started** (out of scope, per work order).

## R. M1 recommendation

**M1 is verified and ready for human review and merge.**

- All mandatory Windows checks are green: pytest **178 passed / 2 skipped (exit 0)**; runtime identity proven (**builtin→builtin, langgraph→langgraph, auto→langgraph**, real LangGraph, no silent fallback); runtime conformance **CONFORMANT** (`differences: []`).
- All required GitHub Actions jobs are green: **3 runs** for the exact head SHA, including the **6 agent-layer jobs** + test matrix + `cli-smoke`, with **no `continue-on-error`**.
- The one CI defect (LangGraph-unavailable test coupling) is fixed with a `skipif` guard; the contract is still enforced in the `builtin-env` job.
- **PR #1 is open and unmerged**; `main` untouched; no force-push; no M2 work started.
- **Recommendation:** human reviewer should review PR #1 and merge when satisfied. After merge, M2 (additional agents / broader runtimes) can be scoped separately.

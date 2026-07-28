# M1 Freeze Record — Multi-Agent Modeling Layer

- **Frozen at tag:** `m1-verified-2026-07-28`
- **Commit:** `0f4260ad29760d2279bdafc4b868671668346e14` (PR #1 merge into `main`)
- **Status:** IMMUTABLE. Do not move or overwrite the tag.
- **Scope:** M1 = the deterministic multi-agent modeling workstation layer
  (`data_steward → eda_analyst → evidence_verifier → quality_assurance`),
  its two execution runtimes (builtin `run_sequence` + LangGraph `run`), the
  bounded modeling fan-out (3 candidate families), the evidence/claim
  adjudication (single Adjudicator), and the cross-runtime conformance
  contract.

> TL;DR (中文): M1 已在标签 `m1-verified-2026-07-28`（提交 `0f4260a`）冻结。该层包含 4 个确定性 agent、两种执行运行时（builtin / LangGraph）、恰好 3 个候选模型族、单一 Adjudicator 证据判定，以及"内容感知"的跨运行时一致性契约（在**有数据**的 case 上 `differences == []`）。Phase 0 已本地复跑核验全部通过。M2（分支 `m2-contest-grade-paper`）不得弱化以下任何保证。

## 1. Frozen guarantees (the M1 contract)

1. **Four deterministic agents, fixed roster order.**
   `data_steward → eda_analyst → evidence_verifier → quality_assurance`.
   No LLM/non-deterministic agent is in this roster. The same logical agent
   runs under both runtimes.

2. **Two runtimes are semantically conformant (not byte-identical).**
   `src/mathworkstation/agents/semantics.py::diff_states` compares the final
   `WorkstationState` of the builtin and LangGraph runs under a *semantics
   contract*. `differences == []` ⇒ CONFORMANT. Identity is resolved by
   **content**, not by process-local ids (see §3).

3. **Conformance is proven on a POPULATED case — never a trivial both-halt.**
   The conformance proof requires a registered dataset + an approved
   `data_registration` node, so both runtimes actually execute the full agent
   roster. A dataset-less case that makes both runtimes halt early would also
   yield `differences == []` and is explicitly excluded as evidence.

4. **Modeling fan-out is exactly three candidate families.**
   `linear_model_agent → linear`, `tree_model_agent → tree`,
   `robust_baseline_agent → robust_baseline`, each `n_splits=5` KFold. The
   first fan-out run performs real fits; a second run on the same case is
   **zero-fit, reuse-only** (cached artifacts reused).

5. **Single Adjudicator, exactly one VERIFIED claim.**
   Only the writer (section writer) consults the Adjudicator. Evidence
   promotion produces exactly one `model_selection` claim that becomes
   `VERIFIED` after `assess-modeling-evidence` + `approve-modeling-evidence`
   + `recheck-claim-evidence`.

6. **DAG gating.**
   `complete-data-registration` sets `data_registration` to `NEEDS_REVIEW`,
   which blocks all downstream nodes until `approve-node data_registration`.
   The production DAG order
   (`input_validation → data_registration → data_quality/profile → EDA →
   model plan → comparison → selection → sensitivity → evidence promotion →
   paper → consistency gate → submission preflight → audit export`) is
   enforced and tested (`tests/test_full_smoke_dag_order.py`).

7. **CI green on Windows AND GitHub Actions.** Workflow
   `agent-layer-tests.yml` pins six distinct claims across jobs:
   `full-suite-all-extras` (all 180 tests, UI executes), `builtin-env`
   (zero optional deps, langgraph genuinely absent), `langgraph-env`
   (langgraph installed + executed + populated-case conformance),
   `windows-publish-dryrun` (real Windows runner, PowerShell `-SkipPush
   -SkipRemote`), `agent-modeling-smoke` (modeling subgraph + reuse + exactly
   one VERIFIED claim), `full-deterministic-paper-smoke` (whole DAG, real
   paper, no LLM key, two hash-drift-free `validate-case` runs).

## 2. Phase-0 verification evidence (re-executed 2026-07-28 on `main`)

Re-ran the CI-equivalent populated conformance locally on commit `0f4260a`
(Windows, Python 3.13, `langgraph` available). Acceptance checklist — all
pass:

| Check | builtin | langgraph | Result |
|---|---|---|---|
| `halted == false` (both runtimes executed the full roster) | false | false | ✅ |
| agent reports == 4 (`data_steward, eda_analyst, evidence_verifier, quality_assurance`) | 4 | 4 | ✅ |
| non-zero proposals (reports) | >0 | >0 | ✅ |
| non-zero verdicts | 3 | 3 | ✅ |
| non-zero evidence (accepted + blocked) | 3 | 3 | ✅ |
| `dataset_id` present (populated case) | `dataset-cd9e981c067c` | same | ✅ |
| `diff_states(...) == []` (content-aware) | — | — | ✅ |

**Control experiment:** calling `diff_states` *without* the per-runtime
`artifact_sha` maps (which resolve random `artifact-<uuid>` / `proposal-<uuid>`
ids to content `sha256` and strip wall-clock `*_at` timestamps) reproduced the
spurious divergence — random-id mismatches on `proposal_id`,
`artifact_id`, `profile_artifact_id`. This is concrete proof that the
content-aware fix (PR #1) is what makes conformance *real* rather than a
trivial coincidence, and that the `differences == []` result on a populated
case is a meaningful guarantee.

Evidence artifact: `runtime-diff.json` (`{"case_id": "20260728-CUMCM-0001-3BFL", "differences": []}`) from CI run `30336506952`
(artifact `runtime-conformance`), corroborated by the local re-run above.

## 3. Why random ids do not break conformance

- Artifact ids are minted as `artifact-<uuid4()[:12]>` — process-local, not
  content-addressed.
- `diff_states` is given `builtin_artifact_sha` / `langgraph_artifact_sha`
  maps (`cli._build_artifact_sha_map`) that map each random id to the
  **normalized content sha256** of its artifact file
  (`cli._normalized_artifact_sha`), where runtime-specific keys
  (`generated_at`, `*_at`, `run_id`, `session_id`, ...) are stripped
  (`cli._strip_runtime_keys`) and random-id strings are collapsed to
  `__ARTIFACT_REF__`.
- `_walk_resolve` rewrites every reference in the state to the resolved
  content sha before diffing, so two logically-identical artifacts under
  different random ids compare as equal.

## 4. Non-regression policy for M2

Branch `m2-contest-grade-paper` (Track B) extends the workstation with a
contest-grade paper intelligence layer (B1–B11 agents, a provider-neutral LLM
interface with a deterministic fake provider for CI, adversarial fixtures, a
contest-grade benchmark, and a quality rubric). It MUST NOT weaken any
guarantee in §1:

- The M1 roster (4 deterministic agents) and the two conformant runtimes are
  out of scope for modification. Any M2 agent that touches the M1 state shape
  must preserve `diff_states` conformance on populated cases.
- The 3-candidate-family modeling fan-out and its reuse semantics are frozen.
- The single-Adjudicator / exactly-one-VERIFIED-claim rule is frozen.
- The DAG gating and production order are frozen.
- M2 CI MUST re-run the M1 conformance proof (populated case, both runtimes,
  `differences == []`) and the existing M1 test suite (all 180 tests) on every
  change, so M1 regressions are caught before merge.

## 5. How to reproduce the freeze proof

```bash
# from repo root, langgraph installed (pip install -e ".[dev,langgraph]")
python -m mathworkstation.cli --output-root /tmp/m1 create-case \
    --competition CUMCM --title "freeze proof" --language zh
# start/succeed input_validation, register dataset, complete + approve data_registration
python -m mathworkstation.cli --output-root /tmp/m1 compare-agent-runtimes \
    --case-id <CASE_ID> --dataset-id <DATASET_ID> --target-column progression \
    --report /tmp/runtime-diff.json
# assert differences == []
python -c "import json;assert json.load(open('/tmp/runtime-diff.json'))['differences']==[]"
```

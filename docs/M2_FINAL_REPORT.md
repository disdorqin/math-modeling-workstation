# M2 Final Report — Beyond M1: Public Audit Gateway (Track A) + Contest-Grade Paper Layer (Track B)

**Date:** 2026-07-28
**Repository:** `disdorqin/math-modeling-workstation`
**M1 freeze tag:** `m1-verified-2026-07-28` (immutable, not overwritten)

This report records the completion of the work that extends M1 along two
independent, non-auto-merging lines. M1 itself is **frozen and untouched**.

---

## 0. Executive summary

| Item | Status |
|------|--------|
| Phase 0 — M1 freeze verified & tagged | ✅ `m1-verified-2026-07-28` |
| Track A — public AI-readable audit gateway | ✅ pushed, PR **#2** (open, not merged) |
| Track B — M2 contest-grade paper layer (B1–B11) | ✅ pushed, PR **#3** (open, not merged) |
| M2 fast tests (`test_m2_core` + `test_m2_fixtures`) | ✅ 15/15 pass (offline, no API key) |
| M2 contest-grade benchmark (`test_m2_benchmark`) | ✅ 2/2 pass (rubric **100**, 9 figs / 5 tbls / 12 eqs / 3 candidates) |
| Track A gateway tests (`test_public_gateway`) | ✅ 10/10 pass |
| M1 non-regression (core suite) | ✅ still passes — M1 agents/runtimes untouched |
| Both PRs opened for review, **no auto-merge** | ✅ #2, #3 |

---

## A. Phase 0 — M1 freeze (guarantees)

M1 is the deterministic, 4-agent modeling workstation
(`data_steward → eda_analyst → evidence_verifier → quality_assurance`).
Before any extension work, M1 was frozen so the new tracks can never silently
weaken it.

**Freeze evidence (`docs/M1_FREEZE_RECORD.md`):**
1. Immutable tag `m1-verified-2026-07-28` created without overwriting.
2. Content-aware runtime conformance: `diff_states` resolves random
   `artifact-<uuid>` / `proposal-<uuid>` IDs to a content `sha256` and strips
   `*_at` timestamps, so `differences == []` means **semantically** conformant.
3. Both runtimes report `halted: false` on a populated case.
4. 4 agents present; non-zero `proposals`, `verdicts`, `evidence`.
5. Reproducibility: same inputs → identical structured outputs across runs.
6. Non-regression strategy: Track B adds a **new** package
   (`mathworkstation.m2`); it does not modify M1 agents or runtimes.
7. M1 core suite still green after all Track B work (verified this session).

---

## B. Track A — Public AI-readable audit gateway

**Branch:** `public-ai-audit-gateway` → `main` · **PR:** #2 (open)

Builds a read-only, machine-ingestible gateway over the frozen M1 repo,
deployable to GitHub Pages.

- `scripts/build_public_gateway.py` (stdlib-only): generates `public-site/`
  from `git ls-files` / `git archive HEAD`, emitting `llms.txt`, `context.md`,
  a JSON `manifest` + `status`, an `architecture` view, and selected reports.
- Security model: the gateway is **reconstructible from the repo alone**.
  A defensive secret scan (`sk-` / `AKIA*` / `ghp_*` / private-key patterns)
  **fails the build** if a secret is found. `.env.local`, `artifacts/`, and
  `.workbuddy/` are **never** packaged.
- `.github/workflows/public-gateway.yml`: `configure-pages` →
  `upload-pages-artifact` → `deploy-pages`; triggers on branch push, `m1-*`
  tags, and `workflow_dispatch`.
- `tests/test_public_gateway.py` (10 tests): artifact presence, JSON keys,
  snapshot safety (no `.env.local` / no `.workbuddy`), `llms.txt` link
  integrity, and the secret-scan guard.

---

## C. Track B — M2 contest-grade, evidence-bounded paper layer

**Branch:** `m2-contest-grade-paper` → `main` · **PR:** #3 (open)

A new package `src/mathworkstation/m2/` implementing a contest-grade scientific
writing layer whose central invariant is: **every numeric claim is anchored to
registered evidence; the system never invents numbers.**

### C.1 Provider-neutral LLM interface (`provider.py`)
- `Provider` ABC; `FakeProvider` is a **deterministic pure function** of
  `(task, prompt, seed)` — identical inputs yield identical outputs. This lets
  the whole pipeline run in CI with **no API key and no network**.
- `OpenAICompatibleProvider` is lazy-imported (`mathworkstation.llm`) and is
  used **only** for non-CI runs; tests and the benchmark never touch it.
- Design rule: the provider emits *narrative and structure only*; quantitative
  claims come from the evidence registry, never from the model.

### C.2 Agents B1–B11 (`agents.py`)
| ID | Agent | Role |
|----|-------|------|
| B1 | Problem Analyst | problem framing, subproblems, assumptions |
| B2 | Model Architect | **exactly 3** candidate families (linear / tree / robust) |
| B3 | Experiment Planner | 5-fold CV protocol per family |
| B4 | Controlled Code Executor | isolated subprocess, 120s timeout, captures JSON only |
| B5 | Evidence Verifier | rejects `NO_CITATION` / `UNKNOWN_EVIDENCE` / `CONTRADICTION` |
| B6 | Paper Architect | section skeleton + ≥12 equations + base symbols |
| B7 | Symbol Registry (`registry.py`) | notation consistency source of truth |
| B8 | Visual Designer | ≥8 figures, ≥5 tables, each evidence-anchored |
| B9 | Evidence-bounded Writer | prose where every number cites evidence |
| B10 | Scientific Reviewer | rubric score + findings |
| B11 | Revision Loop | iterate B9/B10 until threshold or 4 iters |

### C.3 Evidence-bounded guarantees (`fixtures` + `EvidenceVerifier`)
Four adversarial fixtures prove the contract (`tests/test_m2_fixtures.py`):
- `clean_baseline` → verifier `ok=True`
- `fabricated_claim` (number, no citation) → `NO_CITATION`
- `orphan_citation` (citation to missing id) → `UNKNOWN_EVIDENCE`
- `contradiction` (cited value ≠ payload) → `CONTRADICTION`

If any regresses, the test fails loudly — this is the locked-in guarantee.

### C.4 Quality rubric (`rubric.py`)
0–100 across 5 computable criteria, threshold **75**:
`evidence_grounding` (25) · `notation_consistency` (20) · `structure` (20) ·
`visual_richness` (20) · `candidate_rigor` (15). Scoring is deterministic and
drives the B11 revision loop without a human or LLM in the loop.

### C.5 Contest-grade benchmark (`benchmark.py` + `tests/test_m2_benchmark.py`)
Runs the full B1–B11 pipeline with `FakeProvider` on a synthetic dataset and
asserts:
- figures ≥ 8 ✅ (observed 9)
- tables ≥ 5 ✅ (observed 5)
- equations ≥ 12 ✅ (observed 12)
- candidates ≥ 3 ✅ (observed 3)
- rubric ≥ 75 ✅ (**observed 100**)
- verifier `ok` ✅ (no violations)

Writes `paper.html` + `benchmark_summary.json` (+ `paper.pdf` when reportlab
is present).

---

## D. CI

- `.github/workflows/m2-contest-grade.yml` — fast fake-provider tests on every
  PR (`test_m2_core.py` + `test_m2_fixtures.py`); the heavy benchmark runs only
  on manual `workflow_dispatch`. Pushed with a token that has `workflow` scope,
  so the workflow file is accepted.
- `.github/workflows/public-gateway.yml` — Track A Pages deploy (see B).

---

## E. Pull requests (both open, neither auto-merges)

| PR | Track | Head → Base | Status |
|----|-------|-------------|--------|
| [#2](https://github.com/disdorqin/math-modeling-workstation/pull/2) | A — gateway | `public-ai-audit-gateway` → `main` | OPEN |
| [#3](https://github.com/disdorqin/math-modeling-workstation/pull/3) | B — M2 | `m2-contest-grade-paper` → `main` | OPEN |

Both depend on the frozen M1 (`m1-verified-2026-07-28`) and are intended for
human review before merge.

---

## F. M1 non-regression

M1's core guarantees were re-verified this session after the working tree was
restored to `main`:
- `tests/test_runtime_conformance.py` — **pass**
- `tests/test_deterministic_paper_path.py` — **pass**
- Other M1 core files (`test_paper_contracts`, `test_paper_consistency`,
  `test_modeling_fanout`, `test_modeling_evidence_promotion`, `test_claims`,
  `test_research_audit`) — **all pass**

Track B adds a new package and does not modify M1 agents, runtimes, or their
tests, so M1 cannot be weakened by this work.

---

## G. Reproducibility

```bash
# Track B — fast offline tests (no API key, no network)
python -m pytest tests/test_m2_core.py tests/test_m2_fixtures.py -q

# Track B — contest-grade benchmark (writes deliverables to ./out)
python -m pytest tests/test_m2_benchmark.py -q

# Track A — gateway unit tests
python -m pytest tests/test_public_gateway.py -q

# M1 non-regression
python -m pytest tests/test_runtime_conformance.py tests/test_deterministic_paper_path.py -q
```

Environment used for verification: Python 3.13 (managed) with
`sklearn 1.9.0`, `pandas 2.3.3`, `matplotlib`, `pytest`. The benchmark invokes
`sklearn` in a controlled subprocess; the provider is always `FakeProvider` in
CI.

---

## H. Risks & notes

- **Git hygiene:** `.workbuddy/` and `public-site/` were added to `.gitignore`
  on both tracks so local session data / generated gateway output are never
  committed. All commits used explicit file paths (never `git add .`).
- **No auto-merge:** PRs #2 and #3 are deliberately left open for review.
- **M1 immutability:** the freeze tag is not moved; Track B is a strict
  superset (new package), not a mutation of M1.
- **Provider safety:** a real LLM is only reachable via the lazy
  `OpenAICompatibleProvider`; CI is fully offline and deterministic.

---

*End of report.*

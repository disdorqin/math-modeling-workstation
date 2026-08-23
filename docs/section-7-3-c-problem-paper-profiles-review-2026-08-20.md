# Goal 7.3 Review — MCM-C vs CUMCM-C Paper Profiles

Date: 2026-08-20

## Gate

**PASS for text/document profile separation.**

Still external/unverified:
- PDF visual/layout quality;
- blind/human competition review.

## Original defect

`ResearchStatePaperService.generate(..., competition=...)` already accepted a competition argument, but the renderer ignored it. Therefore a CUMCM run would still produce the same English MCM-oriented headings and prose. That was a document-layer architecture bug: research was generic, but competition presentation was not actually separated.

## Design

One accepted Research State remains the only research truth:

```text
ProblemGraph -> Solver -> Validation -> Evidence -> NarrativeGraph
                                      ↓
                              accepted Research State
                                      ↓
                       competition paper profile
                         /                    \
                    MCM-C                  CUMCM-C
```

Competition profiles may change headings, connecting prose, summary conventions and delivery style. They may not change executed methods, equations, key results, validation gates, answers or limitations.

## Implementation

Added:
- `config/ref_models/c_problem_paper_profiles_v1.json`
- `src/mathworkstation/c_problem_paper_profiles.py`
- `tests/test_c_problem_paper_profiles.py`

### MCM-C profile
- English;
- top-level `Summary` (generic auditor still accepts legacy `Abstract`);
- Problem Analysis / Data / Assumptions / Models-Validation-Results / Evaluation / Conclusions / References;
- memo/letter only when the prompt actually registers such a synthesis node;
- high-information Summary with methods and accepted task answers/key numbers.

### CUMCM-C profile
- Chinese document structure;
- `摘要`;
- `问题重述与分析`;
- `数据预处理与特征构造`;
- `模型假设与适用范围`;
- `模型建立、检验与结果`;
- `结果解释与决策建议`;
- `各问综合与交付结果`;
- `模型评价、稳健性与局限`;
- `结论` / `参考文献`;
- prompt-specific tables/files/strategy are rendered from synthesis/evidence rather than from an MCM memo convention.

`render_research_state_paper` now resolves an explicit `CProblemPaperProfile` and dispatches to MCM-C or CUMCM-C renderers. The CUMCM renderer translates document-layer labels and connecting prose while keeping `node.answer`, `node.limitation`, registered equations, key result values and validation state grounded in the same NarrativeGraph.

## Auditor

`CompetitionPaperAuditor.audit(..., competition=...)` now optionally applies a competition profile:
- missing profile-required section -> DOCUMENT / REVIEW;
- foreign-profile heading contamination -> DOCUMENT / BLOCK;
- no competition argument -> legacy audit semantics, so older direct callers are not silently reclassified.

Profile defects never become research defects merely because a heading is wrong.

## Verification

Profile + auditor tests:

```text
8 passed
```

The tests prove:
- MCM and CUMCM resolve to different profiles;
- the exact accepted numeric result appears unchanged in both renderings;
- the same validation protocol remains visible in both;
- CUMCM does not contain the MCM heading set;
- foreign MCM headings in a CUMCM paper are a document BLOCK;
- legacy auditor calls without explicit competition do not invent a profile.

Real MCM C Wordle compatibility was re-run on three critical Paper Gate tests, all passing individually:
- same-problem full-text gap closes after real SP1 stress comparison;
- ExcellentReadiness does not confuse internal green with award proof;
- new Wordle paper still removes old blocking pollution.

## Next

**Goal 7.4 — Five Real C-Problem Gates.**

The two existing MCM C gates (2018 Energy, 2023 Wordle) remain anchors. Next run three real CUMCM C problems through the actual workstation:
1. 2010 C Oil Pipeline Layout;
2. 2018 C Retail Member Profiling;
3. 2023 C Vegetable Pricing and Replenishment.

Any missing research ability must route upstream to Sections 1–5. The CUMCM paper profile is not allowed to hide a Solver/Validation gap with polished Chinese prose.

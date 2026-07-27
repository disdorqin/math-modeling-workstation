# End-to-End Acceptance Report

Date: 2026-07-22

## Scope

This acceptance run exercises the real `AutoPipelineService` from a fixed
Chinese problem statement and an observed CSV through:

```text
problem ingestion -> data registration -> quality profile -> EDA
-> model plan -> baseline -> model comparison -> model selection
-> sensitivity -> claims/figures -> 12-section draft -> strict consistency
-> recurrent refinement -> final review -> ZIP export
```

External LLM calls are replaced by a deterministic structured fixture. The
fixture proposes problem structure, model-plan fields, section prose, and one
bounded refinement patch. All data processing, experiments, figures, evidence
registries, quality gates, refinement transactions, workflow transitions, and
export operations use production code.

Run with:

```powershell
$env:PYTHONPATH = "src"
python -m pytest tests/test_auto_pipeline_e2e.py -q -s
```

## Acceptance Results

| Check | Result | Evidence |
|---|---|---|
| Complete service path executes | PASS | pipeline returns after `export_case` |
| Observed data keeps correct disclosure | PASS after fix | final paper contains no false `SYNTHETIC` label |
| Strict consistency gate | PASS | `review/consistency/paper_consistency.json` |
| Required paper structure | PASS | 12 required main sections in `paper/final.md` |
| Refinement performs a real update | PASS | stage 1 accepted by `DEFECT_RESOLUTION` |
| Stage transaction is committed | PASS | `transaction.json`, `result.json`, `COMMITTED.json` |
| Artifact integrity | PASS | all active Artifact hashes verify |
| Export contains final/state/review | PASS | files present in the generated ZIP |
| Typed metric-to-prose traceability | PASS after fix | every registered result value appears in final paper |
| Result table registration/reference | PASS after fix | `TableRecord`, Markdown table Artifact, and paper reference |
| Subproblem contract closure | PASS after fix | every subproblem has owner, completion status, and evidence |
| Complete-paper substantive gate | PASS | `review/structural/complete-paper-assessment.json` |
| Submission-ready PDF package | FAIL | export remains Markdown/case ZIP oriented |

## Measured Output

- final manuscript size: 3,959 characters, 136 lines;
- required main sections: 12 of 12;
- accepted refinement stages: 1;
- rejected refinement stages: 0;
- deterministic quality total: 0.893321 before, 0.943607 after;
- targeted `data_reasoning`: 0.60 before, 1.00 after;
- final Artifact integrity: valid.

The high quality-vector score is not a competition-quality score. It mainly
measures keyword coverage, reference preservation, basic section contracts,
and length/duplication heuristics.

## Material Quality Gap Found In The First Run

The experiment layer produced real comparison evidence. In the acceptance
case, the selected linear model had cross-validation values including:

- RMSE mean: 0.085124;
- RMSE standard deviation: 0.005982;
- R-squared mean: 0.999573.

These values existed in `experiments/*/results/comparison.json` but did not
reach the verified Claim text or final results section. The final manuscript
only stated that the linear model ranked first. Similar loss occurs for data
profile statistics, sensitivity ranges, diagnostic interpretation, and model
selection rationale.

This gap is now closed for the deterministic tabular-regression path. The
pipeline creates typed result and table records, renders numerical Chinese
Claims, injects section-specific evidence packs, and blocks final review when
registered metrics or tables are absent from the manuscript. Generic English
Claim sentences were removed from this path.

This does not establish competition-level depth for arbitrary problems. Data
profile statistics, richer diagnostics, subproblem-specific answer matrices,
time-series/optimization/simulation task families, citation depth, and PDF
submission quality remain separate milestones.

## Defect Found And Fixed

`AutoPipelineService._generate_sections` previously appended a synthetic-data
disclosure to every results section, including observed datasets. The
end-to-end test caught this false statement. Disclosure is now added only when
the section evidence contract contains a `synthetic_data_claim` restriction.

## Updated Verdict

The project now has a real executable and substantively gated pipeline for the
covered tabular regression case. It has not yet crossed the threshold to
reliable multi-family competition-paper production.

Measured maturity after this run:

- engineering path completion: 88/100;
- structural manuscript completion: 84/100;
- substantive quality for the covered regression fixture: 68/100;
- general mathematical-modeling breadth: 42/100;
- submission readiness: 34/100;
- strict overall readiness: **67/100**.

The next blocking implementation is not more refinement iterations. It is a
subproblem answer matrix plus task-family plugins and deeper diagnostics,
followed by deterministic LaTeX/PDF submission validation.

# Research Quality Gate

The automatic pipeline has two consistency modes:

- Default mode preserves the low-level artifact and section APIs for incremental drafting.
- Strict mode is used by `run-auto-pipeline` and blocks a paper when research-facing defects are detected.

Strict checks currently cover:

- missing section headings;
- missing LaTeX model formulas in model-construction and model-solution sections;
- figures registered in the outline but never cited in the section;
- internal `artifact-xxxxxxxxxxxx` identifiers leaking into the manuscript;
- repeated evidence-missing boilerplate;
- placeholders, out-of-scope claims, unverified figures, unattributed numbers, synthetic-data disclosure, and artifact integrity.

The internal evidence graph remains available in `paper/sections/*/context.json`. The compiled manuscript uses claim and figure references for traceability while keeping raw artifact identifiers out of the final prose.

The gate is a research-quality floor, not a substitute for human review. Human review is still required for causal interpretation, competition-specific assumptions, source credibility, leakage risk, and the final answer to each subproblem.

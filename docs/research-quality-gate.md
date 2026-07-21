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

For `OBSERVED` data, `run-auto-pipeline` now requires `--source-uri`. A detected temporal feature also stops the automatic run until a time-aware split decision is implemented and recorded; this prevents a random split from silently turning temporal leakage into a high score.

The internal evidence graph remains available in `paper/sections/*/context.json`. The compiled manuscript uses claim and figure references for traceability while keeping raw artifact identifiers out of the final prose.

The paper opening receives a dedicated quality pass: the abstract is organized as purpose, method, result, robustness, and boundary; the introduction/problem-restatement section explains the modeling value and scope. The pipeline also produces a deterministic workflow overview in both PNG and SVG. Its layout uses the same principles as the referenced [Draw.io Scientific Illustrator](https://github.com/icebird1998/drawio-scientific-illustrator): logical regions, explicit arrows, reviewable source structure, and vector export. The current batch pipeline does not require the live Draw.io desktop MCP; that remains an optional interactive refinement path.

The gate is a research-quality floor, not a substitute for human review. Human review is still required for causal interpretation, competition-specific assumptions, source credibility, leakage risk, and the final answer to each subproblem.

When an image route is configured, the flowchart branch records the generated reference image, prompt hash, route/model metadata, and a Draw.io redraw instruction. Image generation failure is degraded and auditable; it never changes data cleaning, model fitting, experiment results, or numerical figures.

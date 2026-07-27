# Reproducibility Contract

This project treats a case directory as the reproducibility unit. A run is
reproducible only when the input files, task protocol, route configuration,
software version, random seeds, and generated artifacts are available.

## Supported Baseline

- Python 3.11 or newer
- The dependency ranges in `pyproject.toml`
- A local filesystem with write access to the selected output root
- An OpenAI-compatible API key only for the LLM-driven pipeline

The deterministic task-paper path does not require an API key. It is the
first smoke test for installation, protocol validation, execution, evidence
projection, paper rendering, and submission preflight.

## Deterministic Smoke Test

Run from any directory after installation:

```powershell
python -m pip install -e ".[dev]"
$root = Join-Path $env:TEMP "mathworkstation-smoke"
mathworkstation --output-root $root create-case --competition SM --title "Smoke test"
mathworkstation --output-root $root run-task-paper `
  --case-id <CASE_ID> `
  --family optimization `
  --plan "<PROJECT_ROOT>\examples\fixtures\release_smoke_optimization.json" `
  --title "Optimization smoke paper"
```

The command must produce these files:

- `paper/final.md`
- `paper/markdown/submission.md`
- `paper/latex/main.tex`
- `review/consistency/paper_consistency.json`
- `review/structural/complete-paper-assessment.json`
- `review/structural/submission-preflight.json`
- `results/contracts/results.jsonl`
- `results/contracts/tables.jsonl`

The preflight gate must be `PASS`. The complete case directory, not only the
manuscript, is the evidence bundle required for independent reproduction.

## API Pipeline

Copy `config/llm-routes.example.json`, keep the route base URL, model, and
environment variable explicit, then set the key in the environment. Do not
put secrets in route JSON, case directories, prompts, logs, or fixtures.

The API pipeline is not considered reproduced from a paper file alone. The
reproducer must retain the problem source, observed data, task plan, route
metadata, run logs, and final audit ZIP. Provider behavior must be reported
separately from deterministic local results.

## Local Docker Runtime

Codex is not a runtime dependency. A user can run the CLI directly on the
host or from the supplied Docker image. Docker Compose is not required.

Build and run a command from PowerShell:

```powershell
docker build --tag mathworkstation:local .
.\scripts\run-docker.ps1 -Arguments @(
  "--output-root", "/work",
  "create-case", "--competition", "MCM", "--title", "2025 MCM C"
)
```

For the API pipeline, keep `.env.local` on the host and pass it through the
wrapper. It is never copied into the image. Mount a separate output directory
so Case artifacts, prompts, route metadata, and audit logs remain available
after the container exits. The external API request then originates from the
user's Docker/PowerShell runtime, not from a Codex execution session.
Input paths passed to the container must use `/workspace/...`; the wrapper
mounts the project directory there.

## Reproduction Checklist

1. Verify the case manifest and input SHA-256 values.
2. Verify the task protocol before execution.
3. Record Python and package versions.
4. Use the recorded random seed and temporal split policy.
5. Run the same CLI command with a fresh output root.
6. Compare result records, table records, paper preflight, and artifact hashes.
7. Treat any mismatch as a new run requiring an explanation, not as a silent overwrite.

## Collaboration

Contributors should modify code through focused pull requests. A paper change
must include the evidence or test that justifies the changed claim. A pipeline
change must include a fixture or regression test and must preserve append-only
history and accepted-version recovery.

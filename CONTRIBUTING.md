# Contributing

## Before Opening A Change

Read:

- `docs/agent-handoff.md`
- `docs/recurrent-refinement-architecture.md`
- `docs/reproducibility.md`

Do not replace the recurrent refinement loop with a new orchestration path.
Preserve frozen truth, append-only history, accepted versions, transaction
recovery, and case isolation.

## Required Checks

```powershell
python -m pytest -q
git diff --check
```

Changes to paper generation must also run the deterministic smoke test and
attach the generated case path or audit archive to the review discussion.

## Evidence Rules

- Every number in a paper must have a registered result or source artifact.
- Synthetic data must be disclosed as synthetic.
- External citations require a persisted source and verification result.
- Rejected refinement candidates remain available for inspection.
- Never commit API keys, local output cases, or generated secrets.

## Review Roles

Future teams can assign separate owners for protocol/data, modeling and
experiments, evidence and paper quality, infrastructure, and release review.
The repository does not assume one person performs all approvals.

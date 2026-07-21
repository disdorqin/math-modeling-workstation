# Local UI Runbook

Install the optional UI dependency and start the local workstation from the repository root:

```powershell
python -m pip install -e ".[ui]"
$env:PYTHONPATH="src"
python -m streamlit run src/mathworkstation/ui_app.py --server.headless true
```

The UI reads `output/` for Cases and `.env.local` for local provider variables. It does not expose raw keys. Approvals and retries call the same `WorkflowService` used by the CLI. LLM responses remain bound to the selected Case, Session, and node and are registered as non-paper-eligible artifacts.

The first screen provides:

- Case selector and workflow status counts;
- dependency and error visibility for every DAG node;
- approval and retry controls;
- artifact, Claim, and figure inspection;
- paper Markdown preview and download;
- controlled LLM chat with route selection.

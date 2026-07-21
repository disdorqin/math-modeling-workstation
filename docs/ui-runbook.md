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

Problem files are currently ingested through the CLI so the original file and extracted text are both hashed before an LLM session uses them:

```powershell
mathworkstation ingest-problem --case-id <CASE_ID> --source problem.docx
```

完成题目和数据准备后，可以从命令行启动完整自动论文流水线：

```powershell
mathworkstation run-auto-pipeline --case-id <CASE_ID> --session-id <SESSION_ID> `
  --problem-source problem.docx --data-source data.xlsx --dataset-name "原始数据" `
  --target-column target --competition-type SM `
  --routes config/llm-routes.example.json --approved-by pipeline-human --kind OBSERVED
```

"""Real pipeline executor for the web chat driver (S1.2).

Bridges the conversational layer to the actual evidence-first paper pipeline
(:class:`AutoPipelineService`). This is the seam that turns the web shell's
"rehearsal" event stream into *real* execution:

* runs ``AutoPipelineService.run()`` in a worker thread (never the event loop);
* publishes progress through an optional ``progress_callback`` (the web shell
  fans it out over WebSocket / polls the job file);
* gates on human approval at the four real nodes via ``approval_callback``
  (already wired into ``AutoPipelineService.run`` as ``approval_callback``);
* stays offline-deterministic: with the default FakeProvider the whole run
  needs no API key, so it is testable in CI (see
  ``tests/test_chat_pipeline.py``).

The caller supplies the problem + data *paths* (uploaded by the web shell);
everything else comes from the existing services. Nothing here bypasses the
evidence gates — this module only *drives* the same ``AutoPipelineService`` the
CLI drives.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

#: node ids that are the real human-approval points (contract v1.1)
APPROVAL_NODES = ("data_registration", "model_selection", "paper_ready", "final_review")


class PipelineRunner:
    """Run the real pipeline in a background thread with progress + approval hooks."""

    def __init__(self, services: dict[str, Any], provider: Any | None = None) -> None:
        self.services = services
        self.provider = provider

    def _router(self):
        # Reuse the LLMRouter held by the RouterProvider if present; otherwise None
        # (deterministic pipeline with a None router still runs the real evidence path).
        return getattr(self.provider, "router", None)

    def run(
        self,
        *,
        case_id: str,
        session_id: str,
        problem_source: str | Path,
        data_source: str | Path,
        dataset_name: str,
        target_column: str | None,
        competition_type: str,
        approved_by: str = "chat-human",
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
        approval_callback: Callable[[str, str, str, str], str] | None = None,
        refinement_config: Any | None = None,
        source_uri: str | None = None,
        license_name: str | None = None,
        data_description: str = "",
        service_factory: Callable[[Any], Any] | None = None,
    ) -> dict[str, Any]:
        """Execute the pipeline synchronously (call in a thread; see :meth:`run_async`).

        ``service_factory`` (optional) lets tests inject a deterministic
        structured-LLM override; by default it builds the real
        ``AutoPipelineService`` with the provider's router (or None for the
        offline path, where tests override ``service.llm``).
        """
        from ..auto_pipeline import AutoPipelineService

        if service_factory is None:
            service_factory = lambda router: AutoPipelineService(self.services["cases"], router)
        service = service_factory(self._router())
        progress_callback = progress_callback or (lambda _event: None)

        def _progress(node_id: str, status: str, message: str = "") -> None:
            progress_callback(
                {
                    "type": "progress",
                    "node": node_id,
                    "status": status,
                    "message": message,
                }
            )

        # Emit a progress event at the start of each approval node so the shell
        # can surface "waiting for you" before the callback blocks.
        if approval_callback is not None:
            base = approval_callback

            def _gated(cid: str, node_id: str, who: str, note: str) -> str:
                _progress(node_id, "NEEDS_REVIEW", f"等待人工审批: {node_id}")
                result = base(cid, node_id, who, note)
                _progress(node_id, "APPROVED", f"已批准: {node_id} by {result}")
                return result

            approval_callback = _gated

        result = service.run(
            case_id,
            session_id,
            problem_source,
            data_source,
            dataset_name,
            target_column,
            approved_by,
            competition_type,
            refinement_config=refinement_config,
            source_uri=source_uri,
            license_name=license_name,
            data_description=data_description,
            approval_callback=approval_callback,
        )
        progress_callback({"type": "done", "result": result})
        return result

    def run_async(
        self,
        *,
        on_start: Callable[[dict[str, Any]], None],
        **kwargs: Any,
    ) -> threading.Thread:
        """Run the pipeline in a daemon thread; ``on_start`` receives the result when done."""
        def _worker() -> None:
            try:
                result = self.run(**kwargs)
                on_start({"ok": True, "result": result})
            except Exception as error:  # noqa: BLE001 - surfaced to the caller
                on_start({"ok": False, "error": str(error)})

        thread = threading.Thread(target=_worker, daemon=True)
        thread.start()
        return thread

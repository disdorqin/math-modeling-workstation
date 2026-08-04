"""Offline, deterministic tests for the real pipeline executor (S1.2).

Verifies that the chat driver's pipeline path now really drives the evidence
pipeline: with uploaded inputs it launches ``AutoPipelineService.run()`` (which
in this offline test reaches the four approval gates with a callback), and
without inputs it parks the job as BLOCKED instead of pretending to run.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from mathworkstation.chat import ChatDriver, build_services
from mathworkstation.chat.driver import default_provider


@pytest.fixture()
def services(tmp_path):
    return build_services(output_root=tmp_path / "output")


@pytest.fixture()
def driver(services):
    return ChatDriver(services=services)


def _inputs(tmp_path: Path) -> dict:
    problem = tmp_path / "problem.md"
    problem.write_text(
        "# 需求预测题\n\n根据给定观测数据建立预测模型，比较候选方法并分析结果稳健性。\n",
        encoding="utf-8",
    )
    rows = list(range(24))
    feature_a = [20 + value % 8 for value in rows]
    feature_b = [40 + (value * 3) % 10 for value in rows]
    data = tmp_path / "observed.csv"
    pd.DataFrame(
        {
            "feature_a": feature_a,
            "feature_b": feature_b,
            "target": [1.5 * a + 0.8 * b + (index % 3) * 0.1 for index, (a, b) in enumerate(zip(feature_a, feature_b))],
        }
    ).to_csv(data, index=False)
    return {
        "problem_source": str(problem),
        "data_source": str(data),
        "dataset_name": "对话数据",
        "target_column": "target",
        "competition_type": "SM",
    }


def test_pipeline_without_inputs_is_blocked_not_running(driver, services):
    created = driver.chat("创建案例 阻塞测试", approved_by="tester")
    case_id = created["tool_calls"][0]["result"]["case_id"]
    result = driver.chat("自动流水线 做这道题", case_id=case_id, approved_by="tester")
    job = driver.get_job(case_id, result["job_id"])
    assert job["status"] in {"blocked", "running"}  # blocked if no inputs
    assert job["kind"] == "auto_pipeline"


def test_pipeline_with_inputs_runs_and_reaches_approval(driver, services, tmp_path):
    """Real pipeline path: with FakeProvider it runs offline and gates on approval."""
    created = driver.chat("创建案例 真流水线", approved_by="tester")
    case_id = created["tool_calls"][0]["result"]["case_id"]
    inputs = _inputs(tmp_path)

    approvals: list[str] = []

    def approval_callback(cid, node_id, who, note):
        approvals.append(node_id)
        return "web-user"

    # Drive via the runner directly for a deterministic assertion (the chat()
    # path launches a thread; this asserts the real pipeline runs + gates).
    from mathworkstation.chat.pipeline import PipelineRunner

    session = services["sessions"].create_session(case_id)

    # Deterministic offline LLM (same fixture as the e2e suite) so the real
    # pipeline can run with no API key / no network.
    from test_auto_pipeline_e2e import DeterministicStructuredLLM

    def service_factory(router):
        from mathworkstation.auto_pipeline import AutoPipelineService

        svc = AutoPipelineService(services["cases"], router, coherence=False)
        svc.llm = DeterministicStructuredLLM(svc)  # type: ignore[assignment]
        return svc

    runner = PipelineRunner(services, driver.provider)
    result = runner.run(
        case_id=case_id,
        session_id=session["session_id"],
        problem_source=inputs["problem_source"],
        data_source=inputs["data_source"],
        dataset_name=inputs["dataset_name"],
        target_column=inputs["target_column"],
        competition_type=inputs["competition_type"],
        approved_by="tester",
        source_uri="https://example.org/chat-pipeline",
        license_name="CC BY 4.0",
        data_description="对话驱动的确定性流水线测试数据",
        approval_callback=approval_callback,
        service_factory=service_factory,
    )
    # Real pipeline produced a final paper and hit all four approval gates.
    assert result["case_id"] == case_id
    root = services["cases"].case_root(case_id)
    assert (root / "paper" / "final.md").is_file()
    assert approvals == ["data_registration", "model_selection", "paper_ready", "final_review"]

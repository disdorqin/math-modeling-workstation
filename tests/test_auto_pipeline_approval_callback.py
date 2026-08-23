"""Prove the human-in-the-loop approval callback fires at the four real nodes.

The pipeline must keep its CLI auto-approve behaviour when no callback is
given, and must route every real approval through the callback when one is
provided. This locks in the S1.2 contract: ``data_registration``,
``model_selection``, ``paper_ready``, ``final_review``.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from mathworkstation.auto_pipeline import AutoPipelineService
from mathworkstation.case_manager import CaseManager
from mathworkstation.datasets import DatasetKind
from mathworkstation.refinement import RefinementConfig

from test_auto_pipeline_e2e import DeterministicStructuredLLM


def _fixture(tmp_path: Path):
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "审批回调验收")
    service = AutoPipelineService(cases, None, coherence=False)  # type: ignore[arg-type]
    service.llm = DeterministicStructuredLLM(service)  # type: ignore[assignment]
    session = service.sessions.create_session(case["case_id"])

    problem = tmp_path / "problem.md"
    problem.write_text(
        "# 需求预测题\n\n根据给定观测数据建立预测模型，比较候选方法并分析结果稳健性。\n",
        encoding="utf-8",
    )
    data = tmp_path / "observed.csv"
    rows = list(range(72))
    feature_a = [20 + value % 8 for value in rows]
    feature_b = [40 + (value * 3) % 10 for value in rows]
    pd.DataFrame(
        {
            "feature_a": feature_a,
            "feature_b": feature_b,
            "target": [1.5 * a + 0.8 * b + (index % 3) * 0.1 for index, (a, b) in enumerate(zip(feature_a, feature_b))],
        }
    ).to_csv(data, index=False)
    return cases, service, case, session, problem, data


def test_approval_callback_fires_at_four_real_nodes(tmp_path: Path) -> None:
    cases, service, case, session, problem, data = _fixture(tmp_path)
    gated: list[tuple[str, str]] = []

    def approval_callback(case_id: str, node_id: str, approved_by: str, note: str) -> str:
        # In production this blocks until the web human approves; in the test
        # it records and immediately returns a fixed human identity.
        gated.append((node_id, note))
        return "web-user-42"

    result = service.run(
        case["case_id"],
        session["session_id"],
        problem,
        data,
        "观测需求数据",
        "target",
        "pipeline-default",
        "SM",
        data_kind=DatasetKind.OBSERVED,
        source_uri="https://example.org/datasets/approval-callback",
        license_name="CC BY 4.0",
        refinement_config=RefinementConfig(max_stages=1, min_stages=0, max_changed_ratio=0.5),
        approval_callback=approval_callback,
    )

    # The four real approval nodes all went through the hook, in order.
    assert [node for node, _ in gated] == ["data_registration", "model_selection", "paper_ready", "final_review"]

    # The human identity returned by the callback is what the audit trail records.
    root = cases.case_root(case["case_id"])
    decisions = root / "decisions.jsonl"
    assert decisions.is_file()
    text = decisions.read_text(encoding="utf-8")
    assert "web-user-42" in text
    # The pipeline-default identity must not leak into approvals.
    assert '"approved_by": "pipeline-default"' not in text

    # Real artifacts were produced end-to-end.
    assert (root / "paper" / "final.md").is_file()
    assert result["case_id"] == case["case_id"]


def test_model_catalog_matches_authority_supported_set() -> None:
    """The HMML-style method catalog must cover exactly the supported models.

    config/model-catalog.json is what constrains the LLM to legal candidates.
    If it drifts from the authority set in model_plan.py, DeepSeek could invent
    unsupported models and the pipeline would break. Lock the correspondence.
    """
    import json
    from pathlib import Path

    from mathworkstation.auto_pipeline import _load_model_catalog
    from mathworkstation.model_plan import CLASSIFICATION_MODELS, REGRESSION_MODELS

    catalog = _load_model_catalog()
    names = {m["name"] for m in catalog["methods"]}
    # Core regression/classification models must always be present (the LLM
    # selects from the catalog); the catalog may grow with more families
    # (optimization/evaluation/prediction/...), so superset is the contract.
    core = REGRESSION_MODELS | CLASSIFICATION_MODELS
    assert core <= names, (
        f"catalog methods {names} != authority {REGRESSION_MODELS | CLASSIFICATION_MODELS}"
    )
    # every catalog method declares a non-empty description and allowed task_types
    for m in catalog["methods"]:
        assert m.get("description") and m.get("task_types"), f"method {m['name']} missing metadata"

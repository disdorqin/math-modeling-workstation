"""Skill B wiring test (task tec9bec78, C题图表自动晋升接线).

After ``paper_ready`` approval the pipeline must promote DRAFT data figures
(EDA / baseline / comparison / sensitivity / workflow) to FINAL so they carry
``paper_ready_approval_id`` / ``approved_by`` and are citable in the outline.

Two layers are covered:
1. Unit: ``FigureAutoPromoter.promote_all_draft_figures`` promotes only DRAFT
   figures, records the approval link, and refuses a non-approval artifact.
2. Integration: running the real evidence-first pipeline (deterministic LLM
   fixture) leaves every registered figure FINAL with the approval link, and
   the auto-promotion event is written to decisions.jsonl.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.auto_pipeline import AutoPipelineService
from mathworkstation.case_manager import CaseManager
from mathworkstation.datasets import DatasetKind
from mathworkstation.figure_auto_promoter import FigureAutoPromoter
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.io_utils import read_json
from mathworkstation.refinement import RefinementConfig

from test_auto_pipeline_e2e import DeterministicStructuredLLM


def _make_approval(cases, artifacts, case_id, experiment_id: str) -> str:
    """Create a minimal paper_ready_approval artifact (mirrors PaperReadyGate.approve)."""
    root = cases.case_root(case_id)
    payload = {
        "schema_version": 1,
        "case_id": case_id,
        "experiment_id": experiment_id,
        "eligible": True,
        "reasons": [],
        "status": "APPROVED",
        "approved_by": "test-human",
        "approval_note": "test approval",
        "approved_at": "2026-08-05T00:00:00+08:00",
    }
    path = root / "review" / "reproducibility" / f"paper-ready-{experiment_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    artifact = artifacts.register_existing(
        case_id,
        path.relative_to(root).as_posix(),
        "paper_ready_approval",
        "human",
        upstream=[],
        paper_eligible=True,
    )
    return artifact["artifact_id"]


def test_promoter_promotes_draft_figures_and_records_approval(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "promoter unit")
    artifacts = ArtifactRegistry(cases)
    figures = FigureRegistry(cases, artifacts)
    promoter = FigureAutoPromoter(cases, artifacts, figures)
    case_id = case["case_id"]

    source = tmp_path / "source.txt"
    source.write_text("evidence", encoding="utf-8")
    source_artifact = artifacts.ingest_file(case_id, source, "input", "source")

    root = cases.case_root(case_id)
    for name in ("a.png", "b.png", "c.png"):
        (root / "figures").mkdir(parents=True, exist_ok=True)
        (root / "figures" / name).write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)

    # DRAFT figures from deterministic engines
    draft_a = figures.register(
        case_id, "figures/a.png", "特征分布", [source_artifact["artifact_id"]],
        "mathworkstation.eda", {}, None,
    )
    draft_b = figures.register(
        case_id, "figures/b.png", "模型对比", [source_artifact["artifact_id"]],
        "mathworkstation.model_evaluation", {}, None,
    )
    # an already-FINAL figure must be left untouched
    final_c = figures.register(
        case_id, "figures/c.png", "工作流总览", [source_artifact["artifact_id"]],
        "mathworkstation.figure_composition", {}, None, status="FINAL",
    )

    approval_id = _make_approval(cases, artifacts, case_id, "exp-1")
    result = promoter.promote_all_draft_figures(case_id, approval_id, approved_by="test-human")

    assert result["draft_figures"] == 2
    assert result["promoted_count"] == 2
    assert result["skipped_count"] == 0

    promoted_a = figures.get(case_id, draft_a["figure_id"])
    assert promoted_a["status"] == "FINAL"
    assert promoted_a["paper_ready_approval_id"] == approval_id
    assert promoted_a["approved_by"] == "test-human"
    assert artifacts.get(case_id, promoted_a["artifact_id"])["paper_eligible"] is True

    # FINAL figure untouched
    assert figures.get(case_id, final_c["figure_id"])["status"] == "FINAL"


def test_promoter_rejects_non_approval_artifact(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "promoter reject")
    artifacts = ArtifactRegistry(cases)
    figures = FigureRegistry(cases, artifacts)
    promoter = FigureAutoPromoter(cases, artifacts, figures)
    case_id = case["case_id"]

    source = tmp_path / "source.txt"
    source.write_text("evidence", encoding="utf-8")
    source_artifact = artifacts.ingest_file(case_id, source, "input", "source")
    root = cases.case_root(case_id)
    (root / "figures").mkdir(parents=True, exist_ok=True)
    (root / "figures" / "a.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 8)
    figures.register(
        case_id, "figures/a.png", "特征分布", [source_artifact["artifact_id"]],
        "mathworkstation.eda", {}, None,
    )

    try:
        promoter.promote_all_draft_figures(case_id, source_artifact["artifact_id"])
    except ValueError as error:
        assert "not a paper_ready_approval" in str(error)
    else:
        raise AssertionError("expected ValueError for a non-approval artifact")


def test_pipeline_promotes_figures_after_paper_ready(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "图表自动晋升端到端")
    # Deterministic fixture proposer cannot resolve coherence (P2) issues, so
    # keep classic behaviour -- the promotion wiring is orthogonal to Skill C.
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

    result = service.run(
        case["case_id"],
        session["session_id"],
        problem,
        data,
        "观测需求数据",
        "target",
        "e2e-human",
        "SM",
        data_kind=DatasetKind.OBSERVED,
        source_uri="https://example.org/datasets/modeling-e2e",
        license_name="CC BY 4.0",
        data_description="固定端到端验收数据",
        refinement_config=RefinementConfig(max_stages=1, min_stages=0, max_changed_ratio=0.5),
    )

    root = cases.case_root(case["case_id"])
    figures = service.figures.list_figures(case["case_id"])
    assert figures, "pipeline must register figures (EDA/baseline/comparison/sensitivity/workflow)"

    approval_id = result["paper_ready_artifact_id"]
    for figure in figures:
        assert figure["status"] == "FINAL", (
            f"figure {figure['figure_id']} ({figure.get('title')}) must be FINAL after paper_ready"
        )
        assert figure["paper_ready_approval_id"] == approval_id, (
            f"figure {figure['figure_id']} must link the paper_ready approval"
        )
        artifact = service.artifacts.get(case["case_id"], figure["artifact_id"])
        assert artifact["paper_eligible"] is True

    # the auto-promotion decision is recorded (failures must never be silent)
    decisions = [
        json.loads(line)
        for line in (root / "decisions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    promotion_events = [d for d in decisions if d.get("event") == "figures_auto_promoted"]
    assert promotion_events, "figures_auto_promoted event must be written to decisions.jsonl"
    assert promotion_events[-1]["promoted_count"] >= 1

    # promoted figures end up citable in the paper outline
    outline = read_json(root / "paper" / "outline" / "auto-outline.json")
    all_outline_figures = {
        figure_id
        for section in outline["sections"]
        for figure_id in section.get("figure_ids", [])
    }
    assert all_outline_figures, "outline must reference promoted figures"
    for figure_id in all_outline_figures:
        record = service.figures.get(case["case_id"], figure_id)
        assert record["status"] == "FINAL"

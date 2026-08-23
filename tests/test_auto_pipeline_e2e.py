import json
import zipfile
from pathlib import Path
from typing import Any

import pandas as pd

from mathworkstation.auto_pipeline import AutoPipelineService
from mathworkstation.case_manager import CaseManager
from mathworkstation.datasets import DatasetKind
from mathworkstation.io_utils import atomic_write_json, read_json
from mathworkstation.refinement import RefinementConfig
from mathworkstation.structured_llm import (
    ModelPlanProposal,
    PaperRefinementProposal,
    ProblemAnalysis,
)


class DeterministicStructuredLLM:
    """Structured proposer fixture; all evidence and experiments stay real."""

    def __init__(self, service: AutoPipelineService) -> None:
        self.service = service
        self.calls = 0

    def _response(self, case_id: str, session_id: str, node_id: str, payload: Any) -> dict[str, str]:
        self.calls += 1
        root = self.service.cases.case_root(case_id)
        path = root / "sessions" / session_id / "responses" / f"fixture-{self.calls:03d}.json"
        atomic_write_json(
            path,
            {
                "schema_version": 1,
                "node_id": node_id,
                "fixture": True,
                "payload": payload,
            },
        )
        artifact = self.service.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "llm_response_fixture",
            "test",
            upstream=[],
        )
        return {"artifact_id": artifact["artifact_id"]}

    def json_call(
        self,
        case_id: str,
        session_id: str,
        node_id: str,
        _prompt_name: str,
        variables: dict[str, Any],
        schema: type,
        _input_artifact_ids: list[str],
        **_kwargs: Any,
    ) -> tuple[Any, dict[str, str]]:
        if schema is ProblemAnalysis:
            value = ProblemAnalysis(
                objectives=["建立可解释的需求预测模型并比较候选方法"],
                subproblems=["检查数据质量", "比较回归模型", "评价稳健性"],
                variables=["feature_a", "feature_b", "target"],
                constraints=["结论只适用于给定观测数据范围"],
                evaluation_targets=["rmse"],
                uncertainties=["样本扰动与训练划分"],
                open_questions=[],
            )
        elif schema is ModelPlanProposal:
            value = ModelPlanProposal(
                dataset_id=variables["dataset_id"],
                task_type="regression",
                target_column="target",
                feature_columns=["feature_a", "feature_b"],
                candidate_models=[
                    {"name": "linear", "parameters": {}, "rationale": "可解释基线"},
                    {"name": "ridge", "parameters": {"alpha": 1.0}, "rationale": "控制共线性"},
                    {
                        "name": "random_forest",
                        "parameters": {"n_estimators": 20, "max_depth": 4},
                        "rationale": "检验非线性收益",
                    },
                ],
                primary_metric="rmse",
                cv_folds=3,
                test_size=0.2,
                random_seed=42,
                sensitivity_fractions=[0.7, 0.85, 1.0],
            )
        elif schema is PaperRefinementProposal:
            issues = variables["issues_json"]
            sections = variables["sections_json"]
            patches = []
            additions = {
                "data_analysis": "进一步核查异常值、变量分布和特征关系，使数据推理覆盖来源、缺失机制、异常处理与建模影响。",
                "abstract": "研究目的、研究方法、主要结果、稳健性与适用边界在此形成闭环，并保持结论受证据范围约束。",
                "model_construction": "模型参数、训练方法、评价准则与基本假设共同限定损失函数和适用条件。",
                "model_solution": "模型参数、训练过程、交叉验证、评价指标与假设边界均由实验记录支撑。",
                "results": "结果指标用于比较候选模型，并据此形成受限制条件约束的结论。",
                "problem_restated": "问题目标、约束与评价标准对应到各子问题的输入和输出。",
            }
            excellent_ref = variables.get("excellent_ref_json") or {}
            comparator_signal = bool(excellent_ref.get("generalized_issues"))
            for section_id, source in list(sections.items())[:2]:
                addition = additions.get(section_id, "补充论证链条和适用边界，使章节内容更加完整。")
                if comparator_signal:
                    addition = (
                        "参照优秀论文通用经验："
                        + excellent_ref["generalized_issues"][0].get("aspect", "")
                        + "——"
                        + excellent_ref["generalized_issues"][0].get("reason", "")
                        + "。"
                        + addition
                    )
                patches.append(
                    {
                        "section_id": section_id,
                        "source_sha256": source["source_sha256"],
                        "replacement_markdown": source["markdown"].rstrip()
                        + "\n\n"
                        + addition
                        + "\n",
                        "rationale": (
                            "resolve the selected quality finding"
                            + (" with excellent-paper comparator signal" if comparator_signal else "")
                            + " with a bounded section patch"
                        ),
                    }
                )
            value = PaperRefinementProposal(
                strategy="complete the selected evidence-grounded section reasoning",
                issue_ids=[item["issue_id"] for item in issues],
                expected_gains={item["dimension"]: 0.1 for item in issues if item.get("dimension")},
                patches=patches,
            )
        else:  # pragma: no cover - catches new unmodeled LLM dependencies
            raise AssertionError(f"unexpected schema call: {schema}")
        return value, self._response(case_id, session_id, node_id, value.model_dump(mode="json"))

    def markdown_call(
        self,
        case_id: str,
        session_id: str,
        node_id: str,
        _prompt_name: str,
        variables: dict[str, Any],
        _input_artifact_ids: list[str],
        **_kwargs: Any,
    ) -> tuple[str, dict[str, str]]:
        section_id = variables["section_id"]
        context = variables["context_json"]
        bodies = {
            "abstract": "研究目的在于建立可复现预测流程。研究方法包括数据审查、模型比较和敏感性分析。主要结果由注册实验给出，稳健性与适用边界由后续证据限定。",
            "problem_restated": "研究概述从题目问题出发，将总体目标拆分为数据检查、模型比较和稳健性评价三个子问题，并明确约束与评价标准。",
            "assumptions": "模型假设要求样本口径一致、字段含义稳定。所有推断仅在当前数据适用边界内成立。",
            "notation": r"设变量向量为 $x$，目标为 $y$，预测值为 $\hat y$，损失函数记为 $L$。",
            "data_analysis": "数据字段均来自已登记来源。本节检查缺失情况与数据质量，并依据证据决定后续处理。",
            "model_construction": r"建立回归模型并以损失函数 $L=\lVert y-\hat y\rVert$ 衡量误差；模型参数、训练、评价和假设均受证据约束。",
            "model_solution": r"模型求解采用训练与交叉验证流程，以误差指标评价候选方案，并记录参数和假设；目标函数记为 $L$。",
            "results": "结果部分比较模型指标，结合图表证据说明模型差异，形成受限制条件约束的结论。",
            "sensitivity": "敏感性分析改变样本比例与随机种子，观察结果波动并评价稳健性。",
            "strengths_weaknesses": "模型优点是流程可复现且证据明确；局限和缺点在于数据范围有限，外推需谨慎。",
            "conclusion": "结论回答预测与模型比较目标，并声明适用范围、外推限制和证据边界。",
            "references": "参考文献与数据来源均以已登记且可核验的来源为准。",
        }
        claims = "\n\n".join(
            f"{item['text']} [{item['claim_id']}]" for item in context["allowed_claims"]
        )
        content = f"## {context['title']}\n\n{bodies[section_id]}"
        if claims:
            content += f"\n\n{claims}"
        response = self._response(case_id, session_id, node_id, {"section_id": section_id})
        return content + "\n", response


def test_auto_pipeline_produces_traceable_refined_export(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "端到端验收案例")
    # Deterministic fixture proposer cannot resolve coherence (P2) cross-section
    # issues, so keep the classic non-coherence behaviour here (Skill C is
    # exercised separately by the coherence tests).
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
    final_text = (root / "paper" / "final.md").read_text(encoding="utf-8")
    state = read_json(root / "memory" / "refinement_state.json")
    consistency = read_json(root / "review" / "consistency" / "paper_consistency.json")
    complete_paper = read_json(root / "review" / "structural" / "complete-paper-assessment.json")
    result_records = [
        json.loads(line)
        for line in (root / "results" / "contracts" / "results.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    subproblems = [
        json.loads(line)
        for line in (root / "results" / "contracts" / "subproblems.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    tables = [
        json.loads(line)
        for line in (root / "results" / "contracts" / "tables.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert result["refinement"]["accepted_stages"] == [1]
    assert state["accepted_patch_ids"] and state["active_stage"] is None
    # REVIEW (minor unattributed numbers in the deterministic fixture) is a
    # legitimate non-blocking outcome that refinement polishes; only BLOCK
    # hard-fails. The refined output still must pass the complete-paper gate.
    assert consistency["gate"] in {"PASS", "REVIEW"}
    assert complete_paper["gate"] == "PASS"
    assert complete_paper["issue_codes"] == []
    assert all(title in final_text for title in ("摘要", "模型建立", "结果分析", "结论"))
    assert all(f"{item['value']:.6f}" in final_text for item in result_records)
    assert tables and all(item["table_id"] in final_text for item in tables)
    assert subproblems and all(
        item["owner_section"] and item["status"] == "COMPLETED" and item["evidence_artifact_ids"]
        for item in subproblems
    )
    assert "The validated comparison" not in final_text
    assert "ranked first" not in final_text
    assert "SYNTHETIC" not in final_text.upper()
    assert service.artifacts.verify(case["case_id"])["valid"]

    archive_path = root / result["export"]["archive_path"]
    with zipfile.ZipFile(archive_path) as archive:
        names = set(archive.namelist())
    assert "paper/final.md" in names
    assert "memory/refinement_state.json" in names
    assert "refinement/stages/stage-001/COMMITTED.json" in names
    assert "review/consistency/paper_consistency.json" in names
    assert "review/structural/complete-paper-assessment.json" in names
    assert any(name.startswith("tables/final/table-") for name in names)
    submission_path = root / result["export"]["submission"]["archive_path"]
    with zipfile.ZipFile(submission_path) as submission:
        submission_names = set(submission.namelist())
    assert "paper/final.md" in submission_names
    assert not any(name.startswith(prefix) for name in submission_names for prefix in ("memory/", "refinement/", "sessions/", "evidence/raw_responses/"))

    # Recurrent R2: inject an experiment defect, let the outer auditor route it
    # back to experiments, then execute a real Round-1 repair all the way to a
    # new paper/export. Stable model_plan/baseline must be reused.
    evidence_before = read_json(root / "results" / "contracts" / "active_evidence.json")
    refinement_epoch_before = read_json(root / "memory" / "refinement_state.json")["epoch"]
    service.workflow.mark_stale(case["case_id"], "experiments", "recurrent e2e re-entry probe")
    round_result = service.run_recurrent_round(
        case["case_id"],
        session["session_id"],
        "e2e-human",
        "SM",
        refinement_config=RefinementConfig(max_stages=1, min_stages=0, max_changed_ratio=0.5),
        invalidate=True,
    )
    assert round_result["started"] is True
    assert round_result["plan"].round_number == 1
    assert round_result["plan"].pivot == "experiments"
    assert round_result["decision"].accepted is True
    reentered = round_result["execution"]["model_reentry"]
    rebuilt = round_result["execution"]["rebuild"]
    assert reentered["executed_nodes"] == ["experiments", "model_selection", "sensitivity"]
    evidence_after = read_json(root / "results" / "contracts" / "active_evidence.json")
    assert evidence_after["generation"] == 1
    assert set(evidence_after["result_ids"]).isdisjoint(evidence_before["result_ids"])
    assert set(evidence_after["table_ids"]).isdisjoint(evidence_before["table_ids"])
    assert len(service.contracts.list_results(case["case_id"])) > len(evidence_after["result_ids"])
    assert [item.result_id for item in service.contracts.list_results(case["case_id"], active_only=True)] == evidence_after["result_ids"]

    refinement_state_after = read_json(root / "memory" / "refinement_state.json")
    assert refinement_state_after["epoch"] == refinement_epoch_before + 1
    assert rebuilt["paper"]["complete_paper"].gate == "PASS"
    assert rebuilt["paper"]["submission"]["preflight"]["gate"] == "PASS"
    checkpoint = read_json(root / ".internal" / "checkpoints" / "current.json")
    assert checkpoint["nodes"]["model_plan"]["status"] == "SUCCEEDED"
    assert checkpoint["nodes"]["baseline"]["status"] == "SUCCEEDED"
    assert checkpoint["nodes"]["experiments"]["status"] == "SUCCEEDED"
    assert checkpoint["nodes"]["model_selection"]["status"] == "SUCCEEDED"
    assert checkpoint["nodes"]["sensitivity"]["status"] == "SUCCEEDED"
    assert checkpoint["nodes"]["paper_outline"]["status"] == "SUCCEEDED"
    assert checkpoint["nodes"]["paper_draft"]["status"] == "SUCCEEDED"
    assert checkpoint["nodes"]["consistency_check"]["status"] == "SUCCEEDED"
    assert checkpoint["nodes"]["refinement_loop"]["status"] == "SUCCEEDED"
    assert checkpoint["nodes"]["final_review"]["status"] == "SUCCEEDED"
    assert checkpoint["nodes"]["export"]["status"] == "SUCCEEDED"

    round_state = round_result["state"]
    assert round_state["round"] == 1
    assert round_state["status"] == "IDLE"
    assert round_state["active_lineage"]["model_comparison"] == reentered["comparison_artifact_id"]
    assert round_state["active_lineage"]["paper_evidence_lineage"] == rebuilt["evidence"]["evidence_lineage"]["artifact_id"]
    assert round_state["active_lineage"]["paper_final"] == rebuilt["paper"]["refinement"]["paper_final_artifact_id"]

    # Round 2: a paper-only refinement defect must not touch the accepted model
    # or numeric evidence generation. The paper cell forces a fresh refinement
    # epoch so a previously STOPPED inner loop cannot be mistaken for repair.
    model_comparison_before_paper_round = round_state["active_lineage"]["model_comparison"]
    active_evidence_before_paper_round = read_json(root / "results" / "contracts" / "active_evidence.json")
    refinement_epoch_before_paper_round = read_json(root / "memory" / "refinement_state.json")["epoch"]
    service.workflow.mark_stale(case["case_id"], "refinement_loop", "paper-only recurrent repair probe")
    paper_round = service.run_recurrent_round(
        case["case_id"],
        session["session_id"],
        "e2e-human",
        "SM",
        refinement_config=RefinementConfig(max_stages=1, min_stages=0, max_changed_ratio=0.5),
        invalidate=True,
    )
    assert paper_round["plan"].round_number == 2
    assert paper_round["plan"].pivot == "refinement_loop"
    assert paper_round["decision"].accepted is True
    assert paper_round["execution"]["paper_reentry"]["executed_nodes"] == [
        "refinement_loop",
        "final_review",
        "export",
    ]
    paper_round_state = paper_round["state"]
    assert paper_round_state["active_lineage"]["model_comparison"] == model_comparison_before_paper_round
    assert read_json(root / "results" / "contracts" / "active_evidence.json") == active_evidence_before_paper_round
    assert read_json(root / "memory" / "refinement_state.json")["epoch"] == refinement_epoch_before_paper_round + 1
    assert paper_round_state["round"] == 2
    assert paper_round_state["status"] == "IDLE"

    # Round 3: a data-quality defect must recompute data-quality + EDA and all
    # modeling/paper descendants, while preserving the accepted problem-analysis
    # lineage and the registered immutable dataset id.
    problem_analysis_before_data_round = paper_round_state["active_lineage"]["problem_analysis"]
    dataset_before_data_round = paper_round_state["active_lineage"]["dataset"]
    evidence_before_data_round = read_json(root / "results" / "contracts" / "active_evidence.json")
    service.workflow.mark_stale(case["case_id"], "data_quality", "data-quality recurrent repair probe")
    data_round = service.run_recurrent_round(
        case["case_id"],
        session["session_id"],
        "e2e-human",
        "SM",
        target_column="target",
        refinement_config=RefinementConfig(max_stages=1, min_stages=0, max_changed_ratio=0.5),
        invalidate=True,
    )
    assert data_round["plan"].round_number == 3
    assert data_round["plan"].pivot == "data_quality"
    assert data_round["decision"].accepted is True
    research = data_round["execution"]["research_reentry"]
    assert research["executed_nodes"][:3] == ["data_quality", "eda", "model_plan"]
    data_round_state = data_round["state"]
    assert data_round_state["active_lineage"]["problem_analysis"] == problem_analysis_before_data_round
    assert data_round_state["active_lineage"]["dataset"] == dataset_before_data_round
    evidence_after_data_round = read_json(root / "results" / "contracts" / "active_evidence.json")
    assert evidence_after_data_round["generation"] == 3
    assert set(evidence_after_data_round["result_ids"]).isdisjoint(evidence_before_data_round["result_ids"])
    assert data_round_state["round"] == 3
    assert data_round_state["status"] == "IDLE"

    # Round 4: earliest input-validation repair revalidates immutable registered
    # sources and rebuilds the complete analytical chain without re-uploading
    # either problem or data. This also exercises problem-analysis re-entry as a
    # descendant while keeping the source/dataset lineage fixed.
    immutable_problem_source = data_round_state["active_lineage"]["problem_source"]
    immutable_dataset = data_round_state["active_lineage"]["dataset"]
    service.workflow.mark_stale(case["case_id"], "input_validation", "full-chain recurrent repair probe")
    input_round = service.run_recurrent_round(
        case["case_id"],
        session["session_id"],
        "e2e-human",
        "SM",
        target_column="target",
        refinement_config=RefinementConfig(max_stages=1, min_stages=0, max_changed_ratio=0.5),
        invalidate=True,
    )
    assert input_round["plan"].round_number == 4
    assert input_round["plan"].pivot == "input_validation"
    assert input_round["decision"].accepted is True
    input_research = input_round["execution"]["research_reentry"]
    assert input_research["executed_nodes"][:6] == [
        "input_validation",
        "problem_analysis",
        "data_registration",
        "data_quality",
        "eda",
        "model_plan",
    ]
    input_round_state = input_round["state"]
    assert input_round_state["active_lineage"]["problem_source"] == immutable_problem_source
    assert input_round_state["active_lineage"]["dataset"] == immutable_dataset
    assert read_json(root / "results" / "contracts" / "active_evidence.json")["generation"] == 4
    assert input_round_state["round"] == 4
    assert input_round_state["status"] == "IDLE"
    assert service.recurrent.should_continue(input_round_state) is False


def test_c_type_detection_stable_across_spellings(tmp_path: Path) -> None:
    """C-type detection must not depend on a magic competition spelling.

    Regression test for the flaky momentum integration (t3a5a988f): the old
    code called a non-existent ``CaseManager.get_manifest`` inside a swallowed
    ``except: pass``, so ``problem_type`` was always empty and the C-type
    sections appeared only when ``competition_type`` happened to be spelled
    "MCM-C"/"MCM_C". ``show_case()["manifest"]`` is the real accessor.
    """
    cases = CaseManager(tmp_path / "output")
    service = AutoPipelineService(cases, None, coherence=False)  # type: ignore[arg-type]

    # Bare "C" spelling with manifest problem_type="c"
    case = cases.create_case("MCM", "C 题", problem_type="c", year=2024)
    case_id = case["case_id"]
    assert service._is_c_type(case_id, "C") is True
    assert service._is_c_type(case_id, "MCM-C") is True
    assert service._is_c_type(case_id, "MCM") is True  # manifest drives it
    assert service._case_problem_type(case_id) == "c"

    # Non-C case must stay negative even when spelled with a trailing C
    non_c = cases.create_case("MCM", "A 题", problem_type="a", year=2024)
    assert service._is_c_type(non_c["case_id"], "MCM") is False


def test_momentum_frame_loader_falls_back_to_uploads(tmp_path: Path) -> None:
    """Momentum data loader finds the uploaded csv even without a dataset id."""
    import pandas as pd

    cases = CaseManager(tmp_path / "output")
    service = AutoPipelineService(cases, None, coherence=False)  # type: ignore[arg-type]
    case = cases.create_case("MCM", "C 题", problem_type="c", year=2024)
    case_id = case["case_id"]
    root = cases.case_root(case_id)
    uploaded = root / "input" / "data" / "uploaded"
    uploaded.mkdir(parents=True, exist_ok=True)
    (uploaded / "wimbledon_data.csv").write_text(
        "server,point_victor,elapsed_time\n1,1,0\n2,2,1\n1,1,2\n2,2,3\n",
        encoding="utf-8",
    )
    frame = service._load_momentum_frame(case_id, None)
    assert frame is not None
    assert list(frame.columns) == ["server", "point_victor", "elapsed_time"]

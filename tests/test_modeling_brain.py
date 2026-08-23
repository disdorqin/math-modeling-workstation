from pathlib import Path

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.modeling_brain import ModelingBrainService
from mathworkstation.paper_contracts import SubproblemContract
from mathworkstation.problem_graph import ProblemGraphService


class _StubHMML:
    def retrieve(self, query: str, top_k: int | None = None):
        return [
            {"method": "ARIMA time series forecasting", "description": "temporal forecasting", "score": 0.8},
            {"method": "Linear programming", "description": "optimization", "score": 0.7},
        ]


class _StubCards:
    def retrieve(self, query: str, task_types=None, top_k=None):
        return [
            {
                "model_id": "time_series_arima",
                "title": "ARIMA",
                "family": "时序预测族",
                "task_types": ["prediction"],
                "content": "",
                "score": 0.9,
            }
        ]


def _service(tmp_path: Path, contracts: list[SubproblemContract]):
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "Modeling brain")
    artifacts = ArtifactRegistry(cases)
    graphs = ProblemGraphService(cases, artifacts)
    graphs.persist(case["case_id"], contracts, [])
    service = ModelingBrainService(cases, artifacts, graphs, hmml=_StubHMML(), cards=_StubCards())
    return cases, artifacts, graphs, service, case["case_id"]


def test_modeling_brain_expands_node_search_space_without_pretending_solver_exists(tmp_path: Path) -> None:
    _, artifacts, graphs, service, case_id = _service(
        tmp_path,
        [
            SubproblemContract(
                subproblem_id="SP1",
                title="Forecast future daily demand",
                objective="Predict a future daily value with uncertainty",
            )
        ],
    )
    result = service.deliberate(case_id, "SP1")
    decision = result["decision"]

    assert decision.gate == "PASS"
    assert any(item.source == "knowledge_card" for item in decision.candidates)
    arima = next(item for item in decision.candidates if item.method == "ARIMA")
    assert arima.feasibility == "NEEDS_SOLVER"
    assert any(
        candidate_id.startswith("card:")
        or candidate_id.startswith("hmml:")
        or candidate_id.startswith("skill:")
        for candidate_id in decision.selected_candidate_ids
    )
    assert decision.skill_advice
    assert decision.quality_checks
    assert decision.benchmark_prior_source == "config/ref_models/c_problem_excellent_benchmark_v1.json"
    assert "algorithm_diversity_is_normal" in decision.c_problem_prior_names
    assert any("时间顺序验证" in item for item in decision.benchmark_validation_obligations)
    assert all(item.source in {"native", "hmml", "knowledge_card", "skill"} for item in decision.candidates)
    assert any("SolverRegistry" in item for item in decision.benchmark_forbidden_shortcuts)
    node = graphs.load(case_id).node("SP1")
    assert node.plan.modeling_brain_artifact_id == result["artifact"]["artifact_id"]
    assert node.plan.selected_candidate_ids == decision.selected_candidate_ids
    assert artifacts.verify(case_id)["valid"]


def test_real_wordle_nodes_use_real_hmml_and_knowledge_cards(tmp_path: Path) -> None:
    case_root = Path("output/mcm-c-2023/v3/20260805-MCM-0001-EUP7")
    contracts = [
        SubproblemContract.model_validate_json(line)
        for line in (case_root / "results/contracts/subproblems.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "Wordle Modeling Brain Gate")
    artifacts = ArtifactRegistry(cases)
    graphs = ProblemGraphService(cases, artifacts)
    graphs.persist(case["case_id"], contracts, [])
    service = ModelingBrainService(cases, artifacts, graphs)

    decisions = {
        subproblem_id: service.deliberate(case["case_id"], subproblem_id)["decision"]
        for subproblem_id in ("SP1", "SP2", "SP3", "SP4", "SP5", "SP6")
    }
    assert all(decisions[subproblem_id].gate == "PASS" for subproblem_id in ("SP1", "SP2", "SP3", "SP4", "SP5"))
    assert decisions["SP6"].gate == "SKIP"
    assert any(item.source != "native" for item in decisions["SP1"].candidates)
    assert any(item.source == "knowledge_card" for item in decisions["SP4"].candidates)
    assert any(
        candidate_id.startswith("card:")
        or candidate_id.startswith("hmml:")
        or candidate_id.startswith("skill:")
        for candidate_id in decisions["SP4"].selected_candidate_ids
    )
    assert any(item.source == "skill" for item in decisions["SP4"].candidates)
    assert decisions["SP4"].skill_advice
    loaded = graphs.load(case["case_id"])
    assert all(loaded.node(f"SP{i}").plan.modeling_brain_artifact_id for i in range(1, 6))
    assert artifacts.verify(case["case_id"])["valid"]


def test_modeling_brain_skips_synthesis_deliverable(tmp_path: Path) -> None:
    _, _, _, service, case_id = _service(
        tmp_path,
        [
            SubproblemContract(
                subproblem_id="SP1",
                title="Analyze data",
                objective="Explore interesting patterns in data",
            ),
            SubproblemContract(
                subproblem_id="SP2",
                title="Write summary letter to editor",
                objective="Write a concise letter to editor",
            ),
        ],
    )
    decision = service.deliberate(case_id, "SP2")["decision"]
    assert decision.gate == "SKIP"
    assert decision.candidates == []
    assert decision.selected_candidate_ids == []
    assert any("accepted evidence" in item for item in decision.research_obligations)
    assert any("回溯" in item for item in decision.benchmark_validation_obligations)

from __future__ import annotations

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.paper_contracts import SubproblemContract
from mathworkstation.problem_graph import ProblemGraphBuilder, ProblemGraphService


def _wordle_contracts() -> list[SubproblemContract]:
    # These are the six real 2023 MCM Wordle subproblem titles already present
    # in the repository's generated v3 paper, not an invented single-task fixture.
    titles = [
        "Model daily variation in number of reported results",
        "Analyze effect of word attributes on Hard Mode percentage",
        "Predict distribution of reported results for future word/date",
        "Classify solution words by difficulty",
        "Explore other interesting features of the data set",
        "Write summary letter to Puzzle Editor",
    ]
    return [
        SubproblemContract(
            subproblem_id=f"SP{index}",
            title=title,
            objective=title,
            inputs=["provided Wordle data"],
            outputs=["subproblem-specific result"],
            constraints=["use only admissible evidence"],
        )
        for index, title in enumerate(titles, start=1)
    ]


def test_wordle_problem_graph_routes_real_subproblems_to_distinct_research_families() -> None:
    graph = ProblemGraphBuilder().build(_wordle_contracts())

    assert [node.task_family for node in graph.nodes] == [
        "forecasting",
        "explanatory_inference",
        "distribution_forecasting",
        "classification",
        "exploratory_analysis",
        "synthesis",
    ]
    assert [node.execution_kind for node in graph.nodes] == [
        "MODEL",
        "ANALYSIS",
        "MODEL",
        "MODEL",
        "ANALYSIS",
        "DELIVERABLE",
    ]

    # The previous pipeline gave every SP the same best-model/RMSE method. The
    # graph must carry family-specific method and validation envelopes instead.
    method_heads = {node.plan.candidate_methods[0] for node in graph.nodes}
    validation_heads = {node.plan.validation_protocol[0] for node in graph.nodes}
    assert len(method_heads) == 6
    assert len(validation_heads) == 6
    assert graph.node("SP1").plan.executor_family == "forecasting"
    assert graph.node("SP1").plan.executor_available is True
    assert graph.node("SP4").plan.executor_family == "classification"
    assert graph.node("SP4").plan.executor_available is True
    assert graph.node("SP2").plan.executor_family == "explanatory_inference"
    assert graph.node("SP2").plan.executor_available is True
    assert graph.node("SP3").plan.executor_family == "distribution_forecasting"
    assert graph.node("SP3").plan.executor_available is True
    assert graph.node("SP5").plan.executor_family == "exploratory_analysis"
    assert graph.node("SP5").plan.executor_available is True


def test_wordle_editor_letter_is_a_synthesis_dependency_node_not_a_model_run() -> None:
    graph = ProblemGraphBuilder().build(_wordle_contracts())
    letter = graph.node("SP6")

    assert letter.task_family == "synthesis"
    assert letter.execution_kind == "DELIVERABLE"
    assert letter.plan.requires_model_execution is False
    assert letter.dependencies == ["SP1", "SP2", "SP3", "SP4", "SP5"]
    assert {(edge.source_subproblem_id, edge.target_subproblem_id, edge.relation) for edge in graph.edges} == {
        ("SP1", "SP6", "SYNTHESIZES"),
        ("SP2", "SP6", "SYNTHESIZES"),
        ("SP3", "SP6", "SYNTHESIZES"),
        ("SP4", "SP6", "SYNTHESIZES"),
        ("SP5", "SP6", "SYNTHESIZES"),
    }


def test_problem_graph_infers_high_confidence_cross_question_dependencies_from_contract_text() -> None:
    contracts = [
        SubproblemContract(
            subproblem_id="SP1",
            title="探索销售结构",
            objective="识别数据分布与关联规律",
            outputs=["销售结构证据"],
        ),
        SubproblemContract(
            subproblem_id="SP2",
            title="建立品类定价模型",
            objective="基于问题1的销售结构建立定价与补货模型",
            inputs=["SP1销售结构证据"],
        ),
        SubproblemContract(
            subproblem_id="SP3",
            title="单品约束扩展",
            objective="在上一问基础上加入单品数量与最小陈列量约束",
        ),
    ]

    graph = ProblemGraphBuilder().build(contracts)

    assert graph.node("SP2").dependencies == ["SP1"]
    assert graph.node("SP3").dependencies == ["SP2"]
    assert {(edge.source_subproblem_id, edge.target_subproblem_id) for edge in graph.edges} >= {
        ("SP1", "SP2"),
        ("SP2", "SP3"),
    }


def test_problem_graph_does_not_mark_flat_contracts_completed_without_research_evidence() -> None:
    graph = ProblemGraphBuilder().build(_wordle_contracts())

    assert all(node.state.status == "PLANNED" for node in graph.nodes)
    assert all(node.answer is None for node in graph.nodes)
    assert all(node.state.evidence_artifact_ids == [] for node in graph.nodes)
    assert all(len(node.experiments) == 1 for node in graph.nodes[:5])
    assert graph.node("SP6").experiments == []
    assert len({node.experiments[0].method for node in graph.nodes[:5]}) == 5


def test_problem_graph_service_persists_traceable_case_artifact(tmp_path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "Wordle graph persistence")
    registry = ArtifactRegistry(cases)
    source = tmp_path / "problem.txt"
    source.write_text("2023 MCM Wordle", encoding="utf-8")
    source_artifact = registry.ingest_file(
        case["case_id"], source, "input/problem/source.txt", "problem_extracted_text"
    )

    graph, artifact = ProblemGraphService(cases, registry).persist(
        case["case_id"], _wordle_contracts(), [source_artifact["artifact_id"]]
    )

    assert (cases.case_root(case["case_id"]) / "analysis" / "problem_graph.json").is_file()
    assert artifact["artifact_type"] == "problem_graph"
    assert artifact["upstream"] == [source_artifact["artifact_id"]]
    assert artifact["structure_gate"] == "PASS"
    assert artifact["research_gate"] == "INCOMPLETE"
    assert artifact["assessment_artifact_id"]
    assert (cases.case_root(case["case_id"]) / "review" / "problem_graph" / "assessment.json").is_file()
    assert registry.verify(case["case_id"])["valid"] is True
    assert graph.node("SP6").execution_kind == "DELIVERABLE"


def test_problem_graph_allows_distinct_multi_stage_questions_inside_one_valid_family() -> None:
    contracts = [
        SubproblemContract(subproblem_id="SP1", title="建立一般管线费用模型", objective="建立有无共用管线的通用费用最小模型"),
        SubproblemContract(subproblem_id="SP2", title="加入城乡附加费用优化具体布局", objective="在城区附加费用下求最小总费用和车站位置"),
        SubproblemContract(subproblem_id="SP3", title="细化不同管线单价后的最优布局", objective="在不同非共用和共用管线单价下重新优化"),
    ]
    graph = ProblemGraphBuilder().build(contracts)
    assessment = __import__("mathworkstation.problem_graph", fromlist=["assess_problem_graph"]).assess_problem_graph(graph)

    assert [node.task_family for node in graph.nodes] == ["optimization", "optimization", "optimization"]
    assert assessment.structure_gate == "PASS"
    assert not any(item["code"] == "SUBPROBLEMS_FLATTENED_TO_ONE_FAMILY" for item in assessment.findings)


def test_problem_graph_assessment_refuses_false_completion_without_per_node_evidence(tmp_path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "Wordle graph gate")
    service = ProblemGraphService(cases, ArtifactRegistry(cases))
    graph = service.builder.build(_wordle_contracts())
    graph.node("SP1").state.status = "COMPLETED"

    assessment = service.assess(graph)

    assert assessment.structure_gate == "PASS"
    assert assessment.research_gate == "FAIL"
    assert any(item["code"] == "COMPLETED_WITHOUT_ANSWER_OR_EVIDENCE" for item in assessment.findings)

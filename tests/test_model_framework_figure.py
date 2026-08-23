from __future__ import annotations

from pathlib import Path

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.io_utils import atomic_write_json, now_iso
from mathworkstation.mcm2024_gate import mcm2024_c_contracts, link_mcm2024_c_dependencies
from mathworkstation.model_framework_figure import ModelFrameworkFigureService
from mathworkstation.model_structure import ModelStructurePlanner
from mathworkstation.narrative_graph import NarrativeGraph, NarrativeNode
from mathworkstation.problem_graph import ProblemGraphBuilder
from mathworkstation.research_preferences import ResearchPreferenceProfile


def _narrative_graph() -> NarrativeGraph:
    problem = link_mcm2024_c_dependencies(ProblemGraphBuilder().build(mcm2024_c_contracts()))
    preferences = ResearchPreferenceProfile(
        preferred_modeling_styles=["probabilistic_graphical", "hybrid"],
        priorities=["mathematical_structure", "logical_rigor", "mechanism_depth", "robustness"],
    )
    planner = ModelStructurePlanner()
    nodes = []
    for problem_node in problem.nodes:
        structure = planner.plan_node(problem_node, problem, preferences)
        nodes.append(
            NarrativeNode(
                subproblem_id=problem_node.subproblem_id,
                title=problem_node.title,
                role="SYNTHESIS" if problem_node.execution_kind == "DELIVERABLE" else "RESEARCH",
                task_family=problem_node.task_family,
                objective=problem_node.objective,
                dependencies=list(problem_node.dependencies),
                method=problem_node.plan.candidate_methods[0],
                answer="accepted result",
                limitation="bounded by observed data",
                model_structure=structure,
                gate="PASS",
            )
        )
    return NarrativeGraph(
        case_id="fixture",
        gate="PASS",
        research_gate="PASS",
        model_graph_gate="PASS",
        evidence_graph_gate="PASS",
        nodes=nodes,
        storyline=[node.subproblem_id for node in nodes],
        generated_at=now_iso(),
    )


def test_model_framework_figure_is_distinct_editable_document_layer_visual(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    manifest = cases.create_case("MCM", "2024 C fixture")
    case_id = manifest["case_id"]
    artifacts = ArtifactRegistry(cases)
    figures = FigureRegistry(cases, artifacts)
    root = cases.case_root(case_id)
    source = root / "analysis" / "narrative.json"
    atomic_write_json(source, {"fixture": True})
    source_artifact = artifacts.register_existing(
        case_id,
        source.relative_to(root).as_posix(),
        "narrative_graph",
        "test",
    )

    figure = ModelFrameworkFigureService(cases, artifacts, figures).ensure(
        case_id,
        _narrative_graph(),
        profile_id="MCM_C",
        narrative_artifact_id=source_artifact["artifact_id"],
    )

    assert figure is not None
    assert figure["status"] == "FINAL"
    assert figure["parameters"]["semantic_kind"] == "model_framework"
    assert figure["parameters"]["numeric_evidence"] is False
    assert figure["parameters"]["visual_review_status"] == "REVIEW_PENDING"
    assert len(figure["parameters"]["editable_source_artifact_ids"]) == 2
    assert (root / figure["path"]).stat().st_size > 1000
    spec_path = root / "figures" / "research_state" / "model_framework" / "model-framework-spec.json"
    spec = spec_path.read_text(encoding="utf-8")
    assert "State / Mechanism" not in spec  # rendered label, not a fabricated model object
    assert "SP2" in spec
    assert "probabilistic_state" not in spec  # spec stores mathematical content, not internal archetype labels

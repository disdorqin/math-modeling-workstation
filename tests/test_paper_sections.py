import json
from pathlib import Path

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.claims import ClaimRegistry
from mathworkstation.datasets import DatasetRegistry
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.paper_outline import PaperOutlineService, default_outline
from mathworkstation.paper_sections import PaperSectionWorkspace


def test_section_workspace_creates_isolated_contexts(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Sections")
    artifacts = ArtifactRegistry(cases)
    claims = ClaimRegistry(cases, artifacts, DatasetRegistry(cases, artifacts))
    figures = FigureRegistry(cases, artifacts)
    outline = default_outline("分章节论文", "SM")
    source = tmp_path / "outline.json"
    source.write_text(json.dumps(outline.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")
    outline_result = PaperOutlineService(cases, artifacts, claims, figures).validate_file(case["case_id"], source)
    result = PaperSectionWorkspace(cases, artifacts, claims, figures).initialize(
        case["case_id"], outline_result["outline_artifact_id"]
    )
    assert len(result["manifest"]["sections"]) == 12
    result_section = cases.case_root(case["case_id"]) / "paper" / "sections" / "results"
    context = json.loads((result_section / "context.json").read_text(encoding="utf-8"))
    assert "Do not change other paper sections." in context["control_rules"]
    assert (result_section / "draft.md").read_text(encoding="utf-8").endswith("[SECTION_DRAFT_PENDING]\n")


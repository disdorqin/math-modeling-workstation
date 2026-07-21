from pathlib import Path

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.figure_composition import FigureCompositionService
from mathworkstation.figure_registry import FigureRegistry


def test_workflow_overview_exports_png_and_svg(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Workflow figure")
    artifacts = ArtifactRegistry(cases)
    figures = FigureRegistry(cases, artifacts)
    source = tmp_path / "source.txt"
    source.write_text("evidence", encoding="utf-8")
    source_artifact = artifacts.ingest_file(case["case_id"], source, "input", "source")
    result = FigureCompositionService(cases, artifacts, figures).create_workflow_overview(
        case["case_id"], [source_artifact["artifact_id"]]
    )
    root = cases.case_root(case["case_id"])
    assert (root / result["figure"]["path"]).is_file()
    assert (root / artifacts.get(case["case_id"], result["svg_artifact_id"])["path"]).is_file()

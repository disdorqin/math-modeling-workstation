import json
from pathlib import Path

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.claims import ClaimRegistry
from mathworkstation.datasets import DatasetRegistry
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.paper_consistency import PaperConsistencyChecker
from mathworkstation.paper_outline import PaperOutlineService, default_outline
from mathworkstation.paper_sections import PaperSectionWorkspace


def test_consistency_blocks_placeholders_and_unattributed_numbers(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Consistency")
    artifacts = ArtifactRegistry(cases)
    claims = ClaimRegistry(cases, artifacts, DatasetRegistry(cases, artifacts))
    figures = FigureRegistry(cases, artifacts)
    outline = default_outline("一致性论文", "SM")
    source = tmp_path / "outline.json"
    source.write_text(json.dumps(outline.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")
    outline_result = PaperOutlineService(cases, artifacts, claims, figures).validate_file(case["case_id"], source)
    workspace = PaperSectionWorkspace(cases, artifacts, claims, figures)
    workspace.initialize(case["case_id"], outline_result["outline_artifact_id"])
    workspace.update_draft(case["case_id"], "results", "# 结果\n\n模型准确率为 95%。", "human")
    result = PaperConsistencyChecker(cases, artifacts, claims, figures).check(case["case_id"])
    assert result["report"]["gate"] == "BLOCK"
    codes = {item["code"] for item in result["report"]["findings"]}
    assert "PLACEHOLDER_REMAINS" in codes
    assert "UNATTRIBUTED_NUMBERS" in codes


def test_consistency_passes_completed_empty_evidence_sections(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Consistency Pass")
    artifacts = ArtifactRegistry(cases)
    claims = ClaimRegistry(cases, artifacts, DatasetRegistry(cases, artifacts))
    figures = FigureRegistry(cases, artifacts)
    outline = default_outline("完成论文", "SM")
    source = tmp_path / "outline.json"
    source.write_text(json.dumps(outline.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")
    outline_result = PaperOutlineService(cases, artifacts, claims, figures).validate_file(case["case_id"], source)
    workspace = PaperSectionWorkspace(cases, artifacts, claims, figures)
    workspace.initialize(case["case_id"], outline_result["outline_artifact_id"])
    for section in outline.sections:
        workspace.update_draft(
            case["case_id"],
            section.section_id,
            f"# {section.title}\n\n本节已完成结构性工程验收。",
            "human",
        )
    result = PaperConsistencyChecker(cases, artifacts, claims, figures).check(case["case_id"])
    assert result["report"]["gate"] == "PASS"
    assert artifacts.get(case["case_id"], result["report_artifact_id"])["paper_eligible"] is True


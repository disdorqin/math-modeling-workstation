from pathlib import Path

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.problem_ingestion import ProblemIngestionService


def test_problem_ingestion_preserves_original_and_extracts_markdown(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Problem ingestion")
    source = tmp_path / "题目.md"
    source.write_text("# Problem\n\nUse observed data only.", encoding="utf-8")
    result = ProblemIngestionService(cases, ArtifactRegistry(cases)).ingest(case["case_id"], source)
    original = result["original_artifact"]
    extracted = result["extracted_artifact"]
    assert original["artifact_type"] == "problem_original"
    assert extracted["artifact_type"] == "problem_extracted_text"
    assert extracted["upstream"] == [original["artifact_id"]]
    assert (cases.case_root(case["case_id"]) / extracted["path"]).read_text(encoding="utf-8").startswith("# Problem")

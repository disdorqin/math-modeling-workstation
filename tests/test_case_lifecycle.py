from pathlib import Path

import pytest

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.session_manager import SessionManager


def test_case_session_and_input_isolation(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    first = cases.create_case("SM", "First")
    second = cases.create_case("SM", "Second")

    assert first["case_id"] != second["case_id"]
    assert cases.validate_case(first["case_id"])["valid"]
    session = SessionManager(cases).create_session(first["case_id"])
    assert session["case_id"] == first["case_id"]

    source = tmp_path / "data.csv"
    source.write_text("x,y\n1,2\n", encoding="utf-8")
    registry = ArtifactRegistry(cases)
    artifact = registry.ingest_file(first["case_id"], source, "input/data/uploaded", "observed_data")
    assert artifact["sha256"]
    assert registry.verify(first["case_id"])["valid"]
    assert not registry.list_artifacts(second["case_id"])

    source.write_text("x,y\n9,9\n", encoding="utf-8")
    with pytest.raises(FileExistsError):
        registry.ingest_file(first["case_id"], source, "input/data/uploaded", "observed_data")


def test_archive_hides_case_by_default(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "Archive")
    cases.archive_case(case["case_id"])
    assert cases.list_cases() == []
    assert cases.list_cases(include_archived=True)[0]["archived"] is True


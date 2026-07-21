import json
from pathlib import Path

from mathworkstation.case_manager import CaseManager
from mathworkstation.ui_app import _sessions_for_case, _status_counts, _workflow_rows


def test_ui_reads_case_sessions_and_workflow_rows(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "UI")
    case_id = case["case_id"]
    sessions_root = cases.case_root(case_id) / "sessions" / "S01"
    sessions_root.mkdir(parents=True)
    (sessions_root / "session.json").write_text(
        json.dumps({"session_id": "S01", "case_id": case_id, "status": "ACTIVE"}),
        encoding="utf-8",
    )
    sessions = _sessions_for_case(cases, case_id)
    assert sessions[0]["session_id"] == "S01"

    workflow = {
        "nodes": {
            "input": {"status": "SUCCEEDED", "attempts": 1, "last_error": None},
            "review": {"status": "NEEDS_REVIEW", "attempts": 1, "last_error": {"message": "check"}},
        },
        "definitions": {
            "input": {"approval_required": False, "dependencies": []},
            "review": {"approval_required": True, "dependencies": ["input"]},
        },
    }
    assert _status_counts(workflow)["NEEDS_REVIEW"] == 1
    assert _workflow_rows(workflow)[1]["last_error"] == "check"

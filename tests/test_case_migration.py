from pathlib import Path

from mathworkstation.case_manager import CaseManager


def test_case_migration_adds_new_registry_files_idempotently(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Migration")
    root = cases.case_root(case["case_id"])
    (root / "figure_registry.jsonl").unlink()
    (root / "experiment_registry.jsonl").unlink()
    assert not cases.validate_case(case["case_id"])["valid"]
    migrated = cases.migrate_case(case["case_id"])
    assert migrated["valid"]
    assert set(migrated["created_files"]) == {"figure_registry.jsonl", "experiment_registry.jsonl"}
    assert cases.migrate_case(case["case_id"])["created_files"] == []


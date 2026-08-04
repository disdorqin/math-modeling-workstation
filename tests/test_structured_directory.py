"""Tests for structured directory layout (competition-type-year/version).

Verifies that:
1. New create_case with problem_type/year creates structured path
2. Legacy create_case without problem_type/year uses flat path
3. case_root resolves both new and legacy paths
4. list_cases scans both structures
5. Manifest includes new fields when using structured path
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mathworkstation.case_manager import CaseManager


class TestStructuredDirectory:
    """Test new structured directory layout."""

    def test_new_structure_creates_correct_path(self, tmp_path: Path):
        """New structure: output/mcm-c-2024/v1/<case_id>/"""
        manager = CaseManager(tmp_path)
        manifest = manager.create_case(
            competition="MCM",
            title="Test Case",
            problem_type="c",
            year=2024,
            version=1,
        )
        case_id = manifest["case_id"]
        # Should be in output/mcm-c-2024/v1/<case_id>/
        expected_dir = tmp_path / "mcm-c-2024" / "v1" / case_id
        assert expected_dir.is_dir(), f"Expected {expected_dir} to exist"
        # case_root should resolve it
        assert manager.case_root(case_id) == expected_dir

    def test_new_structure_manifest_fields(self, tmp_path: Path):
        """Manifest should include problem_type, year, version when using structured path."""
        manager = CaseManager(tmp_path)
        manifest = manager.create_case(
            competition="MCM",
            title="Test Case",
            problem_type="c",
            year=2024,
            version=2,
        )
        assert manifest["problem_type"] == "c"
        assert manifest["year"] == 2024
        assert manifest["version"] == 2
        assert manifest["directory_structure"] == "structured"

    def test_legacy_structure_creates_flat_path(self, tmp_path: Path):
        """Legacy structure: output/<case_id>/"""
        manager = CaseManager(tmp_path)
        manifest = manager.create_case(
            competition="SM",
            title="Legacy Case",
        )
        case_id = manifest["case_id"]
        # Should be in output/<case_id>/
        expected_dir = tmp_path / case_id
        assert expected_dir.is_dir(), f"Expected {expected_dir} to exist"
        assert manager.case_root(case_id) == expected_dir
        # Legacy manifest should not have new fields
        assert "problem_type" not in manifest
        assert "year" not in manifest

    def test_version_increment(self, tmp_path: Path):
        """Different versions create separate directories."""
        manager = CaseManager(tmp_path)
        m1 = manager.create_case("MCM", "v1 case", problem_type="c", year=2024, version=1)
        m2 = manager.create_case("MCM", "v2 case", problem_type="c", year=2024, version=2)
        root1 = manager.case_root(m1["case_id"])
        root2 = manager.case_root(m2["case_id"])
        assert root1.parent.name == "v1"
        assert root2.parent.name == "v2"
        assert root1 != root2

    def test_case_root_resolves_legacy_path(self, tmp_path: Path):
        """case_root should find cases in legacy flat structure."""
        manager = CaseManager(tmp_path)
        manifest = manager.create_case("SM", "Legacy")
        case_id = manifest["case_id"]
        # Should resolve from flat path
        assert manager.case_root(case_id).is_dir()

    def test_case_root_resolves_structured_path(self, tmp_path: Path):
        """case_root should find cases in structured path."""
        manager = CaseManager(tmp_path)
        manifest = manager.create_case("MCM", "Structured", problem_type="a", year=2023)
        case_id = manifest["case_id"]
        assert manager.case_root(case_id).is_dir()

    def test_list_cases_includes_both_structures(self, tmp_path: Path):
        """list_cases should find cases in both legacy and structured paths."""
        manager = CaseManager(tmp_path)
        # Create one legacy
        m1 = manager.create_case("SM", "Legacy")
        # Create one structured
        m2 = manager.create_case("MCM", "Structured", problem_type="c", year=2024)
        cases = manager.list_cases()
        case_ids = {c["case_id"] for c in cases}
        assert m1["case_id"] in case_ids
        assert m2["case_id"] in case_ids

    def test_case_not_found_raises(self, tmp_path: Path):
        """case_root should raise CaseNotFoundError for missing case."""
        manager = CaseManager(tmp_path)
        from mathworkstation.errors import CaseNotFoundError
        with pytest.raises(CaseNotFoundError):
            manager.case_root("nonexistent-case-id")

    def test_archive_excluded_from_list(self, tmp_path: Path):
        """Archived cases should not appear in list_cases by default."""
        manager = CaseManager(tmp_path)
        manifest = manager.create_case("SM", "To Archive")
        case_id = manifest["case_id"]
        manager.archive_case(case_id)
        cases = manager.list_cases()
        case_ids = {c["case_id"] for c in cases}
        assert case_id not in case_ids

    def test_problem_type_normalization(self, tmp_path: Path):
        """Problem type should be normalized to lowercase."""
        manager = CaseManager(tmp_path)
        manifest = manager.create_case("MCM", "Test", problem_type="C", year=2024)
        assert manifest["problem_type"] == "c"
        # Directory should use lowercase
        case_id = manifest["case_id"]
        root = manager.case_root(case_id)
        assert root.parent.parent.name == "mcm-c-2024"

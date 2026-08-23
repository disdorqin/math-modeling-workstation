"""Tests for Paper Learning Loop (Hermes/KEPA inspired).

Verifies:
1. Lessons storage: add, confirm, reject, list, export
2. Reflection: extract lessons from pipeline logs, refinement, O-award comparison
3. Progressive loading: filter by competition, priority sorting
4. Gate interface: pending → confirmed/rejected
5. End-to-end: reflection → storage → loading
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mathworkstation.paper_lessons import (
    PaperLessonsStore, Lesson, LessonCategory, LessonStatus,
)
from mathworkstation.paper_reflection import PaperReflection
from mathworkstation.paper_lesson_loader import PaperLessonLoader


class TestLessonsStorage:
    """Test paper_lessons.json storage."""

    def test_add_lesson(self, tmp_path: Path):
        store = PaperLessonsStore(tmp_path, "case-001")
        lesson = store.add_lesson(
            category="pitfall",
            competition="mcm-c",
            lesson="C题时间序列数据默认用时间顺序切分防泄漏",
            source_case="case-001",
            tags=["temporal", "split"],
        )
        assert lesson.lesson_id == "lesson-0001"
        assert lesson.status == LessonStatus.PENDING
        assert lesson.category == "pitfall"

    def test_confirm_lesson(self, tmp_path: Path):
        store = PaperLessonsStore(tmp_path, "case-001")
        lesson = store.add_lesson("always", "mcm-c", "test lesson", "case-001")
        confirmed = store.confirm_lesson(lesson.lesson_id)
        assert confirmed.status == LessonStatus.CONFIRMED

    def test_reject_lesson(self, tmp_path: Path):
        store = PaperLessonsStore(tmp_path, "case-001")
        lesson = store.add_lesson("always", "mcm-c", "test lesson", "case-001")
        rejected = store.reject_lesson(lesson.lesson_id)
        assert rejected.status == LessonStatus.REJECTED

    def test_list_lessons_filters(self, tmp_path: Path):
        store = PaperLessonsStore(tmp_path, "case-001")
        store.add_lesson("pitfall", "mcm-c", "pitfall 1", "case-001")
        store.add_lesson("always", "mcm-c", "always 1", "case-001")
        store.add_lesson("pitfall", "cumcm-a", "pitfall 2", "case-001")

        pitfall_c = store.list_lessons(category="pitfall", competition="mcm-c")
        assert len(pitfall_c) == 1

        always = store.list_lessons(category="always")
        assert len(always) == 1

    def test_get_pending(self, tmp_path: Path):
        store = PaperLessonsStore(tmp_path, "case-001")
        store.add_lesson("pitfall", "mcm-c", "pending 1", "case-001")
        store.add_lesson("always", "mcm-c", "pending 2", "case-001")
        store.confirm_lesson("lesson-0001")

        pending = store.get_pending()
        assert len(pending) == 1
        assert pending[0].lesson_id == "lesson-0002"

    def test_export_markdown(self, tmp_path: Path):
        store = PaperLessonsStore(tmp_path, "case-001")
        store.add_lesson("pitfall", "mcm-c", "pitfall lesson", "case-001")
        store.add_lesson("always", "mcm-c", "always lesson", "case-001")
        store.confirm_lesson("lesson-0001")
        store.confirm_lesson("lesson-0002")

        md = store.export_markdown()
        assert "pitfall lesson" in md
        assert "always lesson" in md
        assert "## Pitfall Lessons" in md
        assert "## Always Lessons" in md

    def test_persistence(self, tmp_path: Path):
        store1 = PaperLessonsStore(tmp_path, "case-001")
        store1.add_lesson("pitfall", "mcm-c", "persistent lesson", "case-001")

        # Reload from disk
        store2 = PaperLessonsStore(tmp_path, "case-001")
        assert len(store2.list_lessons()) == 1
        assert store2.list_lessons()[0].lesson == "persistent lesson"

    def test_load_for_paper_competition_filter(self, tmp_path: Path):
        store = PaperLessonsStore(tmp_path)
        store.add_lesson("pitfall", "mcm-c", "mcm-c lesson", "case-001")
        store.add_lesson("pitfall", "cumcm-a", "cumcm-a lesson", "case-001")
        store.add_lesson("always", "mcm-c", "mcm-c always", "case-001")
        store.confirm_lesson("lesson-0001")
        store.confirm_lesson("lesson-0002")
        store.confirm_lesson("lesson-0003")

        mcm_c_lessons = store.load_for_paper("mcm-c")
        assert all(l.competition == "mcm-c" for l in mcm_c_lessons)

    def test_load_for_paper_priority(self, tmp_path: Path):
        store = PaperLessonsStore(tmp_path)
        store.add_lesson("always", "mcm-c", "always lesson", "case-001")
        store.add_lesson("pitfall", "mcm-c", "pitfall lesson", "case-001")
        store.add_lesson("recent", "mcm-c", "recent lesson", "case-001")
        store.confirm_lesson("lesson-0001")
        store.confirm_lesson("lesson-0002")
        store.confirm_lesson("lesson-0003")

        lessons = store.load_for_paper("mcm-c")
        # Pitfall should come first
        assert lessons[0].category == "pitfall"
        assert lessons[1].category == "always"
        assert lessons[2].category == "recent"

    def test_get_stats(self, tmp_path: Path):
        store = PaperLessonsStore(tmp_path)
        store.add_lesson("pitfall", "mcm-c", "p1", "case-001")
        store.add_lesson("always", "mcm-c", "a1", "case-001")
        store.confirm_lesson("lesson-0001")

        stats = store.get_stats()
        assert stats["total"] == 2
        assert stats["by_category"]["pitfall"] == 1
        assert stats["by_status"]["pending"] == 1
        assert stats["by_status"]["confirmed"] == 1


class TestPaperReflection:
    """Test reflection module."""

    def test_reflect_basic(self, tmp_path: Path):
        reflection = PaperReflection(tmp_path)
        result = reflection.reflect(
            case_id="case-001",
            competition="mcm-c",
            refinement_stages=3,
            figures_count=5,
            consistency_gate="PASS",
        )
        assert result["candidate_count"] > 0
        assert result["case_id"] == "case-001"

    def test_reflect_with_errors(self, tmp_path: Path):
        reflection = PaperReflection(tmp_path)
        logs = [
            {"level": "error", "msg": "PDF parsing failed"},
            {"level": "warn", "msg": "temporal split review"},
        ]
        result = reflection.reflect(
            case_id="case-001",
            competition="mcm-c",
            pipeline_logs=logs,
        )
        assert result["candidate_count"] >= 2  # error + warning lessons

    def test_reflect_o_award_comparison(self, tmp_path: Path):
        reflection = PaperReflection(tmp_path)
        paper = "This is our paper with abstract and methodology sections."
        o_award = "This is the O-award paper with abstract, methodology, and conclusion sections."
        result = reflection.reflect(
            case_id="case-001",
            competition="mcm-c",
            paper_content=paper,
            o_award_content=o_award,
        )
        # Should detect missing conclusion
        assert result["candidate_count"] > 0

    def test_reflect_stores_as_pending(self, tmp_path: Path):
        reflection = PaperReflection(tmp_path)
        result = reflection.reflect(
            case_id="case-001",
            competition="mcm-c",
            refinement_stages=5,
        )
        # Verify lessons are stored as pending
        store = PaperLessonsStore(tmp_path, "case-001")
        pending = store.get_pending()
        assert len(pending) == result["candidate_count"]


class TestPaperLessonLoader:
    """Test progressive loading."""

    def test_load_for_new_paper(self, tmp_path: Path):
        store = PaperLessonsStore(tmp_path)
        store.add_lesson("pitfall", "mcm-c", "pitfall 1", "case-001")
        store.add_lesson("always", "mcm-c", "always 1", "case-001")
        store.add_lesson("recent", "mcm-c", "recent 1", "case-001")
        store.confirm_lesson("lesson-0001")
        store.confirm_lesson("lesson-0002")
        store.confirm_lesson("lesson-0003")

        loader = PaperLessonLoader(store)
        lessons = loader.load_for_new_paper("mcm-c")
        assert len(lessons) == 3
        # Pitfall first
        assert lessons[0].category == "pitfall"

    def test_format_for_prompt(self, tmp_path: Path):
        store = PaperLessonsStore(tmp_path)
        store.add_lesson("pitfall", "mcm-c", "test lesson", "case-001")
        store.confirm_lesson("lesson-0001")

        loader = PaperLessonLoader(store)
        lessons = loader.load_for_new_paper("mcm-c")
        formatted = loader.format_for_prompt(lessons)
        assert "test lesson" in formatted
        assert "⚠️" in formatted  # pitfall marker

    def test_format_for_model_plan(self, tmp_path: Path):
        store = PaperLessonsStore(tmp_path)
        store.add_lesson("pitfall", "mcm-c", "model plan lesson", "case-001")
        store.confirm_lesson("lesson-0001")

        loader = PaperLessonLoader(store)
        formatted = loader.format_for_model_plan("mcm-c")
        assert "model plan lesson" in formatted

    def test_format_empty(self, tmp_path: Path):
        store = PaperLessonsStore(tmp_path)
        loader = PaperLessonLoader(store)
        formatted = loader.format_for_model_plan("mcm-c")
        assert formatted == ""

    def test_get_summary(self, tmp_path: Path):
        store = PaperLessonsStore(tmp_path)
        store.add_lesson("pitfall", "mcm-c", "p1", "case-001")
        store.add_lesson("always", "mcm-c", "a1", "case-001")
        store.confirm_lesson("lesson-0001")
        store.confirm_lesson("lesson-0002")

        loader = PaperLessonLoader(store)
        summary = loader.get_summary("mcm-c")
        assert summary["total_lessons"] == 2
        assert "pitfall" in summary["by_category"]

    def test_competition_prefix_match(self, tmp_path: Path):
        """mcm lessons should load for mcm-c."""
        store = PaperLessonsStore(tmp_path)
        store.add_lesson("always", "mcm", "mcm general", "case-001")
        store.add_lesson("always", "mcm-c", "mcm-c specific", "case-001")
        store.confirm_lesson("lesson-0001")
        store.confirm_lesson("lesson-0002")

        loader = PaperLessonLoader(store)
        lessons = loader.load_for_new_paper("mcm-c")
        assert len(lessons) == 2


class TestEndToEnd:
    """End-to-end test: reflection → storage → loading."""

    def test_full_cycle(self, tmp_path: Path):
        # 1. Reflection produces candidate lessons
        reflection = PaperReflection(tmp_path)
        result = reflection.reflect(
            case_id="case-e2e",
            competition="mcm-c",
            refinement_stages=5,
            figures_count=6,
            consistency_gate="PASS",
        )
        assert result["candidate_count"] > 0

        # 2. Gate: confirm some lessons
        store = PaperLessonsStore(tmp_path, "case-e2e")
        pending = store.get_pending()
        assert len(pending) > 0
        store.confirm_lesson(pending[0].lesson_id)
        if len(pending) > 1:
            store.reject_lesson(pending[1].lesson_id)

        # 3. Progressive loading for new paper
        loader = PaperLessonLoader(store)
        lessons = loader.load_for_new_paper("mcm-c")
        confirmed = [l for l in lessons if l.status == "confirmed"]
        assert len(confirmed) >= 1

        # 4. Export markdown
        md = store.export_markdown()
        assert len(md) > 0

    def test_no_double_nesting_when_root_is_case_dir(self, tmp_path: Path):
        """PaperLessonsStore should not double-nest when root already ends with case_id."""
        case_dir = tmp_path / "my-case-001"
        case_dir.mkdir()
        store = PaperLessonsStore(case_dir, "my-case-001")
        # Should be at <case_dir>/memory/paper_lessons.json, NOT <case_dir>/my-case-001/memory/...
        assert store.lessons_path == case_dir / "memory" / "paper_lessons.json"
        store.add_lesson("always", "mcm-c", "test", "my-case-001")
        assert store.lessons_path.is_file()

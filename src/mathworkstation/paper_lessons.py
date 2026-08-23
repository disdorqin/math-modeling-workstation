"""Paper Lessons storage — cross-paper learning (Hermes/KEPA inspired).

Stores generalized writing lessons in JSON (machine-readable) with
markdown export for human review. Lessons are categorized as:
- always: loaded for every paper (best practices)
- pitfall: common mistakes to avoid
- recent: newly learned, may still be relevant

Location: <case_root>/memory/paper_lessons.json (per-case)
          or global at output/paper_lessons.json (shared across cases)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path
from typing import Any

from .io_utils import atomic_write_json, atomic_write_text, now_iso, read_json


class LessonCategory(str, Enum):
    ALWAYS = "always"
    PITFALL = "pitfall"
    RECENT = "recent"


class LessonStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    REJECTED = "rejected"


@dataclass
class Lesson:
    lesson_id: str
    category: str  # LessonCategory value
    competition: str  # e.g. "mcm-c", "cumcm-a"
    lesson: str  # the "how to" generalized lesson
    source_case: str  # case_id where this was learned
    source_section: str = ""  # which paper section triggered this
    date: str = field(default_factory=now_iso)
    status: str = LessonStatus.PENDING
    confidence: float = 1.0  # 0-1, how confident we are
    tags: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Lesson:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


class PaperLessonsStore:
    """Manages paper lessons for a case or globally."""

    def __init__(self, root: Path, case_id: str | None = None) -> None:
        self.root = root
        self.case_id = case_id
        if case_id:
            # Avoid double-nesting: if root already ends with case_id, don't append again
            if root.name == case_id:
                self.lessons_path = root / "memory" / "paper_lessons.json"
            else:
                self.lessons_path = root / case_id / "memory" / "paper_lessons.json"
        else:
            self.lessons_path = root / "paper_lessons.json"
        self.lessons_path.parent.mkdir(parents=True, exist_ok=True)
        self._lessons: list[Lesson] = self._load()

    def _load(self) -> list[Lesson]:
        if not self.lessons_path.is_file():
            return []
        try:
            data = json.loads(self.lessons_path.read_text(encoding="utf-8"))
            return [Lesson.from_dict(item) for item in data.get("lessons", [])]
        except (json.JSONDecodeError, KeyError):
            return []

    def _save(self) -> None:
        data = {
            "schema_version": 1,
            "updated_at": now_iso(),
            "total_lessons": len(self._lessons),
            "lessons": [lesson.to_dict() for lesson in self._lessons],
        }
        atomic_write_json(self.lessons_path, data)

    def add_lesson(
        self,
        category: str,
        competition: str,
        lesson: str,
        source_case: str,
        source_section: str = "",
        status: str = LessonStatus.PENDING,
        confidence: float = 1.0,
        tags: list[str] | None = None,
    ) -> Lesson:
        """Add a new lesson (default status=pending for gate review)."""
        lesson_id = f"lesson-{len(self._lessons) + 1:04d}"
        new_lesson = Lesson(
            lesson_id=lesson_id,
            category=category,
            competition=competition,
            lesson=lesson,
            source_case=source_case,
            source_section=source_section,
            status=status,
            confidence=confidence,
            tags=tags or [],
        )
        self._lessons.append(new_lesson)
        self._save()
        return new_lesson

    def confirm_lesson(self, lesson_id: str) -> Lesson | None:
        """Gate: confirm a pending lesson."""
        for lesson in self._lessons:
            if lesson.lesson_id == lesson_id:
                lesson.status = LessonStatus.CONFIRMED
                self._save()
                return lesson
        return None

    def reject_lesson(self, lesson_id: str) -> Lesson | None:
        """Gate: reject a pending lesson."""
        for lesson in self._lessons:
            if lesson.lesson_id == lesson_id:
                lesson.status = LessonStatus.REJECTED
                self._save()
                return lesson
        return None

    def list_lessons(
        self,
        category: str | None = None,
        competition: str | None = None,
        status: str | None = None,
    ) -> list[Lesson]:
        """List lessons with optional filters."""
        results = self._lessons
        if category:
            results = [l for l in results if l.category == category]
        if competition:
            results = [l for l in results if l.competition == competition]
        if status:
            results = [l for l in results if l.status == status]
        return results

    def get_pending(self) -> list[Lesson]:
        """Get all pending lessons awaiting gate review."""
        return self.list_lessons(status=LessonStatus.PENDING)

    def export_markdown(self, output_path: Path | None = None) -> str:
        """Export lessons as human-readable markdown."""
        lines = ["# Paper Lessons\n"]
        lines.append(f"_Updated: {now_iso()}_\n")

        for category in [LessonCategory.ALWAYS, LessonCategory.PITFALL, LessonCategory.RECENT]:
            cat_lessons = [l for l in self._lessons if l.category == category and l.status == LessonStatus.CONFIRMED]
            if not cat_lessons:
                continue
            lines.append(f"\n## {category.value.title()} Lessons\n")
            for lesson in cat_lessons:
                lines.append(f"- **[{lesson.lesson_id}]** ({lesson.competition}) {lesson.lesson}")
                if lesson.source_case:
                    lines.append(f"  - Source: `{lesson.source_case}`")
                if lesson.tags:
                    lines.append(f"  - Tags: {', '.join(lesson.tags)}")

        md_content = "\n".join(lines) + "\n"
        if output_path:
            atomic_write_text(output_path, md_content)
        return md_content

    def load_for_paper(self, competition: str, max_lessons: int = 20) -> list[Lesson]:
        """Progressive loading: select relevant lessons for a new paper.

        Priority: pitfall > always > recent, filtered by competition.
        C题 lessons get priority (loaded first).
        """
        confirmed = [l for l in self._lessons if l.status == LessonStatus.CONFIRMED]

        # Filter by competition (exact match or prefix match)
        relevant = [
            l for l in confirmed
            if l.competition == competition or l.competition.startswith(competition.split("-")[0])
        ]

        # Sort by priority: pitfall first, then always, then recent
        priority = {LessonCategory.PITFALL: 0, LessonCategory.ALWAYS: 1, LessonCategory.RECENT: 2}
        relevant.sort(key=lambda l: (priority.get(l.category, 99), -l.confidence))

        return relevant[:max_lessons]

    def get_stats(self) -> dict[str, Any]:
        """Get lesson statistics."""
        by_category = {}
        by_status = {}
        by_competition = {}
        for lesson in self._lessons:
            by_category[lesson.category] = by_category.get(lesson.category, 0) + 1
            by_status[lesson.status] = by_status.get(lesson.status, 0) + 1
            by_competition[lesson.competition] = by_competition.get(lesson.competition, 0) + 1
        return {
            "total": len(self._lessons),
            "by_category": by_category,
            "by_status": by_status,
            "by_competition": by_competition,
        }

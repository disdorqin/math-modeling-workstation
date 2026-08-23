"""Paper Lesson Loader — progressive loading for new papers.

Loads relevant lessons from the store and formats them for injection
into model_plan / paper_section prompts. Priority: C题 first, pitfall > always > recent.
"""

from __future__ import annotations

from typing import Any

from .paper_lessons import PaperLessonsStore, Lesson, LessonCategory


class PaperLessonLoader:
    """Loads and formats lessons for prompt injection."""

    def __init__(self, store: PaperLessonsStore) -> None:
        self.store = store

    def load_for_new_paper(
        self,
        competition: str,
        max_lessons: int = 15,
        include_pitfalls: bool = True,
        include_always: bool = True,
        include_recent: bool = True,
    ) -> list[Lesson]:
        """Load relevant lessons for a new paper.

        Args:
            competition: e.g. "mcm-c", "cumcm-a"
            max_lessons: maximum lessons to load
            include_pitfalls: include pitfall lessons (highest priority)
            include_always: include always lessons
            include_recent: include recent lessons

        Returns:
            Sorted list of relevant lessons
        """
        confirmed = self.store.list_lessons(status="confirmed")

        # Filter by competition (exact or prefix match)
        relevant = []
        for lesson in confirmed:
            if lesson.competition == competition:
                relevant.append(lesson)
            elif lesson.competition.startswith(competition.split("-")[0]):
                relevant.append(lesson)

        # Filter by category
        filtered = []
        for lesson in relevant:
            if lesson.category == LessonCategory.PITFALL and include_pitfalls:
                filtered.append(lesson)
            elif lesson.category == LessonCategory.ALWAYS and include_always:
                filtered.append(lesson)
            elif lesson.category == LessonCategory.RECENT and include_recent:
                filtered.append(lesson)

        # Sort: pitfall first, then always, then recent; by confidence descending
        priority = {LessonCategory.PITFALL: 0, LessonCategory.ALWAYS: 1, LessonCategory.RECENT: 2}
        filtered.sort(key=lambda l: (priority.get(l.category, 99), -l.confidence))

        return filtered[:max_lessons]

    def format_for_prompt(self, lessons: list[Lesson]) -> str:
        """Format lessons as text for injection into prompts."""
        if not lessons:
            return ""

        lines = ["## 写作经验教训 (Paper Lessons)\n"]
        lines.append("_从过往论文中提炼的经验,请在写作中参考:_\n")

        for lesson in lessons:
            prefix = "⚠️" if lesson.category == LessonCategory.PITFALL else "✅"
            lines.append(f"{prefix} [{lesson.category}] {lesson.lesson}")

        return "\n".join(lines)

    def format_for_model_plan(self, competition: str) -> str:
        """Format lessons specifically for model_plan prompt injection."""
        lessons = self.load_for_new_paper(competition, max_lessons=10)
        if not lessons:
            return ""
        return self.format_for_prompt(lessons)

    def format_for_paper_section(self, competition: str, section: str) -> str:
        """Format lessons for a specific paper section."""
        all_lessons = self.load_for_new_paper(competition, max_lessons=15)

        # Filter to section-relevant lessons
        section_lessons = [
            l for l in all_lessons
            if not l.source_section or l.source_section == section or l.category == LessonCategory.PITFALL
        ]

        return self.format_for_prompt(section_lessons[:10])

    def get_summary(self, competition: str) -> dict[str, Any]:
        """Get summary of available lessons for a competition."""
        lessons = self.store.load_for_paper(competition)
        by_category = {}
        for lesson in lessons:
            by_category[lesson.category] = by_category.get(lesson.category, 0) + 1
        return {
            "competition": competition,
            "total_lessons": len(lessons),
            "by_category": by_category,
            "top_pitfalls": [
                l.lesson for l in lessons
                if l.category == LessonCategory.PITFALL
            ][:3],
        }

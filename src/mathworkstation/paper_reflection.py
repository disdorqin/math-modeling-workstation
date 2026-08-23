"""Paper Reflection — post-final_review lesson extraction.

After a paper passes final_review, this module:
1. Compares our paper with O-award reference (if available)
2. Extracts generalized lessons from the experience
3. Outputs candidate lessons (pending gate review)

Triggered by: final_review approval in auto_pipeline.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .io_utils import atomic_write_json, atomic_write_text, now_iso, read_json
from .paper_lessons import PaperLessonsStore, LessonCategory, LessonStatus


class PaperReflection:
    """Extracts lessons from a completed paper for cross-paper learning."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def reflect(
        self,
        case_id: str,
        competition: str,
        paper_content: str | None = None,
        o_award_content: str | None = None,
        pipeline_logs: list[dict[str, Any]] | None = None,
        refinement_stages: int = 0,
        figures_count: int = 0,
        consistency_gate: str = "unknown",
    ) -> dict[str, Any]:
        """Run reflection on a completed paper.

        Returns candidate lessons (pending gate review by claude_code).
        """
        lessons_store = PaperLessonsStore(self.root, case_id)
        candidates: list[dict[str, Any]] = []

        # 1. Pipeline experience lessons
        if pipeline_logs:
            candidates.extend(self._extract_pipeline_lessons(case_id, competition, pipeline_logs))

        # 2. Refinement lessons
        if refinement_stages > 0:
            candidates.extend(self._extract_refinement_lessons(
                case_id, competition, refinement_stages
            ))

        # 3. Figure/composition lessons
        if figures_count > 0:
            candidates.append({
                "category": LessonCategory.ALWAYS,
                "competition": competition,
                "lesson": f"本篇生成了 {figures_count} 张图,确保每张图在正文被引用",
                "source_case": case_id,
                "source_section": "figures",
                "tags": ["figures", "citation"],
            })

        # 4. O-award comparison lessons
        if o_award_content and paper_content:
            candidates.extend(self._compare_with_o_award(
                case_id, competition, paper_content, o_award_content
            ))

        # 5. Consistency gate lessons
        if consistency_gate != "unknown":
            candidates.append({
                "category": LessonCategory.ALWAYS,
                "competition": competition,
                "lesson": f"consistency gate 结果为 {consistency_gate},确保摘要-正文-结论一致",
                "source_case": case_id,
                "source_section": "consistency",
                "tags": ["consistency", "gate"],
            })

        # Store all candidates as pending
        stored = []
        for candidate in candidates:
            lesson = lessons_store.add_lesson(
                category=candidate["category"],
                competition=candidate["competition"],
                lesson=candidate["lesson"],
                source_case=candidate["source_case"],
                source_section=candidate.get("source_section", ""),
                status=LessonStatus.PENDING,
                confidence=candidate.get("confidence", 0.8),
                tags=candidate.get("tags", []),
            )
            stored.append(lesson.to_dict())

        return {
            "case_id": case_id,
            "competition": competition,
            "candidate_count": len(stored),
            "candidates": stored,
            "reflection_at": now_iso(),
        }

    def _extract_pipeline_lessons(
        self, case_id: str, competition: str, logs: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Extract lessons from pipeline execution logs."""
        lessons = []
        error_logs = [l for l in logs if l.get("level") == "error"]
        warn_logs = [l for l in logs if l.get("level") == "warn"]

        if error_logs:
            error_msgs = [l.get("msg", "") for l in error_logs[:3]]
            lessons.append({
                "category": LessonCategory.PITFALL,
                "competition": competition,
                "lesson": f"流水线遇到 {len(error_logs)} 个错误,首次运行时关注: {'; '.join(error_msgs[:2])}",
                "source_case": case_id,
                "source_section": "pipeline",
                "tags": ["pipeline", "error"],
                "confidence": 0.9,
            })

        if warn_logs:
            lessons.append({
                "category": LessonCategory.PITFALL,
                "competition": competition,
                "lesson": f"流水线有 {len(warn_logs)} 个警告,检查数据质量和研究审查",
                "source_case": case_id,
                "source_section": "pipeline",
                "tags": ["pipeline", "warning"],
                "confidence": 0.7,
            })

        return lessons

    def _extract_refinement_lessons(
        self, case_id: str, competition: str, stages: int
    ) -> list[dict[str, Any]]:
        """Extract lessons from refinement stages."""
        lessons = []
        if stages >= 5:
            lessons.append({
                "category": LessonCategory.ALWAYS,
                "competition": competition,
                "lesson": f"打磨经过 {stages} 个 Stage,高质量论文需要多轮打磨(摘要→人性化→图表→符号→最终)",
                "source_case": case_id,
                "source_section": "refinement",
                "tags": ["refinement", "quality"],
                "confidence": 0.85,
            })
        elif stages > 0:
            lessons.append({
                "category": LessonCategory.RECENT,
                "competition": competition,
                "lesson": f"打磨经过 {stages} 个 Stage,增加打磨轮次可能提升质量",
                "source_case": case_id,
                "source_section": "refinement",
                "tags": ["refinement"],
                "confidence": 0.7,
            })
        return lessons

    def _compare_with_o_award(
        self, case_id: str, competition: str, paper: str, o_award: str
    ) -> list[dict[str, Any]]:
        """Compare our paper with O-award reference and extract lessons."""
        lessons = []
        paper_lower = paper.lower()
        o_award_lower = o_award.lower()

        # Check for key sections present in O-award but missing in ours
        key_sections = ["abstract", "introduction", "methodology", "results", "conclusion"]
        for section in key_sections:
            if section in o_award_lower and section not in paper_lower:
                lessons.append({
                    "category": LessonCategory.PITFALL,
                    "competition": competition,
                    "lesson": f"O奖论文有 {section} 部分,确保论文包含完整结构",
                    "source_case": case_id,
                    "source_section": section,
                    "tags": ["structure", "o-award"],
                    "confidence": 0.9,
                })

        # Check for visualization presence
        o_award_has_figure = any(marker in o_award_lower for marker in ["figure", "fig.", "chart", "plot"])
        paper_has_figure = any(marker in paper_lower for marker in ["figure", "fig.", "chart", "plot"])
        if o_award_has_figure and not paper_has_figure:
            lessons.append({
                "category": LessonCategory.PITFALL,
                "competition": competition,
                "lesson": "O奖论文有图表可视化,确保论文包含数据图表",
                "source_case": case_id,
                "source_section": "figures",
                "tags": ["figures", "o-award"],
                "confidence": 0.85,
            })

        # Length comparison
        if len(paper) < len(o_award) * 0.5:
            lessons.append({
                "category": LessonCategory.PITFALL,
                "competition": competition,
                "lesson": f"论文篇幅({len(paper)}字)仅为O奖({len(o_award)}字)的{len(paper)*100//len(o_award)}%,增加内容深度",
                "source_case": case_id,
                "source_section": "length",
                "tags": ["length", "o-award"],
                "confidence": 0.8,
            })

        return lessons

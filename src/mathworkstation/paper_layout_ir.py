from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .paper_art_direction import PageCompositionPlan


BlockKind = Literal[
    "heading",
    "paragraph",
    "display_math",
    "figure",
    "table",
    "bullet_list",
    "blank",
]


class LayoutIntent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    keep_with_next: bool = False
    avoid_page_break_inside: bool = False
    placement: str = ""
    width_fraction: float | None = None
    max_height_fraction: float | None = None
    pairable: bool = False
    preferred_anchor: str = ""


class PaperLayoutBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")

    block_id: str
    kind: BlockKind
    text: str = ""
    level: int = 0
    alt: str = ""
    path: str = ""
    rows: list[str] = Field(default_factory=list)
    items: list[str] = Field(default_factory=list)
    intent: LayoutIntent = Field(default_factory=LayoutIntent)


class PaperLayoutIR(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    title: str
    blocks: list[PaperLayoutBlock]


class PaperLayoutIRBuilder:
    """Parse accepted paper Markdown into explicit layout blocks.

    This is intentionally a document-layer IR. It preserves text and data exactly
    while making page-composition decisions addressable by block id.
    """

    IMAGE_RE = re.compile(r"^!\[(?P<alt>.*?)\]\((?P<path>.*?)\)\s*$")
    HEADING_RE = re.compile(r"^(?P<level>#{1,4})\s+(?P<title>.+?)\s*$")

    def build(
        self,
        markdown: str,
        *,
        composition_plan: PageCompositionPlan | None = None,
    ) -> PaperLayoutIR:
        lines = markdown.splitlines()
        title = "Mathematical Modeling Paper"
        blocks: list[PaperLayoutBlock] = []
        index = 0
        counter = 0

        def add(kind: BlockKind, **kwargs: object) -> None:
            nonlocal counter
            counter += 1
            blocks.append(PaperLayoutBlock(block_id=f"block-{counter:04d}", kind=kind, **kwargs))

        while index < len(lines):
            raw = lines[index]
            stripped = raw.strip()

            heading = self.HEADING_RE.match(raw)
            if heading:
                level = len(heading.group("level"))
                text = heading.group("title").strip()
                if level == 1 and title == "Mathematical Modeling Paper":
                    title = text
                add(
                    "heading",
                    text=text,
                    level=level,
                    intent=LayoutIntent(keep_with_next=True, avoid_page_break_inside=True),
                )
                index += 1
                continue

            if stripped == "$$":
                math_lines: list[str] = []
                index += 1
                while index < len(lines) and lines[index].strip() != "$$":
                    math_lines.append(lines[index])
                    index += 1
                if index < len(lines):
                    index += 1
                add(
                    "display_math",
                    text="\n".join(math_lines),
                    intent=LayoutIntent(avoid_page_break_inside=True),
                )
                continue

            image = self.IMAGE_RE.match(raw)
            if image:
                path = image.group("path")
                composition = composition_plan.figure_for_path(path) if composition_plan is not None else None
                add(
                    "figure",
                    alt=image.group("alt"),
                    path=path,
                    intent=LayoutIntent(
                        avoid_page_break_inside=True,
                        placement=composition.placement if composition is not None else "htbp",
                        width_fraction=composition.width_fraction if composition is not None else 0.92,
                        max_height_fraction=composition.max_height_fraction if composition is not None else 0.43,
                        pairable=composition.pairable if composition is not None else False,
                        preferred_anchor=composition.preferred_anchor if composition is not None else "argument",
                    ),
                )
                index += 1
                continue

            if stripped.startswith("|") and index + 1 < len(lines) and _is_markdown_separator(lines[index + 1]):
                rows: list[str] = []
                while index < len(lines) and lines[index].strip().startswith("|"):
                    rows.append(lines[index])
                    index += 1
                add("table", rows=rows, intent=LayoutIntent(avoid_page_break_inside=False))
                continue

            if stripped.startswith("- "):
                items: list[str] = []
                while index < len(lines) and lines[index].strip().startswith("- "):
                    items.append(lines[index].strip()[2:].strip())
                    index += 1
                add("bullet_list", items=items, intent=LayoutIntent(avoid_page_break_inside=True))
                continue

            if not stripped:
                add("blank")
                index += 1
                continue

            add("paragraph", text=raw)
            index += 1

        return PaperLayoutIR(title=title, blocks=blocks)


def _is_markdown_separator(line: str) -> bool:
    cells = _split_markdown_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def _split_markdown_row(line: str) -> list[str]:
    text = line.strip().strip("|")
    return [cell.strip() for cell in text.split("|")]

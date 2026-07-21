from __future__ import annotations

from pathlib import Path
from typing import Any

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .io_utils import atomic_write_text
from .paths import resolve_within


class ProblemIngestionService:
    def __init__(self, cases: CaseManager, artifacts: ArtifactRegistry) -> None:
        self.cases = cases
        self.artifacts = artifacts

    def ingest(self, case_id: str, source: str | Path) -> dict[str, Any]:
        source_path = Path(source).resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        original = self.artifacts.ingest_file(
            case_id,
            source_path,
            "input/problem/original",
            "problem_original",
        )
        text = self._extract(source_path)
        root = self.cases.case_root(case_id)
        extracted_name = _safe_stem(source_path.stem) + ".md"
        extracted_path = resolve_within(root, f"input/problem/extracted/{extracted_name}")
        atomic_write_text(extracted_path, text.rstrip() + "\n")
        extracted = self.artifacts.register_existing(
            case_id,
            extracted_path.relative_to(root).as_posix(),
            "problem_extracted_text",
            "problem_ingestion",
            upstream=[original["artifact_id"]],
        )
        return {
            "original_artifact": original,
            "extracted_artifact": extracted,
            "characters": len(text),
            "format": source_path.suffix.lower().lstrip(".") or "text",
        }

    @staticmethod
    def _extract(source: Path) -> str:
        suffix = source.suffix.lower()
        if suffix in {".txt", ".md", ".markdown"}:
            return source.read_text(encoding="utf-8-sig")
        if suffix == ".pdf":
            try:
                from pypdf import PdfReader
            except ImportError as error:
                raise RuntimeError("PDF ingestion requires optional dependency: pypdf") from error
            reader = PdfReader(str(source))
            return "\n\n".join(page.extract_text() or "" for page in reader.pages)
        if suffix == ".docx":
            try:
                from docx import Document
            except ImportError as error:
                raise RuntimeError("DOCX ingestion requires optional dependency: python-docx") from error
            document = Document(str(source))
            return "\n\n".join(paragraph.text for paragraph in document.paragraphs)
        raise ValueError("problem file must be .txt, .md, .markdown, .pdf, or .docx")


def _safe_stem(value: str) -> str:
    sanitized = "".join(character if character.isalnum() or character in "._-" else "_" for character in value)
    return sanitized[:100] or "problem"

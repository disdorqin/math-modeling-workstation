from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
from typing import Literal


PdfTextBackend = Literal["pymupdf", "pypdf", "pdftotext"]


def extract_pdf_text(path: str | Path, *, max_pages: int | None = None) -> tuple[str, PdfTextBackend]:
    """Extract Unicode text from an excellent-paper PDF without OCR.

    CUMCM PDFs frequently embed Chinese fonts in a way that Poppler's
    ``pdftotext`` cannot map back to Unicode even though a usable text layer is
    present. PyMuPDF and pypdf often recover the embedded ToUnicode mapping.

    This helper intentionally does *not* OCR. If neither parser recovers useful
    text, callers must mark text-layer extraction unavailable and route the PDF
    to the later visual/OCR review path rather than fabricating a full-text
    benchmark from empty text.
    """

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)

    attempts: list[str] = []
    try:
        import fitz  # type: ignore

        document = fitz.open(source)
        limit = len(document) if max_pages is None else min(len(document), max_pages)
        text = "\n".join(document[index].get_text("text") for index in range(limit))
        document.close()
        if _text_layer_is_usable(text):
            return text, "pymupdf"
        attempts.append("pymupdf:unusable_text_layer")
    except Exception as exc:  # optional extraction backend
        attempts.append(f"pymupdf:{type(exc).__name__}")

    try:
        from pypdf import PdfReader  # type: ignore

        reader = PdfReader(str(source))
        limit = len(reader.pages) if max_pages is None else min(len(reader.pages), max_pages)
        text = "\n".join((reader.pages[index].extract_text() or "") for index in range(limit))
        if _text_layer_is_usable(text):
            return text, "pypdf"
        attempts.append("pypdf:unusable_text_layer")
    except Exception as exc:  # optional extraction backend
        attempts.append(f"pypdf:{type(exc).__name__}")

    executable = shutil.which("pdftotext")
    if executable:
        try:
            command = [executable, "-enc", "UTF-8"]
            if max_pages is not None:
                command.extend(["-f", "1", "-l", str(max(1, int(max_pages)))])
            command.extend([str(source), "-"])
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=45,
                check=False,
            )
            text = completed.stdout or ""
            if completed.returncode == 0 and _text_layer_is_usable(text):
                return text, "pdftotext"
            attempts.append(f"pdftotext:unusable_or_rc_{completed.returncode}")
        except Exception as exc:  # optional local CLI fallback
            attempts.append(f"pdftotext:{type(exc).__name__}")
    else:
        attempts.append("pdftotext:not_installed")

    raise ValueError("PDF_UNICODE_TEXT_LAYER_UNAVAILABLE:" + ";".join(attempts))


def pdf_page_count(path: str | Path) -> int:
    """Return page count using the same non-OCR parser stack."""

    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    try:
        import fitz  # type: ignore

        document = fitz.open(source)
        count = len(document)
        document.close()
        return int(count)
    except Exception:
        from pypdf import PdfReader  # type: ignore

        return int(len(PdfReader(str(source)).pages))


def _text_layer_is_usable(text: str) -> bool:
    compact = "".join(text.split())
    if len(compact) < 200:
        return False
    semantic = sum(character.isalpha() or "\u4e00" <= character <= "\u9fff" for character in compact)
    return semantic >= 100

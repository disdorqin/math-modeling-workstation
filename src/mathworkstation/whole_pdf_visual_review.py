from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import fitz
from PIL import Image, ImageDraw
from pydantic import BaseModel, ConfigDict, Field

from .io_utils import atomic_write_json, now_iso


FindingSeverity = Literal["INFO", "REVIEW"]
StructuralGate = Literal["PASS", "REVIEW"]
VisionGate = Literal["REVIEW_PENDING", "PASS", "REVISE", "REJECT"]


class PDFVisualFinding(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int
    code: str
    severity: FindingSeverity
    detail: str
    repair_hint: str


class PDFPageVisualMetrics(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page: int
    page_role: Literal["NORMAL", "CONTENTS", "SUMMARY", "REFERENCES", "AI_USE_REPORT"] = "NORMAL"
    width_pt: float
    height_pt: float
    text_chars: int
    text_blocks: int
    image_count: int
    image_area_ratio: float = Field(ge=0.0)
    ink_density: float = Field(ge=0.0, le=1.0)
    edge_ink_density: float = Field(ge=0.0, le=1.0)
    rendered_path: str


class WholePDFVisualAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: int = 1
    case_id: str
    pdf_path: str
    page_count: int
    structural_gate: StructuralGate
    vision_gate: VisionGate
    metrics: list[PDFPageVisualMetrics]
    findings: list[PDFVisualFinding]
    contact_sheet_path: str
    reviewed_at: str


class WholePDFVisualReviewer:
    """Render and structurally inspect a complete competition PDF.

    The deterministic layer catches layout pathologies cheaply. It deliberately
    does not claim aesthetic or semantic vision review; `vision_gate` remains
    REVIEW_PENDING until an actual multimodal or human reviewer records a result.
    """

    def __init__(self, cases: Any, artifacts: Any) -> None:
        self.cases = cases
        self.artifacts = artifacts

    def review(self, case_id: str, pdf_path: str | Path, *, dpi: int = 110) -> dict[str, Any]:
        source = Path(pdf_path).resolve()
        if not source.is_file():
            raise FileNotFoundError(source)
        root = self.cases.case_root(case_id)
        review_dir = root / "review" / "pdf_visual"
        pages_dir = review_dir / "pages"
        pages_dir.mkdir(parents=True, exist_ok=True)

        document = fitz.open(source)
        metrics: list[PDFPageVisualMetrics] = []
        findings: list[PDFVisualFinding] = []
        rendered_paths: list[Path] = []
        scale = dpi / 72.0

        for page_index, page in enumerate(document, start=1):
            page_rect = page.rect
            text = page.get_text("text") or ""
            text_blocks = [block for block in page.get_text("blocks") if str(block[4]).strip()]
            image_rects = []
            for image in page.get_images(full=True):
                xref = int(image[0])
                try:
                    image_rects.extend(page.get_image_rects(xref))
                except Exception:
                    continue
            page_area = max(1.0, float(page_rect.width * page_rect.height))
            image_area = sum(max(0.0, float(rect.width * rect.height)) for rect in image_rects)
            image_area_ratio = min(1.5, image_area / page_area)

            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            rendered = pages_dir / f"page-{page_index:03d}.png"
            pix.save(str(rendered))
            rendered_paths.append(rendered)
            ink_density, edge_density = _image_density(rendered)

            metric = PDFPageVisualMetrics(
                page=page_index,
                page_role=_infer_page_role(text),
                width_pt=round(float(page_rect.width), 2),
                height_pt=round(float(page_rect.height), 2),
                text_chars=len("".join(text.split())),
                text_blocks=len(text_blocks),
                image_count=len(image_rects),
                image_area_ratio=round(image_area_ratio, 4),
                ink_density=round(ink_density, 4),
                edge_ink_density=round(edge_density, 4),
                rendered_path=rendered.relative_to(root).as_posix(),
            )
            metrics.append(metric)
            findings.extend(_page_findings(metric))

        document.close()
        contact_sheet = review_dir / "contact-sheet.png"
        _make_contact_sheet(rendered_paths, contact_sheet)

        structural_gate: StructuralGate = "REVIEW" if any(item.severity == "REVIEW" for item in findings) else "PASS"
        assessment = WholePDFVisualAssessment(
            case_id=case_id,
            pdf_path=str(source),
            page_count=len(metrics),
            structural_gate=structural_gate,
            vision_gate="REVIEW_PENDING",
            metrics=metrics,
            findings=findings,
            contact_sheet_path=contact_sheet.relative_to(root).as_posix(),
            reviewed_at=now_iso(),
        )
        manifest_path = review_dir / "manifest.json"
        atomic_write_json(manifest_path, assessment.model_dump(mode="json"))
        review_job_path = review_dir / "vision-review-job.json"
        atomic_write_json(
            review_job_path,
            {
                "schema_version": 1,
                "case_id": case_id,
                "status": "REVIEW_PENDING",
                "contact_sheet": contact_sheet.relative_to(root).as_posix(),
                "pages": [item.rendered_path for item in metrics],
                "priority_pages": sorted({item.page for item in findings if item.severity == "REVIEW"}),
                "instructions": [
                    "Inspect the rendered page, not only the source Markdown/LaTeX.",
                    "Check hierarchy, whitespace rhythm, figure legibility, float placement, clipping, and page-to-page visual continuity.",
                    "Return page-specific repair instructions; do not invent or modify research claims or numerical evidence.",
                ],
            },
        )
        manifest_artifact = self.artifacts.register_existing(
            case_id,
            manifest_path.relative_to(root).as_posix(),
            "whole_pdf_visual_review",
            "whole_pdf_visual_reviewer",
            paper_eligible=False,
        )
        contact_artifact = self.artifacts.register_existing(
            case_id,
            contact_sheet.relative_to(root).as_posix(),
            "pdf_visual_contact_sheet",
            "whole_pdf_visual_reviewer",
            upstream=[manifest_artifact["artifact_id"]],
            paper_eligible=False,
        )
        job_artifact = self.artifacts.register_existing(
            case_id,
            review_job_path.relative_to(root).as_posix(),
            "whole_pdf_vision_review_job",
            "whole_pdf_visual_reviewer",
            upstream=[manifest_artifact["artifact_id"], contact_artifact["artifact_id"]],
            paper_eligible=False,
        )
        return {
            "assessment": assessment,
            "manifest_artifact": manifest_artifact,
            "contact_sheet_artifact": contact_artifact,
            "vision_review_job_artifact": job_artifact,
        }


def _image_density(path: Path) -> tuple[float, float]:
    with Image.open(path).convert("L") as image:
        image.thumbnail((1000, 1400))
        pixels = list(image.getdata())
        if not pixels:
            return 0.0, 0.0
        dark = sum(1 for value in pixels if value < 245)
        width, height = image.size
        band_x = max(1, int(width * 0.03))
        band_y = max(1, int(height * 0.03))
        edge_total = 0
        edge_dark = 0
        for y in range(height):
            for x in range(width):
                if x < band_x or x >= width - band_x or y < band_y or y >= height - band_y:
                    edge_total += 1
                    if image.getpixel((x, y)) < 245:
                        edge_dark += 1
        return dark / len(pixels), edge_dark / max(1, edge_total)


def _infer_page_role(text: str) -> Literal["NORMAL", "CONTENTS", "SUMMARY", "REFERENCES", "AI_USE_REPORT"]:
    normalized = " ".join((text or "").split()).strip().lower()
    if normalized.startswith("contents") or normalized.startswith("table of contents"):
        return "CONTENTS"
    if normalized.startswith("summary"):
        return "SUMMARY"
    if normalized.startswith("references"):
        return "REFERENCES"
    if normalized.startswith("ai use report"):
        return "AI_USE_REPORT"
    return "NORMAL"


def _page_findings(metric: PDFPageVisualMetrics) -> list[PDFVisualFinding]:
    findings: list[PDFVisualFinding] = []
    if metric.text_chars < 140 and metric.image_area_ratio >= 0.25:
        findings.append(
            PDFVisualFinding(
                page=metric.page,
                code="FLOAT_DOMINATED_PAGE",
                severity="REVIEW",
                detail="Page is dominated by figures with very little explanatory text.",
                repair_hint="Group compatible figures, reduce vertical footprint, or keep the interpretation paragraph on the same page.",
            )
        )
    if (
        metric.page_role == "NORMAL"
        and metric.ink_density < 0.035
        and metric.text_chars < 500
        and metric.image_area_ratio < 0.20
    ):
        findings.append(
            PDFVisualFinding(
                page=metric.page,
                code="EXCESSIVE_WHITESPACE",
                severity="REVIEW",
                detail="Page has unusually low visual/content density.",
                repair_hint="Rebalance section breaks and float placement; do not fill space with decorative content.",
            )
        )
    if metric.ink_density > 0.32 or (metric.text_chars > 2900 and metric.image_area_ratio > 0.12):
        findings.append(
            PDFVisualFinding(
                page=metric.page,
                code="OVERDENSE_PAGE",
                severity="REVIEW",
                detail="Page is unusually dense and may be difficult to scan.",
                repair_hint="Move secondary evidence/table rows, shorten duplicated prose, or split the visual argument across adjacent pages.",
            )
        )
    if metric.edge_ink_density > 0.055:
        findings.append(
            PDFVisualFinding(
                page=metric.page,
                code="EDGE_CONTENT_RISK",
                severity="REVIEW",
                detail="A noticeable amount of rendered content is close to the outer page edge.",
                repair_hint="Inspect margins, wide tables, captions, and clipped figures on this page.",
            )
        )
    return findings


def _make_contact_sheet(rendered_paths: list[Path], destination: Path) -> None:
    if not rendered_paths:
        return
    thumbs: list[Image.Image] = []
    for path in rendered_paths:
        with Image.open(path).convert("RGB") as source:
            image = source.copy()
        image.thumbnail((300, 420))
        thumbs.append(image)
    columns = 4
    cell_w, cell_h = 320, 455
    rows = (len(thumbs) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * cell_w, rows * cell_h), "white")
    draw = ImageDraw.Draw(sheet)
    for index, image in enumerate(thumbs):
        col = index % columns
        row = index // columns
        x = col * cell_w + (cell_w - image.width) // 2
        y = row * cell_h + 10
        sheet.paste(image, (x, y))
        draw.text((col * cell_w + 8, row * cell_h + cell_h - 24), f"Page {index + 1}", fill="black")
    destination.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(destination, format="PNG")

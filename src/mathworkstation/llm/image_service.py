from __future__ import annotations

import hashlib
import io
import uuid
from typing import Any

from PIL import Image

from ..artifact_registry import ArtifactRegistry
from ..case_manager import CaseManager
from ..figure_registry import FigureRegistry
from .audit import LLMAuditLogger
from .image_router import ImageRequest, ImageRouter


class CaseImageService:
    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        figures: FigureRegistry,
        router: ImageRouter,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.figures = figures
        self.router = router

    def generate(
        self,
        case_id: str,
        title: str,
        prompt: str,
        source_artifact_ids: list[str] | None = None,
        model: str | None = None,
        size: str = "1024x1024",
    ) -> dict[str, Any]:
        root = self.cases.case_root(case_id)
        self.router.audit = LLMAuditLogger(root / ".internal" / "llm_events.jsonl")
        result = self.router.generate(
            ImageRequest(
                prompt=prompt,
                model=model,
                size=size,
                metadata={"case_id": case_id},
            )
        )
        with Image.open(io.BytesIO(result.content)) as image:
            image.verify()
            image_format = (image.format or "PNG").lower()
        extension = "jpg" if image_format in {"jpeg", "jpg"} else image_format
        if extension not in {"png", "jpg", "webp"}:
            raise ValueError(f"unsupported generated image format: {image_format}")
        relative_path = f"figures/draft/ai-{uuid.uuid4().hex[:12]}.{extension}"
        destination = root / relative_path
        destination.write_bytes(result.content)
        figure = self.figures.register(
            case_id,
            relative_path,
            title,
            source_artifact_ids or [],
            "mathworkstation.llm.image_service:CaseImageService.generate",
            {
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "route": result.route_name,
                "model": result.model,
                "size": size,
                "latency_ms": result.latency_ms,
            },
            run_id=None,
            status="DRAFT",
        )
        return {"figure": figure, "bytes": len(result.content), "format": image_format}

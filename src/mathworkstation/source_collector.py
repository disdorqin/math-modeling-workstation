from __future__ import annotations

import mimetypes
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .io_utils import append_jsonl, now_iso
from .paths import resolve_within


class SourceCollector:
    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        timeout_seconds: int = 30,
        max_bytes: int = 100 * 1024 * 1024,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.timeout_seconds = timeout_seconds
        self.max_bytes = max_bytes

    def collect_url(self, case_id: str, url: str) -> dict[str, Any]:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("source URL must use http or https")
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "MathModelingWorkstation/0.1"},
        )
        collected_at = now_iso()
        with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
            content_length = response.headers.get("Content-Length")
            if content_length and int(content_length) > self.max_bytes:
                raise ValueError("source exceeds collection size limit")
            body = response.read(self.max_bytes + 1)
            if len(body) > self.max_bytes:
                raise ValueError("source exceeds collection size limit")
            final_url = response.geturl()
            content_type = response.headers.get_content_type()
            status_code = response.status

        filename = _safe_filename(parsed, content_type)
        source_id = f"source-{uuid.uuid4().hex[:12]}"
        case_root = self.cases.case_root(case_id)
        relative_path = f"evidence/sources/{source_id}-{filename}"
        target = resolve_within(case_root, relative_path)
        target.write_bytes(body)
        artifact = self.artifacts.register_existing(
            case_id,
            relative_path,
            "external_source_snapshot",
            "source_collector",
        )
        record = {
            "schema_version": 1,
            "source_id": source_id,
            "case_id": case_id,
            "requested_url": url,
            "final_url": final_url,
            "retrieved_at": collected_at,
            "http_status": status_code,
            "content_type": content_type,
            "artifact_id": artifact["artifact_id"],
            "sha256": artifact["sha256"],
            "size_bytes": artifact["size_bytes"],
        }
        append_jsonl(case_root / "evidence" / "urls.jsonl", record)
        return record


def _safe_filename(parsed: urllib.parse.ParseResult, content_type: str) -> str:
    candidate = Path(urllib.parse.unquote(parsed.path)).name or "download"
    sanitized = "".join(character if character.isalnum() or character in "._-" else "_" for character in candidate)
    if "." not in sanitized:
        extension = mimetypes.guess_extension(content_type) or ".bin"
        sanitized += extension
    return sanitized[:120]


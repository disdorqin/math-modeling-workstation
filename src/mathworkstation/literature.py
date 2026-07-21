from __future__ import annotations

import json
import re
import urllib.parse
import urllib.request
import uuid
from pathlib import Path
from typing import Any, Callable

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .io_utils import append_jsonl, atomic_write_json, atomic_write_text, now_iso
from .paths import resolve_within


class LiteratureService:
    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        timeout_seconds: int = 30,
        opener: Callable[..., Any] | None = None,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.timeout_seconds = timeout_seconds
        self.opener = opener or urllib.request.urlopen

    def registry_path(self, case_id: str) -> Path:
        return self.cases.case_root(case_id) / "literature_registry.jsonl"

    def list_records(self, case_id: str) -> list[dict[str, Any]]:
        path = self.registry_path(case_id)
        if not path.is_file():
            return []
        records: dict[str, dict[str, Any]] = {}
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                record = json.loads(line)
                records[record["citation_id"]] = record
        return list(records.values())

    def search_crossref(self, case_id: str, query: str, rows: int = 5) -> dict[str, Any]:
        query = query.strip()
        if len(query) < 3:
            raise ValueError("literature query must contain at least 3 characters")
        rows = max(1, min(rows, 20))
        params = urllib.parse.urlencode({"query.bibliographic": query, "rows": rows})
        url = f"https://api.crossref.org/works?{params}"
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "MathModelingWorkstation/0.1 (mailto:local@example.invalid)"},
        )
        with self.opener(request, timeout=self.timeout_seconds) as response:
            if getattr(response, "status", 200) != 200:
                raise RuntimeError(f"Crossref returned HTTP {response.status}")
            body = response.read()
        payload = json.loads(body.decode("utf-8"))
        search_id = f"literature-{uuid.uuid4().hex[:12]}"
        root = self.cases.case_root(case_id)
        snapshot_path = root / "evidence" / "snapshots" / f"{search_id}.json"
        atomic_write_json(snapshot_path, {"query": query, "url": url, "retrieved_at": now_iso(), "response": payload})
        snapshot_artifact = self.artifacts.register_existing(
            case_id,
            snapshot_path.relative_to(root).as_posix(),
            "literature_search_snapshot",
            "crossref",
        )
        discovered: list[dict[str, Any]] = []
        for item in (payload.get("message") or {}).get("items", []):
            doi = str(item.get("DOI") or "").strip().lower()
            if not doi:
                continue
            record = self._record_from_crossref(case_id, item, snapshot_artifact["artifact_id"])
            append_jsonl(self.registry_path(case_id), record)
            discovered.append(record)
        return {
            "search_id": search_id,
            "query": query,
            "snapshot_artifact_id": snapshot_artifact["artifact_id"],
            "records": discovered,
        }

    def export_bibtex(self, case_id: str) -> dict[str, Any]:
        records = self.list_records(case_id)
        root = self.cases.case_root(case_id)
        path = root / "paper" / "references" / "references.bib"
        content = "\n\n".join(record["bibtex"] for record in records) + ("\n" if records else "")
        atomic_write_text(path, content)
        artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "literature_bibtex",
            "python",
            upstream=list(dict.fromkeys(record["source_artifact_id"] for record in records)),
        )
        return {"artifact_id": artifact["artifact_id"], "path": path.relative_to(root).as_posix(), "count": len(records)}

    def verify_citations(self, case_id: str) -> dict[str, Any]:
        records = self.list_records(case_id)
        results: list[dict[str, Any]] = []
        for record in records:
            request = urllib.request.Request(
                f"https://api.crossref.org/works/{urllib.parse.quote(record['doi'], safe='')}",
                headers={"User-Agent": "MathModelingWorkstation/0.1 (mailto:local@example.invalid)"},
            )
            try:
                with self.opener(request, timeout=self.timeout_seconds) as response:
                    results.append({"citation_id": record["citation_id"], "doi": record["doi"], "exists": response.status == 200})
            except Exception as error:
                results.append({"citation_id": record["citation_id"], "doi": record["doi"], "exists": False, "error": f"{type(error).__name__}: {error}"})
        report = {"schema_version": 1, "case_id": case_id, "checked": len(results), "results": results, "generated_at": now_iso()}
        root = self.cases.case_root(case_id)
        path = root / "review" / "citation" / "citation_verification.json"
        atomic_write_json(path, report)
        artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "citation_verification",
            "crossref",
            upstream=list(dict.fromkeys(record["source_artifact_id"] for record in records)),
        )
        return {"report": report, "artifact_id": artifact["artifact_id"]}

    @staticmethod
    def _record_from_crossref(case_id: str, item: dict[str, Any], source_artifact_id: str) -> dict[str, Any]:
        doi = str(item.get("DOI") or "").strip().lower()
        title = (item.get("title") or [doi])[0]
        authors = [
            {"given": author.get("given", ""), "family": author.get("family", "")}
            for author in item.get("author", [])
        ]
        year = _year(item)
        key = _citation_key(authors, year, doi)
        return {
            "schema_version": 1,
            "citation_id": f"citation-{uuid.uuid4().hex[:12]}",
            "case_id": case_id,
            "key": key,
            "doi": doi,
            "title": title,
            "authors": authors,
            "year": year,
            "container_title": (item.get("container-title") or [""])[0],
            "url": item.get("URL") or f"https://doi.org/{doi}",
            "status": "DISCOVERED",
            "source_artifact_id": source_artifact_id,
            "bibtex": _bibtex(key, title, authors, year, doi),
            "created_at": now_iso(),
        }


def _year(item: dict[str, Any]) -> int | None:
    for field in ("published-print", "published-online", "issued"):
        date_parts = (item.get(field) or {}).get("date-parts") or []
        if date_parts and date_parts[0]:
            value = date_parts[0][0]
            if value is not None:
                return int(value)
    return None


def _citation_key(authors: list[dict[str, str]], year: int | None, doi: str) -> str:
    family = re.sub(r"[^A-Za-z0-9]", "", (authors[0].get("family") if authors else "Author")) or "Author"
    suffix = year or "nd"
    return f"{family}{suffix}-{doi.replace('/', '-').replace('.', '-')[:18]}"


def _bibtex(key: str, title: str, authors: list[dict[str, str]], year: int | None, doi: str) -> str:
    author_text = " and ".join(
        f"{author['given']} {author['family']}".strip() or "Unknown"
        for author in authors
    ) or "Unknown"
    return (
        f"@article{{{key},\n"
        f"  author = {{{author_text}}},\n"
        f"  title = {{{title}}},\n"
        f"  year = {{{year or ''}}},\n"
        f"  doi = {{{doi}}}\n"
        "}"
    )

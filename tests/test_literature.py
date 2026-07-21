import json
from io import BytesIO
from pathlib import Path

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.literature import LiteratureService
from mathworkstation.literature import _year


class FakeResponse:
    status = 200

    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self):
        return self.body


def test_crossref_search_registers_snapshot_bibtex_and_verification(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Literature")
    artifacts = ArtifactRegistry(cases)
    payload = {
        "message": {
            "items": [
                {
                    "DOI": "10.1000/example",
                    "title": ["A reproducible modeling paper"],
                    "author": [{"given": "Ada", "family": "Lovelace"}],
                    "published": {"date-parts": [[2024]]},
                    "container-title": ["Modeling Journal"],
                    "URL": "https://doi.org/10.1000/example",
                }
            ]
        }
    }
    calls: list[str] = []

    def opener(request, timeout):
        calls.append(request.full_url)
        return FakeResponse(json.dumps(payload).encode("utf-8"))

    service = LiteratureService(cases, artifacts, opener=opener)
    result = service.search_crossref(case["case_id"], "reproducible modeling")
    assert result["records"][0]["doi"] == "10.1000/example"
    bib = service.export_bibtex(case["case_id"])
    assert bib["count"] == 1
    bib_path = cases.case_root(case["case_id"]) / "paper" / "references" / "references.bib"
    assert "@article{" in bib_path.read_text(encoding="utf-8")
    verification = service.verify_citations(case["case_id"])
    assert verification["report"]["results"][0]["exists"] is True
    assert len(calls) == 2


def test_crossref_null_year_is_tolerated() -> None:
    assert _year({"published-online": {"date-parts": [[None]]}}) is None

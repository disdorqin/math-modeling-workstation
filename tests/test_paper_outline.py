import json
from pathlib import Path

import pytest

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.claims import ClaimInput, ClaimRegistry
from mathworkstation.datasets import DatasetRegistry
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.paper_outline import PaperOutlineService, default_outline


def test_outline_requires_verified_claims(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Outline")
    root = cases.case_root(case["case_id"])
    artifacts = ArtifactRegistry(cases)
    evidence_path = root / "results" / "metrics" / "evidence.json"
    evidence_path.write_text("{}", encoding="utf-8")
    evidence = artifacts.register_existing(
        case["case_id"], "results/metrics/evidence.json", "model_metrics", "python", paper_eligible=False
    )
    claims = ClaimRegistry(cases, artifacts, DatasetRegistry(cases, artifacts))
    claim = claims.create(
        case["case_id"],
        ClaimInput(text="结果尚未审批", claim_type="result", evidence_artifact_ids=[evidence["artifact_id"]]),
        "human",
    )
    outline = default_outline("测试论文", "SM")
    outline.sections[7].claim_ids = [claim["claim_id"]]
    source = tmp_path / "outline.json"
    source.write_text(outline.model_dump_json(), encoding="utf-8")
    service = PaperOutlineService(cases, artifacts, claims, FigureRegistry(cases, artifacts))
    with pytest.raises(ValueError, match="unverified claim"):
        service.validate_file(case["case_id"], source)


def test_default_outline_validates_without_evidence(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "Default Outline")
    outline = default_outline("工程验收论文", "MCM")
    source = tmp_path / "outline.json"
    source.write_text(json.dumps(outline.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8")
    artifacts = ArtifactRegistry(cases)
    service = PaperOutlineService(
        cases,
        artifacts,
        ClaimRegistry(cases, artifacts, DatasetRegistry(cases, artifacts)),
        FigureRegistry(cases, artifacts),
    )
    result = service.validate_file(case["case_id"], source)
    assert artifacts.get(case["case_id"], result["outline_artifact_id"])["artifact_type"] == "paper_outline"


def test_outline_accepts_windows_utf8_bom(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "BOM Outline")
    outline = default_outline("Windows 提纲", "SM")
    source = tmp_path / "outline.json"
    source.write_text(outline.model_dump_json(), encoding="utf-8-sig")
    artifacts = ArtifactRegistry(cases)
    result = PaperOutlineService(
        cases,
        artifacts,
        ClaimRegistry(cases, artifacts, DatasetRegistry(cases, artifacts)),
        FigureRegistry(cases, artifacts),
    ).validate_file(case["case_id"], source)
    assert result["outline_artifact_id"]


def _section_ids(outline) -> list[str]:
    return [s.section_id for s in outline.sections]


def test_default_outline_mcm_c_spelling_gets_c_type_sections() -> None:
    """"MCM-C" spelling must trigger the timeseries/momentum sections.

    Regression test for the flaky momentum integration (t3a5a988f): the old
    ``len(competition_type) >= 2`` guard plus a pydantic ``min_length=2`` made
    C-type detection depend on the exact spelling, so the sections appeared
    only sometimes.
    """
    outline = default_outline("C 题论文", "MCM-C")
    ids = _section_ids(outline)
    assert "timeseries_analysis" in ids
    assert "momentum_analysis" in ids


def test_default_outline_problem_type_c_triggers_c_type_sections() -> None:
    """problem_type='c' alone (e.g. from the case manifest) must enable C-type
    sections even when competition_type is the generic "MCM" spelling."""
    outline = default_outline("C 题论文", "MCM", problem_type="c")
    ids = _section_ids(outline)
    assert "timeseries_analysis" in ids
    assert "momentum_analysis" in ids


def test_default_outline_non_c_has_no_c_type_sections() -> None:
    outline = default_outline("A 题论文", "MCM")
    ids = _section_ids(outline)
    assert "momentum_analysis" not in ids
    assert "timeseries_analysis" not in ids

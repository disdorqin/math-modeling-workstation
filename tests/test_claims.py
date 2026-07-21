from pathlib import Path

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.claims import ClaimInput, ClaimRegistry
from mathworkstation.datasets import DatasetKind, DatasetRegistry


def test_claim_requires_paper_ready_evidence_and_marks_synthetic(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Claims")
    root = cases.case_root(case["case_id"])
    source = root / "input" / "data" / "uploaded" / "data.csv"
    source.write_text("x,target\n1,2\n", encoding="utf-8")
    artifacts = ArtifactRegistry(cases)
    source_artifact = artifacts.register_existing(
        case["case_id"], "input/data/uploaded/data.csv", "synthetic_data", "python"
    )
    datasets = DatasetRegistry(cases, artifacts)
    dataset = datasets.register(
        case["case_id"], "Synthetic", source_artifact["artifact_id"], DatasetKind.SYNTHETIC, "generated", "python"
    )
    result_path = root / "results" / "metrics" / "metric.json"
    result_path.write_text("{}", encoding="utf-8")
    result_artifact = artifacts.register_existing(
        case["case_id"], "results/metrics/metric.json", "model_metrics", "python", paper_eligible=False
    )
    claims = ClaimRegistry(cases, artifacts, datasets)
    draft = claims.create(
        case["case_id"],
        ClaimInput(
            text="模型在工程夹具上的误差较低",
            claim_type="model_result",
            evidence_artifact_ids=[result_artifact["artifact_id"]],
            dataset_ids=[dataset["dataset_id"]],
        ),
        "human",
    )
    assert draft["status"] == "DRAFT"
    assert set(draft["restrictions"]) == {"evidence_not_paper_ready", "synthetic_data_claim"}


def test_claim_is_verified_with_paper_ready_evidence(tmp_path: Path) -> None:
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("SM", "Verified Claim")
    root = cases.case_root(case["case_id"])
    result = root / "results" / "metrics" / "metric.json"
    result.write_text("{}", encoding="utf-8")
    artifacts = ArtifactRegistry(cases)
    artifact = artifacts.register_existing(
        case["case_id"], "results/metrics/metric.json", "model_metrics", "python", paper_eligible=True
    )
    claim = ClaimRegistry(cases, artifacts, DatasetRegistry(cases, artifacts)).create(
        case["case_id"],
        ClaimInput(
            text="交叉验证指标已通过审批",
            claim_type="model_result",
            evidence_artifact_ids=[artifact["artifact_id"]],
        ),
        "human",
    )
    assert claim["status"] == "VERIFIED"
    assert claim["restrictions"] == []


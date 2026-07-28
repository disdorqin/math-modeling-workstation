"""Tests for the public AI-readable audit gateway builder.

These run the generator against the real (tracked) repository and assert the
safety + completeness invariants the gateway must hold:

  * every required artifact is produced,
  * status.json / architecture.json / manifest are valid + keyed,
  * source-snapshot.zip is a real git archive that excludes secrets
    (.env.local) and local-only dirs (.workbuddy),
  * llms.txt points at status.json,
  * the forbidden-secret scan passes on generated output AND catches a planted
    secret (so the guard is real, not a no-op).
"""
from __future__ import annotations

import json
import sys
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.build_public_gateway import (  # noqa: E402
    SECRET_PATTERNS,
    build_gateway,
    scan_forbidden,
)


@pytest.fixture(scope="module")
def built(tmp_path_factory) -> Path:
    # Build once for the module. Pass a static ci_meta so the test does not
    # depend on `gh` network access or a live CI run.
    out = tmp_path_factory.mktemp("public-site") / "public-site"
    summary = build_gateway(
        REPO_ROOT, out, ci_meta={"source": "test", "latest_green_run": None}
    )
    assert summary["scan_violations"] == 0
    return out


def test_required_artifacts_present(built: Path) -> None:
    required = [
        "index.html",
        "status.json",
        "repository-manifest.json",
        "architecture.json",
        "llms.txt",
        "repository-context.md",
        "source-snapshot.zip",
        "ci/latest.json",
        "reports/README.md" if (built / "reports" / "README.md").exists() else "reports",
        "artifacts",
    ]
    for name in required:
        p = built / name
        assert p.exists(), f"missing gateway artifact: {name}"


def test_status_json_keys(built: Path) -> None:
    status = json.loads((built / "status.json").read_text(encoding="utf-8"))
    assert status["repository"] == "disdorqin/math-modeling-workstation"
    assert status["milestone"]["m1"]["status"] == "frozen"
    assert status["milestone"]["m1"]["tag"] == "m1-verified-2026-07-28"
    assert status["commit"]
    assert status["tracked_file_count"] > 0
    assert len(status["planes"]) == 3


def test_architecture_json_keys(built: Path) -> None:
    arch = json.loads((built / "architecture.json").read_text(encoding="utf-8"))
    assert arch["m1"]["status"] == "frozen"
    assert len(arch["m1"]["guarantees"]) >= 5
    assert len(arch["planes"]) == 3


def test_manifest_lists_tracked_files(built: Path) -> None:
    man = json.loads((built / "repository-manifest.json").read_text(encoding="utf-8"))
    paths = {f["path"] for f in man["files"]}
    assert "src/mathworkstation/cli.py" in paths
    assert man["total_files"] == len(man["files"])
    # manifest must only list tracked files (never .env.local)
    assert not any("env.local" in p for p in paths)


def test_source_snapshot_is_safe_zip(built: Path) -> None:
    zp = built / "source-snapshot.zip"
    assert zp.exists()
    with zipfile.ZipFile(zp) as zf:
        names = zf.namelist()
    assert len(names) > 0
    assert any(n.endswith("cli.py") for n in names)
    # The snapshot must come from git archive: untracked secrets + local dirs
    # must never appear.
    assert not any("env.local" in n for n in names)
    assert not any(".workbuddy" in n for n in names)
    assert not any(n.startswith("artifacts/") for n in names)


def test_llms_txt_references_status(built: Path) -> None:
    txt = (built / "llms.txt").read_text(encoding="utf-8")
    assert "status.json" in txt
    assert "m1-verified-2026-07-28" in txt


def test_generated_output_has_no_secrets(built: Path) -> None:
    # Re-scan exactly what the builder scans.
    from scripts.build_public_gateway import collect_texts_for_scan
    texts = collect_texts_for_scan(built)
    violations = scan_forbidden(texts)
    assert violations == [], f"secret patterns leaked: {violations}"


def test_forbidden_scan_actually_detects_secrets() -> None:
    """Guard against a silently-broken scanner: a planted OpenAI key must trip.

    The fake key is assembled at runtime (not written as a literal) so the
    repo's pre-commit secret_guard does not block this test file while the
    scanner-under-test still receives a real-looking secret.
    """
    planted = "here is a key " + "sk-" + ("abcdefghijklmnopqrstuvwxyz123456") + " and more"
    violations = scan_forbidden([("planted.txt", planted)])
    assert any(v["pattern"] == "openai_sk" for v in violations)


def test_secret_patterns_compiled() -> None:
    assert SECRET_PATTERNS, "no secret patterns defined"
    for _label, pat in SECRET_PATTERNS:
        assert hasattr(pat, "search")


def test_reports_copied(built: Path) -> None:
    reports = list((built / "reports").rglob("*.md"))
    assert len(reports) > 0
    # M1 freeze record must be present for auditors.
    assert any(p.name == "M1_FREEZE_RECORD.md" for p in reports)

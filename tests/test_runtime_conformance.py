"""Non-trivial runtime conformance.

The builtin runner and LangGraph must agree on a *populated* case where both
actually execute the agent pipeline. This guards the exact trap from the
pre-merge audit: a fresh, dataset-less case makes ``data_steward`` block in
BOTH runtimes, which yields ``differences == []`` only because both halted
identically. That is not conformance worth proving.

The conformance harness resolves each workspace's random ``artifact-<uuid>``
ids (and the proposal ids derived from them) to their *content* identity before
comparing, so two runtimes that decided the same things but minted different
ids compare conformant instead of spuriously diverging -- while a genuinely
different decision still fails the comparison.
"""

from __future__ import annotations

import contextlib
import io
import json
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest

import mathworkstation.cli as cli
from mathworkstation.agents.graph import langgraph_available
from mathworkstation.agents.semantics import diff_states
from mathworkstation.cli import _build_artifact_sha_map, _run_agents_in_workspace

REPO_ROOT = Path(__file__).resolve().parents[1]
DIABETES = REPO_ROOT / "examples" / "fixtures" / "diabetes_progression.csv"

pytestmark = pytest.mark.skipif(
    not DIABETES.exists(),
    reason="diabetes fixture missing",
)


def _run_cli(output_root: Path, args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cli.main(["--output-root", str(output_root), *args])
    return rc, buf.getvalue()


def _populate_case(output_root: Path):
    """Create a case and walk the minimal DAG so the agent pipeline can execute
    non-trivially: register a numeric dataset and approve data_registration so
    data_quality unblocks."""
    rc, out = _run_cli(output_root, [
        "create-case", "--competition", "CUMCM", "--title", "conformance",
        "--language", "zh",
    ])
    assert rc == 0, out
    case_id = json.loads(out)["case_id"]
    _run_cli(output_root, ["start-node", "--case-id", case_id, "--node-id", "input_validation"])
    _run_cli(output_root, ["succeed-node", "--case-id", case_id, "--node-id", "input_validation"])
    rc, out = _run_cli(output_root, [
        "register-dataset", "--case-id", case_id, "--name", "diabetes",
        "--kind", "OBSERVED", "--source", str(DIABETES), "--description", "fixture",
    ])
    assert rc == 0, out
    dataset_id = json.loads(out)["dataset_id"]
    _run_cli(output_root, ["complete-data-registration", "--case-id", case_id])
    _run_cli(output_root, [
        "approve-node", "--case-id", case_id, "--node-id", "data_registration",
        "--approved-by", "conformance-test",
    ])
    return case_id, dataset_id


def _summarize(state: dict) -> dict:
    return {
        "halted": bool(state.get("halted")),
        "agents": [r["agent"] for r in state.get("reports", [])],
        "proposals": sum(len(r.get("proposals", [])) for r in state.get("reports", [])),
        "verdicts": len(state.get("verdicts", [])),
        "evidence": sum(
            1 for r in state.get("reports", []) for p in r.get("proposals", [])
            if p.get("evidence")
        ),
    }


@pytest.mark.skipif(not langgraph_available(), reason="langgraph not installed")
def test_builtin_and_langgraph_conform_on_populated_case(tmp_path):
    output_root = tmp_path / "cases"
    case_id, dataset_id = _populate_case(output_root)
    args = SimpleNamespace(
        session_id=None,
        dataset_id=dataset_id,
        target_column="progression",
        goal="complete the modeling case",
    )

    results: dict[str, dict] = {}
    artifact_sha: dict[str, dict] = {}
    with tempfile.TemporaryDirectory(prefix="mmw-conf-") as tmp:
        source = output_root / case_id
        for name, prefer in (("builtin", False), ("langgraph", True)):
            ws = Path(tmp) / name
            shutil.copytree(source, ws / case_id)
            state, runtime_used = _run_agents_in_workspace(ws, case_id, args, prefer_langgraph=prefer)
            assert runtime_used == name, f"{name}: runtime selection mismatch"
            results[name] = state
            artifact_sha[name] = _build_artifact_sha_map(ws / case_id)

    # --- Non-trivial execution assertions (the heart of the audit) ---
    for name, state in results.items():
        assert not state["halted"], f"{name} halted: {state.get('halt_reason')!r}"
        assert dataset_id, "dataset_id must be populated"
        agents = [r["agent"] for r in state.get("reports", [])]
        assert len(agents) >= 4, f"{name} executed too few agents: {agents}"
        assert {"data_steward", "eda_analyst", "evidence_verifier", "quality_assurance"} <= set(agents)
        summary = _summarize(state)
        assert summary["proposals"] >= 1, f"{name} produced no proposals"
        assert summary["verdicts"] >= 1, f"{name} produced no verdicts"
        assert summary["evidence"] >= 1, f"{name} produced no evidence references"
        assert any(r.get("status") for r in state.get("reports", [])), f"{name} empty agent report"

    # --- Content-aware conformance: differences must be empty ---
    diff = diff_states(
        results["builtin"], results["langgraph"],
        builtin_artifact_sha=artifact_sha["builtin"],
        langgraph_artifact_sha=artifact_sha["langgraph"],
    )
    assert diff == [], "non-trivial runtimes disagree:\n" + json.dumps(diff, ensure_ascii=False, indent=2)


@pytest.mark.skipif(not langgraph_available(), reason="langgraph not installed")
def test_compare_cli_end_to_end_on_populated_case(tmp_path):
    output_root = tmp_path / "cases"
    case_id, dataset_id = _populate_case(output_root)
    report = tmp_path / "conformance.json"
    rc, out = _run_cli(output_root, [
        "compare-agent-runtimes", "--case-id", case_id,
        "--dataset-id", dataset_id, "--target-column", "progression",
        "--report", str(report),
    ])
    assert rc == 0, out
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["case_id"] == case_id
    assert data["differences"] == [], json.dumps(data["differences"], ensure_ascii=False, indent=2)


def test_early_halt_is_not_counted_as_conformant(tmp_path):
    """A dataset-less case makes data_steward block in BOTH runtimes. The
    conformance harness must NOT treat that as a meaningful pass -- the
    positive test's ``halted == False`` assertion would fail. This documents
    the trap and proves the harness would catch it."""
    output_root = tmp_path / "cases"
    rc, out = _run_cli(output_root, [
        "create-case", "--competition", "CUMCM", "--title", "halt", "--language", "zh",
    ])
    assert rc == 0, out
    case_id = json.loads(out)["case_id"]
    args = SimpleNamespace(session_id=None, dataset_id=None, target_column=None, goal="complete the modeling case")
    state, _ = _run_agents_in_workspace(output_root, case_id, args, prefer_langgraph=False)
    assert state["halted"], "expected data_steward to block without a dataset_id"
    # If someone compared this dataset-less case, both runtimes would halt
    # identically and a naive differences == [] would be the trap. The positive
    # test guards against it by requiring halted == False.

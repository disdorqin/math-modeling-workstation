"""Tests for the runtime semantics contract (agents/semantics.py).

IMPORTANT SCOPE NOTE: this environment has no PyPI access, so a real
LangGraph run cannot happen here (confirmed: pypi.org and every attempted
mirror return 403). Every test below exercises the *comparator* against
synthetic/hand-built state -- it proves the diffing logic is correct, not
that a real builtin-vs-langgraph run agrees. The one thing about LangGraph
that genuinely runs for real in this suite is the "unavailable" error path
(TestLanggraphUnavailablePath), because LangGraph really is unavailable here.
"""

from __future__ import annotations

import contextlib
import io

import pytest

from mathworkstation.agents.graph import langgraph_available
from mathworkstation.agents.semantics import canonicalize_state, diff_states, render_report
from mathworkstation.case_manager import CaseManager
from mathworkstation.cli import main as cli_main


class TestCanonicalization:
    def test_runtime_specific_keys_are_stripped(self) -> None:
        state = {"verdicts": [{"proposal_id": "p-1", "status": "ACCEPTED", "decided_at": "2026-01-01T00:00:00Z"}]}
        canonical = canonicalize_state(state)
        assert "decided_at" not in canonical["verdicts"][0]

    def test_dict_key_order_does_not_survive_canonicalization(self) -> None:
        a = canonicalize_state({"b": 1, "a": 2})
        assert list(a.keys()) == ["a", "b"]


class TestDiffStates:
    def _base_state(self) -> dict:
        return {
            "case_id": "case-1",
            "session_id": None,
            "dataset_id": "dataset-1",
            "target_column": "y",
            "goal": "test",
            "halted": False,
            "halt_reason": "",
            "blocked": [],
            "reports": [{"agent": "a1", "status": "OK", "notes": "", "blocked_reason": "", "proposals": []}],
            "verdicts": [
                {
                    "proposal_id": "proposal-abc123",
                    "status": "ACCEPTED",
                    "codes": [],
                    "message": "ok",
                    "produced": {"claim_id": "claim-1", "status": "VERIFIED"},
                    "replayed": False,
                    "decided_at": "2026-01-01T00:00:00Z",
                }
            ],
            "accepted": [{"agent": "a1", "kind": "CLAIM", "summary": "s", "produced": {"claim_id": "claim-1"}}],
        }

    def test_identical_states_are_conformant(self) -> None:
        state = self._base_state()
        differences = diff_states(state, state)
        assert differences == []
        assert render_report(differences).startswith("CONFORMANT")

    def test_wall_clock_only_difference_is_conformant(self) -> None:
        """The whole point of the contract: two runs that differ only in
        decided_at timestamps must NOT be reported as a mismatch."""
        builtin = self._base_state()
        langgraph = self._base_state()
        langgraph["verdicts"][0]["decided_at"] = "2099-12-31T23:59:59Z"
        assert diff_states(builtin, langgraph) == []

    def test_produced_dict_key_order_difference_is_conformant(self) -> None:
        """CANONICAL fields must not be flagged just because key order differs."""
        builtin = self._base_state()
        langgraph = self._base_state()
        # same content, different key insertion order
        langgraph["verdicts"][0]["produced"] = {"status": "VERIFIED", "claim_id": "claim-1"}
        assert diff_states(builtin, langgraph) == []

    def test_different_verdict_status_is_reported_not_normalized_away(self) -> None:
        builtin = self._base_state()
        langgraph = self._base_state()
        langgraph["verdicts"][0]["status"] = "REJECTED"
        differences = diff_states(builtin, langgraph)
        assert len(differences) == 1
        assert differences[0]["path"] == "verdicts.0.status"
        assert differences[0]["classification"] == "EXACT"
        assert "NON-CONFORMANT" in render_report(differences)

    def test_different_accepted_count_is_reported(self) -> None:
        builtin = self._base_state()
        langgraph = self._base_state()
        langgraph["accepted"] = []
        differences = diff_states(builtin, langgraph)
        assert any(d["path"] == "accepted" for d in differences)

    def test_different_halt_reason_is_reported(self) -> None:
        builtin = self._base_state()
        langgraph = self._base_state()
        langgraph["halted"] = True
        langgraph["halt_reason"] = "some other agent blocked"
        differences = diff_states(builtin, langgraph)
        paths = {d["path"] for d in differences}
        assert "halted" in paths
        assert "halt_reason" in paths


@pytest.mark.skipif(
    langgraph_available(),
    reason="LangGraph is installed here; the unavailable-path tests only make "
    "sense in the builtin-only environment (CI builtin-env job).",
)
class TestLanggraphUnavailablePath:
    """The one part of this file backed by a REAL environment fact: LangGraph
    genuinely is not importable here (PyPI is network-blocked in this sandbox)."""

    def test_langgraph_is_genuinely_unavailable_in_this_sandbox(self) -> None:
        assert langgraph_available() is False

    def test_compare_agent_runtimes_cli_exits_3_with_a_distinct_message(self, tmp_path) -> None:
        """Real, locally-executed evidence (not a mock): the compare-agent-runtimes
        CLI command, run against a real case in this real sandbox, where
        LangGraph really is unavailable, exits 3 -- distinct from the generic
        exit-1 error path -- with a message a caller can grep for."""
        cases = CaseManager(tmp_path)
        created = cases.create_case("CUMCM", "运行时对比测试", "zh")
        case_id = created["case_id"]

        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            exit_code = cli_main(
                ["--output-root", str(tmp_path), "compare-agent-runtimes", "--case-id", case_id]
            )
        assert exit_code == 3
        assert "LANGGRAPH_UNAVAILABLE" in stderr.getvalue()

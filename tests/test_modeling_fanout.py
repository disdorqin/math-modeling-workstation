"""Real, end-to-end tests for the bounded modeling fan-out's compute-level
reuse and historical-artifact handling (requirements #9 and #10 of the
2026-07-26 verification pass).

Every test here drives the *actual* agents (LinearModelAgent, TreeModelAgent,
RobustBaselineAgent, ModelEvaluationAgent, ModelJudgeAgent) against a real,
freshly created case with a real registered numeric dataset -- fitting real
scikit-learn pipelines on real (synthetic, generated-in-test) data, exactly as
`scripts/run_modeling_fanout_on_case.py` does against the real diabetes case.
Nothing here is a hand-rolled substitute for the agents' own logic.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from mathworkstation.agents import modeling
from mathworkstation.agents.adjudicator import Adjudicator
from mathworkstation.agents.contracts import AgentRequest
from mathworkstation.agents.modeling import (
    ModelEvaluationAgent,
    ModelJudgeAgent,
    build_modeling_agents,
    build_modeling_protocol,
)
from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.claims import ClaimRegistry
from mathworkstation.datasets import DatasetKind, DatasetRegistry
from mathworkstation.figure_registry import FigureRegistry


def _write_dataset_csv(path: Path, n_rows: int = 40, seed_offset: int = 0) -> None:
    rng = np.random.default_rng(7 + seed_offset)
    x1 = rng.normal(size=n_rows)
    x2 = rng.normal(size=n_rows)
    y = 3.0 * x1 - 2.0 * x2 + rng.normal(scale=0.1, size=n_rows)
    pd.DataFrame({"x1": x1, "x2": x2, "y": y}).to_csv(path, index=False)


class _Harness:
    """Wires one real case with a registered numeric dataset -- the same
    wiring `scripts/run_modeling_fanout_on_case.py` uses against the real
    diabetes case, built fresh in ``tmp_path`` so these tests own their data."""

    CANDIDATE_NAMES = ("linear_model_agent", "tree_model_agent", "robust_baseline_agent")

    def __init__(self, tmp_path: Path, n_rows: int = 40, seed_offset: int = 0) -> None:
        self.cases = CaseManager(tmp_path)
        self.artifacts = ArtifactRegistry(self.cases)
        self.datasets = DatasetRegistry(self.cases, self.artifacts)
        self.claims = ClaimRegistry(self.cases, self.artifacts, self.datasets)
        self.figures = FigureRegistry(self.cases, self.artifacts)
        self.adjudicator = Adjudicator(self.cases, self.artifacts, self.claims, self.figures)
        created = self.cases.create_case("CUMCM", "modeling fan-out reuse tests", "zh")
        self.case_id = created["case_id"]
        self.dataset_id = self._register_dataset("dataset", n_rows, seed_offset)

    def _register_dataset(self, name: str, n_rows: int, seed_offset: int) -> str:
        case_root = self.cases.case_root(self.case_id)
        data_path = case_root / "data" / "raw" / f"{name}.csv"
        data_path.parent.mkdir(parents=True, exist_ok=True)
        _write_dataset_csv(data_path, n_rows=n_rows, seed_offset=seed_offset)
        data_artifact = self.artifacts.register_existing(
            self.case_id,
            data_path.relative_to(case_root).as_posix(),
            "dataset_file",
            "test_fixture",
        )
        record = self.datasets.register(
            self.case_id,
            name,
            data_artifact["artifact_id"],
            DatasetKind.SYNTHETIC,
            "generated",
            "test_fixture",
        )
        return record["dataset_id"]

    def register_second_dataset(self, seed_offset: int = 99) -> str:
        self.dataset_id = self._register_dataset("dataset_v2", n_rows=40, seed_offset=seed_offset)
        return self.dataset_id

    def build_protocol(self, **overrides) -> dict:
        defaults = dict(primary_metric="rmse", n_splits=5, random_state=42)
        defaults.update(overrides)
        return build_modeling_protocol(
            self.cases,
            self.artifacts,
            self.datasets,
            self.case_id,
            self.dataset_id,
            "y",
            ["x1", "x2"],
            **defaults,
        )

    def agents(self) -> dict:
        return build_modeling_agents(self.cases, self.artifacts)

    def run_candidate(self, agent_name: str, protocol_artifact_id: str):
        agent = self.agents()[agent_name]
        request = AgentRequest(
            case_id=self.case_id, goal="test", inputs={"protocol_artifact_id": protocol_artifact_id}
        )
        return agent.run(request)

    def run_all_candidates(self, protocol_artifact_id: str) -> dict:
        return {name: self.run_candidate(name, protocol_artifact_id) for name in self.CANDIDATE_NAMES}

    def run_evaluation(self, protocol_artifact_id: str):
        agent = ModelEvaluationAgent(self.cases, self.artifacts)
        request = AgentRequest(
            case_id=self.case_id, goal="test", inputs={"protocol_artifact_id": protocol_artifact_id}
        )
        return agent.run(request)

    def run_judge(self, comparison_artifact_id: str):
        agent = ModelJudgeAgent(self.cases, self.artifacts)
        request = AgentRequest(
            case_id=self.case_id, goal="test", inputs={"comparison_artifact_id": comparison_artifact_id}
        )
        return agent.run(request)

    def active_artifacts(self, artifact_type: str) -> list:
        return [
            a
            for a in self.artifacts.list_artifacts(self.case_id)
            if a["artifact_type"] == artifact_type and a["status"] == "ACTIVE"
        ]

    def all_artifacts(self, artifact_type: str) -> list:
        return [a for a in self.artifacts.list_artifacts(self.case_id) if a["artifact_type"] == artifact_type]

    def read_artifact(self, artifact: dict) -> dict:
        case_root = self.cases.case_root(self.case_id)
        return json.loads((case_root / artifact["path"]).read_text(encoding="utf-8"))


def _patch_fit_counter(monkeypatch) -> list:
    """Count real `_evaluate` (the K-fold fitting loop) calls without
    changing its behaviour, so tests can assert "zero model fits" for real
    rather than by inference from `reuse_status` alone."""
    calls: list[str] = []
    original = modeling._CandidateModelAgent._evaluate

    def counting(self, case_id, protocol, protocol_artifact):
        calls.append(self.model_family)
        return original(self, case_id, protocol, protocol_artifact)

    monkeypatch.setattr(modeling._CandidateModelAgent, "_evaluate", counting)
    return calls


class TestProtocolIdempotency:
    def test_rebuilding_an_unchanged_protocol_returns_the_same_artifact(self, tmp_path) -> None:
        harness = _Harness(tmp_path)
        first = harness.build_protocol()
        second = harness.build_protocol()
        assert first["protocol_artifact_id"] == second["protocol_artifact_id"]
        assert len(harness.all_artifacts("modeling_protocol")) == 1


class TestCandidateReuse:
    def test_second_identical_run_performs_zero_fits_and_reuses_every_candidate(self, tmp_path, monkeypatch) -> None:
        harness = _Harness(tmp_path)
        protocol_id = harness.build_protocol()["protocol_artifact_id"]
        calls = _patch_fit_counter(monkeypatch)

        first = harness.run_all_candidates(protocol_id)
        assert len(calls) == 3
        for report in first.values():
            assert report.proposals[0].payload["reuse_status"] == "computed"
            assert report.proposals[0].payload["status"] == "VALID"

        calls.clear()
        second = harness.run_all_candidates(protocol_id)
        assert calls == []  # zero model fits on the second identical run
        for name, report in second.items():
            payload = report.proposals[0].payload
            assert payload["reuse_status"] == "reused"
            assert payload["candidate_artifact_id"] == first[name].proposals[0].payload["candidate_artifact_id"]

        # reuse does not duplicate registry entities: still exactly one
        # ACTIVE (and zero SUPERSEDED) candidate artifact per model family.
        assert len(harness.active_artifacts("model_candidate")) == 3
        assert len(harness.all_artifacts("model_candidate")) == 3

    def test_protocol_change_forces_recompute_and_preserves_history(self, tmp_path, monkeypatch) -> None:
        harness = _Harness(tmp_path)
        protocol_id = harness.build_protocol()["protocol_artifact_id"]
        harness.run_all_candidates(protocol_id)

        protocol_id_2 = harness.build_protocol(n_splits=4)["protocol_artifact_id"]
        assert protocol_id_2 != protocol_id  # different fold count -> different hashed content

        calls = _patch_fit_counter(monkeypatch)
        second = harness.run_all_candidates(protocol_id_2)
        assert len(calls) == 3  # every candidate refit under the new protocol
        for report in second.values():
            assert report.proposals[0].payload["reuse_status"] == "computed"

        all_candidates = harness.all_artifacts("model_candidate")
        assert len(all_candidates) == 6  # 3 original + 3 recomputed, nothing deleted
        assert len(harness.active_artifacts("model_candidate")) == 3
        assert sum(1 for a in all_candidates if a["status"] == "SUPERSEDED") == 3

    def test_dataset_change_forces_recompute(self, tmp_path, monkeypatch) -> None:
        harness = _Harness(tmp_path)
        built1 = harness.build_protocol()
        protocol_id = built1["protocol_artifact_id"]
        harness.run_all_candidates(protocol_id)

        harness.register_second_dataset()
        built2 = harness.build_protocol()
        protocol_id_2 = built2["protocol_artifact_id"]
        assert protocol_id_2 != protocol_id
        assert built2["protocol"]["dataset_hash"] != built1["protocol"]["dataset_hash"]

        calls = _patch_fit_counter(monkeypatch)
        second = harness.run_all_candidates(protocol_id_2)
        assert len(calls) == 3
        for report in second.values():
            assert report.proposals[0].payload["reuse_status"] == "computed"

    def test_one_changed_candidate_invalidates_only_itself_and_the_comparison(self, tmp_path, monkeypatch) -> None:
        harness = _Harness(tmp_path)
        protocol_id = harness.build_protocol()["protocol_artifact_id"]
        harness.run_all_candidates(protocol_id)
        first_eval = harness.run_evaluation(protocol_id)
        first_comparison_id = first_eval.proposals[0].payload["comparison_artifact_id"]
        assert first_eval.proposals[0].payload["reuse_status"] == "computed"

        # Only the tree agent's own implementation changes (a hyperparameter
        # tweak) -- the protocol itself, and the other two candidates, do not.
        monkeypatch.setattr(modeling.TreeModelAgent, "_hyperparameters", lambda self: {"max_depth": 2})

        from sklearn.tree import DecisionTreeRegressor

        monkeypatch.setattr(
            modeling.TreeModelAgent,
            "_estimator",
            lambda self: DecisionTreeRegressor(max_depth=2, random_state=42),
        )

        calls = _patch_fit_counter(monkeypatch)
        harness.run_candidate("tree_model_agent", protocol_id)
        assert calls == ["tree"]  # only the changed candidate was ever refit

        second_eval = harness.run_evaluation(protocol_id)
        assert second_eval.proposals[0].payload["reuse_status"] == "computed"  # comparison must recompute
        assert second_eval.proposals[0].payload["comparison_artifact_id"] != first_comparison_id

        all_candidates = harness.all_artifacts("model_candidate")
        assert len(all_candidates) == 4  # 3 original + 1 recomputed tree candidate
        by_family = {}
        for artifact in all_candidates:
            content = harness.read_artifact(artifact)
            by_family.setdefault(content["model_family"], []).append(artifact)
        assert len(by_family["tree"]) == 2
        assert sum(1 for a in by_family["tree"] if a["status"] == "ACTIVE") == 1
        assert len(by_family["linear"]) == 1  # never touched, never superseded
        assert len(by_family["robust_baseline"]) == 1


class TestComparisonReuse:
    def test_second_identical_evaluation_reuses_the_comparison(self, tmp_path) -> None:
        harness = _Harness(tmp_path)
        protocol_id = harness.build_protocol()["protocol_artifact_id"]
        harness.run_all_candidates(protocol_id)

        first = harness.run_evaluation(protocol_id)
        assert first.proposals[0].payload["reuse_status"] == "computed"
        first_id = first.proposals[0].payload["comparison_artifact_id"]

        second = harness.run_evaluation(protocol_id)
        assert second.proposals[0].payload["reuse_status"] == "reused"
        assert second.proposals[0].payload["comparison_artifact_id"] == first_id

        assert len(harness.all_artifacts("model_comparison")) == 1  # no duplicate registry entry


class TestHistoricalCandidateFiltering:
    def test_evaluation_only_considers_the_current_protocol_generation(self, tmp_path) -> None:
        """Repeated debugging runs (protocol tweak, rerun, tweak again) leave
        several historical protocol generations' candidates in the registry.
        Because candidate/comparison artifacts live at a *stable* path
        (candidate-{family}.json / comparison.json), only the most recent
        generation's candidates are ever ACTIVE at once -- older generations
        are automatically SUPERSEDED, not deleted, the moment a newer
        generation's candidate is written to the same path. The evaluation
        agent for "the current protocol" therefore only ever sees the
        current generation's three candidates, never the accumulated
        historical set, without any extra metadata beyond what
        ArtifactRegistry.register_existing already tracks."""
        harness = _Harness(tmp_path)
        protocol_id_1 = harness.build_protocol()["protocol_artifact_id"]
        harness.run_all_candidates(protocol_id_1)
        eval1 = harness.run_evaluation(protocol_id_1)
        assert eval1.proposals[0].payload["candidate_count"] == 3

        protocol_id_2 = harness.build_protocol(n_splits=4)["protocol_artifact_id"]
        harness.run_all_candidates(protocol_id_2)

        protocol_id_3 = harness.build_protocol(n_splits=3)["protocol_artifact_id"]
        harness.run_all_candidates(protocol_id_3)

        # three full historical generations of debug candidates now exist --
        # append-only audit history is never deleted.
        all_candidates = harness.all_artifacts("model_candidate")
        assert len(all_candidates) == 9
        assert sum(1 for a in all_candidates if a["status"] == "SUPERSEDED") == 6
        assert len(harness.active_artifacts("model_candidate")) == 3

        # evaluating the CURRENT (latest) protocol generation only ever sees
        # its own three candidates -- not all nine historical ones -- even
        # though every historical candidate artifact is still on record.
        eval3 = harness.run_evaluation(protocol_id_3)
        assert eval3.proposals[0].payload["candidate_count"] == 3
        comparison_artifact = harness.artifacts.get(
            harness.case_id, eval3.proposals[0].payload["comparison_artifact_id"]
        )
        comparison = harness.read_artifact(comparison_artifact)
        assert comparison["protocol_id"] == protocol_id_3
        assert {c["candidate_id"] for c in comparison["candidates"]} == {
            "candidate-linear",
            "candidate-tree",
            "candidate-robust_baseline",
        }

        # a stale generation (superseded the moment the next one was
        # written) can no longer be evaluated as "the" current comparison --
        # its candidates are historical evidence, not live inputs.
        stale = harness.run_evaluation(protocol_id_1)
        assert stale.status == "BLOCKED"


class TestEndToEndReuseDoesNotDuplicateTheClaim:
    def test_rerunning_the_full_fanout_replays_instead_of_writing_a_second_claim(self, tmp_path) -> None:
        harness = _Harness(tmp_path, n_rows=60)
        protocol_id = harness.build_protocol()["protocol_artifact_id"]

        def run_once() -> list:
            harness.run_all_candidates(protocol_id)
            eval_report = harness.run_evaluation(protocol_id)
            comparison_id = eval_report.proposals[0].payload["comparison_artifact_id"]
            judge_report = harness.run_judge(comparison_id)
            return [harness.adjudicator.decide(harness.case_id, p) for p in judge_report.proposals]

        first_verdicts = run_once()
        assert all(not v.replayed for v in first_verdicts)

        second_verdicts = run_once()
        assert any(v.replayed for v in second_verdicts)

        # exactly one claim exists no matter how many times the identical
        # fan-out is rerun (WINNER outcomes create a claim; a rerun with an
        # unchanged comparison_artifact_id must not create a second one).
        winner_claims = [v for v in first_verdicts if v.produced.get("claim_id")]
        if winner_claims:
            assert len(harness.claims.list_claims(harness.case_id)) == len(winner_claims)

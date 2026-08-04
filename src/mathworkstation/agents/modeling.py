"""The bounded modeling fan-out: candidate agents, a protocol-aware evaluator, and a judge.

This is a *closed* set of agents, not an open-ended "call any model" surface:

    build_modeling_protocol()               # one immutable protocol, shared by all candidates
        -> linear_model_agent    \\
        -> tree_model_agent       }-> model_evaluation_agent -> model_judge_agent
        -> robust_baseline_agent /

Every candidate agent trains under the *same* protocol (same dataset hash, same
feature set, same fold indices, same primary metric) and writes one typed
``model_candidate`` artifact. No candidate agent ranks itself against the
others or claims to be the winner — a candidate that cannot be fit still writes
a candidate record, marked ``INVALID`` with a reason, rather than disappearing.

``model_evaluation_agent`` is the only place that reads every candidate and
decides, per protocol, which ones are actually usable evidence (right protocol,
right dataset, right shape) — independent of what the candidate agent itself
claimed. Nothing it finds is dropped; an invalid candidate is recorded as
invalid, not omitted.

``model_judge_agent`` reads that evaluation, and only that evaluation — never a
candidate agent's own prose — to decide WINNER / TIE / NO_ACCEPTABLE_WINNER. It
*proposes* a :class:`~mathworkstation.agents.contracts.ProposalKind.MODEL_SELECTION`
verdict; only ``Adjudicator._handle_model_selection`` (see ``adjudicator.py``)
may turn that into a claim. This module produces artifacts and proposals; it
never touches the claim or figure registries.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd
from sklearn.linear_model import HuberRegressor, LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import KFold, TimeSeriesSplit
from sklearn.pipeline import Pipeline
from sklearn.tree import DecisionTreeRegressor

from ..artifact_registry import ArtifactRegistry
from ..baseline import _preprocessor
from ..case_manager import CaseManager
from ..datasets import DatasetRegistry
from ..io_utils import atomic_write_json, read_json, sha256_file
from ..paths import resolve_within
from ..tabular import read_table
from .base import DeterministicAgent
from .contracts import AgentReport, AgentRequest, ProposalKind

#: metric_name -> whether a smaller value is better. Anything not listed is
#: rejected explicitly rather than silently assumed "bigger is better".
_METRIC_DIRECTION = {"rmse": "minimize", "mae": "minimize", "r2": "maximize"}

#: model_family -> a hyperparameter-count-free complexity rank, used only to
#: break a genuine numeric tie (never to override a real metric difference).
_COMPLEXITY_RANK = {"robust_baseline": 0, "linear": 1, "tree": 2}

#: relative metric difference below which two candidates are treated as tied
#: rather than one being declared better on noise.
_TIE_TOLERANCE = 0.01


# --------------------------------------------------------------------- protocol


def build_modeling_protocol(
    cases: CaseManager,
    artifacts: ArtifactRegistry,
    datasets: DatasetRegistry,
    case_id: str,
    dataset_id: str,
    target_column: str,
    feature_columns: list[str],
    *,
    primary_metric: str = "rmse",
    n_splits: int = 5,
    random_state: int = 42,
    created_by: str = "modeling_protocol_builder",
    split_strategy: str = "random",
    temporal_column: str | None = None,
) -> dict[str, Any]:
    """Register one immutable, hashed modeling protocol.

    Every field a candidate or the evaluator later checks against is decided
    here, once: which rows, which folds (as literal row-position lists, not
    just a seed — so "did you actually evaluate on the same folds" is checked
    by comparing lists, not by trusting that two runs of KFold agree), which
    metric, and which direction is "better". Nothing downstream may silently
    redefine any of this; it may only cite this artifact by id and hash.

    Args:
        split_strategy: "random" (default KFold with shuffle) or "time_ordered"
            (TimeSeriesSplit for temporal data to prevent leakage).
        temporal_column: Column name to sort by when split_strategy="time_ordered".
            If None and split_strategy="time_ordered", uses original row order.
    """
    if primary_metric not in _METRIC_DIRECTION:
        raise ValueError(f"unsupported primary_metric: {primary_metric!r}")
    if split_strategy not in ("random", "time_ordered"):
        raise ValueError(f"unsupported split_strategy: {split_strategy!r}")
    dataset = datasets.get(case_id, dataset_id)
    source_artifact = artifacts.get(case_id, dataset["artifact_id"])
    case_root = cases.case_root(case_id)
    frame = read_table(resolve_within(case_root, source_artifact["path"]))
    missing = sorted(set([target_column, *feature_columns]) - set(frame.columns))
    if missing:
        raise ValueError(f"protocol references missing columns: {missing}")
    modeling = frame[[*feature_columns, target_column]].dropna(subset=[target_column])
    if len(modeling) < n_splits * 2:
        raise ValueError("insufficient rows for the requested fold count")

    # Sort by temporal column for time-ordered splitting (prevents data leakage)
    if split_strategy == "time_ordered":
        if temporal_column and temporal_column in modeling.columns:
            modeling = modeling.sort_values(by=temporal_column, kind="mergesort").reset_index(drop=True)
        # TimeSeriesSplit: train on past, test on future (no shuffle)
        splitter = TimeSeriesSplit(n_splits=n_splits)
        fold_test_indices = [test_idx.tolist() for _, test_idx in splitter.split(modeling)]
    else:
        splitter = KFold(n_splits=n_splits, shuffle=True, random_state=random_state)
        fold_test_indices = [test_idx.tolist() for _, test_idx in splitter.split(modeling)]

    protocol = {
        "schema_version": 1,
        "case_id": case_id,
        "dataset_id": dataset_id,
        "dataset_artifact_id": source_artifact["artifact_id"],
        "dataset_hash": source_artifact["sha256"],
        "target_column": target_column,
        "feature_columns": list(feature_columns),
        "task_type": "regression",
        "primary_metric": primary_metric,
        "metric_direction": _METRIC_DIRECTION[primary_metric],
        "n_splits": n_splits,
        "random_state": random_state,
        "split_strategy": split_strategy,
        "temporal_column": temporal_column,
        "fold_test_indices": fold_test_indices,
        "n_rows": int(len(modeling)),
        "created_by": created_by,
        # Deliberately no wall-clock timestamp in the hashed content: the
        # registry entry already carries one (artifact["created_at"]), and a
        # protocol with unchanged inputs must produce byte-identical content
        # so re-running the builder is a no-op (register_existing's own
        # same-path/same-hash reuse), not a fresh artifact every time.
    }
    protocol_path = case_root / "agents" / "modeling" / f"protocol-{dataset_id}-{target_column}.json"
    atomic_write_json(protocol_path, protocol)
    protocol_artifact = artifacts.register_existing(
        case_id,
        protocol_path.relative_to(case_root).as_posix(),
        "modeling_protocol",
        created_by,
        upstream=[source_artifact["artifact_id"]],
    )
    return {
        "protocol": protocol,
        "protocol_artifact_id": protocol_artifact["artifact_id"],
        "protocol_hash": protocol_artifact["sha256"],
        "frame": modeling,
    }


def _row_positions(frame: pd.DataFrame, protocol: dict[str, Any]) -> tuple[pd.DataFrame, pd.Series]:
    features = frame[protocol["feature_columns"]].reset_index(drop=True)
    target = frame[protocol["target_column"]].reset_index(drop=True)
    return features, target


def _metric_value(name: str, actual, predicted) -> float:
    if name == "rmse":
        return math.sqrt(mean_squared_error(actual, predicted))
    if name == "mae":
        return float(mean_absolute_error(actual, predicted))
    if name == "r2":
        return float(r2_score(actual, predicted))
    raise ValueError(f"unsupported metric: {name}")


# ------------------------------------------------------------------- candidates


class _CandidateModelAgent(DeterministicAgent):
    """Common shell for the three candidate agents.

    Fitting is delegated to :meth:`_estimator`; everything around it — loading
    the protocol, replaying its exact folds, writing a typed candidate
    artifact, and reporting without self-declaring a winner — is identical
    across candidates so their artifacts are directly comparable.
    """

    mandate = (ProposalKind.ANALYSIS_ACTION,)
    model_family = "unknown"

    def __init__(self, cases: CaseManager, artifacts: ArtifactRegistry) -> None:
        self.cases = cases
        self.artifacts = artifacts

    def _estimator(self):  # pragma: no cover - overridden per subclass
        raise NotImplementedError

    def _hyperparameters(self) -> dict[str, Any]:
        return {}

    def run(self, request: AgentRequest) -> AgentReport:
        protocol_artifact_id = request.inputs.get("protocol_artifact_id")
        if not protocol_artifact_id:
            return self.blocked("no protocol_artifact_id supplied")
        try:
            protocol_artifact = self.artifacts.get(request.case_id, protocol_artifact_id)
        except KeyError:
            return self.blocked(f"protocol artifact not found: {protocol_artifact_id}")
        case_root = self.cases.case_root(request.case_id)
        protocol = read_json(case_root / protocol_artifact["path"])

        # Stable path (no protocol id embedded): a protocol change makes the
        # *content* written here differ, which is exactly the signal
        # ArtifactRegistry.register_existing needs to supersede the old
        # candidate and register a new ACTIVE one at the same path -- the
        # same mechanism that gives build_modeling_protocol its idempotency,
        # reused here to also solve "stale candidates pile up at distinct
        # paths" (see docs/multi-agent-architecture.md, reuse & historical
        # artifact handling).
        candidate_path = case_root / "agents" / "modeling" / f"candidate-{self.model_family}.json"

        reused = self._find_reusable_candidate(
            request.case_id, candidate_path, protocol_artifact, self._hyperparameters()
        )
        if reused is not None:
            record = dict(reused)
            reuse_status = "reused"
        else:
            record = self._evaluate(request.case_id, protocol, protocol_artifact)
            atomic_write_json(candidate_path, record)
            reuse_status = "computed"

        candidate_artifact = self.artifacts.register_existing(
            request.case_id,
            candidate_path.relative_to(case_root).as_posix(),
            "model_candidate",
            self.name,
            upstream=[protocol_artifact_id],
        )
        # Deliberately not rewritten to disk: the artifact's registered sha256
        # was computed from the file as written, and must keep matching it
        # exactly -- adding a self-referential id after registration would
        # silently invalidate that hash. Callers get the id from the return
        # value / the ArtifactRegistry entry, not from the file's own content.
        # reuse_status is likewise runtime-only, never persisted, for the same
        # reason -- it describes *this run*, not the artifact's content.
        record["candidate_artifact_id"] = candidate_artifact["artifact_id"]
        record["reuse_status"] = reuse_status

        proposal = self.propose(
            ProposalKind.ANALYSIS_ACTION,
            summary=f"{self.model_family} 候选模型评估完成，状态 {record['status']}",
            payload={
                "candidate_id": record["candidate_id"],
                "model_family": self.model_family,
                "status": record["status"],
                "metric_name": record["metric_name"],
                "protocol_artifact_id": protocol_artifact_id,
                "candidate_artifact_id": candidate_artifact["artifact_id"],
                "reuse_status": reuse_status,
            },
            evidence=[candidate_artifact["artifact_id"], protocol_artifact_id],
            rationale=(
                "确定性拟合，指标由协议规定的折内验证计算"
                if reuse_status == "computed"
                else "复用既有候选产物：协议、数据集与候选内容哈希均未变化，未重新拟合模型"
            ),
        )
        return AgentReport(agent=self.name, proposals=[proposal], notes=f"{record['status']} ({reuse_status})")

    def _find_reusable_candidate(
        self,
        case_id: str,
        candidate_path,
        protocol_artifact: dict[str, Any],
        current_hyperparameters: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Return the existing candidate record if it is safe to reuse, else ``None``.

        Reuse requires every one of: a file already exists at the stable
        path; its content was fit under *this exact* protocol artifact (same
        id *and* same hash, so a same-id-different-content protocol edit --
        which should not happen given protocols are content-addressed, but is
        checked anyway -- cannot be silently reused); its hyperparameters
        match what this agent would fit *right now* (a config/code change to
        the candidate agent itself -- e.g. a different ``max_depth`` -- must
        force a refit even though the protocol did not change); its own
        status is ``VALID`` (an invalid/stale candidate is never silently
        reused); and the currently-registered ACTIVE artifact at that path
        still hashes to exactly the bytes on disk (guards against a file
        edited or replaced out from under the registry between runs).
        """
        if not candidate_path.is_file():
            return None
        try:
            existing = read_json(candidate_path)
        except (OSError, ValueError):
            return None
        if existing.get("protocol_id") != protocol_artifact["artifact_id"]:
            return None
        if existing.get("protocol_hash") != protocol_artifact["sha256"]:
            return None
        if existing.get("hyperparameters") != current_hyperparameters:
            return None
        if existing.get("status") != "VALID":
            return None
        case_root = self.cases.case_root(case_id)
        relative_path = candidate_path.relative_to(case_root).as_posix()
        active_here = [
            item
            for item in self.artifacts.list_artifacts(case_id)
            if item.get("path") == relative_path and item.get("status") == "ACTIVE"
        ]
        if not active_here:
            return None
        if active_here[-1].get("sha256") != sha256_file(candidate_path):
            return None
        return existing

    def _evaluate(
        self, case_id: str, protocol: dict[str, Any], protocol_artifact: dict[str, Any]
    ) -> dict[str, Any]:
        candidate_id = f"candidate-{self.model_family}"
        base_record = {
            "schema_version": 1,
            "candidate_id": candidate_id,
            "agent": self.name,
            "model_family": self.model_family,
            "hyperparameters": self._hyperparameters(),
            "protocol_id": protocol_artifact["artifact_id"],
            "protocol_hash": protocol_artifact["sha256"],
            "dataset_id": protocol["dataset_id"],
            "dataset_hash": protocol["dataset_hash"],
            "target_column": protocol["target_column"],
            "feature_columns": protocol["feature_columns"],
            "metric_name": protocol["primary_metric"],
            "metric_direction": protocol["metric_direction"],
            "n_folds": protocol["n_splits"],
            # No wall-clock timestamp here either -- see build_modeling_protocol's
            # comment. A candidate fit under an unchanged protocol must hash
            # identically on rerun.
        }
        try:
            case_root = self.cases.case_root(case_id)
            source_path = resolve_within(case_root, self._dataset_path(protocol))
            frame = read_table(source_path)
            frame = frame[[*protocol["feature_columns"], protocol["target_column"]]].dropna(
                subset=[protocol["target_column"]]
            )
            if len(frame) != protocol["n_rows"]:
                raise ValueError(
                    f"row count {len(frame)} does not match protocol n_rows {protocol['n_rows']}"
                )
            features, target = _row_positions(frame, protocol)
            fold_values: list[float] = []
            for test_idx in protocol["fold_test_indices"]:
                test_idx = list(test_idx)
                train_idx = [i for i in range(len(features)) if i not in set(test_idx)]
                pipeline = Pipeline([("preprocessor", _preprocessor(features)), ("model", self._estimator())])
                pipeline.fit(features.iloc[train_idx], target.iloc[train_idx])
                predicted = pipeline.predict(features.iloc[test_idx])
                fold_values.append(_metric_value(protocol["primary_metric"], target.iloc[test_idx], predicted))
            base_record.update(
                {
                    "metric_value": float(np.mean(fold_values)),
                    "fold_metric_values": [float(v) for v in fold_values],
                    "status": "VALID",
                    "invalid_reason": "",
                }
            )
        except Exception as error:  # noqa: BLE001 - a failed fit is still a typed, recorded candidate
            base_record.update(
                {
                    "metric_value": None,
                    "fold_metric_values": [],
                    "status": "INVALID",
                    "invalid_reason": f"{type(error).__name__}: {error}",
                }
            )
        return base_record

    def _dataset_path(self, protocol: dict[str, Any]) -> str:  # pragma: no cover - overridden per subclass
        raise NotImplementedError


class LinearModelAgent(_CandidateModelAgent):
    name = "linear_model_agent"
    model_family = "linear"

    def __init__(self, cases: CaseManager, artifacts: ArtifactRegistry) -> None:
        super().__init__(cases, artifacts)

    def _estimator(self):
        return LinearRegression()

    def _dataset_path(self, protocol: dict[str, Any]) -> str:
        return self.artifacts.get(protocol["case_id"], protocol["dataset_artifact_id"])["path"]


class TreeModelAgent(_CandidateModelAgent):
    name = "tree_model_agent"
    model_family = "tree"

    def _estimator(self):
        return DecisionTreeRegressor(max_depth=4, random_state=42)

    def _hyperparameters(self) -> dict[str, Any]:
        return {"max_depth": 4, "random_state": 42}

    def _dataset_path(self, protocol: dict[str, Any]) -> str:
        return self.artifacts.get(protocol["case_id"], protocol["dataset_artifact_id"])["path"]


class RobustBaselineAgent(_CandidateModelAgent):
    name = "robust_baseline_agent"
    model_family = "robust_baseline"

    def _estimator(self):
        return HuberRegressor(max_iter=500)

    def _hyperparameters(self) -> dict[str, Any]:
        return {"max_iter": 500, "estimator": "HuberRegressor"}

    def _dataset_path(self, protocol: dict[str, Any]) -> str:
        return self.artifacts.get(protocol["case_id"], protocol["dataset_artifact_id"])["path"]


# ---------------------------------------------------------------- evaluation


class ModelEvaluationAgent(DeterministicAgent):
    """Reads every candidate for a protocol and decides, independently, what is usable.

    "Protocol-aware" means it re-derives validity from the protocol, not from
    the candidate's own ``status`` field: a candidate that self-reports VALID
    but was fit under a stale dataset hash is still marked INVALID here, with
    the specific reason. A candidate is never omitted from the comparison —
    silently dropping a failed candidate would let a bad model disappear
    instead of being visibly rejected.
    """

    name = "model_evaluation_agent"
    mandate = (ProposalKind.ANALYSIS_ACTION,)

    _REQUIRED_FIELDS = ("metric_name", "metric_value", "fold_metric_values")

    #: bumped whenever `_validate`'s logic changes -- a stored comparison
    #: written under an older evaluation implementation is never silently
    #: reused, even if the protocol and candidate hashes still match.
    _EVALUATION_VERSION = 1

    def __init__(self, cases: CaseManager, artifacts: ArtifactRegistry) -> None:
        self.cases = cases
        self.artifacts = artifacts

    def run(self, request: AgentRequest) -> AgentReport:
        protocol_artifact_id = request.inputs.get("protocol_artifact_id")
        if not protocol_artifact_id:
            return self.blocked("no protocol_artifact_id supplied")
        try:
            protocol_artifact = self.artifacts.get(request.case_id, protocol_artifact_id)
        except KeyError:
            return self.blocked(f"protocol artifact not found: {protocol_artifact_id}")
        case_root = self.cases.case_root(request.case_id)
        protocol = read_json(case_root / protocol_artifact["path"])

        candidate_artifacts = [
            item
            for item in self.artifacts.list_artifacts(request.case_id)
            if item["artifact_type"] == "model_candidate" and item["status"] == "ACTIVE"
        ]
        candidates = []
        for artifact in candidate_artifacts:
            content = read_json(case_root / artifact["path"])
            if content.get("protocol_id") != protocol_artifact_id:
                continue  # a candidate for a *different* protocol is not this comparison's evidence
            content["candidate_artifact_id"] = artifact["artifact_id"]
            candidates.append(self._validate(content, protocol, protocol_artifact))
        if not candidates:
            return self.blocked("no candidate artifacts found for this protocol")

        # Ordered by candidate_id so the signature (and therefore the
        # comparison content) does not depend on artifact_registry.jsonl's
        # incidental append order.
        input_signature = sorted(
            (
                {
                    "candidate_id": c["candidate_id"],
                    "candidate_artifact_id": c["candidate_artifact_id"],
                    "sha256": next(
                        a["sha256"] for a in candidate_artifacts if a["artifact_id"] == c["candidate_artifact_id"]
                    ),
                }
                for c in candidates
            ),
            key=lambda item: item["candidate_id"],
        )
        candidates_sorted = sorted(candidates, key=lambda c: c["candidate_id"])

        # Stable path: see _CandidateModelAgent.run for why (protocol changes
        # are detected by content, not by embedding the protocol id in the
        # filename).
        comparison_path = case_root / "agents" / "modeling" / "comparison.json"

        reused = self._find_reusable_comparison(
            request.case_id, comparison_path, protocol_artifact, input_signature
        )
        if reused is not None:
            comparison = reused
            reuse_status = "reused"
        else:
            comparison = {
                "schema_version": 1,
                "produced_by": "agent_modeling_fanout",
                "protocol_id": protocol_artifact_id,
                "protocol_hash": protocol_artifact["sha256"],
                "primary_metric": protocol["primary_metric"],
                "metric_direction": protocol["metric_direction"],
                "evaluation_version": self._EVALUATION_VERSION,
                "input_signature": input_signature,
                "candidates": candidates_sorted,
                # No wall-clock timestamp -- same idempotency reasoning as the
                # protocol and candidate records above.
            }
            atomic_write_json(comparison_path, comparison)
            reuse_status = "computed"

        comparison_artifact = self.artifacts.register_existing(
            request.case_id,
            comparison_path.relative_to(case_root).as_posix(),
            "model_comparison",
            self.name,
            upstream=[protocol_artifact_id, *[c["candidate_artifact_id"] for c in candidates]],
        )

        valid_count = sum(1 for c in comparison["candidates"] if c["status"] == "VALID")
        proposal = self.propose(
            ProposalKind.ANALYSIS_ACTION,
            summary="模型候选评估完成，已生成协议感知的比较产物",
            payload={
                "protocol_artifact_id": protocol_artifact_id,
                "comparison_artifact_id": comparison_artifact["artifact_id"],
                "candidate_count": len(comparison["candidates"]),
                "valid_count": valid_count,
                "invalid_count": len(comparison["candidates"]) - valid_count,
                "reuse_status": reuse_status,
            },
            evidence=[comparison_artifact["artifact_id"], protocol_artifact_id],
            rationale=(
                "每个候选相对协议独立复核，无候选被静默丢弃"
                if reuse_status == "computed"
                else "复用既有比较产物：协议、候选集合与每个候选的内容哈希均未变化"
            ),
        )
        return AgentReport(
            agent=self.name,
            proposals=[proposal],
            notes=f"{valid_count}/{len(comparison['candidates'])} valid ({reuse_status})",
        )

    def _find_reusable_comparison(
        self,
        case_id: str,
        comparison_path,
        protocol_artifact: dict[str, Any],
        input_signature: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Return the existing comparison content if it is safe to reuse, else ``None``.

        Reuse requires: a comparison already exists at the stable path; it
        was produced under this exact protocol artifact (id and hash); by
        this exact evaluation implementation version; from exactly this set
        of candidates (same candidate ids, same candidate artifact ids, same
        candidate content hashes -- a changed candidate anywhere invalidates
        reuse and forces recomputation, it is never partially reused); and
        the registry's ACTIVE entry at that path still matches the bytes on
        disk.
        """
        if not comparison_path.is_file():
            return None
        try:
            existing = read_json(comparison_path)
        except (OSError, ValueError):
            return None
        if existing.get("protocol_id") != protocol_artifact["artifact_id"]:
            return None
        if existing.get("protocol_hash") != protocol_artifact["sha256"]:
            return None
        if existing.get("evaluation_version") != self._EVALUATION_VERSION:
            return None
        if existing.get("input_signature") != input_signature:
            return None
        case_root = self.cases.case_root(case_id)
        relative_path = comparison_path.relative_to(case_root).as_posix()
        active_here = [
            item
            for item in self.artifacts.list_artifacts(case_id)
            if item.get("path") == relative_path and item.get("status") == "ACTIVE"
        ]
        if not active_here:
            return None
        if active_here[-1].get("sha256") != sha256_file(comparison_path):
            return None
        return existing

    def _validate(
        self, content: dict[str, Any], protocol: dict[str, Any], protocol_artifact: dict[str, Any]
    ) -> dict[str, Any]:
        record = dict(content)
        if record.get("status") == "INVALID" and record.get("invalid_reason"):
            return record  # candidate already reported its own failure; carry it through unchanged

        if record.get("protocol_id") != protocol_artifact["artifact_id"] or record.get(
            "protocol_hash"
        ) != protocol_artifact["sha256"]:
            record["status"] = "INVALID"
            record["invalid_reason"] = "PROTOCOL_MISMATCH: candidate was evaluated under a different protocol"
            return record
        if record.get("dataset_hash") != protocol["dataset_hash"]:
            record["status"] = "INVALID"
            record["invalid_reason"] = "STALE_EVIDENCE: candidate dataset_hash does not match the protocol"
            return record
        if any(record.get(field) in (None, "", []) for field in self._REQUIRED_FIELDS):
            record["status"] = "INVALID"
            record["invalid_reason"] = "MISSING_EVALUATION_FIELDS: required evaluation field absent"
            return record
        if not record.get("metric_direction"):
            record["status"] = "INVALID"
            record["invalid_reason"] = "METRIC_DIRECTION_MISSING"
            return record
        if len(record.get("fold_metric_values", [])) != protocol["n_splits"]:
            record["status"] = "INVALID"
            record["invalid_reason"] = (
                f"fold count {len(record.get('fold_metric_values', []))} != protocol n_splits {protocol['n_splits']}"
            )
            return record
        record["status"] = "VALID"
        record["invalid_reason"] = ""
        return record


# --------------------------------------------------------------------- judge


class ModelJudgeAgent(DeterministicAgent):
    """Reads the comparison artifact -- not any agent's prose -- and proposes a verdict.

    The judge never writes a claim. It proposes WINNER / TIE / NO_ACCEPTABLE_WINNER;
    ``Adjudicator._handle_model_selection`` independently re-derives the winner
    from the same comparison artifact before accepting the proposal, so the
    judge cannot make the claim true by asserting it.
    """

    name = "model_judge_agent"
    mandate = (ProposalKind.MODEL_SELECTION,)

    def __init__(self, cases: CaseManager, artifacts: ArtifactRegistry) -> None:
        self.cases = cases
        self.artifacts = artifacts

    def run(self, request: AgentRequest) -> AgentReport:
        comparison_artifact_id = request.inputs.get("comparison_artifact_id")
        if not comparison_artifact_id:
            return self.blocked("no comparison_artifact_id supplied")
        try:
            comparison_artifact = self.artifacts.get(request.case_id, comparison_artifact_id)
        except KeyError:
            return self.blocked(f"comparison artifact not found: {comparison_artifact_id}")
        case_root = self.cases.case_root(request.case_id)
        comparison = read_json(case_root / comparison_artifact["path"])
        protocol_id = comparison["protocol_id"]
        protocol_hash = comparison["protocol_hash"]
        direction = comparison["metric_direction"]

        valid = [c for c in comparison["candidates"] if c["status"] == "VALID"]
        payload_base = {
            "protocol_id": protocol_id,
            "protocol_hash": protocol_hash,
            "comparison_artifact_id": comparison_artifact_id,
        }
        evidence = [protocol_id, comparison_artifact_id]

        if not valid:
            proposal = self.propose(
                ProposalKind.MODEL_SELECTION,
                summary="无候选模型通过协议校验，无法选出获胜模型",
                payload={**payload_base, "outcome": "NO_ACCEPTABLE_WINNER"},
                evidence=evidence,
                rationale="所有候选在协议校验下均为 INVALID",
            )
            return AgentReport(agent=self.name, proposals=[proposal], notes="NO_ACCEPTABLE_WINNER")

        ordered = sorted(
            valid,
            key=lambda c: c["metric_value"] if direction == "minimize" else -c["metric_value"],
        )
        best = ordered[0]
        tied = [best]
        for candidate in ordered[1:]:
            if self._within_tolerance(best["metric_value"], candidate["metric_value"]):
                tied.append(candidate)
            else:
                break

        if len(tied) == 1:
            winner = best
            claim_text = (
                f"在协议 {protocol_id} 规定的 {comparison.get('primary_metric', comparison.get('primary_metric'))} "
                f"下，{winner['model_family']} 候选模型（{winner['candidate_id']}）的 "
                f"{winner['metric_name']} 为 {self._format(winner['metric_value'])}，"
                f"为 {len(comparison['candidates'])} 个候选中的最优模型。"
            )
            proposal = self.propose(
                ProposalKind.MODEL_SELECTION,
                summary=f"模型裁决完成，{winner['model_family']} 胜出",
                payload={
                    **payload_base,
                    "outcome": "WINNER",
                    "winner_candidate_id": winner["candidate_id"],
                    "claim_text": claim_text,
                    "claim_type": "model_selection",
                    "dataset_ids": [comparison.get("dataset_id")] if comparison.get("dataset_id") else [],
                    "section_hint": "results",
                },
                evidence=evidence,
                rationale="逐一比较协议下各候选的折均指标，取满足容差外的严格最优者",
            )
            return AgentReport(agent=self.name, proposals=[proposal], notes=f"WINNER={winner['candidate_id']}")

        simpler = self._simpler_under_tie(tied)
        if simpler is not None:
            winner = simpler
            claim_text = (
                f"候选模型 {', '.join(c['candidate_id'] for c in tied)} 在协议 {protocol_id} 下的 "
                f"{winner['metric_name']} 差异在容差范围内（视为并列）；按“并列取更简单模型”规则，"
                f"{winner['model_family']} 候选模型（{winner['candidate_id']}）的 "
                f"{winner['metric_name']} 为 {self._format(winner['metric_value'])}，被选为最终模型。"
            )
            proposal = self.propose(
                ProposalKind.MODEL_SELECTION,
                summary=f"模型裁决完成，并列后按简单优先规则选定 {winner['model_family']}",
                payload={
                    **payload_base,
                    "outcome": "WINNER",
                    "winner_candidate_id": winner["candidate_id"],
                    "claim_text": claim_text,
                    "claim_type": "model_selection",
                    "dataset_ids": [comparison.get("dataset_id")] if comparison.get("dataset_id") else [],
                    "section_hint": "results",
                },
                evidence=evidence,
                rationale="并列候选按模型复杂度打破平局，而非按指标本身",
            )
            return AgentReport(agent=self.name, proposals=[proposal], notes=f"WINNER(tie-break)={winner['candidate_id']}")

        proposal = self.propose(
            ProposalKind.MODEL_SELECTION,
            summary="多个候选模型指标并列，且复杂度无法区分，判定为平局",
            payload={
                **payload_base,
                "outcome": "TIE",
                "tie_candidate_ids": [c["candidate_id"] for c in tied],
            },
            evidence=evidence,
            rationale="指标差异在容差范围内，且候选复杂度并列，无法在不臆断的情况下选出唯一获胜者",
        )
        return AgentReport(agent=self.name, proposals=[proposal], notes="TIE")

    @staticmethod
    def _within_tolerance(best_value: float, other_value: float) -> bool:
        denominator = abs(best_value) or 1.0
        return abs(other_value - best_value) / denominator <= _TIE_TOLERANCE

    @staticmethod
    def _simpler_under_tie(tied: list[dict[str, Any]]) -> dict[str, Any] | None:
        ranked = sorted(
            tied,
            key=lambda c: _COMPLEXITY_RANK.get(c["model_family"], len(_COMPLEXITY_RANK)),
        )
        if len(ranked) < 2:
            return ranked[0] if ranked else None
        # only a real tie-break if the simplest candidate's rank is strictly
        # lower than the next -- if two candidates share a rank, this is not
        # resolvable by complexity and must fall through to TIE.
        best_rank = _COMPLEXITY_RANK.get(ranked[0]["model_family"], len(_COMPLEXITY_RANK))
        next_rank = _COMPLEXITY_RANK.get(ranked[1]["model_family"], len(_COMPLEXITY_RANK))
        return ranked[0] if best_rank < next_rank else None

    @staticmethod
    def _format(value: float) -> str:
        text = f"{value:.3f}"
        return text.rstrip("0").rstrip(".") if "." in text else text


def build_modeling_agents(
    cases: CaseManager, artifacts: ArtifactRegistry
) -> dict[str, DeterministicAgent]:
    """The five named agents this module implements, keyed by their ``name``."""
    return {
        "linear_model_agent": LinearModelAgent(cases, artifacts),
        "tree_model_agent": TreeModelAgent(cases, artifacts),
        "robust_baseline_agent": RobustBaselineAgent(cases, artifacts),
        "model_evaluation_agent": ModelEvaluationAgent(cases, artifacts),
        "model_judge_agent": ModelJudgeAgent(cases, artifacts),
    }

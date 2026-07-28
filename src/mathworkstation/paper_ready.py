from __future__ import annotations

import json
from typing import Any

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .experiments import ExperimentRegistry
from .io_utils import append_jsonl, atomic_write_json, now_iso


class PaperReadyGate:
    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        experiments: ExperimentRegistry,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.experiments = experiments

    def assess(
        self,
        case_id: str,
        experiment_id: str,
        selection_artifact_id: str,
        sensitivity_artifact_id: str,
        additional_artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        experiment = self.experiments.get(case_id, experiment_id)
        selection = self.artifacts.get(case_id, selection_artifact_id)
        sensitivity = self.artifacts.get(case_id, sensitivity_artifact_id)
        reasons: list[str] = []
        # PAPER_READY is the state approve() itself writes. Accepting it keeps the
        # gate re-runnable, so a later approval can promote additional evidence
        # (data profile, EDA summary, ...) without invalidating the first decision.
        if experiment["status"] not in ("SUCCEEDED", "PAPER_READY"):
            reasons.append("experiment_not_succeeded")
        if selection["artifact_type"] != "model_selection":
            reasons.append("invalid_model_selection_artifact")
        if sensitivity["artifact_type"] != "sensitivity_results":
            reasons.append("invalid_sensitivity_artifact")
        sensitivity_payload = json.loads(
            (self.cases.case_root(case_id) / sensitivity["path"]).read_text(encoding="utf-8")
        )
        if sensitivity_payload.get("gate") != "PASS":
            reasons.append("sensitivity_requires_review")
        artifact_check = self.artifacts.verify(case_id)
        if not artifact_check["valid"]:
            reasons.append("artifact_integrity_failed")
        required_ids = [
            experiment.get("comparison_artifact_id"),
            experiment.get("diagnostics_artifact_id"),
            selection_artifact_id,
            sensitivity_artifact_id,
        ]
        required_ids.extend(additional_artifact_ids or [])
        if any(not item for item in required_ids):
            reasons.append("required_artifact_missing")
        return {
            "schema_version": 1,
            "case_id": case_id,
            "experiment_id": experiment_id,
            "eligible": not reasons,
            "reasons": reasons,
            "required_artifact_ids": [item for item in required_ids if item],
            "assessed_at": now_iso(),
        }

    def approve(
        self,
        case_id: str,
        experiment_id: str,
        selection_artifact_id: str,
        sensitivity_artifact_id: str,
        approved_by: str,
        note: str,
        additional_artifact_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if not note.strip():
            raise ValueError("paper-ready approval requires a note")
        assessment = self.assess(
            case_id,
            experiment_id,
            selection_artifact_id,
            sensitivity_artifact_id,
            additional_artifact_ids,
        )
        if not assessment["eligible"]:
            raise ValueError(f"experiment is not paper ready: {assessment['reasons']}")
        root = self.cases.case_root(case_id)
        approval = {
            **assessment,
            "status": "APPROVED",
            "approved_by": approved_by,
            "approval_note": note,
            "approved_at": now_iso(),
        }
        path = root / "review" / "reproducibility" / f"paper-ready-{experiment_id}.json"
        atomic_write_json(path, approval)
        approval_artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "paper_ready_approval",
            "human",
            upstream=assessment["required_artifact_ids"],
            paper_eligible=True,
        )
        promoted: list[str] = []
        for artifact_id in assessment["required_artifact_ids"]:
            self.artifacts.promote_to_paper(case_id, artifact_id, approval_artifact["artifact_id"])
            promoted.append(artifact_id)
        self.experiments.update(
            case_id,
            experiment_id,
            "PAPER_READY",
            paper_eligible=True,
            paper_ready_approval_id=approval_artifact["artifact_id"],
        )
        append_jsonl(
            root / "decisions.jsonl",
            {
                "timestamp": now_iso(),
                "event": "experiment_paper_ready",
                "experiment_id": experiment_id,
                "approved_by": approved_by,
                "approval_artifact_id": approval_artifact["artifact_id"],
            },
        )
        return {
            "approval": approval,
            "approval_artifact_id": approval_artifact["artifact_id"],
            "promoted_artifact_ids": promoted,
        }


class ModelingEvidenceGate:
    """The same evidence-promotion primitive as :class:`PaperReadyGate`, wired
    to the bounded modeling fan-out's artifact shape instead of the manual
    plan/experiment/sensitivity path.

    Deliberately not a subclass of ``PaperReadyGate``: that gate's ``assess``
    requires an :class:`~mathworkstation.experiments.ExperimentRegistry`
    experiment and a ``sensitivity_results`` artifact, neither of which the
    modeling fan-out (``agents/modeling.py``) produces -- it has its own
    integrity chain (an immutable ``modeling_protocol``, a
    protocol-referencing ``model_comparison``). Reusing ``assess``/``approve``
    as-is would mean either forcing a fake experiment/sensitivity pair into
    existence (a parallel shortcut) or silently loosening the manual path's
    checks. Both are exactly what the eligibility rules must not do. What
    *is* reused, unchanged, is ``ArtifactRegistry.promote_to_paper`` -- the
    one truly generic step ("this artifact may now back a VERIFIED claim")
    -- via the same call the manual gate makes.
    """

    def __init__(self, cases: CaseManager, artifacts: ArtifactRegistry) -> None:
        self.cases = cases
        self.artifacts = artifacts

    def assess(self, case_id: str, protocol_artifact_id: str, comparison_artifact_id: str) -> dict[str, Any]:
        reasons: list[str] = []
        try:
            protocol_artifact = self.artifacts.get(case_id, protocol_artifact_id)
        except KeyError:
            return self._ineligible(case_id, protocol_artifact_id, comparison_artifact_id, ["protocol_artifact_unknown"])
        try:
            comparison_artifact = self.artifacts.get(case_id, comparison_artifact_id)
        except KeyError:
            return self._ineligible(case_id, protocol_artifact_id, comparison_artifact_id, ["comparison_artifact_unknown"])

        if protocol_artifact.get("artifact_type") != "modeling_protocol":
            reasons.append("invalid_protocol_artifact")
        if protocol_artifact.get("status") != "ACTIVE":
            reasons.append("protocol_artifact_not_active")
        if comparison_artifact.get("artifact_type") != "model_comparison":
            reasons.append("invalid_comparison_artifact")
        if comparison_artifact.get("status") != "ACTIVE":
            reasons.append("comparison_artifact_not_active")

        candidate_artifact_ids: list[str] = []
        if not reasons:
            comparison = json.loads(
                (self.cases.case_root(case_id) / comparison_artifact["path"]).read_text(encoding="utf-8")
            )
            if comparison.get("protocol_id") != protocol_artifact_id:
                reasons.append("comparison_references_a_different_protocol")
            elif comparison.get("protocol_hash") != protocol_artifact.get("sha256"):
                reasons.append("comparison_protocol_hash_is_stale")
            candidates = comparison.get("candidates", [])
            valid_candidates = [c for c in candidates if c.get("status") == "VALID"]
            if not valid_candidates:
                reasons.append("no_valid_candidate_in_comparison")
            candidate_artifact_ids = sorted(
                {c["candidate_artifact_id"] for c in candidates if c.get("candidate_artifact_id")}
            )

        artifact_check = self.artifacts.verify(case_id)
        if not artifact_check["valid"]:
            reasons.append("artifact_integrity_failed")

        required_ids = [protocol_artifact_id, comparison_artifact_id, *candidate_artifact_ids]
        return {
            "schema_version": 1,
            "case_id": case_id,
            "protocol_artifact_id": protocol_artifact_id,
            "comparison_artifact_id": comparison_artifact_id,
            "eligible": not reasons,
            "reasons": reasons,
            "required_artifact_ids": required_ids,
            "assessed_at": now_iso(),
        }

    def _ineligible(self, case_id: str, protocol_artifact_id: str, comparison_artifact_id: str, reasons: list[str]) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "case_id": case_id,
            "protocol_artifact_id": protocol_artifact_id,
            "comparison_artifact_id": comparison_artifact_id,
            "eligible": False,
            "reasons": reasons,
            "required_artifact_ids": [],
            "assessed_at": now_iso(),
        }

    def approve(
        self,
        case_id: str,
        protocol_artifact_id: str,
        comparison_artifact_id: str,
        approved_by: str,
        note: str,
    ) -> dict[str, Any]:
        if not note.strip():
            raise ValueError("modeling evidence approval requires a note")
        assessment = self.assess(case_id, protocol_artifact_id, comparison_artifact_id)
        if not assessment["eligible"]:
            raise ValueError(f"modeling evidence is not paper ready: {assessment['reasons']}")
        root = self.cases.case_root(case_id)
        approval = {
            **assessment,
            "status": "APPROVED",
            "approved_by": approved_by,
            "approval_note": note,
            "approved_at": now_iso(),
        }
        path = root / "review" / "reproducibility" / f"modeling-evidence-{comparison_artifact_id}.json"
        approval_artifact_upstream = assessment["required_artifact_ids"]
        atomic_write_json(path, approval)
        approval_artifact = self.artifacts.register_existing(
            case_id,
            path.relative_to(root).as_posix(),
            "paper_ready_approval",
            "human",
            upstream=approval_artifact_upstream,
            paper_eligible=True,
        )
        promoted: list[str] = []
        for artifact_id in assessment["required_artifact_ids"]:
            self.artifacts.promote_to_paper(case_id, artifact_id, approval_artifact["artifact_id"])
            promoted.append(artifact_id)
        append_jsonl(
            root / "decisions.jsonl",
            {
                "timestamp": now_iso(),
                "event": "modeling_evidence_paper_ready",
                "protocol_artifact_id": protocol_artifact_id,
                "comparison_artifact_id": comparison_artifact_id,
                "approved_by": approved_by,
                "approval_artifact_id": approval_artifact["artifact_id"],
            },
        )
        return {
            "approval": approval,
            "approval_artifact_id": approval_artifact["artifact_id"],
            "promoted_artifact_ids": promoted,
        }

"""Concrete agents.

Four deterministic agents form the vertical slice that is wired end to end today:

    DataStewardAgent -> EDAAnalystAgent -> EvidenceVerifierAgent -> QualityAssuranceAgent

Each wraps an engine the workstation already has, so the slice runs with no API
key and produces byte-identical output on re-run. The LLM-backed roles
(decomposition, model rationale, section writing) are declared in
``docs/multi-agent-architecture.md`` and slot into the same graph via
:class:`~mathworkstation.agents.base.LLMAgent`; they are not implemented here.
"""

from __future__ import annotations

from typing import Any

from ..artifact_registry import ArtifactRegistry
from ..case_manager import CaseManager
from ..claims import ClaimRegistry
from ..data_service import DataService
from ..eda import EDAEngine
from ..figure_registry import FigureRegistry
from ..io_utils import read_json
from ..paper_consistency import PaperConsistencyChecker
from .base import DeterministicAgent
from .contracts import AgentReport, AgentRequest, ProposalKind


def _artifact_of_type(
    artifacts: ArtifactRegistry, case_id: str, artifact_type: str
) -> dict[str, Any] | None:
    match = [
        item
        for item in artifacts.list_artifacts(case_id)
        if item["artifact_type"] == artifact_type and item["status"] == "ACTIVE"
    ]
    return match[-1] if match else None


class DataStewardAgent(DeterministicAgent):
    """Registers the data profile and reports what the quality gate decided.

    It proposes no claims. Data facts only become claims after the profile
    artifact has been promoted, which is a human decision — the steward's job is
    to make the gate result visible, not to argue past it.
    """

    name = "data_steward"
    mandate = (ProposalKind.DATA_ACTION, ProposalKind.REPAIR_REQUEST)

    def __init__(self, data: DataService, artifacts: ArtifactRegistry) -> None:
        self.data = data
        self.artifacts = artifacts

    def run(self, request: AgentRequest) -> AgentReport:
        dataset_id = request.inputs.get("dataset_id")
        if not dataset_id:
            return self.blocked("no dataset_id supplied")
        result = self._profile_or_reuse(request, dataset_id)
        if result is None:
            return self.blocked("data_quality 已完成但找不到画像产物")
        profile = result["profile"]
        gate = profile["quality_gate"]
        proposals = [
            self.propose(
                ProposalKind.DATA_ACTION,
                summary=f"数据画像完成，质量门为 {gate}",
                payload={
                    "dataset_id": dataset_id,
                    "quality_gate": gate,
                    "rows": profile["shape"]["rows"],
                    "columns": profile["shape"]["columns"],
                    "missing_cells": profile["missing_cells"],
                    "duplicate_rows": profile["duplicate_rows"],
                    "profile_artifact_id": result["profile_artifact_id"],
                },
                evidence=[result["profile_artifact_id"]],
                rationale="确定性画像，指标直接来自登记数据集",
            )
        ]
        if gate != "PASS":
            proposals.append(
                self.propose(
                    ProposalKind.REPAIR_REQUEST,
                    summary=f"数据质量门为 {gate}，建模前需要人工处理",
                    payload={"dataset_id": dataset_id, "issues": profile["issues"]},
                    evidence=[result["profile_artifact_id"]],
                )
            )
        return AgentReport(
            agent=self.name,
            proposals=proposals,
            notes=f"gate={gate}",
        )

    def _profile_or_reuse(
        self, request: AgentRequest, dataset_id: str
    ) -> dict[str, Any] | None:
        """Profile the dataset, or reuse the existing profile when already done.

        Agent runs must be re-entrant: an operator will re-run the pipeline on a
        case that is already partly complete, and a node that has legitimately
        SUCCEEDED must not be forced through an illegal DAG transition. When the
        gate has already been decided, the steward reports that decision from the
        registered artifact instead of recomputing it.
        """
        snapshot = self.data.workflow.checkpoints.snapshot(request.case_id)
        status = snapshot["nodes"]["data_quality"]["status"]
        if status not in {"SUCCEEDED", "DEGRADED"}:
            return self.data.profile_dataset(
                request.case_id,
                dataset_id,
                request.inputs.get("target_column"),
                request.session_id,
            )
        artifact = _artifact_of_type(self.artifacts, request.case_id, "data_profile")
        if artifact is None:
            return None
        profile = read_json(self.artifacts.cases.case_root(request.case_id) / artifact["path"])
        return {
            "profile": profile,
            "profile_artifact_id": artifact["artifact_id"],
            "reused": True,
        }


class EDAAnalystAgent(DeterministicAgent):
    """Runs exploratory analysis and surfaces the structure that constrains modeling.

    The useful output is not "here are some plots" but the collinearity and
    target-association structure that later dictates the model family. That
    structure is emitted as an advisory proposal so the modeling agent inherits
    a reason, not just a dataset.
    """

    name = "eda_analyst"
    mandate = (ProposalKind.ANALYSIS_ACTION, ProposalKind.FIGURE_REQUEST)

    #: |r| above which two features are reported as structurally collinear.
    COLLINEARITY_THRESHOLD = 0.6

    def __init__(
        self,
        eda: EDAEngine,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
    ) -> None:
        self.eda = eda
        self.cases = cases
        self.artifacts = artifacts

    def run(self, request: AgentRequest) -> AgentReport:
        dataset_id = request.inputs.get("dataset_id")
        if not dataset_id:
            return self.blocked("no dataset_id supplied")
        target = request.inputs.get("target_column")
        try:
            result = self.eda.run(request.case_id, dataset_id, target)
        except ValueError as error:
            return self.blocked(str(error))

        summary = result["summary"]
        structure = self._structure(request.case_id, dataset_id, target)
        proposals = [
            self.propose(
                ProposalKind.ANALYSIS_ACTION,
                summary="探索性分析完成，已提取相关结构",
                payload={
                    "dataset_id": dataset_id,
                    "numeric_columns": summary["numeric_columns"],
                    "target_column": summary.get("target_column"),
                    **structure,
                },
                evidence=[result["summary_artifact_id"]],
                rationale="相关系数由确定性脚本在登记数据上计算",
            )
        ]
        if structure.get("collinear_pairs"):
            proposals.append(
                self.propose(
                    ProposalKind.ANALYSIS_ACTION,
                    summary="检出结构性多重共线性，建议采用正则化线性模型族",
                    payload={
                        "collinear_pairs": structure["collinear_pairs"],
                        "recommended_family": "regularized_linear",
                    },
                    evidence=[result["summary_artifact_id"]],
                    rationale=(
                        "共线特征组会使普通最小二乘系数方差膨胀；"
                        "L2 收缩方差、L1 兼做特征筛选"
                    ),
                    confidence=0.9,
                )
            )
        return AgentReport(agent=self.name, proposals=proposals, notes=structure.get("note", ""))

    def _structure(self, case_id: str, dataset_id: str, target: str | None) -> dict[str, Any]:
        """Recompute correlations from the registered table.

        The EDA summary keeps per-column statistics but not the correlation
        matrix, and reading the registered artifact is cheaper than widening that
        schema. Reading through the registry (not an arbitrary path) keeps the
        provenance chain intact.
        """
        try:
            import numpy as np  # noqa: F401 - pandas dependency check
            import pandas as pd
        except ImportError:  # pragma: no cover - pandas is a hard dependency
            return {"note": "pandas unavailable"}
        dataset_artifact = _artifact_of_type(self.artifacts, case_id, "observed_data")
        if dataset_artifact is None:
            return {"note": "no observed dataset artifact"}
        path = self.cases.case_root(case_id) / dataset_artifact["path"]
        frame = pd.read_csv(path) if path.suffix.lower() == ".csv" else pd.read_excel(path)
        numeric = frame.select_dtypes("number")
        if numeric.shape[1] < 2:
            return {"note": "fewer than two numeric columns"}
        corr = numeric.corr()
        features = [column for column in numeric.columns if column != target]
        collinear = []
        for index, left in enumerate(features):
            for right in features[index + 1 :]:
                value = float(corr.loc[left, right])
                if abs(value) > self.COLLINEARITY_THRESHOLD:
                    collinear.append({"left": left, "right": right, "r": round(value, 4)})
        target_assoc: list[dict[str, Any]] = []
        if target and target in corr.columns:
            ordered = corr[target].drop(labels=[target]).sort_values(key=abs, ascending=False)
            target_assoc = [
                {"feature": name, "r": round(float(value), 4)}
                for name, value in ordered.items()
            ]
        return {
            "collinear_pairs": sorted(collinear, key=lambda item: -abs(item["r"])),
            "target_association": target_assoc[:5],
        }


class EvidenceVerifierAgent(DeterministicAgent):
    """Turns typed records into claims, and refuses to state anything else.

    This agent is the one place where a number becomes a sentence. It reads only
    promoted (``paper_eligible``) artifacts, so a claim it proposes is
    admissible by construction; anything it cannot source is reported as a
    repair request rather than softened into vague prose.
    """

    name = "evidence_verifier"
    mandate = (ProposalKind.CLAIM, ProposalKind.REPAIR_REQUEST)

    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        claims: ClaimRegistry,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.claims = claims

    def run(self, request: AgentRequest) -> AgentReport:
        proposals = []
        comparison = _artifact_of_type(self.artifacts, request.case_id, "model_comparison")
        if comparison and comparison.get("paper_eligible"):
            proposals.extend(self._comparison_claims(request.case_id, comparison))
        elif comparison:
            proposals.append(
                self.propose(
                    ProposalKind.REPAIR_REQUEST,
                    summary="模型比较结果尚未通过 paper-ready 审批，无法进入论文",
                    payload={"artifact_id": comparison["artifact_id"]},
                )
            )

        sensitivity = _artifact_of_type(self.artifacts, request.case_id, "sensitivity_results")
        if sensitivity and sensitivity.get("paper_eligible"):
            proposals.extend(self._sensitivity_claims(request.case_id, sensitivity))

        if not proposals:
            return self.skipped("没有已晋升的实验证据可供登记结论")
        return AgentReport(agent=self.name, proposals=proposals)

    def _comparison_claims(self, case_id: str, artifact: dict[str, Any]) -> list:
        payload = read_json(self.cases.case_root(case_id) / artifact["path"])
        best = payload["best_model"]
        metric = payload["primary_metric"]
        models = payload["models"]
        winner = models[best]
        ranked = sorted(models.items(), key=lambda item: item[1][f"{metric}_mean"])
        table = "；".join(
            f"{name} {values[f'{metric}_mean']:.3f}" for name, values in ranked
        )
        return [
            self.propose(
                ProposalKind.CLAIM,
                summary=f"{best} 在 {payload['cv_folds']} 折交叉验证下 {metric} 最优",
                payload={
                    "text": (
                        f"在 {payload['cv_folds']} 折交叉验证下，{best} 的 {metric} 均值为 "
                        f"{winner[f'{metric}_mean']:.3f}、标准差为 {winner[f'{metric}_std']:.3f}，"
                        f"为 {len(models)} 个候选模型中最优；各模型 {metric} 均值依次为 {table}。"
                    ),
                    "claim_type": "model_result",
                    "section_hint": "results",
                },
                evidence=[artifact["artifact_id"]],
                rationale="数值逐字取自已审批的比较结果产物",
            )
        ]

    def _sensitivity_claims(self, case_id: str, artifact: dict[str, Any]) -> list:
        payload = read_json(self.cases.case_root(case_id) / artifact["path"])
        grouped = payload.get("grouped", [])
        if not grouped:
            return []
        means = "、".join(
            f"{item['fraction']:.0%} 时 {item['mean']:.3f}" for item in grouped
        )
        return [
            self.propose(
                ProposalKind.CLAIM,
                summary="样本比例与随机种子敏感性结果",
                payload={
                    "text": (
                        f"在 {len(grouped)} 个样本比例 × 每档 {grouped[0]['runs']} 个随机种子的重复实验中，"
                        f"{payload['best_model']} 的留出 {payload['primary_metric']} 均值为 {means}；"
                        f"最大组内相对标准差 {payload['worst_relative_std']:.2%}，"
                        f"最大相对退化 {payload['worst_relative_degradation']:.2%}，"
                        f"稳健性门为 {payload['gate']}。"
                    ),
                    "claim_type": "sensitivity",
                    "section_hint": "sensitivity",
                },
                evidence=[artifact["artifact_id"]],
                rationale="数值逐字取自已审批的敏感性结果产物",
            )
        ]


class QualityAssuranceAgent(DeterministicAgent):
    """Runs the consistency gate and reports each finding as a typed review item.

    It has no authority to relax a gate. A BLOCK finding becomes a NEEDS_HUMAN
    verdict, which is the point: quality assurance escalates, it does not
    negotiate.
    """

    name = "quality_assurance"
    mandate = (ProposalKind.REVIEW_FINDING,)

    def __init__(self, checker: PaperConsistencyChecker) -> None:
        self.checker = checker

    def run(self, request: AgentRequest) -> AgentReport:
        try:
            result = self.checker.check(request.case_id)
        except FileNotFoundError:
            return self.skipped("论文章节尚未初始化，跳过一致性检查")
        report = result["report"]
        proposals = [
            self.propose(
                ProposalKind.REVIEW_FINDING,
                summary=f"[{finding['severity']}] {finding['section_id']}: {finding['code']}",
                payload={
                    "severity": finding["severity"],
                    "code": finding["code"],
                    "section_id": finding["section_id"],
                    "detail": finding.get("detail", ""),
                },
            )
            for finding in report["findings"]
        ]
        if not proposals:
            proposals.append(
                self.propose(
                    ProposalKind.REVIEW_FINDING,
                    summary="论文一致性检查通过，无未决问题",
                    payload={"severity": "INFO", "code": "CONSISTENCY_PASS"},
                )
            )
        return AgentReport(agent=self.name, proposals=proposals, notes=f"gate={report['gate']}")


def build_default_roster(
    *,
    data: DataService,
    eda: EDAEngine,
    cases: CaseManager,
    artifacts: ArtifactRegistry,
    claims: ClaimRegistry,
    figures: FigureRegistry,
    checker: PaperConsistencyChecker,
) -> list[DeterministicAgent]:
    """The deterministic slice, in execution order."""
    return [
        DataStewardAgent(data, artifacts),
        EDAAnalystAgent(eda, cases, artifacts),
        EvidenceVerifierAgent(cases, artifacts, claims),
        QualityAssuranceAgent(checker),
    ]

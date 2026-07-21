from __future__ import annotations

from collections import Counter
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from .artifact_registry import ArtifactRegistry
from .case_manager import CaseManager
from .io_utils import append_jsonl, atomic_write_json, atomic_write_text, now_iso, read_json, sha256_file
from .paper_consistency import CLAIM_REF, FIGURE_REF, INTERNAL_ARTIFACT_REF, NUMBER, PLACEHOLDER
from .paper_outline import section_contract
from .run_manager import RunManager
from .stage_service import _render_final_manuscript
from .workflow import FailureCategory
from .workflow_service import WorkflowService


DIMENSIONS = (
    "problem_coverage",
    "evidence_alignment",
    "data_reasoning",
    "model_logic",
    "result_explanation",
    "figure_alignment",
    "abstract_quality",
    "writing_quality",
)

DIMENSION_SECTION = {
    "problem_coverage": "problem_restated",
    "evidence_alignment": "global",
    "data_reasoning": "data_analysis",
    "model_logic": "model_construction",
    "result_explanation": "results",
    "figure_alignment": "results",
    "abstract_quality": "abstract",
    "writing_quality": "global",
}


@dataclass(frozen=True)
class RefinementConfig:
    max_stages: int = 10
    min_stages: int = 2
    patience: int = 2
    min_delta: float = 0.015
    target_dimension_delta: float = 0.01
    semantic_tolerance: float = 0.005
    max_rejection_streak: int = 2
    max_no_progress_attempts: int = 3
    max_issue_attempts: int = 2
    max_sections_per_stage: int = 2
    max_issues_per_stage: int = 3
    max_changed_ratio: float = 0.12
    quality_ema_beta: float = 0.6
    targets: dict[str, float] = field(
        default_factory=lambda: {
            "problem_coverage": 0.72,
            "evidence_alignment": 0.95,
            "data_reasoning": 0.72,
            "model_logic": 0.72,
            "result_explanation": 0.72,
            "figure_alignment": 0.90,
            "abstract_quality": 0.75,
            "writing_quality": 0.72,
        }
    )

    def __post_init__(self) -> None:
        if self.max_stages < 1 or not 0 <= self.min_stages <= self.max_stages:
            raise ValueError("invalid refinement stage bounds")
        if self.patience < 1 or self.max_rejection_streak < 1:
            raise ValueError("refinement patience values must be positive")
        if not 0 < self.max_changed_ratio <= 1:
            raise ValueError("max_changed_ratio must be in (0, 1]")
        missing = set(DIMENSIONS) - self.targets.keys()
        if missing:
            raise ValueError(f"missing quality targets: {sorted(missing)}")


class PaperQualityEvaluator:
    def evaluate(
        self,
        sections: dict[str, str],
        frozen: dict[str, Any],
        targets: dict[str, float],
    ) -> dict[str, Any]:
        findings: list[dict[str, Any]] = []
        contracts = frozen["sections"]
        for section_id, contract in contracts.items():
            content = sections.get(section_id, "")
            if not content.strip():
                findings.append(_finding("P0", section_id, "SECTION_MISSING", "section is absent"))
                continue
            if not content.lstrip().startswith("#"):
                findings.append(_finding("P1", section_id, "SECTION_HEADING_MISSING", ""))
            placeholders = PLACEHOLDER.findall(content)
            if placeholders:
                findings.append(_finding("P0", section_id, "PLACEHOLDER_REMAINS", ", ".join(placeholders)))
            internal = INTERNAL_ARTIFACT_REF.findall(content)
            if internal:
                findings.append(_finding("P0", section_id, "INTERNAL_ARTIFACT_REFERENCE", ", ".join(internal)))
            claims = set(CLAIM_REF.findall(content))
            figures = set(FIGURE_REF.findall(content))
            required_claims = set(contract["required_claim_ids"])
            required_figures = set(contract["required_figure_ids"])
            allowed_claims = set(contract["allowed_claim_ids"])
            allowed_figures = set(contract["allowed_figure_ids"])
            if not required_claims.issubset(claims):
                findings.append(_finding("P0", section_id, "VERIFIED_CLAIM_REMOVED", ", ".join(sorted(required_claims - claims))))
            if not required_figures.issubset(figures):
                findings.append(_finding("P0", section_id, "VERIFIED_FIGURE_REMOVED", ", ".join(sorted(required_figures - figures))))
            if claims - allowed_claims:
                findings.append(_finding("P0", section_id, "CLAIM_OUT_OF_SCOPE", ", ".join(sorted(claims - allowed_claims))))
            if figures - allowed_figures:
                findings.append(_finding("P0", section_id, "FIGURE_OUT_OF_SCOPE", ", ".join(sorted(figures - allowed_figures))))
            numbers = Counter(NUMBER.findall(_body(content)))
            if numbers != Counter(contract["number_tokens"]):
                findings.append(_finding("P0", section_id, "VERIFIED_NUMBERS_CHANGED", _counter_diff(Counter(contract["number_tokens"]), numbers)))
            missing_contracts = [
                "/".join(group)
                for group in section_contract(section_id).get("required_any", [])
                if not any(token in content for token in group)
            ]
            if missing_contracts:
                findings.append(_finding("P1", section_id, "SECTION_CONTRACT_MISSING", "; ".join(missing_contracts)))
            if section_id in {"model_construction", "model_solution"} and "$" not in content and "\\begin{" not in content:
                findings.append(_finding("P1", section_id, "MODEL_FORMULA_MISSING", ""))
            if contract.get("synthetic_disclosure_required") and "SYNTHETIC" not in content.upper() and "合成" not in content:
                findings.append(_finding("P0", section_id, "SYNTHETIC_DISCLOSURE_MISSING", ""))

        dimensions = self._dimensions(sections, frozen)
        for dimension, score in dimensions.items():
            if score + 1e-9 < targets[dimension]:
                findings.append(
                    _finding(
                        "P2",
                        DIMENSION_SECTION[dimension],
                        f"{dimension.upper()}_BELOW_TARGET",
                        f"score={score:.4f}, target={targets[dimension]:.4f}",
                        dimension=dimension,
                    )
                )
        hard_pass = not any(item["severity"] in {"P0", "P1"} for item in findings)
        total = sum(dimensions.values()) / len(dimensions)
        return {
            "schema_version": 1,
            "hard_gate": "PASS" if hard_pass else "BLOCK",
            "quality_vector": {"hard_gate": 1.0 if hard_pass else 0.0, **dimensions, "total": round(total, 6)},
            "findings": findings,
            "evaluated_at": now_iso(),
        }

    def _dimensions(self, sections: dict[str, str], frozen: dict[str, Any]) -> dict[str, float]:
        nonempty = sum(bool(value.strip()) for value in sections.values())
        coverage = nonempty / max(1, len(frozen["section_order"]))
        problem = _keyword_score(sections.get("problem_restated", ""), ("问题", "目标", "约束", "评价"))
        data = _keyword_score(sections.get("data_analysis", ""), ("数据", "缺失", "异常", "分布", "特征"))
        model_text = sections.get("model_construction", "") + sections.get("model_solution", "")
        model = 0.65 * _keyword_score(model_text, ("模型", "参数", "训练", "评价", "假设")) + 0.35 * float("$" in model_text or "\\begin{" in model_text)
        result_text = sections.get("results", "") + sections.get("conclusion", "")
        results = _keyword_score(result_text, ("结果", "指标", "比较", "结论", "限制"))
        required_claims = sum(len(item["required_claim_ids"]) for item in frozen["sections"].values())
        present_claims = sum(len(set(CLAIM_REF.findall(sections.get(section_id, "")))) for section_id in frozen["section_order"])
        evidence = 1.0 if required_claims == 0 else min(1.0, present_claims / required_claims)
        required_figures = sum(len(item["required_figure_ids"]) for item in frozen["sections"].values())
        present_figures = sum(len(set(FIGURE_REF.findall(sections.get(section_id, "")))) for section_id in frozen["section_order"])
        figures = 1.0 if required_figures == 0 else min(1.0, present_figures / required_figures)
        abstract = sections.get("abstract", "")
        abstract_keywords = _keyword_score(abstract, ("目的", "方法", "结果", "结论"))
        abstract_length = min(1.0, max(0.0, len(abstract) - 200) / 500)
        abstract_score = 0.7 * abstract_keywords + 0.3 * abstract_length
        paragraphs = [
            paragraph.strip()
            for content in sections.values()
            for paragraph in re.split(r"\n\s*\n", content)
            if len(paragraph.strip()) >= 30 and not paragraph.lstrip().startswith("#")
        ]
        duplicate_ratio = 0.0 if not paragraphs else 1 - len(set(paragraphs)) / len(paragraphs)
        useful_length = sum(min(1.0, len(value) / 350) for value in sections.values()) / max(1, len(sections))
        writing = max(0.0, 0.55 * useful_length + 0.45 * (1 - duplicate_ratio))
        return {
            "problem_coverage": round(0.6 * problem + 0.4 * coverage, 6),
            "evidence_alignment": round(evidence, 6),
            "data_reasoning": round(data, 6),
            "model_logic": round(model, 6),
            "result_explanation": round(results, 6),
            "figure_alignment": round(figures, 6),
            "abstract_quality": round(abstract_score, 6),
            "writing_quality": round(min(1.0, writing), 6),
        }


class IssueRegistry:
    def __init__(self, path: Path) -> None:
        self.path = path

    def current(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        if not self.path.is_file():
            return result
        with self.path.open("r", encoding="utf-8") as handle:
            for line in handle:
                if line.strip():
                    event = json.loads(line)
                    result[event["issue_id"]] = event
        return result

    def update(self, findings: list[dict[str, Any]], stage: int) -> dict[str, dict[str, Any]]:
        previous = self.current()
        seen: set[str] = set()
        for finding in findings:
            issue_id = _issue_id(finding["section_id"], finding["code"])
            seen.add(issue_id)
            old = previous.get(issue_id, {})
            event = {
                "schema_version": 1,
                "issue_id": issue_id,
                "status": "OPEN",
                "severity": finding["severity"],
                "section_id": finding["section_id"],
                "code": finding["code"],
                "dimension": finding.get("dimension"),
                "detail": finding.get("detail", ""),
                "first_seen_stage": old.get("first_seen_stage", stage),
                "last_seen_stage": stage,
                "attempt_count": old.get("attempt_count", 0),
                "updated_at": now_iso(),
            }
            append_jsonl(self.path, event)
            previous[issue_id] = event
        for issue_id, old in list(previous.items()):
            if old.get("status") == "OPEN" and issue_id not in seen:
                event = {**old, "status": "RESOLVED", "resolved_stage": stage, "updated_at": now_iso()}
                append_jsonl(self.path, event)
                previous[issue_id] = event
        return previous

    def record_attempt(self, issue_ids: list[str], stage: int, accepted: bool) -> None:
        current = self.current()
        for issue_id in issue_ids:
            if issue_id not in current:
                continue
            event = {
                **current[issue_id],
                "attempt_count": current[issue_id].get("attempt_count", 0) + 1,
                "last_attempt_stage": stage,
                "last_attempt_accepted": accepted,
                "updated_at": now_iso(),
            }
            append_jsonl(self.path, event)


ProposalFunction = Callable[[dict[str, Any]], dict[str, Any]]


class RefinementService:
    def __init__(
        self,
        cases: CaseManager,
        artifacts: ArtifactRegistry,
        workflow: WorkflowService,
        runs: RunManager,
        evaluator: PaperQualityEvaluator | None = None,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.workflow = workflow
        self.runs = runs
        self.evaluator = evaluator or PaperQualityEvaluator()

    def run(
        self,
        case_id: str,
        session_id: str | None,
        proposer: ProposalFunction | None,
        config: RefinementConfig | None = None,
    ) -> dict[str, Any]:
        config = config or RefinementConfig()
        root = self.cases.case_root(case_id)
        controller = self.workflow.checkpoints.load(case_id)
        runtime = controller.runtimes["refinement_loop"]
        if runtime.status.value == "RUNNING" and runtime.active_run_id:
            started = {"run": {"run_id": runtime.active_run_id}, "resumed": True}
        else:
            started = self.workflow.start_node(case_id, "refinement_loop", session_id)
        try:
            state, sections, frozen = self._load_or_initialize(case_id, config, started["run"]["run_id"])
            issues = IssueRegistry(root / "refinement" / "issues.jsonl")
            stop_reason = "MAX_STAGES"
            while state["iteration"] < config.max_stages:
                before = self.evaluator.evaluate(sections, frozen, config.targets)
                current_issues = issues.update(before["findings"], state["iteration"])
                selected = _select_issues(current_issues, config)
                if not selected:
                    stop_reason = "CONVERGED"
                    break
                if proposer is None:
                    stop_reason = "NO_PROPOSER"
                    break
                stage = state["iteration"] + 1
                result = self._run_stage(case_id, session_id, stage, sections, frozen, state, before, selected, proposer, config)
                issues.record_attempt(result["issue_ids"], stage, result["accepted"])
                sections = result["sections"]
                state = self._transition_state(state, result, config)
                atomic_write_json(root / "memory" / "refinement_state.json", state)
                append_jsonl(root / "refinement" / "history.jsonl", result["history_event"])
                if state["rejection_streak"] >= config.max_rejection_streak:
                    if state["strategy_reset_count"] == 0 and state["iteration"] < config.max_stages:
                        state["strategy_reset_count"] = 1
                        state["rejection_streak"] = 0
                        state["no_progress_streak"] = 0
                        state["last_strategy_reset_at"] = now_iso()
                        atomic_write_json(root / "memory" / "refinement_state.json", state)
                        continue
                    stop_reason = "REJECTION_LIMIT"
                    break
                if state["no_progress_streak"] >= config.patience:
                    if state["strategy_reset_count"] == 0 and state["iteration"] < config.max_stages:
                        state["strategy_reset_count"] = 1
                        state["no_progress_streak"] = 0
                        state["last_strategy_reset_at"] = now_iso()
                        atomic_write_json(root / "memory" / "refinement_state.json", state)
                    elif state["no_progress_streak"] >= config.max_no_progress_attempts:
                        stop_reason = "PLATEAU"
                        break
            state["status"] = "STOPPED"
            state["stop_reason"] = stop_reason
            state["updated_at"] = now_iso()
            atomic_write_json(root / "memory" / "refinement_state.json", state)
            final_artifact = self._publish_final(case_id, sections, state, started["run"]["run_id"])
            node = self.workflow.succeed_node(case_id, "refinement_loop")
            return {
                "succeeded": True,
                "stop_reason": stop_reason,
                "stages_completed": state["iteration"],
                "accepted_stages": state["accepted_stages"],
                "rejected_stages": state["rejected_stages"],
                "quality_vector": state["quality_vector"],
                "paper_final_artifact_id": final_artifact["artifact_id"],
                "workflow_node": node,
            }
        except Exception as error:
            self.workflow.fail_node(case_id, "refinement_loop", FailureCategory.SCHEMA, f"{type(error).__name__}: {error}")
            raise

    def _load_or_initialize(
        self,
        case_id: str,
        config: RefinementConfig,
        run_id: str,
    ) -> tuple[dict[str, Any], dict[str, str], dict[str, Any]]:
        root = self.cases.case_root(case_id)
        state_path = root / "memory" / "refinement_state.json"
        epoch = 1
        if state_path.is_file():
            state = read_json(state_path)
            frozen = read_json(root / "memory" / "frozen_facts.json")
            sections_artifact = self.artifacts.get(case_id, state["current_sections_artifact_id"])
            sections = read_json(root / sections_artifact["path"])["sections"]
            if state["frozen_evidence_digest"] == self._evidence_digest(case_id):
                return state, sections, frozen
            epoch = int(state.get("epoch", 1)) + 1
            atomic_write_json(
                root / "refinement" / "epochs" / f"epoch-{epoch - 1:03d}" / "final_state.json",
                {**state, "archived_at": now_iso(), "archive_reason": "frozen evidence digest changed"},
            )

        manifest = read_json(root / "paper" / "sections" / "manifest.json")
        sections = {
            item["section_id"]: (root / "paper" / "sections" / item["section_id"] / "draft.md").read_text(encoding="utf-8")
            for item in manifest["sections"]
        }
        initial_text = _assemble(sections, [item["section_id"] for item in manifest["sections"]])
        version_name = "stage-000" if epoch == 1 else f"epoch-{epoch:03d}-stage-000"
        atomic_write_text(root / "paper" / "initial.md", initial_text)
        atomic_write_text(root / "paper" / "current.md", initial_text)
        atomic_write_text(root / "paper" / "versions" / f"{version_name}.md", initial_text)
        sections_path = root / "paper" / "versions" / f"{version_name}.sections.json"
        atomic_write_json(sections_path, {"schema_version": 1, "stage": 0, "sections": sections})
        initial_artifact = self.artifacts.register_existing(case_id, (root / "paper" / "versions" / f"{version_name}.md").relative_to(root).as_posix(), "paper_refinement_version", "python", run_id=run_id, paper_eligible=True)
        sections_artifact = self.artifacts.register_existing(case_id, sections_path.relative_to(root).as_posix(), "paper_refinement_sections", "python", run_id=run_id, upstream=[initial_artifact["artifact_id"]])
        self.artifacts.register_existing(case_id, "paper/initial.md", "paper_refinement_initial", "python", run_id=run_id, upstream=[initial_artifact["artifact_id"]])
        self.artifacts.register_existing(case_id, "paper/current.md", "paper_refinement_current", "python", run_id=run_id, upstream=[initial_artifact["artifact_id"]], paper_eligible=True)
        frozen = self._freeze(case_id, sections, manifest)
        atomic_write_json(root / "memory" / "frozen_facts.json", frozen)
        atomic_write_json(root / "memory" / "frozen_evidence.json", frozen["evidence"])
        evaluation = self.evaluator.evaluate(sections, frozen, config.targets)
        state = {
            "schema_version": 1,
            "epoch": epoch,
            "iteration": 0,
            "status": "RUNNING",
            "current_paper_artifact_id": initial_artifact["artifact_id"],
            "current_sections_artifact_id": sections_artifact["artifact_id"],
            "frozen_evidence_digest": frozen["evidence"]["digest"],
            "quality_vector": evaluation["quality_vector"],
            "quality_ema": evaluation["quality_vector"]["total"],
            "accepted_stages": [],
            "rejected_stages": [],
            "plateau_count": 0,
            "rejection_streak": 0,
            "no_progress_streak": 0,
            "strategy_reset_count": 0,
            "recent_patch_fingerprints": [],
            "config": asdict(config),
            "updated_at": now_iso(),
        }
        atomic_write_json(state_path, state)
        return state, sections, frozen

    def _run_stage(
        self,
        case_id: str,
        session_id: str | None,
        stage: int,
        sections: dict[str, str],
        frozen: dict[str, Any],
        state: dict[str, Any],
        before: dict[str, Any],
        selected: list[dict[str, Any]],
        proposer: ProposalFunction,
        config: RefinementConfig,
    ) -> dict[str, Any]:
        root = self.cases.case_root(case_id)
        stage_root = (
            root / "refinement" / "stages" / f"stage-{stage:03d}"
            if int(state.get("epoch", 1)) == 1
            else root / "refinement" / "epochs" / f"epoch-{int(state['epoch']):03d}" / "stages" / f"stage-{stage:03d}"
        )
        stage_root.mkdir(parents=True, exist_ok=True)
        run = self.runs.start_run(case_id, "refinement_stage", session_id)
        try:
            editable_ids = _editable_sections(selected, frozen["section_order"], config.max_sections_per_stage)
            context = {
                "stage": stage,
                "quality_vector": before["quality_vector"],
                "issues": selected,
                "controller": {
                    "update_gate": _update_gate(selected, state, config),
                    "reset_gate": bool(state["strategy_reset_count"]),
                    "output_gate_sections": editable_ids,
                    "max_sections": config.max_sections_per_stage,
                    "max_changed_ratio": config.max_changed_ratio,
                },
                "sections": {
                    section_id: {
                        "source_sha256": _text_sha256(sections[section_id]),
                        "markdown": sections[section_id],
                        "evidence_contract": frozen["sections"][section_id],
                    }
                    for section_id in editable_ids
                },
                "failed_strategies": state.get("failed_strategies", [])[-3:],
                "current_paper_artifact_id": state["current_paper_artifact_id"],
            }
            atomic_write_json(stage_root / "input.json", context)
            atomic_write_json(stage_root / "evaluation.before.json", before)
            atomic_write_json(stage_root / "selection.json", {"issues": selected, "editable_sections": editable_ids})
            proposal = proposer(context)
            atomic_write_json(stage_root / "plan.json", proposal)
            candidate_sections, patch_meta = self._apply_proposal(sections, proposal, selected, editable_ids, config)
            candidate_text = _assemble(candidate_sections, frozen["section_order"])
            atomic_write_text(stage_root / "candidate.md", candidate_text)
            after = self.evaluator.evaluate(candidate_sections, frozen, config.targets)
            atomic_write_json(stage_root / "evaluation.after.json", after)
            decision = _acceptance_decision(before, after, selected, sections, candidate_sections, config)
            patch_fingerprint = _payload_digest(proposal)
            if patch_fingerprint in state.get("recent_patch_fingerprints", []):
                decision["accepted"] = False
                decision["reasons"] = [*decision["reasons"], "repeated patch fingerprint"]
            decision.update({"stage": stage, "run_id": run["run_id"], "patch_fingerprint": patch_fingerprint, "decided_at": now_iso()})
            atomic_write_json(stage_root / "decision.json", decision)
            candidate_artifact = self.artifacts.register_existing(case_id, (stage_root / "candidate.md").relative_to(root).as_posix(), "paper_refinement_candidate", "llm", run_id=run["run_id"], upstream=[state["current_paper_artifact_id"]], paper_eligible=False)
            decision_artifact = self.artifacts.register_existing(case_id, (stage_root / "decision.json").relative_to(root).as_posix(), "paper_refinement_decision", "python", run_id=run["run_id"], upstream=[candidate_artifact["artifact_id"]], paper_eligible=decision["accepted"])
            if decision["accepted"]:
                version_name = f"stage-{stage:03d}" if int(state.get("epoch", 1)) == 1 else f"epoch-{int(state['epoch']):03d}-stage-{stage:03d}"
                sections_path = root / "paper" / "versions" / f"{version_name}.sections.json"
                version_path = root / "paper" / "versions" / f"{version_name}.md"
                patch_path = root / "paper" / "patches" / f"{version_name}.patch.json"
                atomic_write_json(sections_path, {"schema_version": 1, "stage": stage, "sections": candidate_sections})
                atomic_write_text(version_path, candidate_text)
                atomic_write_json(patch_path, patch_meta)
                atomic_write_text(root / "paper" / "current.md", candidate_text)
                version_artifact = self.artifacts.register_existing(case_id, version_path.relative_to(root).as_posix(), "paper_refinement_version", "python", run_id=run["run_id"], upstream=[state["current_paper_artifact_id"], decision_artifact["artifact_id"]], paper_eligible=True)
                sections_artifact = self.artifacts.register_existing(case_id, sections_path.relative_to(root).as_posix(), "paper_refinement_sections", "python", run_id=run["run_id"], upstream=[version_artifact["artifact_id"]])
                self.artifacts.register_existing(case_id, patch_path.relative_to(root).as_posix(), "paper_refinement_patch", "python", run_id=run["run_id"], upstream=[decision_artifact["artifact_id"]])
                current_artifact = self.artifacts.register_existing(case_id, "paper/current.md", "paper_refinement_current", "python", run_id=run["run_id"], upstream=[version_artifact["artifact_id"]], paper_eligible=True)
                artifact_ids = {"paper": current_artifact["artifact_id"], "sections": sections_artifact["artifact_id"]}
                output_sections = candidate_sections
            else:
                artifact_ids = {"paper": state["current_paper_artifact_id"], "sections": state["current_sections_artifact_id"]}
                output_sections = sections
            self.runs.finish_run(case_id, run["run_id"], "SUCCEEDED")
            return {
                "accepted": decision["accepted"],
                "decision": decision,
                "issue_ids": list(proposal.get("issue_ids", [])),
                "strategy": proposal.get("strategy", ""),
                "patch_fingerprint": patch_fingerprint,
                "quality_before": before["quality_vector"],
                "quality_after": after["quality_vector"],
                "sections": output_sections,
                "artifact_ids": artifact_ids,
                "history_event": {"timestamp": now_iso(), "stage": stage, "accepted": decision["accepted"], "run_id": run["run_id"], "reasons": decision["reasons"], **artifact_ids},
            }
        except Exception as error:
            self.runs.finish_run(case_id, run["run_id"], "FAILED", {"type": type(error).__name__, "message": str(error)})
            raise

    def _apply_proposal(
        self,
        sections: dict[str, str],
        proposal: dict[str, Any],
        selected: list[dict[str, Any]],
        editable_ids: list[str],
        config: RefinementConfig,
    ) -> tuple[dict[str, str], dict[str, Any]]:
        selected_ids = {item["issue_id"] for item in selected}
        issue_ids = set(proposal.get("issue_ids", []))
        if not issue_ids or not issue_ids.issubset(selected_ids):
            raise ValueError("proposal references unselected issue IDs")
        patches = proposal.get("patches")
        if not isinstance(patches, list) or not 1 <= len(patches) <= config.max_sections_per_stage:
            raise ValueError("proposal patch count exceeds stage budget")
        output = dict(sections)
        changed: list[dict[str, Any]] = []
        seen: set[str] = set()
        for patch in patches:
            section_id = patch.get("section_id")
            if section_id in seen or section_id not in editable_ids:
                raise ValueError(f"section is duplicated or outside output gate: {section_id}")
            seen.add(section_id)
            source = sections[section_id]
            if patch.get("source_sha256") != _text_sha256(source):
                raise ValueError(f"stale section patch: {section_id}")
            replacement = str(patch.get("replacement_markdown", "")).strip() + "\n"
            if not replacement.lstrip().startswith("#"):
                raise ValueError(f"replacement has no heading: {section_id}")
            output[section_id] = replacement
            changed.append({"section_id": section_id, "before_sha256": _text_sha256(source), "after_sha256": _text_sha256(replacement), "rationale": patch.get("rationale", "")})
        return output, {"schema_version": 1, "strategy": proposal.get("strategy", ""), "issue_ids": sorted(issue_ids), "changes": changed}

    def _transition_state(self, state: dict[str, Any], result: dict[str, Any], config: RefinementConfig) -> dict[str, Any]:
        updated = dict(state)
        updated["iteration"] += 1
        accepted = result["accepted"]
        before = result["quality_before"]["total"]
        after = result["quality_after"]["total"] if accepted else before
        delta = after - before
        updated["quality_vector"] = result["quality_after"] if accepted else result["quality_before"]
        updated["quality_ema"] = round(config.quality_ema_beta * state["quality_ema"] + (1 - config.quality_ema_beta) * after, 6)
        updated["rejection_streak"] = 0 if accepted else state["rejection_streak"] + 1
        updated["no_progress_streak"] = 0 if accepted and delta >= config.min_delta else state["no_progress_streak"] + 1
        updated["accepted_stages"] = [*state["accepted_stages"], updated["iteration"]] if accepted else list(state["accepted_stages"])
        updated["rejected_stages"] = list(state["rejected_stages"]) if accepted else [*state["rejected_stages"], updated["iteration"]]
        updated["current_paper_artifact_id"] = result["artifact_ids"]["paper"]
        updated["current_sections_artifact_id"] = result["artifact_ids"]["sections"]
        updated["recent_patch_fingerprints"] = [*state.get("recent_patch_fingerprints", []), result["patch_fingerprint"]][-5:]
        if not accepted:
            updated["failed_strategies"] = [*state.get("failed_strategies", []), {"stage": updated["iteration"], "strategy": result["strategy"], "reasons": result["decision"]["reasons"]}][-10:]
        updated["updated_at"] = now_iso()
        return updated

    def _freeze(self, case_id: str, sections: dict[str, str], manifest: dict[str, Any]) -> dict[str, Any]:
        root = self.cases.case_root(case_id)
        contracts: dict[str, Any] = {}
        for item in manifest["sections"]:
            section_id = item["section_id"]
            context = read_json(root / "paper" / "sections" / section_id / "context.json")
            content = sections[section_id]
            contracts[section_id] = {
                "allowed_claim_ids": sorted(item["claim_id"] for item in context["allowed_claims"]),
                "allowed_figure_ids": sorted(item["figure_id"] for item in context["allowed_figures"]),
                "required_claim_ids": sorted(set(CLAIM_REF.findall(content))),
                "required_figure_ids": sorted(set(FIGURE_REF.findall(content))),
                "number_tokens": NUMBER.findall(_body(content)),
                "synthetic_disclosure_required": any("synthetic_data_claim" in claim.get("restrictions", []) for claim in context["allowed_claims"]),
                "context_artifact_id": item["context_artifact_id"],
            }
        return {
            "schema_version": 1,
            "case_id": case_id,
            "section_order": [item["section_id"] for item in manifest["sections"]],
            "sections": contracts,
            "evidence": {"digest": self._evidence_digest(case_id), "frozen_at": now_iso()},
        }

    def _evidence_digest(self, case_id: str) -> str:
        root = self.cases.case_root(case_id)
        artifacts = [
            {"artifact_id": item["artifact_id"], "sha256": item["sha256"], "type": item["artifact_type"]}
            for item in self.artifacts.list_artifacts(case_id)
            if item.get("status") == "ACTIVE"
            and not item["path"].startswith(("paper/", "review/", "refinement/", "memory/", "export/", "sessions/", "runs/"))
        ]
        registries = {}
        for name in ("claim_registry.jsonl", "figure_registry.jsonl", "dataset_registry.jsonl", "experiment_registry.jsonl"):
            path = root / name
            registries[name] = sha256_file(path) if path.is_file() else None
        return _payload_digest({"artifacts": sorted(artifacts, key=lambda item: item["artifact_id"]), "registries": registries})

    def _publish_final(self, case_id: str, sections: dict[str, str], state: dict[str, Any], run_id: str) -> dict[str, Any]:
        root = self.cases.case_root(case_id)
        final_text = _render_final_manuscript(_assemble(sections, read_json(root / "memory" / "frozen_facts.json")["section_order"]))
        atomic_write_text(root / "paper" / "paper_final.md", final_text)
        atomic_write_text(root / "paper" / "final.md", final_text)
        artifact = self.artifacts.register_existing(case_id, "paper/paper_final.md", "paper_final", "python", run_id=run_id, upstream=[state["current_paper_artifact_id"]], paper_eligible=True)
        self.artifacts.register_existing(case_id, "paper/final.md", "paper_refinement_final", "python", run_id=run_id, upstream=[artifact["artifact_id"]], paper_eligible=True)
        return artifact


def _select_issues(current: dict[str, dict[str, Any]], config: RefinementConfig) -> list[dict[str, Any]]:
    severity = {"P0": 0, "P1": 1, "P2": 2}
    candidates = [
        item for item in current.values()
        if item.get("status") == "OPEN" and item.get("attempt_count", 0) < config.max_issue_attempts
    ]
    candidates.sort(key=lambda item: (severity.get(item["severity"], 9), item.get("attempt_count", 0), item["issue_id"]))
    return candidates[: config.max_issues_per_stage]


def _editable_sections(issues: list[dict[str, Any]], order: list[str], limit: int) -> list[str]:
    result: list[str] = []
    for issue in issues:
        section_id = issue["section_id"]
        if section_id == "global":
            section_id = "abstract" if "abstract" in order else order[0]
        if section_id in order and section_id not in result:
            result.append(section_id)
        if len(result) == limit:
            break
    return result or order[:1]


def _acceptance_decision(
    before: dict[str, Any],
    after: dict[str, Any],
    selected: list[dict[str, Any]],
    old_sections: dict[str, str],
    new_sections: dict[str, str],
    config: RefinementConfig,
) -> dict[str, Any]:
    reasons: list[str] = []
    if after["hard_gate"] != "PASS":
        reasons.append("hard gate failed")
    before_severe = {(item["section_id"], item["code"]) for item in before["findings"] if item["severity"] in {"P0", "P1"}}
    after_severe = {(item["section_id"], item["code"]) for item in after["findings"] if item["severity"] in {"P0", "P1"}}
    if after_severe - before_severe:
        reasons.append("new P0/P1 issue introduced")
    selected_dimensions = {item.get("dimension") for item in selected if item.get("dimension")}
    gains = {dimension: after["quality_vector"][dimension] - before["quality_vector"][dimension] for dimension in DIMENSIONS}
    regressed = [dimension for dimension, gain in gains.items() if gain < -config.semantic_tolerance]
    if regressed:
        reasons.append(f"guard dimensions regressed: {', '.join(regressed)}")
    targeted_gain = max((gains[item] for item in selected_dimensions), default=0.0)
    selected_codes = {(item["section_id"], item["code"]) for item in selected}
    after_codes = {(item["section_id"], item["code"]) for item in after["findings"]}
    resolved = bool(selected_codes - after_codes)
    if targeted_gain < config.target_dimension_delta and not resolved:
        reasons.append("no measurable targeted gain or defect resolution")
    old_size = sum(len(value) for value in old_sections.values())
    new_size = sum(len(value) for value in new_sections.values())
    changed = sum(max(len(old_sections[key]), len(new_sections[key])) for key in old_sections if old_sections[key] != new_sections[key])
    changed_ratio = changed / max(1, old_size, new_size)
    if changed_ratio > config.max_changed_ratio:
        reasons.append(f"change budget exceeded: {changed_ratio:.4f}")
    return {
        "schema_version": 1,
        "accepted": not reasons,
        "route": "DEFECT_RESOLUTION" if resolved else "MEASURED_GAIN",
        "reasons": reasons or ["quality contract passed"],
        "dimension_gains": gains,
        "targeted_gain": targeted_gain,
        "changed_ratio": changed_ratio,
    }


def _finding(severity: str, section_id: str, code: str, detail: str, dimension: str | None = None) -> dict[str, Any]:
    return {"severity": severity, "section_id": section_id, "code": code, "detail": detail, "dimension": dimension}


def _issue_id(section_id: str, code: str) -> str:
    return f"issue-{hashlib.sha256(f'{section_id}:{code}'.encode()).hexdigest()[:12]}"


def _body(content: str) -> str:
    return "\n".join(line for line in content.splitlines() if not line.lstrip().startswith("#"))


def _counter_diff(expected: Counter[str], actual: Counter[str]) -> str:
    removed = list((expected - actual).elements())[:10]
    added = list((actual - expected).elements())[:10]
    return f"removed={removed}, added={added}"


def _keyword_score(text: str, keywords: tuple[str, ...]) -> float:
    return sum(keyword in text for keyword in keywords) / len(keywords)


def _text_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _payload_digest(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _assemble(sections: dict[str, str], order: list[str]) -> str:
    return "\n\n".join(sections[section_id].strip() for section_id in order).strip() + "\n"


def _update_gate(issues: list[dict[str, Any]], state: dict[str, Any], config: RefinementConfig) -> float:
    severity = {"P0": 1.0, "P1": 0.8, "P2": 0.55}
    confidence = max((severity.get(item["severity"], 0.4) for item in issues), default=0.0)
    remaining = max(0.2, 1 - state["iteration"] / config.max_stages)
    return round(confidence * remaining, 4)

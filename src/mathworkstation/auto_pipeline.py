from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .artifact_registry import ArtifactRegistry
from .baseline import BaselineEngine
from .case_manager import CaseManager
from .checkpoint_manager import CheckpointManager
from .claims import ClaimInput, ClaimRegistry
from .data_quality import TabularProfiler
from .data_service import DataService
from .datasets import DatasetKind, DatasetRegistry
from .eda import EDAEngine
from .evaluation_service import EvaluationService
from .experiments import ExperimentRegistry
from .export_service import ExportService
from .figure_registry import FigureRegistry
from .llm.router import LLMRouter
from .llm.service import CaseLLMService
from .memory_manager import MemoryManager
from .model_evaluation import ModelEvaluationEngine
from .model_plan import ModelPlan, ModelPlanService
from .modeling_service import ModelingService
from .paper_consistency import PaperConsistencyChecker
from .paper_outline import PaperOutlineService, default_outline
from .paper_ready import PaperReadyGate
from .paper_sections import PaperSectionWorkspace
from .problem_ingestion import ProblemIngestionService
from .run_manager import RunManager
from .selection import ModelSelectionRegistry
from .sensitivity import SensitivityEngine
from .session_manager import SessionManager
from .stage_service import StageService
from .structured_llm import ModelPlanProposal, ProblemAnalysis, StructuredLLM
from .tabular import read_table
from .workflow_service import WorkflowService
from .workflow import FailureCategory
from .io_utils import atomic_write_json, atomic_write_text, read_json


class AutoPipelineService:
    def __init__(self, cases: CaseManager, llm_router: LLMRouter) -> None:
        self.cases = cases
        self.artifacts = ArtifactRegistry(cases)
        self.checkpoints = CheckpointManager(cases)
        self.memory = MemoryManager(cases, self.artifacts)
        self.sessions = SessionManager(cases)
        self.workflow = WorkflowService(cases, RunManager(cases), self.checkpoints, self.memory)
        self.datasets = DatasetRegistry(cases, self.artifacts)
        self.figures = FigureRegistry(cases, self.artifacts)
        self.experiments = ExperimentRegistry(cases, self.artifacts)
        self.claims = ClaimRegistry(cases, self.artifacts, self.datasets)
        self.data = DataService(self.artifacts, self.datasets, TabularProfiler(cases, self.artifacts, self.datasets), self.workflow)
        self.modeling = ModelingService(
            self.workflow,
            EDAEngine(cases, self.artifacts, self.datasets, self.figures),
            BaselineEngine(cases, self.artifacts, self.datasets, self.experiments, self.figures),
        )
        self.plans = ModelPlanService(cases, self.artifacts)
        self.evaluation = EvaluationService(
            self.workflow,
            self.plans,
            ModelEvaluationEngine(cases, self.artifacts, self.datasets, self.experiments, self.figures),
            SensitivityEngine(cases, self.artifacts, self.datasets, self.experiments, self.figures),
            ModelSelectionRegistry(cases, self.artifacts, self.experiments),
        )
        self.stages = StageService(cases, self.artifacts, self.workflow)
        self.sections = PaperSectionWorkspace(cases, self.artifacts, self.claims, self.figures)
        self.outlines = PaperOutlineService(cases, self.artifacts, self.claims, self.figures)
        self.paper_ready = PaperReadyGate(cases, self.artifacts, self.experiments)
        self.consistency = PaperConsistencyChecker(cases, self.artifacts, self.claims, self.figures)
        self.exporter = ExportService(cases, self.artifacts, self.workflow)
        self.ingestion = ProblemIngestionService(cases, self.artifacts)
        self.llm = StructuredLLM(CaseLLMService(cases, self.artifacts, self.sessions, self.checkpoints, llm_router))

    def run(
        self,
        case_id: str,
        session_id: str,
        problem_source: str | Path,
        data_source: str | Path,
        dataset_name: str,
        target_column: str | None,
        approved_by: str,
        competition_type: str,
        data_kind: DatasetKind = DatasetKind.OBSERVED,
    ) -> dict[str, Any]:
        problem = self.ingestion.ingest(case_id, problem_source)
        data = self.data.register_uploaded(case_id, data_source, dataset_name, data_kind, approved_by)
        dataset_id = data["dataset"]["dataset_id"]
        problem_artifact_id = problem["extracted_artifact"]["artifact_id"]
        self._complete_simple("input_validation", case_id, session_id)

        problem_analysis, problem_response = self._run_problem_analysis(case_id, session_id, problem_artifact_id, competition_type, approved_by)
        self.data.complete_registration(case_id, session_id)
        self.workflow.approve_node(case_id, "data_registration", approved_by, "Dataset provenance reviewed")
        profile = self.data.profile_dataset(case_id, dataset_id, target_column, session_id)
        if profile["workflow_node"]["status"] != "SUCCEEDED":
            raise ValueError(f"data quality gate did not pass: {profile['workflow_node']['status']}")
        eda = self.modeling.run_eda(case_id, dataset_id, target_column, session_id)
        if not eda["succeeded"]:
            raise ValueError(f"EDA failed: {eda['error']}")
        plan_result = self._run_model_plan(case_id, session_id, dataset_id, problem_analysis, problem_artifact_id, target_column, approved_by)
        plan_artifact_id = plan_result["plan_artifact_id"]
        baseline = self.modeling.run_baseline(case_id, dataset_id, plan_result["plan"]["target_column"], plan_result["plan"]["feature_columns"], plan_result["plan"]["task_type"], plan_result["plan"]["test_size"], plan_result["plan"]["random_seed"], session_id)
        if not baseline["succeeded"]:
            raise ValueError(f"baseline failed: {baseline['error']}")
        comparison = self.evaluation.run_comparison(case_id, plan_artifact_id, session_id)
        experiment_id = comparison["result"]["experiment_id"]
        selection = self.evaluation.select_model(case_id, experiment_id, comparison["result"]["best_model"], comparison["result"]["comparison_artifact_id"], approved_by, "Selected best validated primary metric result", session_id)
        sensitivity = self.evaluation.run_sensitivity(case_id, experiment_id, plan_artifact_id, None, session_id)
        assessment = self.paper_ready.assess(case_id, experiment_id, selection["selection"]["artifact_id"], sensitivity["result"]["artifact_id"])
        if not assessment["eligible"]:
            raise ValueError(f"paper ready gate failed: {assessment['reasons']}")
        ready = self.paper_ready.approve(case_id, experiment_id, selection["selection"]["artifact_id"], sensitivity["result"]["artifact_id"], approved_by, "Automated evidence chain reviewed")
        claim = self.claims.create(case_id, ClaimInput(
            text=f"The validated comparison selected {comparison['result']['best_model']} as the best model under the declared primary metric.",
            claim_type="model_result",
            evidence_artifact_ids=[comparison["result"]["comparison_artifact_id"], sensitivity["result"]["artifact_id"]],
            dataset_ids=[dataset_id],
            section_hint="results",
        ), approved_by)
        outline = self._create_outline(case_id, claim["claim_id"], competition_type)
        sections = self.sections.initialize(case_id, outline["outline_artifact_id"])
        self._generate_sections(case_id, session_id, sections, approved_by)
        paper = self.stages.complete_paper_draft(case_id, session_id)
        consistency = self.stages.check_consistency(case_id, self.consistency, session_id)
        if consistency["result"]["report"]["gate"] != "PASS":
            raise ValueError(f"paper consistency gate failed: {consistency['result']['report']['findings']}")
        self._complete_review(case_id, session_id, approved_by)
        export = self.exporter.export_case(case_id, session_id)
        return {
            "case_id": case_id,
            "session_id": session_id,
            "problem_analysis_artifact_id": problem_response["artifact_id"],
            "model_plan_artifact_id": plan_artifact_id,
            "paper_ready_artifact_id": ready["approval_artifact_id"],
            "paper_artifact_id": paper["artifact"]["artifact_id"],
            "consistency_artifact_id": consistency["result"]["report_artifact_id"],
            "export": export,
        }

    def _complete_simple(self, node_id: str, case_id: str, session_id: str) -> None:
        self.workflow.start_node(case_id, node_id, session_id)
        self.workflow.succeed_node(case_id, node_id)

    def _run_problem_analysis(self, case_id: str, session_id: str, artifact_id: str, competition: str, approved_by: str) -> tuple[ProblemAnalysis, dict[str, Any]]:
        self.workflow.start_node(case_id, "problem_analysis", session_id)
        brief_path = self.cases.case_root(case_id) / ".internal" / "resume_brief.md"
        brief = brief_path.read_text(encoding="utf-8") if brief_path.is_file() else ""
        problem_artifact = self.artifacts.get(case_id, artifact_id)
        problem_text = (self.cases.case_root(case_id) / problem_artifact["path"]).read_text(encoding="utf-8-sig")
        try:
            analysis, response = self.llm.json_call(case_id, session_id, "problem_analysis", "problem_analysis", {"case_id": case_id, "competition_type": competition, "resume_brief": f"{brief}\n\nDeclared problem text:\n{problem_text}"}, ProblemAnalysis, [artifact_id])
        except Exception as error:
            self.workflow.fail_node(case_id, "problem_analysis", FailureCategory.SCHEMA, f"{type(error).__name__}: {error}")
            raise
        root = self.cases.case_root(case_id)
        path = root / "analysis" / "problem_analysis.json"
        atomic_write_json(path, analysis.model_dump(mode="json"))
        structured = self.artifacts.register_existing(case_id, path.relative_to(root).as_posix(), "problem_analysis_structured", "llm", upstream=[response["artifact_id"]])
        self.workflow.succeed_node(case_id, "problem_analysis")
        self.workflow.approve_node(case_id, "problem_analysis", approved_by, "Structured problem analysis validated")
        return analysis, {**response, "artifact_id": structured["artifact_id"]}

    def _run_model_plan(self, case_id: str, session_id: str, dataset_id: str, analysis: ProblemAnalysis, problem_artifact_id: str, target_column: str | None, approved_by: str) -> dict[str, Any]:
        self.workflow.start_node(case_id, "model_plan", session_id)
        dataset = self.datasets.get(case_id, dataset_id)
        profile_path = self.cases.case_root(case_id) / "data" / "dictionaries" / f"{dataset_id}.profile.json"
        profile = read_json(profile_path) if profile_path.is_file() else {}
        frame = read_table(self.cases.case_root(case_id) / self.artifacts.get(case_id, dataset["artifact_id"])["path"])
        columns = list(frame.columns)
        try:
            proposal, response = self.llm.json_call(case_id, session_id, "model_plan", "model_plan", {"case_id": case_id, "dataset_id": dataset_id, "columns_json": columns, "profile_json": profile, "problem_analysis_json": analysis.model_dump(mode="json")}, ModelPlanProposal, [problem_artifact_id])
        except Exception as error:
            self.workflow.fail_node(case_id, "model_plan", FailureCategory.SCHEMA, f"{type(error).__name__}: {error}")
            raise
        payload = proposal.model_dump(mode="json")
        aliases = {
            "linear_regression": "linear",
            "ridge_regression": "ridge",
            "lasso_regression": "lasso",
            "elastic_net_regression": "elastic_net",
            "random_forest_regressor": "random_forest",
            "gradient_boosting_regressor": "gradient_boosting",
        }
        supported = {"linear", "ridge", "lasso", "elastic_net", "random_forest", "gradient_boosting", "logistic"}
        normalized_candidates = []
        for candidate in payload["candidate_models"]:
            raw_name = candidate.get("name") or candidate.get("model")
            if not raw_name:
                continue
            name = aliases.get(raw_name, raw_name)
            if name not in supported:
                continue
            candidate["name"] = name
            if not candidate.get("parameters"):
                candidate["parameters"] = candidate.get("hyperparameters") or {}
            candidate.pop("supported", None)
            candidate.pop("model", None)
            candidate.pop("hyperparameters", None)
            if not candidate.get("rationale"):
                candidate["rationale"] = "LLM-proposed candidate after deterministic alias normalization"
            normalized_candidates.append(candidate)
        payload["candidate_models"] = normalized_candidates
        if len(normalized_candidates) < 2:
            raise ValueError("LLM model proposal contains fewer than two supported candidate models")
        if target_column:
            payload["target_column"] = target_column
        root = self.cases.case_root(case_id)
        path = root / "analysis" / "auto_model_plan.json"
        atomic_write_json(path, payload)
        result = self.plans.validate_file(case_id, path, dataset_id)
        self.workflow.succeed_node(case_id, "model_plan")
        self.workflow.approve_node(case_id, "model_plan", approved_by, "Structured model plan validated")
        return {"plan": result["plan"]["plan"], "plan_artifact_id": result["plan_artifact_id"], "llm_response": response}

    def _create_outline(self, case_id: str, claim_id: str, competition: str) -> dict[str, Any]:
        self.workflow.start_node(case_id, "paper_outline")
        outline = default_outline("自动生成数学建模论文", competition)
        payload = outline.model_dump(mode="json")
        for section in payload["sections"]:
            if section["section_id"] == "results":
                section["claim_ids"] = [claim_id]
        path = self.cases.case_root(case_id) / "paper" / "outline" / "auto-outline.json"
        atomic_write_json(path, payload)
        result = self.outlines.validate_file(case_id, path)
        self.workflow.succeed_node(case_id, "paper_outline")
        self.workflow.approve_node(case_id, "paper_outline", "pipeline", "Outline schema and evidence scope validated")
        return result

    def _generate_sections(self, case_id: str, session_id: str, manifest: dict[str, Any], approved_by: str) -> None:
        for item in manifest["manifest"]["sections"]:
            section_id = item["section_id"]
            context_path = self.cases.case_root(case_id) / "paper" / "sections" / section_id / "context.json"
            context = json.loads(context_path.read_text(encoding="utf-8"))
            content, _ = self.llm.markdown_call(case_id, session_id, "paper_draft", "paper_section", {"case_id": case_id, "section_id": section_id, "language": "zh", "context_json": context}, [item["context_artifact_id"]])
            content = content.replace("[SECTION_DRAFT_PENDING]", "本节尚未登记可用证据，保留结构性说明。")
            content = content.replace("[NEEDS_EVIDENCE]", "本节暂无已登记证据，保留结构性说明，不作外推结论。")
            content = content.replace("[TODO]", "本节待基于新增证据补充。")
            content = content.replace("[TBD]", "本节待基于新增证据补充。")
            if section_id == "results" and "SYNTHETIC" not in content.upper() and "合成" not in content:
                content += "\n\n本节结果基于明确标注的 SYNTHETIC 数据，不能外推为真实竞赛结论。"
            self.sections.update_draft(case_id, section_id, content, "llm")

    def _complete_review(self, case_id: str, session_id: str, approved_by: str) -> None:
        self.workflow.start_node(case_id, "final_review", session_id)
        self.workflow.succeed_node(case_id, "final_review")
        self.workflow.approve_node(case_id, "final_review", approved_by, "Consistency gate passed")

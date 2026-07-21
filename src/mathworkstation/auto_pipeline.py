from __future__ import annotations

import json
import re
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
from .research_audit import ResearchAuditService
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
        self.consistency = PaperConsistencyChecker(cases, self.artifacts, self.claims, self.figures, strict=True)
        self.exporter = ExportService(cases, self.artifacts, self.workflow)
        self.ingestion = ProblemIngestionService(cases, self.artifacts)
        self.llm = StructuredLLM(CaseLLMService(cases, self.artifacts, self.sessions, self.checkpoints, llm_router))
        self.research = ResearchAuditService(cases, self.artifacts, self.datasets)

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
        source_uri: str | None = None,
        license_name: str | None = None,
        data_description: str = "",
    ) -> dict[str, Any]:
        problem = self.ingestion.ingest(case_id, problem_source)
        data = self.data.register_uploaded(
            case_id,
            data_source,
            dataset_name,
            data_kind,
            approved_by,
            source_uri=source_uri,
            license_name=license_name,
            description=data_description,
        )
        dataset_id = data["dataset"]["dataset_id"]
        problem_artifact_id = problem["extracted_artifact"]["artifact_id"]
        self._complete_simple("input_validation", case_id, session_id)

        problem_analysis, problem_response = self._run_problem_analysis(case_id, session_id, problem_artifact_id, competition_type, approved_by)
        problem_analysis_artifact_id = problem_response["artifact_id"]
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
        additional_evidence = [
            problem_analysis_artifact_id,
            profile["profile_artifact_id"],
            profile["report_artifact_id"],
            eda["result"]["summary_artifact_id"],
            eda["result"]["report_artifact_id"],
            plan_artifact_id,
            plan_result["report_artifact_id"],
            sensitivity["result"]["report_artifact_id"],
            plan_result["research_audit_artifact_id"],
            plan_result["research_audit_report_artifact_id"],
            *[figure["artifact_id"] for figure in eda["result"]["figures"]],
            baseline["result"]["figure"]["artifact_id"],
            comparison["result"]["figure"]["artifact_id"],
            sensitivity["result"]["figure"]["artifact_id"],
        ]
        assessment = self.paper_ready.assess(case_id, experiment_id, selection["selection"]["artifact_id"], sensitivity["result"]["artifact_id"], additional_evidence)
        if not assessment["eligible"]:
            raise ValueError(f"paper ready gate failed: {assessment['reasons']}")
        ready = self.paper_ready.approve(case_id, experiment_id, selection["selection"]["artifact_id"], sensitivity["result"]["artifact_id"], approved_by, "Automated evidence chain reviewed", additional_evidence)
        claim_map = {
            "problem_restated": self.claims.create(case_id, ClaimInput(text="The problem analysis was extracted from the declared problem artifact and retained as structured evidence.", claim_type="problem_analysis", evidence_artifact_ids=[problem_analysis_artifact_id], section_hint="problem_restated"), approved_by),
            "data_analysis": self.claims.create(case_id, ClaimInput(text="The dataset profiling and exploratory analysis artifacts passed the declared data quality workflow.", claim_type="data_quality", evidence_artifact_ids=[profile["profile_artifact_id"], profile["report_artifact_id"], eda["result"]["summary_artifact_id"], eda["result"]["report_artifact_id"]], dataset_ids=[dataset_id], section_hint="data_analysis"), approved_by),
            "model_construction": self.claims.create(case_id, ClaimInput(text="The model plan was validated against the dataset schema and the research audit recorded feature and split decisions before formal comparison.", claim_type="model_plan", evidence_artifact_ids=[plan_artifact_id, plan_result["report_artifact_id"], plan_result["research_audit_artifact_id"], plan_result["research_audit_report_artifact_id"]], dataset_ids=[dataset_id], section_hint="model_construction"), approved_by),
            "model_solution": self.claims.create(case_id, ClaimInput(text=f"The declared candidate models were evaluated using the reproducible experiment pipeline; {comparison['result']['best_model']} ranked first under the selected metric.", claim_type="model_comparison", evidence_artifact_ids=[comparison["result"]["comparison_artifact_id"], comparison["result"]["diagnostics_artifact_id"]], dataset_ids=[dataset_id], section_hint="model_solution"), approved_by),
            "results": self.claims.create(case_id, ClaimInput(text=f"The validated comparison selected {comparison['result']['best_model']} as the best model under the declared primary metric.", claim_type="model_result", evidence_artifact_ids=[comparison["result"]["comparison_artifact_id"], sensitivity["result"]["artifact_id"]], dataset_ids=[dataset_id], section_hint="results"), approved_by),
            "sensitivity": self.claims.create(case_id, ClaimInput(text="The sensitivity analysis completed across the declared sample fractions and random seeds with a recorded gate.", claim_type="sensitivity", evidence_artifact_ids=[sensitivity["result"]["artifact_id"], sensitivity["result"]["report_artifact_id"]], dataset_ids=[dataset_id], section_hint="sensitivity"), approved_by),
        }
        claim = claim_map["results"]
        claim_ids = {key: value["claim_id"] for key, value in claim_map.items()}
        section_claims: dict[str, str | list[str]] = {
            **claim_ids,
            "abstract": [claim_ids["problem_restated"], claim_ids["results"], claim_ids["sensitivity"]],
            "strengths_weaknesses": [claim_ids["results"], claim_ids["sensitivity"]],
            "conclusion": [claim_ids["results"], claim_ids["sensitivity"]],
        }
        section_figures: dict[str, list[str]] = {
            "data_analysis": [figure["figure_id"] for figure in eda["result"]["figures"]],
            "model_solution": [comparison["result"]["figure"]["figure_id"], baseline["result"]["figure"]["figure_id"]],
            "results": [baseline["result"]["figure"]["figure_id"], comparison["result"]["figure"]["figure_id"]],
            "sensitivity": [sensitivity["result"]["figure"]["figure_id"]],
        }
        outline = self._create_outline(case_id, section_claims, section_figures, competition_type)
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
            normalized_raw_name = str(raw_name).strip().lower()
            name = aliases.get(normalized_raw_name, normalized_raw_name)
            if name not in supported:
                continue
            candidate["name"] = name
            if not candidate.get("parameters"):
                candidate["parameters"] = candidate.get("hyperparameters") or {}
            candidate["parameters"] = _scalarize_parameters(candidate["parameters"])
            candidate.pop("supported", None)
            candidate.pop("model", None)
            candidate.pop("hyperparameters", None)
            if not candidate.get("rationale"):
                candidate["rationale"] = candidate.get("notes") or "LLM-proposed candidate after deterministic alias and median-parameter normalization"
            candidate.pop("notes", None)
            normalized_candidates.append(candidate)
        payload["candidate_models"] = normalized_candidates
        if len(normalized_candidates) < 2:
            raise ValueError("LLM model proposal contains fewer than two supported candidate models")
        fractions = [float(value) for value in payload.get("sensitivity_fractions", []) if 0.2 < float(value) <= 1.0]
        payload["sensitivity_fractions"] = sorted(set(fractions)) if len(set(fractions)) >= 2 else [0.7, 0.85, 1.0]
        payload["cv_folds"] = min(10, max(2, int(payload.get("cv_folds", 5))))
        payload["test_size"] = min(0.49, max(0.06, float(payload.get("test_size", 0.2))))
        if target_column:
            payload["target_column"] = target_column
        research_audit = self.research.audit(
            case_id,
            dataset_id,
            payload["target_column"],
            list(payload["feature_columns"]),
            approved_by,
        )
        blocking_research_issues = {
            "SOURCE_URI_MISSING",
            "TEMPORAL_SPLIT_REVIEW",
            "TARGET_AS_FEATURE",
            "NO_RECOMMENDED_FEATURES",
        }
        if research_audit["report"]["gate"] == "BLOCK" or any(
            issue["code"] in blocking_research_issues
            for issue in research_audit["report"]["issues"]
            if issue["severity"] == "REVIEW" or issue["severity"] == "BLOCK"
        ):
            raise ValueError(f"research audit blocked model plan: {research_audit['report']['issues']}")
        payload["feature_columns"] = research_audit["report"]["recommended_feature_columns"]
        root = self.cases.case_root(case_id)
        path = root / "analysis" / "auto_model_plan.json"
        atomic_write_json(path, payload)
        result = self.plans.validate_file(case_id, path, dataset_id)
        self.workflow.succeed_node(case_id, "model_plan")
        self.workflow.approve_node(case_id, "model_plan", approved_by, "Structured model plan validated")
        return {
            "plan": result["plan"]["plan"],
            "plan_artifact_id": result["plan_artifact_id"],
            "report_artifact_id": result["report_artifact_id"],
            "research_audit_artifact_id": research_audit["artifact_id"],
            "research_audit_report_artifact_id": research_audit["report_artifact_id"],
            "llm_response": response,
        }

    def _create_outline(
        self,
        case_id: str,
        claim_ids: dict[str, str | list[str]],
        figure_ids: dict[str, list[str]],
        competition: str,
    ) -> dict[str, Any]:
        self.workflow.start_node(case_id, "paper_outline")
        outline = default_outline("自动生成数学建模论文", competition)
        payload = outline.model_dump(mode="json")
        for section in payload["sections"]:
            assigned = claim_ids.get(section["section_id"], [])
            section["claim_ids"] = [assigned] if isinstance(assigned, str) else list(assigned)
            section["figure_ids"] = list(figure_ids.get(section["section_id"], []))
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
            content = _polish_section_draft(section_id, content, context)
            if not content.lstrip().startswith("#"):
                content = f"## {context['title']}\n\n{content}"
            for figure in context["allowed_figures"]:
                figure_ref = figure["figure_id"]
                if figure_ref not in content:
                    content += f"\n\n图表证据：{figure['title']} [{figure_ref}]\n\n![{figure['title']}](../{figure['path']})\n"
            if section_id == "results" and "SYNTHETIC" not in content.upper() and "合成" not in content:
                content += "\n\n本节结果基于明确标注的 SYNTHETIC 数据，不能外推为真实竞赛结论。"
            if any("synthetic_data_claim" in claim.get("restrictions", []) for claim in context["allowed_claims"]) and "SYNTHETIC" not in content.upper() and "合成" not in content:
                content += "\n\n本节基于明确标注的 SYNTHETIC 数据，相关结论不外推至真实竞赛数据。"
            self.sections.update_draft(case_id, section_id, content, "llm")

    def _complete_review(self, case_id: str, session_id: str, approved_by: str) -> None:
        self.workflow.start_node(case_id, "final_review", session_id)
        self.workflow.succeed_node(case_id, "final_review")
        self.workflow.approve_node(case_id, "final_review", approved_by, "Consistency gate passed")


def _scalarize_parameters(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _scalarize_parameters(item) for key, item in value.items()}
    if isinstance(value, list):
        candidates = [item for item in value if item is not None]
        if not candidates:
            return None
        numeric = [item for item in candidates if isinstance(item, (int, float)) and not isinstance(item, bool)]
        if len(numeric) == len(candidates):
            ordered = sorted(numeric)
            return ordered[len(ordered) // 2]
        return _scalarize_parameters(candidates[0])
    return value


def _polish_section_draft(section_id: str, content: str, context: dict[str, Any]) -> str:
    """Remove repetitive fallback prose and enforce a useful evidence-led floor."""
    lines = [line.rstrip() for line in content.strip().splitlines()]
    boilerplate = {
        "本节暂无已登记证据，保留结构性说明，不作外推结论。",
        "本节尚未登记可用证据，保留结构性说明。",
    }
    filtered: list[str] = []
    for line in lines:
        normalized = line.strip().strip("。")
        if normalized in {item.strip("。") for item in boilerplate}:
            continue
        filtered.append(line)
    content = "\n".join(filtered).strip()
    claims = context.get("allowed_claims", [])
    claim_ids = {claim["claim_id"] for claim in claims}
    cited = set(re.findall(r"claim-[a-f0-9]{12}", content))
    if claims and not cited.intersection(claim_ids):
        digest = "\n\n".join(
            f"{claim['text']} [{claim['claim_id']}]"
            for claim in claims
            if claim.get("text")
        )
        if digest:
            content = f"{_section_scaffold(section_id)}\n\n{digest}"
    if not content:
        content = _section_scaffold(section_id)
    return content.rstrip() + "\n"


def _section_scaffold(section_id: str) -> str:
    scaffolds = {
        "abstract": "本文围绕题目目标建立可复现的数学建模流程，依次完成问题界定、数据检验、模型比较、稳健性分析与证据归档。摘要中的具体结果仅引用后续已验证证据。",
        "problem_restated": "本节将题目要求转化为可验证的建模目标，并明确输入、输出、约束条件和评价标准。未在问题材料中明确的内容保留为待核实事项。",
        "assumptions": "模型假设应逐条对应题目条件或数据证据。对于无法由当前材料支持的假设，本流程将其标记为待核实，不将其包装成事实结论。",
        "notation": r"设样本为 $\{(x_i,y_i)\}_{i=1}^{n}$，其中 $x_i$ 表示第 $i$ 个样本的特征向量，$y_i$ 表示目标变量，$\hat y_i$ 表示模型预测值。其余符号以具体模型和数据字典为准。",
        "data_analysis": "本节按照数据来源、字段含义、缺失与重复、异常值及分布结构的顺序报告数据分析。所有统计数字均必须来自已登记的数据质量或探索性分析证据。",
        "model_construction": "将目标变量记为 $y$，特征矩阵记为 $X$。候选模型应在数据字典和题目目标约束下确定，并明确损失函数、参数、训练划分及适用边界。",
        "model_solution": r"本节记录模型训练、交叉验证、参数设定和模型选择规则。对回归任务，主指标可写为 $\mathrm{RMSE}=\sqrt{\frac{1}{n}\sum_{i=1}^{n}(y_i-\hat y_i)^2}$；算法过程只描述已经注册并执行的实验，不以未经验证的经验替代实验结果。",
        "results": "本节只报告通过模型选择和实验注册的结果，并将评价指标、比较对象、数据范围与随机种子一并说明，避免脱离证据进行外推。",
        "sensitivity": "敏感性分析围绕样本规模、随机划分或关键参数改变模型结论的程度展开。稳健性判断应以已登记的敏感性实验和门控结果为依据。",
        "strengths_weaknesses": "模型优点应从可复现性、解释性、预测性能或计算成本等已验证维度评价；局限性应覆盖数据范围、假设条件、指标选择和外推风险。",
        "conclusion": "结论应逐条回答题目目标，区分已验证结果、模型解释和待核实事项，并明确数据来源与适用范围。",
        "references": "参考文献仅列出已登记且完成来源核验的文献或数据来源；未完成核验的条目不进入正式参考文献表。",
    }
    return scaffolds.get(section_id, "本节按研究目的、方法、证据和限制组织内容，具体陈述以已登记证据为准。")

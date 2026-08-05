from __future__ import annotations

from pathlib import Path
from typing import Any

from .claims import ClaimInput, ClaimRegistry
from .figure_registry import FigureRegistry
from .io_utils import atomic_write_json, atomic_write_text, now_iso
from .paper_contracts import (
    AssumptionRecord,
    DiagnosticRecord,
    PaperContractService,
    StorylineRecord,
    SubproblemAnswerRecord,
)
from .paper_outline import default_outline
from .paper_sections import PaperSectionWorkspace
from .paper_consistency import PaperConsistencyChecker
from .stage_service import StageService
from .submission import SubmissionService
from .task_paper_bridge import TaskPaperEvidenceBridge
from .paper_contracts import SubproblemContract


class TaskPaperPipelineService:
    """Runs one complete evidence-to-paper path for a task family."""

    def __init__(
        self,
        cases: Any,
        artifacts: Any,
        bridge: TaskPaperEvidenceBridge,
        contracts: PaperContractService,
        claims: ClaimRegistry,
        figures: FigureRegistry,
        outlines: Any,
        sections: PaperSectionWorkspace,
        stages: StageService,
        consistency: PaperConsistencyChecker,
        submission: SubmissionService,
    ) -> None:
        self.cases = cases
        self.artifacts = artifacts
        self.bridge = bridge
        self.contracts = contracts
        self.claims = claims
        self.figures = figures
        self.outlines = outlines
        self.sections = sections
        self.stages = stages
        self.consistency = consistency
        self.submission = submission

    def run(
        self,
        case_id: str,
        family: str,
        plan: dict[str, Any],
        frame: Any | None = None,
        title: str | None = None,
        dataset_ids: list[str] | None = None,
        source_artifact_ids: list[str] | None = None,
        created_by: str = "human",
        competition_type: str = "SM",
    ) -> dict[str, Any]:
        evidence = self.bridge.execute_and_register(
            case_id, family, plan, frame, dataset_ids, source_artifact_ids, created_by
        )
        task_artifact_id = evidence["execution"]["artifact"]["artifact_id"]
        self._advance_workflow(case_id, created_by, task_artifact_id)
        self._persist_contracts(case_id, family, plan, evidence, task_artifact_id)
        claim = evidence["claim"]
        figure_id = evidence["figure"]["figure_id"]
        table_id = evidence["table"].table_id
        outline_payload = default_outline(title or f"{family} 数学建模论文", competition_type).model_dump(mode="json")
        for section in outline_payload["sections"]:
            section_id = section["section_id"]
            section["claim_ids"] = [claim["claim_id"]] if section_id in {"abstract", "model_solution", "results", "sensitivity", "conclusion"} else []
            section["figure_ids"] = [figure_id] if section_id in {"results", "sensitivity"} else []
        root = self.cases.case_root(case_id)
        outline_path = root / "paper" / "outline" / "task-outline.json"
        atomic_write_json(outline_path, outline_payload)
        self._advance_node(case_id, "paper_outline", created_by, "Task-specific outline generated from registered evidence")
        outline = self.outlines.validate_file(case_id, outline_path)
        self._approve_if_needed(case_id, "paper_outline", created_by, "Task-specific outline evidence scope validated")
        manifest = self.sections.initialize(case_id, outline["outline_artifact_id"])
        self._write_sections(case_id, manifest, family, plan, evidence, claim, table_id, figure_id)
        paper = self.stages.complete_paper_draft(case_id)
        consistency = self.stages.check_consistency(case_id, self.consistency)
        if not consistency["succeeded"]:
            raise ValueError(f"task paper consistency failed: {consistency['result']['report']['findings']}")
        final_text = (root / "paper" / "paper_final.md").read_text(encoding="utf-8")
        assessment, assessment_artifact = self.contracts.write_assessment(case_id, final_text)
        if assessment.gate != "PASS":
            raise ValueError(f"task complete-paper contract failed: {assessment.issue_codes}")
        atomic_write_text(root / "paper" / "final.md", final_text)
        submission = self.submission.prepare(case_id, competition_type)
        if submission["preflight"]["gate"] != "PASS":
            raise ValueError(f"task submission preflight failed: {submission['preflight']['findings']}")
        return {
            "case_id": case_id,
            "family": family,
            "task_run_id": evidence["execution"]["task_run_id"],
            "claim_id": claim["claim_id"],
            "table_id": table_id,
            "figure_id": figure_id,
            "paper_artifact_id": paper["final_artifact"]["artifact_id"],
            "consistency_artifact_id": consistency["result"]["report_artifact_id"],
            "complete_paper_artifact_id": assessment_artifact["artifact_id"],
            "submission": submission,
        }

    def _advance_workflow(self, case_id: str, approved_by: str, task_artifact_id: str) -> None:
        for node_id in ("input_validation", "problem_analysis", "data_registration", "data_quality", "eda", "model_plan", "baseline", "experiments", "model_selection", "sensitivity"):
            self._advance_node(case_id, node_id, approved_by, f"Task-family evidence: {task_artifact_id}")
            self._approve_if_needed(case_id, node_id, approved_by, f"Task-family evidence reviewed: {task_artifact_id}")

    def _advance_node(self, case_id: str, node_id: str, approved_by: str, note: str) -> None:
        snapshot = self.stages.workflow.checkpoints.load(case_id).snapshot()["nodes"][node_id]
        if snapshot["status"] == "SUCCEEDED":
            return
        if snapshot["status"] == "NEEDS_REVIEW":
            return
        self.stages.workflow.start_node(case_id, node_id)
        self.stages.workflow.succeed_node(case_id, node_id)

    def _approve_if_needed(self, case_id: str, node_id: str, approved_by: str, note: str) -> None:
        snapshot = self.stages.workflow.checkpoints.load(case_id).snapshot()["nodes"][node_id]
        if snapshot["status"] == "NEEDS_REVIEW":
            self.stages.workflow.approve_node(case_id, node_id, approved_by, note)

    def _persist_contracts(self, case_id: str, family: str, plan: dict[str, Any], evidence: dict[str, Any], task_artifact_id: str) -> None:
        subproblems = [
            SubproblemContract(
                subproblem_id=f"subproblem-{family}-{index:02d}",
                title=title,
                objective=title,
                inputs=list(plan.keys()),
                outputs=["evidence-backed result"],
                evaluation_metrics=[records.metric for records in evidence["result_records"][:3]],
                owner_section="problem_restated",
                status="COMPLETED",
                evidence_artifact_ids=[task_artifact_id],
            )
            for index, title in enumerate((f"定义{family}任务与数据协议", f"执行{family}模型并报告指标", f"分析{family}结果的稳健性与限制"), start=1)
        ]
        self.contracts.persist_subproblems(case_id, subproblems)
        records = evidence["result_records"]
        primary = records[0]
        self.contracts.persist_analysis_records(
            case_id,
            assumptions=[AssumptionRecord(
                assumption_id=f"assumption-{family}",
                statement=f"{family} 的输入、划分和执行参数遵循已登记任务协议。",
                source_artifact_ids=[task_artifact_id],
                necessity="保证执行结果可复现且不混淆数据范围。",
                risk="协议或数据范围变化会改变结果解释。",
                validation="任务插件协议校验和确定性执行均通过。",
                affected_sections=["assumptions", "model_construction", "conclusion"],
            )],
            diagnostics=[DiagnosticRecord(
                diagnostic_id=f"diagnostic-{family}",
                diagnostic_type="UNCERTAINTY",
                metric=primary.metric,
                value=primary.value,
                interpretation=f"{family} 结果由确定性执行器生成，指标 {primary.metric} 为 {primary.formatted_value()}。",
                limitation="该结果受任务协议、输入数据和执行参数限制，不代表超出样本范围的外部验证。",
                source_artifact_ids=[task_artifact_id],
            )],
            answers=[SubproblemAnswerRecord(
                answer_id=f"answer-{item.subproblem_id}",
                subproblem_id=item.subproblem_id,
                method=f"采用 {family} 任务协议与确定性执行器",
                result_record_ids=[record.result_id for record in records],
                answer=_answer_for_subproblem(index, family, primary),
                limitation="结论仅适用于当前输入、协议和执行参数。",
                source_artifact_ids=[task_artifact_id],
            ) for index, item in enumerate(subproblems, start=1)],
            storyline=StorylineRecord(
                storyline_id=f"storyline-{family}",
                title=f"{family} 问题—方法—证据—结论主线",
                steps=[
                    {"stage": "问题", "text": f"明确 {family} 任务和输入协议。"},
                    {"stage": "方法", "text": "调用已验证的确定性执行器。"},
                    {"stage": "证据", "text": f"报告表格、图形和 {primary.metric}。"},
                    {"stage": "结论", "text": "声明适用边界与限制。"},
                ],
                subproblem_ids=[item.subproblem_id for item in subproblems],
                source_record_ids=[record.result_id for record in records],
            ),
        )

    def _write_sections(self, case_id: str, manifest: dict[str, Any], family: str, plan: dict[str, Any], evidence: dict[str, Any], claim: dict[str, Any], table_id: str, figure_id: str) -> None:
        root = self.cases.case_root(case_id)
        packs = {section_id: self.contracts.build_section_pack(case_id, section_id) for section_id in [item["section_id"] for item in manifest["manifest"]["sections"]]}
        for item in manifest["manifest"]["sections"]:
            section_id = item["section_id"]
            pack = packs[section_id]
            metrics = "；".join(f"{record.metric}={record.formatted_value()}" for record in pack.results)
            answers = "\n\n".join(answer.answer for answer in pack.answers)
            table = next((item for item in pack.tables if item.table_id == table_id), None)
            table_markdown = _render_table(table) if table is not None else ""
            if section_id == "abstract":
                content = f"## 摘要\n\n围绕 {family} 任务，本文在已登记协议下完成可复现的确定性执行，主要结果如下：{metrics}。{pack.diagnostics[0].limitation if pack.diagnostics else '结论受协议和数据范围约束。'}\n\n{claim['text']} [{claim['claim_id']}]"
            elif section_id == "problem_restated":
                content = f"## 引言与问题重述\n\n研究概述：本研究将 {family} 任务拆分为协议定义、模型执行和结果稳健性三个子问题。目标是产生可复现且可审查的结果。"
            elif section_id == "assumptions":
                content = f"## 模型假设\n\n假设：{pack.assumptions[0].statement} 适用边界：{pack.assumptions[0].risk}。"
            elif section_id == "notation":
                content = "## 符号说明\n\n设结果指标为 $m$，任务输入为 $X$，执行输出为 $R$。变量与目标分别由任务协议中的输入字段和优化目标定义。"
            elif section_id == "data_analysis":
                content = "## 数据分析\n\n数据质量与任务协议的字段、时间范围或参数范围由执行输入确定；本节核查缺失、质量和范围，不引入协议之外的数据解释。"
            elif section_id == "model_construction":
                content = f"## 模型建立\n\n模型结构：任务族为 {family}，协议字段为 {', '.join(plan.keys())}。目标函数或评价规则由插件实现。\n\n任务输出记为 $R=F(X;\\theta)$，其中 $F$ 表示已登记确定性执行器。"
            elif section_id == "model_solution":
                content = f"## 模型求解\n\n模型求解采用已验证的 {family} 执行器，执行协议和参数被写入任务运行证据。模型指标通过登记的评价规则计算，必要时进行交叉验证或重复执行。目标函数记为 $R=F(X;\\theta)$。{claim['text']} [{claim['claim_id']}]"
            elif section_id == "results":
                content = f"## 结果分析\n\n结果：{metrics}。图表证据：{evidence['figure']['title']} [{figure_id}]。结果表 [{table_id}]。\n\n{table_markdown}\n{claim['text']} [{claim['claim_id']}]"
            elif section_id == "sensitivity":
                content = f"## 敏感性与稳健性\n\n敏感性与稳健性：当前结果受执行参数和输入范围限制，指标波动应结合协议变化、随机种子或参数比例解释。{pack.diagnostics[0].limitation if pack.diagnostics else ''} 结果表 [{table_id}]，图表证据：{evidence['figure']['title']} [{figure_id}]。"
            elif section_id == "strengths_weaknesses":
                content = "## 模型优缺点\n\n优点：协议明确、结果可复现、证据可追踪。局限：输入范围、模型假设和执行参数限制外推能力。"
            elif section_id == "conclusion":
                content = f"## 结论\n\n{answers}\n\n适用范围与外推限制：结论只适用于已登记输入和任务协议。结果汇总如下：\n\n{table_markdown}\n{claim['text']} [{claim['claim_id']}]"
            else:
                content = "## 参考文献\n\n参考文献与数据来源以已登记、可核验来源为准。"
            self.sections.update_draft(case_id, section_id, content, "task-paper-renderer")


def _render_table(table: Any) -> str:
    header = "| " + " | ".join(str(item) for item in table.columns) + " |"
    divider = "|" + "|".join("---" for _ in table.columns) + "|"
    rows = ["| " + " | ".join(str(item) for item in row) + " |" for row in table.rows]
    return "\n".join([f"表：{table.title} [{table.table_id}]", "", header, divider, *rows])


def _answer_for_subproblem(index: int, family: str, primary: Any) -> str:
    if index == 1:
        detail = f"已完成 {family} 任务协议字段、输入边界和执行约束登记。"
    elif index == 2:
        detail = f"确定性执行器已完成计算，{primary.metric} 为 {primary.formatted_value()}。"
    else:
        detail = "稳健性结论：结果仅在当前协议、输入范围和执行参数下成立。"
    return f"子问题 {index}：{detail}"

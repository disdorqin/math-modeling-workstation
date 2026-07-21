from __future__ import annotations

import argparse
import json
import sys
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
from .figure_registry import FigureRegistry
from .memory_manager import MemoryManager
from .llm.config import RouterConfig
from .llm.image_router import ImageRouter
from .llm.image_service import CaseImageService
from .llm.prompts import PromptRegistry
from .llm.router import LLMRouter
from .llm.service import CaseLLMService
from .model_evaluation import ModelEvaluationEngine
from .model_plan import ModelPlanService
from .modeling_service import ModelingService
from .paper_ready import PaperReadyGate
from .paper_consistency import PaperConsistencyChecker
from .paper_outline import PaperOutlineService, default_outline
from .paper_sections import PaperSectionWorkspace
from .recovery import RecoveryService
from .run_manager import RunManager
from .session_manager import SessionManager
from .selection import ModelSelectionRegistry
from .sensitivity import SensitivityEngine
from .source_collector import SourceCollector
from .workflow import FailureCategory
from .workflow_service import WorkflowService


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mathworkstation")
    parser.add_argument("--output-root", default="output", help="case output directory")
    commands = parser.add_subparsers(dest="command", required=True)

    create = commands.add_parser("create-case", help="create an isolated modeling case")
    create.add_argument("--competition", required=True)
    create.add_argument("--title", required=True)
    create.add_argument("--language", default="zh")

    commands.add_parser("list-cases", help="list active cases").add_argument(
        "--include-archived", action="store_true"
    )

    for command in (
        "show-case",
        "show-workflow",
        "validate-case",
        "archive-case",
        "create-session",
        "resume-case",
        "migrate-case",
    ):
        item = commands.add_parser(command)
        item.add_argument("--case-id", required=True)

    ingest = commands.add_parser("ingest-file", help="copy and register an immutable input file")
    ingest.add_argument("--case-id", required=True)
    ingest.add_argument("--source", required=True)
    ingest.add_argument("--destination", default="input/data/uploaded")
    ingest.add_argument("--artifact-type", default="uploaded_data")

    start = commands.add_parser("start-node")
    start.add_argument("--case-id", required=True)
    start.add_argument("--node-id", required=True)
    start.add_argument("--session-id")

    succeed = commands.add_parser("succeed-node")
    succeed.add_argument("--case-id", required=True)
    succeed.add_argument("--node-id", required=True)

    fail = commands.add_parser("fail-node")
    fail.add_argument("--case-id", required=True)
    fail.add_argument("--node-id", required=True)
    fail.add_argument("--category", required=True, choices=[item.value for item in FailureCategory])
    fail.add_argument("--message", required=True)

    approve = commands.add_parser("approve-node")
    approve.add_argument("--case-id", required=True)
    approve.add_argument("--node-id", required=True)
    approve.add_argument("--approved-by", required=True)
    approve.add_argument("--note", default="")

    stale = commands.add_parser("mark-stale")
    stale.add_argument("--case-id", required=True)
    stale.add_argument("--node-id", required=True)
    stale.add_argument("--reason", required=True)

    retry = commands.add_parser("retry-node")
    retry.add_argument("--case-id", required=True)
    retry.add_argument("--node-id", required=True)
    retry.add_argument("--requested-by", required=True)
    retry.add_argument("--reason", required=True)

    register = commands.add_parser("register-dataset")
    register.add_argument("--case-id", required=True)
    register.add_argument("--source", required=True)
    register.add_argument("--name", required=True)
    register.add_argument("--kind", choices=[item.value for item in DatasetKind], required=True)
    register.add_argument("--created-by", default="human")
    register.add_argument("--source-uri")
    register.add_argument("--license")
    register.add_argument("--derived-from", action="append", default=[])
    register.add_argument("--description", default="")

    register_artifact = commands.add_parser("register-artifact-dataset")
    register_artifact.add_argument("--case-id", required=True)
    register_artifact.add_argument("--artifact-id", required=True)
    register_artifact.add_argument("--name", required=True)
    register_artifact.add_argument("--kind", choices=[item.value for item in DatasetKind], required=True)
    register_artifact.add_argument("--source-type", required=True)
    register_artifact.add_argument("--created-by", default="human")
    register_artifact.add_argument("--source-uri")
    register_artifact.add_argument("--license")
    register_artifact.add_argument("--derived-from", action="append", default=[])
    register_artifact.add_argument("--description", default="")

    complete_data = commands.add_parser("complete-data-registration")
    complete_data.add_argument("--case-id", required=True)
    complete_data.add_argument("--session-id")

    profile = commands.add_parser("profile-dataset")
    profile.add_argument("--case-id", required=True)
    profile.add_argument("--dataset-id", required=True)
    profile.add_argument("--target-column")
    profile.add_argument("--session-id")

    list_datasets = commands.add_parser("list-datasets")
    list_datasets.add_argument("--case-id", required=True)

    collect = commands.add_parser("collect-url")
    collect.add_argument("--case-id", required=True)
    collect.add_argument("--url", required=True)

    run_eda = commands.add_parser("run-eda")
    run_eda.add_argument("--case-id", required=True)
    run_eda.add_argument("--dataset-id", required=True)
    run_eda.add_argument("--target-column")
    run_eda.add_argument("--session-id")

    baseline = commands.add_parser("run-baseline")
    baseline.add_argument("--case-id", required=True)
    baseline.add_argument("--dataset-id", required=True)
    baseline.add_argument("--target-column", required=True)
    baseline.add_argument("--feature", action="append", default=[])
    baseline.add_argument("--task-type", choices=["auto", "regression", "classification"], default="auto")
    baseline.add_argument("--test-size", type=float, default=0.25)
    baseline.add_argument("--random-seed", type=int, default=42)
    baseline.add_argument("--session-id")

    list_figures = commands.add_parser("list-figures")
    list_figures.add_argument("--case-id", required=True)

    list_experiments = commands.add_parser("list-experiments")
    list_experiments.add_argument("--case-id", required=True)

    validate_plan = commands.add_parser("validate-model-plan")
    validate_plan.add_argument("--case-id", required=True)
    validate_plan.add_argument("--source", required=True)
    validate_plan.add_argument("--dataset-id")

    comparison = commands.add_parser("run-model-comparison")
    comparison.add_argument("--case-id", required=True)
    comparison.add_argument("--plan-artifact-id", required=True)
    comparison.add_argument("--session-id")

    selection = commands.add_parser("select-model")
    selection.add_argument("--case-id", required=True)
    selection.add_argument("--experiment-id", required=True)
    selection.add_argument("--selected-model", required=True)
    selection.add_argument("--comparison-artifact-id", required=True)
    selection.add_argument("--selected-by", required=True)
    selection.add_argument("--rationale", required=True)
    selection.add_argument("--session-id")

    sensitivity = commands.add_parser("run-sensitivity")
    sensitivity.add_argument("--case-id", required=True)
    sensitivity.add_argument("--experiment-id", required=True)
    sensitivity.add_argument("--plan-artifact-id", required=True)
    sensitivity.add_argument("--seed", type=int, action="append", default=[])
    sensitivity.add_argument("--session-id")

    assess = commands.add_parser("assess-paper-ready")
    assess.add_argument("--case-id", required=True)
    assess.add_argument("--experiment-id", required=True)
    assess.add_argument("--selection-artifact-id", required=True)
    assess.add_argument("--sensitivity-artifact-id", required=True)

    approve_ready = commands.add_parser("approve-paper-ready")
    approve_ready.add_argument("--case-id", required=True)
    approve_ready.add_argument("--experiment-id", required=True)
    approve_ready.add_argument("--selection-artifact-id", required=True)
    approve_ready.add_argument("--sensitivity-artifact-id", required=True)
    approve_ready.add_argument("--approved-by", required=True)
    approve_ready.add_argument("--note", required=True)

    create_claim = commands.add_parser("create-claim")
    create_claim.add_argument("--case-id", required=True)
    create_claim.add_argument("--text", required=True)
    create_claim.add_argument("--claim-type", required=True)
    create_claim.add_argument("--evidence-artifact-id", action="append", required=True)
    create_claim.add_argument("--dataset-id", action="append", default=[])
    create_claim.add_argument("--section-hint")
    create_claim.add_argument("--created-by", default="human")

    default_paper = commands.add_parser("create-default-outline")
    default_paper.add_argument("--case-id", required=True)
    default_paper.add_argument("--title", required=True)
    default_paper.add_argument("--competition-type", required=True)
    default_paper.add_argument("--language", choices=["zh", "en", "bilingual"], default="zh")
    default_paper.add_argument("--output", required=True)

    validate_outline = commands.add_parser("validate-outline")
    validate_outline.add_argument("--case-id", required=True)
    validate_outline.add_argument("--source", required=True)

    init_sections = commands.add_parser("init-paper-sections")
    init_sections.add_argument("--case-id", required=True)
    init_sections.add_argument("--outline-artifact-id", required=True)

    update_section = commands.add_parser("update-section")
    update_section.add_argument("--case-id", required=True)
    update_section.add_argument("--section-id", required=True)
    update_section.add_argument("--source", required=True)
    update_section.add_argument("--created-by", default="human")

    consistency = commands.add_parser("check-paper-consistency")
    consistency.add_argument("--case-id", required=True)

    llm_chat = commands.add_parser("llm-chat")
    llm_chat.add_argument("--case-id", required=True)
    llm_chat.add_argument("--session-id", required=True)
    llm_chat.add_argument("--node-id", required=True)
    llm_chat.add_argument("--routes", required=True)
    llm_chat.add_argument("--message-file", required=True)
    llm_chat.add_argument("--input-artifact-id", action="append", default=[])
    llm_chat.add_argument("--model")
    llm_chat.add_argument("--max-tokens", type=int, default=2000)
    llm_chat.add_argument("--temperature", type=float, default=0.2)

    image = commands.add_parser("generate-illustration")
    image.add_argument("--case-id", required=True)
    image.add_argument("--routes", required=True)
    image.add_argument("--title", required=True)
    image.add_argument("--prompt-file", required=True)
    image.add_argument("--source-artifact-id", action="append", default=[])
    image.add_argument("--model")
    image.add_argument("--size", default="1024x1024")

    commands.add_parser("list-prompts")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    cases = CaseManager(Path(args.output_root))
    artifacts = ArtifactRegistry(cases)
    checkpoints = CheckpointManager(cases)
    memory = MemoryManager(cases, artifacts)
    sessions = SessionManager(cases)
    runs = RunManager(cases)
    workflow = WorkflowService(cases, runs, checkpoints, memory)
    datasets = DatasetRegistry(cases, artifacts)
    data = DataService(
        artifacts,
        datasets,
        TabularProfiler(cases, artifacts, datasets),
        workflow,
    )
    sources = SourceCollector(cases, artifacts)
    figures = FigureRegistry(cases, artifacts)
    experiments = ExperimentRegistry(cases, artifacts)
    modeling = ModelingService(
        workflow,
        EDAEngine(cases, artifacts, datasets, figures),
        BaselineEngine(cases, artifacts, datasets, experiments, figures),
    )
    plans = ModelPlanService(cases, artifacts)
    selections = ModelSelectionRegistry(cases, artifacts, experiments)
    evaluation = EvaluationService(
        workflow,
        plans,
        ModelEvaluationEngine(cases, artifacts, datasets, experiments, figures),
        SensitivityEngine(cases, artifacts, datasets, experiments, figures),
        selections,
    )
    paper_ready = PaperReadyGate(cases, artifacts, experiments)
    claims = ClaimRegistry(cases, artifacts, datasets)
    outline_service = PaperOutlineService(cases, artifacts, claims, figures)
    section_workspace = PaperSectionWorkspace(cases, artifacts, claims, figures)
    consistency_checker = PaperConsistencyChecker(cases, artifacts, claims, figures)

    try:
        if args.command == "create-case":
            _print(cases.create_case(args.competition, args.title, args.language))
        elif args.command == "list-cases":
            _print(cases.list_cases(args.include_archived))
        elif args.command == "show-case":
            _print(cases.show_case(args.case_id))
        elif args.command == "show-workflow":
            _print(checkpoints.snapshot(args.case_id))
        elif args.command == "validate-case":
            result = cases.validate_case(args.case_id)
            result["artifacts"] = artifacts.verify(args.case_id)
            _print(result)
            return 0 if result["valid"] and result["artifacts"]["valid"] else 1
        elif args.command == "archive-case":
            _print(cases.archive_case(args.case_id))
        elif args.command == "create-session":
            _print(sessions.create_session(args.case_id))
        elif args.command == "resume-case":
            service = RecoveryService(cases, artifacts, checkpoints, memory)
            _print(service.inspect(args.case_id))
        elif args.command == "migrate-case":
            _print(cases.migrate_case(args.case_id))
        elif args.command == "ingest-file":
            _print(
                artifacts.ingest_file(
                    args.case_id,
                    args.source,
                    args.destination,
                    args.artifact_type,
                )
            )
        elif args.command == "start-node":
            _print(workflow.start_node(args.case_id, args.node_id, args.session_id))
        elif args.command == "succeed-node":
            protected = {"model_plan", "experiments", "model_selection", "sensitivity"}
            if args.node_id in protected:
                raise ValueError(f"{args.node_id} must use its dedicated validated service")
            _print(workflow.succeed_node(args.case_id, args.node_id))
        elif args.command == "fail-node":
            _print(
                workflow.fail_node(
                    args.case_id,
                    args.node_id,
                    FailureCategory(args.category),
                    args.message,
                )
            )
        elif args.command == "approve-node":
            _print(
                workflow.approve_node(
                    args.case_id,
                    args.node_id,
                    args.approved_by,
                    args.note,
                )
            )
        elif args.command == "mark-stale":
            _print(workflow.mark_stale(args.case_id, args.node_id, args.reason))
        elif args.command == "retry-node":
            _print(
                workflow.retry_node(
                    args.case_id,
                    args.node_id,
                    args.requested_by,
                    args.reason,
                )
            )
        elif args.command == "register-dataset":
            _print(
                data.register_uploaded(
                    args.case_id,
                    args.source,
                    args.name,
                    DatasetKind(args.kind),
                    args.created_by,
                    source_uri=args.source_uri,
                    license_name=args.license,
                    derived_from=args.derived_from,
                    description=args.description,
                )
            )
        elif args.command == "register-artifact-dataset":
            _print(
                data.register_artifact(
                    args.case_id,
                    args.artifact_id,
                    args.name,
                    DatasetKind(args.kind),
                    args.source_type,
                    args.created_by,
                    source_uri=args.source_uri,
                    license_name=args.license,
                    derived_from=args.derived_from,
                    description=args.description,
                )
            )
        elif args.command == "complete-data-registration":
            _print(data.complete_registration(args.case_id, args.session_id))
        elif args.command == "profile-dataset":
            _print(data.profile_dataset(args.case_id, args.dataset_id, args.target_column, args.session_id))
        elif args.command == "list-datasets":
            _print(datasets.current_records(args.case_id))
        elif args.command == "collect-url":
            _print(sources.collect_url(args.case_id, args.url))
        elif args.command == "run-eda":
            _print(modeling.run_eda(args.case_id, args.dataset_id, args.target_column, args.session_id))
        elif args.command == "run-baseline":
            _print(
                modeling.run_baseline(
                    args.case_id,
                    args.dataset_id,
                    args.target_column,
                    args.feature or None,
                    args.task_type,
                    args.test_size,
                    args.random_seed,
                    args.session_id,
                )
            )
        elif args.command == "list-figures":
            _print(figures.list_figures(args.case_id))
        elif args.command == "list-experiments":
            _print(experiments.list_experiments(args.case_id))
        elif args.command == "validate-model-plan":
            _print(plans.validate_file(args.case_id, args.source, args.dataset_id))
        elif args.command == "run-model-comparison":
            _print(evaluation.run_comparison(args.case_id, args.plan_artifact_id, args.session_id))
        elif args.command == "select-model":
            _print(
                evaluation.select_model(
                    args.case_id,
                    args.experiment_id,
                    args.selected_model,
                    args.comparison_artifact_id,
                    args.selected_by,
                    args.rationale,
                    args.session_id,
                )
            )
        elif args.command == "run-sensitivity":
            _print(
                evaluation.run_sensitivity(
                    args.case_id,
                    args.experiment_id,
                    args.plan_artifact_id,
                    args.seed or None,
                    args.session_id,
                )
            )
        elif args.command == "assess-paper-ready":
            _print(
                paper_ready.assess(
                    args.case_id,
                    args.experiment_id,
                    args.selection_artifact_id,
                    args.sensitivity_artifact_id,
                )
            )
        elif args.command == "approve-paper-ready":
            _print(
                paper_ready.approve(
                    args.case_id,
                    args.experiment_id,
                    args.selection_artifact_id,
                    args.sensitivity_artifact_id,
                    args.approved_by,
                    args.note,
                )
            )
        elif args.command == "create-claim":
            _print(
                claims.create(
                    args.case_id,
                    ClaimInput(
                        text=args.text,
                        claim_type=args.claim_type,
                        evidence_artifact_ids=args.evidence_artifact_id,
                        dataset_ids=args.dataset_id,
                        section_hint=args.section_hint,
                    ),
                    args.created_by,
                )
            )
        elif args.command == "create-default-outline":
            outline = default_outline(
                args.title,
                args.competition_type,
                args.language,
            )
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(outline.model_dump_json(indent=2), encoding="utf-8")
            _print({"output": str(output_path.resolve())})
        elif args.command == "validate-outline":
            _print(outline_service.validate_file(args.case_id, args.source))
        elif args.command == "init-paper-sections":
            _print(section_workspace.initialize(args.case_id, args.outline_artifact_id))
        elif args.command == "update-section":
            content = Path(args.source).read_text(encoding="utf-8-sig")
            _print(section_workspace.update_draft(args.case_id, args.section_id, content, args.created_by))
        elif args.command == "check-paper-consistency":
            _print(consistency_checker.check(args.case_id))
        elif args.command == "llm-chat":
            route_config = RouterConfig.model_validate_json(
                Path(args.routes).read_text(encoding="utf-8-sig")
            )
            message = Path(args.message_file).read_text(encoding="utf-8-sig")
            llm_service = CaseLLMService(
                cases,
                artifacts,
                sessions,
                checkpoints,
                LLMRouter(route_config),
            )
            _print(
                llm_service.invoke(
                    args.case_id,
                    args.session_id,
                    args.node_id,
                    [{"role": "user", "content": message}],
                    args.input_artifact_id,
                    args.model,
                    args.max_tokens,
                    args.temperature,
                )
            )
        elif args.command == "generate-illustration":
            route_config = RouterConfig.model_validate_json(
                Path(args.routes).read_text(encoding="utf-8-sig")
            )
            prompt = Path(args.prompt_file).read_text(encoding="utf-8-sig")
            image_service = CaseImageService(
                cases,
                artifacts,
                figures,
                ImageRouter(route_config),
            )
            _print(
                image_service.generate(
                    args.case_id,
                    args.title,
                    prompt,
                    args.source_artifact_id,
                    args.model,
                    args.size,
                )
            )
        elif args.command == "list-prompts":
            _print(PromptRegistry("prompts").list_prompts())
        else:
            raise AssertionError(f"unhandled command: {args.command}")
    except Exception as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

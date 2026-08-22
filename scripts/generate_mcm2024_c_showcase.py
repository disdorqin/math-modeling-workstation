from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict
from pathlib import Path

import fitz
import numpy as np

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.claims import ClaimRegistry
from mathworkstation.competition_latex_export import CompetitionLatexExporter
from mathworkstation.competition_paper_auditor import CompetitionPaperAuditor
from mathworkstation.datasets import DatasetRegistry
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.mcm2024_gate import MCM2024_C_DATA_DIR, link_mcm2024_c_dependencies, mcm2024_c_contracts
from mathworkstation.mcm2024_pipeline import FEATURES, analyze_wimbledon, load_wimbledon, render_figures
from mathworkstation.narrative_graph import NarrativeGraphService
from mathworkstation.paper_contracts import PaperContractService
from mathworkstation.problem_graph import ProblemGraphService
from mathworkstation.research_preferences import ResearchPreferenceProfile, ResearchPreferenceService
from mathworkstation.research_state_ingestion import (
    AcceptedResultSpec,
    AcceptedSubproblemExecution,
    AcceptedTableSpec,
    ResearchStateIngestionService,
)
from mathworkstation.research_state_paper import ResearchStatePaperService
from mathworkstation.whole_pdf_visual_review import WholePDFVisualReviewer


TITLE = "Flow Without Myth: A Probabilistic State Model of Tennis Momentum and Swing Risk"
REPO_ROOT = Path(__file__).resolve().parents[1]
SHOWCASE_ROOT = REPO_ROOT / "docs" / "generated_samples" / "mcm2024_c_showcase"
OUTPUT_ROOT = SHOWCASE_ROOT / "workspace"


def build_showcase() -> dict[str, object]:
    problem_pdf = MCM2024_C_DATA_DIR / "problem.pdf"
    data_csv = MCM2024_C_DATA_DIR / "wimbledon_data.csv"
    benchmark_pdf = MCM2024_C_DATA_DIR / "o_award_reference.pdf"
    for path in (problem_pdf, data_csv, benchmark_pdf):
        if not path.is_file():
            raise FileNotFoundError(path)

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    cases = CaseManager(OUTPUT_ROOT)
    case = cases.create_case("MCM", TITLE)
    case_id = case["case_id"]
    root = cases.case_root(case_id)
    artifacts = ArtifactRegistry(cases)
    figures = FigureRegistry(cases, artifacts)
    contracts = PaperContractService(cases, artifacts)
    graphs = ProblemGraphService(cases, artifacts)

    # Development benchmark: apply the user's current research taste, but keep
    # human checkpoints non-blocking.  In a formal contest these values come
    # from the pre-run interview through the Chat Driver.
    ResearchPreferenceService(cases, artifacts).save(
        case_id,
        ResearchPreferenceProfile(
            preferred_modeling_styles=["probabilistic_graphical", "dynamic_system", "hybrid"],
            priorities=[
                "mathematical_structure",
                "logical_rigor",
                "mechanism_depth",
                "robustness",
                "visual_storytelling",
            ],
            claim_strength="award_ambitious",
            paper_style="balanced",
            visual_density="rich",
            unified_framework_preferred=True,
            predictive_accuracy_is_primary=False,
            human_loop_mode="OFF",
            notes=[
                "Prefer one unified mathematical framework across questions.",
                "Use predictive accuracy as validation evidence, not as the modeling objective.",
                "Favor model structure diagrams, varied evidence figures, inheritance across questions, and robustness analysis.",
            ],
        ),
    )

    problem_artifact = artifacts.ingest_file(case_id, problem_pdf, "input/problem", "problem_source")
    data_artifact = artifacts.ingest_file(case_id, data_csv, "input/data", "observed_data")
    artifacts.ingest_file(case_id, benchmark_pdf, "input/benchmark", "excellent_paper_benchmark")

    contracts.persist_subproblems(case_id, mcm2024_c_contracts())
    graph = link_mcm2024_c_dependencies(graphs.builder.build(contracts.list_subproblems(case_id)))
    graphs.save(
        case_id,
        graph,
        [problem_artifact["artifact_id"], data_artifact["artifact_id"]],
        created_by="mcm2024_showcase",
    )
    print(f"[mcm2024] {case_id} inputs and problem graph ready", flush=True)

    frame = load_wimbledon(data_csv)
    analysis = analyze_wimbledon(frame, n_permutations=250)
    analysis_dir = root / "analysis" / "mcm2024"
    analysis_dir.mkdir(parents=True, exist_ok=True)
    summary_path = analysis_dir / "summary.json"
    null_path = analysis_dir / "null_tests.csv"
    cv_path = analysis_dir / "cv_predictions.csv"

    summary = {
        "schema_version": 2,
        "case_id": case_id,
        "n_points": analysis.n_points,
        "n_matches": analysis.n_matches,
        "server_point_win_rate": analysis.server_point_win_rate,
        "flow_state_transition_matrix": analysis.state_transition_matrix,
        "featured_final": {
            "match_id": "2023-wimbledon-1701",
            "players": list(analysis.final_players),
            "points": analysis.final_points,
            "server_point_win_rate": analysis.final_server_point_win_rate,
            "ljung_p": analysis.final_ljung_p,
            "runs_p": analysis.final_runs_p,
            "permutation_p": analysis.final_permutation_p,
            "rf_heldout_auc": analysis.final_holdout_auc,
            "rf_heldout_balanced_accuracy": analysis.final_holdout_balanced_accuracy,
            "logit_heldout_auc": analysis.final_holdout_logit_auc,
            "logit_heldout_balanced_accuracy": analysis.final_holdout_logit_balanced_accuracy,
        },
        "momentum_null_tests": {
            "ljung_reject_count": analysis.ljung_reject_count,
            "runs_reject_count": analysis.runs_reject_count,
            "permutation_reject_count": analysis.permutation_reject_count,
            "matches": analysis.n_matches,
        },
        "probabilistic_swing_model": {
            "eligible_rows": analysis.prediction_rows,
            "swing_rate": analysis.swing_rate,
            "logistic": asdict(analysis.logit_summary),
            "logistic_brier": analysis.brier_score,
            "logistic_coefficients": analysis.logit_coefficients[:10],
            "calibration_points": analysis.calibration_points,
            "random_forest_comparator": asdict(analysis.rf_summary),
            "rf_top_feature_importance": analysis.feature_importance[:10],
            "sensitivity_auc": analysis.sensitivity_auc,
        },
    }
    from mathworkstation.io_utils import atomic_write_json, atomic_write_text

    atomic_write_json(summary_path, summary)
    analysis.null_tests.to_csv(null_path, index=False)
    analysis.cv_predictions.to_csv(cv_path, index=False)
    summary_artifact = artifacts.register_existing(
        case_id,
        summary_path.relative_to(root).as_posix(),
        "mcm2024_analysis_summary",
        "mcm2024_pipeline",
        upstream=[data_artifact["artifact_id"]],
        paper_eligible=False,
    )
    null_artifact = artifacts.register_existing(
        case_id,
        null_path.relative_to(root).as_posix(),
        "momentum_null_test_results",
        "mcm2024_pipeline",
        upstream=[data_artifact["artifact_id"], summary_artifact["artifact_id"]],
        paper_eligible=False,
    )
    cv_artifact = artifacts.register_existing(
        case_id,
        cv_path.relative_to(root).as_posix(),
        "swing_prediction_cv_results",
        "mcm2024_pipeline",
        upstream=[data_artifact["artifact_id"], summary_artifact["artifact_id"]],
        paper_eligible=False,
    )
    print(
        f"[mcm2024] analysis complete: logistic AUC={analysis.logit_summary.auc:.3f}, "
        f"RF comparator AUC={analysis.rf_summary.auc:.3f}, "
        f"final logistic holdout AUC={analysis.final_holdout_logit_auc:.3f}",
        flush=True,
    )

    rendered = render_figures(analysis, root / "figures" / "final", profile="MCM_C")
    figure_titles = {
        "final-match-flow": "Serve-adjusted Flow Score through the 2023 Wimbledon final",
        "null-test-comparison": "Serve-conditioned persistence tests across Wimbledon matches",
        "flow-state-transition": "Empirical transition probabilities among three Flow states",
        "swing-prediction-roc": "Grouped cross-validated discrimination of near-term swing risk",
        "swing-calibration": "Calibration of the probabilistic swing-hazard layer",
        "swing-feature-importance": "Nonlinear comparator: leading indicators of an approaching reversal",
        "final-holdout-swing-risk": "Flow Score and swing risk in the final excluded from training",
        "match-generalization": "Held-out match-level generalization",
        "flow-window-sensitivity": "Sensitivity to the Flow Score aggregation window",
    }
    figure_semantics = {
        "final-match-flow": ("SP1", "state_trajectory", "primary"),
        "null-test-comparison": ("SP1", "probability_validation_null", "primary"),
        "flow-state-transition": ("SP2", "probabilistic_state_transition", "primary"),
        "swing-prediction-roc": ("SP2", "probability_validation_roc", "primary"),
        "swing-calibration": ("SP2", "probability_validation_calibration", "primary"),
        "swing-feature-importance": ("SP2", "model_interpretability", "supplementary_evidence"),
        "final-holdout-swing-risk": ("SP3", "state_trajectory", "primary"),
        "match-generalization": ("SP3", "generalization_distribution", "supplementary_evidence"),
        "flow-window-sensitivity": ("SP3", "parameter_sensitivity_curve", "supplementary_evidence"),
    }
    figure_source_by_sp = {
        "SP1": [summary_artifact["artifact_id"], null_artifact["artifact_id"]],
        "SP2": [summary_artifact["artifact_id"], cv_artifact["artifact_id"]],
        "SP3": [summary_artifact["artifact_id"], cv_artifact["artifact_id"]],
    }
    for item in rendered:
        png_path = Path(item["path"])
        svg_path = Path(item["svg_path"])
        stem = png_path.stem
        subproblem_id, semantic_kind, paper_role = figure_semantics[stem]
        svg_artifact = artifacts.register_existing(
            case_id,
            svg_path.relative_to(root).as_posix(),
            "scientific_data_figure_vector",
            "mcm2024_pipeline",
            upstream=figure_source_by_sp[subproblem_id],
            paper_eligible=False,
        )
        figures.register(
            case_id,
            png_path.relative_to(root).as_posix(),
            figure_titles[stem],
            [*figure_source_by_sp[subproblem_id], svg_artifact["artifact_id"]],
            "mathworkstation.mcm2024_pipeline",
            {
                "subproblem_id": subproblem_id,
                "semantic_kind": semantic_kind,
                "paper_role": paper_role,
                "purpose": figure_titles[stem],
                "publication_profile": "MCM_C",
                "dpi": 600,
                "vector_source": True,
                "svg_artifact_id": svg_artifact["artifact_id"],
                "caption_first": True,
                "numeric_evidence": True,
            },
            run_id=None,
            status="FINAL",
        )
    print(f"[mcm2024] {len(rendered)} solver-evidence figures rendered and registered", flush=True)

    transition_rows = []
    state_names = ["Player 2 flow", "Neutral", "Player 1 flow"]
    for name, row in zip(state_names, analysis.state_transition_matrix):
        transition_rows.append([name, *[f"{value:.3f}" for value in row]])
    coefficient_rows = [[name, f"{value:+.3f}"] for name, value in analysis.logit_coefficients[:8]]
    sensitivity_rows = [[window, f"{auc:.3f}"] for window, auc in analysis.sensitivity_auc]
    per_auc = np.asarray([value for _, value in analysis.per_match_auc], dtype=float)

    packets = [
        AcceptedSubproblemExecution(
            subproblem_id="SP1",
            method="Serve-adjusted Flow with Ljung-Box and bootstrap null inference",
            solver_evidence_artifact_ids=[summary_artifact["artifact_id"], null_artifact["artifact_id"]],
            validation_protocol_id="serve-conditioned-null-and-residual-persistence-audit",
            validation_summary={
                "matches": analysis.n_matches,
                "ljung_rejections": analysis.ljung_reject_count,
                "server_null_rejections": analysis.permutation_reject_count,
                "interpretation": "persistent residual momentum is not established after conditioning on serve",
            },
            time_column="point_no within match_id",
            target_column="point_victor",
            feature_columns=["server", "point_victor", "match_id", "point_no"],
            numeric_columns=["set_no", "game_no", "point_no", "p1_points_won", "p2_points_won"],
            preprocessing_notes=[
                "Within each match, points are kept in their original order before any rolling statistic or null test is computed.",
                "The tournament-wide server point-win rate defines the first-order baseline e_t; Flow is computed from point outcome minus this serve-conditioned expectation.",
                "The Flow Score uses a seven-point trailing window, so no future point enters the descriptive state at time t.",
            ],
            results=[
                AcceptedResultSpec(
                    result_type="EXPLORATORY",
                    metric="server point-win probability",
                    value=analysis.server_point_win_rate,
                    scope=f"all {analysis.n_points} points across {analysis.n_matches} matches",
                ),
                AcceptedResultSpec(
                    result_type="EXPLORATORY",
                    metric="Ljung-Box rejection fraction",
                    value=analysis.ljung_reject_count / analysis.n_matches,
                    scope="match-wise residual persistence tests at alpha=0.05",
                ),
                AcceptedResultSpec(
                    result_type="SIMULATION",
                    metric="serve-conditioned null rejection fraction",
                    value=analysis.permutation_reject_count / analysis.n_matches,
                    scope="server-sequence-preserving Monte Carlo tests at alpha=0.05",
                ),
            ],
            tables=[
                AcceptedTableSpec(
                    title="Momentum persistence diagnostics",
                    columns=["Diagnostic", "Rejecting matches", "Featured-final p-value"],
                    rows=[
                        ["Ljung-Box residual dependence", f"{analysis.ljung_reject_count}/{analysis.n_matches}", f"{analysis.final_ljung_p:.3f}"],
                        ["Server-conditioned simulation", f"{analysis.permutation_reject_count}/{analysis.n_matches}", f"{analysis.final_permutation_p:.3f}"],
                        ["Raw Runs Test (secondary)", f"{analysis.runs_reject_count}/{analysis.n_matches}", f"{analysis.final_runs_p:.3f}"],
                    ],
                    table_role="relationship_validation",
                )
            ],
            answer=(
                "After removing the tournament-wide server advantage, the Flow Score describes local relative performance, "
                f"but persistent residual momentum is not established: Ljung-Box rejects in {analysis.ljung_reject_count}/{analysis.n_matches} matches "
                f"and the serve-conditioned simulation rejects in {analysis.permutation_reject_count}/{analysis.n_matches}."
            ),
            limitation="The Flow Score is an observable performance state, not a direct measurement of psychology, confidence, injury, or causal momentum.",
        ),
        AcceptedSubproblemExecution(
            subproblem_id="SP2",
            method="Probabilistic state-transition logistic hazard classification with calibration and Random Forest comparator",
            solver_evidence_artifact_ids=[summary_artifact["artifact_id"], cv_artifact["artifact_id"]],
            validation_protocol_id="grouped-match-probability-calibration-and-nonlinear-comparator",
            validation_summary={
                "grouping": "complete matches held out together",
                "logistic_auc": analysis.logit_summary.auc,
                "logistic_brier": analysis.brier_score,
                "rf_comparator_auc": analysis.rf_summary.auc,
                "role": "logistic hazard is the interpretable probabilistic core; RF is a nonlinear robustness comparator",
            },
            time_column="point_no within match_id",
            target_column="swing_within_horizon",
            feature_columns=list(FEATURES),
            numeric_columns=list(FEATURES),
            preprocessing_notes=[
                "The continuous Flow Score is converted to three states using the declared neutral deadband; a positive label means the current non-neutral state reaches the opposite side within the next five points.",
                "Future points are used only to construct the swing label. Every predictor is computed from the current or previous points.",
                "GroupKFold keeps every point from one match entirely in the same fold, preventing within-match temporal/context leakage.",
                "The logistic hazard is the interpretable probabilistic core; Random Forest is retained only as a nonlinear comparator under the identical split protocol.",
            ],
            results=[
                AcceptedResultSpec(
                    result_type="CLASSIFICATION",
                    metric="grouped ROC AUC",
                    value=analysis.logit_summary.auc,
                    direction="MAXIMIZE",
                    scope="interpretable logistic swing-hazard model with match-grouped cross-validation",
                    model_name="Probabilistic state-transition logistic hazard",
                ),
                AcceptedResultSpec(
                    result_type="CLASSIFICATION",
                    metric="Brier score",
                    value=analysis.brier_score,
                    direction="MINIMIZE",
                    scope="out-of-match probabilistic calibration of the logistic hazard layer",
                    model_name="Probabilistic state-transition logistic hazard",
                ),
                AcceptedResultSpec(
                    result_type="MODEL_COMPARISON",
                    metric="nonlinear comparator ROC AUC",
                    value=analysis.rf_summary.auc,
                    direction="MAXIMIZE",
                    scope="Random Forest comparator under the identical grouped protocol",
                    model_name="Random Forest comparator",
                ),
            ],
            tables=[
                AcceptedTableSpec(
                    title="Probabilistic swing-hazard model and nonlinear comparator",
                    columns=["Model", "ROC AUC", "Balanced accuracy", "F1"],
                    rows=[
                        ["Logistic state-transition hazard", f"{analysis.logit_summary.auc:.3f}", f"{analysis.logit_summary.balanced_accuracy:.3f}", f"{analysis.logit_summary.f1:.3f}"],
                        ["Random Forest comparator", f"{analysis.rf_summary.auc:.3f}", f"{analysis.rf_summary.balanced_accuracy:.3f}", f"{analysis.rf_summary.f1:.3f}"],
                    ],
                    table_role="relationship_validation",
                ),
                AcceptedTableSpec(
                    title="Serve-adjusted Flow-state transition matrix",
                    columns=["Current state", "to P2 flow", "to neutral", "to P1 flow"],
                    rows=transition_rows,
                    table_role="summary_metrics",
                ),
                AcceptedTableSpec(
                    title="Largest standardized logistic hazard effects",
                    columns=["Current-information feature", "Standardized coefficient"],
                    rows=coefficient_rows,
                    table_role="parameter_summary",
                ),
            ],
            answer=(
                "The unified probabilistic layer treats local Flow as a three-state process and estimates near-term reversal risk with an interpretable logistic hazard. "
                f"Grouped cross-validation gives AUC={analysis.logit_summary.auc:.3f} with Brier score={analysis.brier_score:.3f}; "
                f"the Random Forest comparator reaches AUC={analysis.rf_summary.auc:.3f}, showing moderate nonlinear headroom without replacing the structural core."
            ),
            limitation="The state and hazard relations are predictive and conditional on observed match context; coefficient signs are not causal tactical effects.",
        ),
        AcceptedSubproblemExecution(
            subproblem_id="SP3",
            method="Probabilistic state-transition logistic hazard with grouped resampling",
            solver_evidence_artifact_ids=[summary_artifact["artifact_id"], cv_artifact["artifact_id"]],
            validation_protocol_id="unseen-final-holdout-cross-match-generalization-and-window-sensitivity",
            validation_summary={
                "featured_final_excluded_from_training": True,
                "logistic_final_auc": analysis.final_holdout_logit_auc,
                "rf_final_auc": analysis.final_holdout_auc,
                "window_auc": analysis.sensitivity_auc,
            },
            time_column="point_no within match_id",
            target_column="swing_within_horizon",
            feature_columns=list(FEATURES),
            numeric_columns=list(FEATURES),
            preprocessing_notes=[
                "For the featured-final transfer test, every point from that match is removed before fitting and is used only after training is complete.",
                "Sensitivity recomputes the entire Flow feature and grouped validation protocol for windows 5, 7, 9, and 11 rather than perturbing only the final plotted curve.",
                "Coaching statements are derived only after the holdout and sensitivity checks and do not introduce new quantitative claims.",
            ],
            results=[
                AcceptedResultSpec(
                    result_type="CLASSIFICATION",
                    metric="unseen-final logistic ROC AUC",
                    value=analysis.final_holdout_logit_auc,
                    direction="MAXIMIZE",
                    scope="Alcaraz-Djokovic final completely excluded from logistic-hazard training",
                ),
                AcceptedResultSpec(
                    result_type="CLASSIFICATION",
                    metric="unseen-final RF comparator ROC AUC",
                    value=analysis.final_holdout_auc,
                    direction="MAXIMIZE",
                    scope="Alcaraz-Djokovic final completely excluded from Random Forest training",
                ),
                AcceptedResultSpec(
                    result_type="SENSITIVITY",
                    metric="flow-window AUC range",
                    value=max(value for _, value in analysis.sensitivity_auc) - min(value for _, value in analysis.sensitivity_auc),
                    direction="MINIMIZE",
                    scope="grouped validation across flow windows 5, 7, 9, and 11",
                ),
            ],
            tables=[
                AcceptedTableSpec(
                    title="Generalization and sensitivity checks",
                    columns=["Check", "Value"],
                    rows=[
                        ["Unseen-final logistic AUC", f"{analysis.final_holdout_logit_auc:.3f}"],
                        ["Unseen-final RF comparator AUC", f"{analysis.final_holdout_auc:.3f}"],
                        ["Median held-out match RF AUC", f"{float(np.median(per_auc)):.3f}" if len(per_auc) else "-"],
                        *[[f"Flow window {window}", f"AUC {auc:.3f}"] for window, auc in analysis.sensitivity_auc],
                    ],
                    table_role="summary_metrics",
                )
            ],
            answer=(
                f"The structural framework transfers beyond ordinary folds: when the entire featured final is excluded, the logistic core reaches AUC={analysis.final_holdout_logit_auc:.3f} "
                f"and the RF comparator reaches {analysis.final_holdout_auc:.3f}. Window perturbations preserve the qualitative conclusion that swing risk is only moderately, not deterministically, predictable. "
                "Coaching guidance therefore focuses on decaying advantages and uncertainty-aware alerts rather than claiming a persistent hidden force."
            ),
            limitation="Numerical parameters are Wimbledon-sample specific; only the serve-conditioned residual/state/hazard architecture is claimed to transfer after re-estimating the structural baseline.",
        ),
    ]
    ingestion = ResearchStateIngestionService(cases, artifacts, contracts, graphs).ingest(
        case_id,
        packets,
        generation=1,
        created_by="mcm2024_showcase",
    )
    print(
        f"[mcm2024] canonical Research State activated: {len(ingestion['result_ids'])} results, {len(ingestion['table_ids'])} tables",
        flush=True,
    )

    datasets = DatasetRegistry(cases, artifacts)
    claims = ClaimRegistry(cases, artifacts, datasets)
    narrative = NarrativeGraphService(cases, artifacts, contracts, claims, figures, graphs)
    paper = ResearchStatePaperService(
        cases,
        artifacts,
        contracts,
        figures,
        narrative,
        CompetitionPaperAuditor(),
    ).generate(case_id, TITLE, competition="MCM")
    print(f"[mcm2024] generic ResearchStatePaperService complete", flush=True)
    if paper["assessment"].block_count:
        blockers = [item.code for item in paper["assessment"].findings if item.severity == "BLOCK"]
        raise RuntimeError("Paper hard gate blocked MCM2024 showcase: " + ", ".join(blockers))

    markdown_path = root / "paper" / "research_state" / "draft.md"
    submission = root / "paper" / "submission"
    submission.mkdir(parents=True, exist_ok=True)
    tex_path = submission / "mcm-2024-c-showcase.tex"
    exported = CompetitionLatexExporter().export(
        markdown_path,
        tex_path,
        competition="MCM",
        control_number="XXXXXXXX",
        composition_plan=paper["page_composition"],
    )
    print(f"[mcm2024] LaTeX export complete ({exported.figure_count} figures, {exported.table_count} tables)", flush=True)
    pdf_path = _compile_xelatex(exported.tex_path, passes=3)
    with fitz.open(pdf_path) as document:
        page_count = document.page_count
    if page_count > 25:
        raise RuntimeError(f"MCM page limit exceeded: {page_count} pages")
    print(f"[mcm2024] PDF compiled: {page_count} pages", flush=True)

    visual_review = WholePDFVisualReviewer(cases, artifacts).review(case_id, pdf_path)
    assessment = visual_review["assessment"]
    print(
        f"[mcm2024] whole-PDF review: structural={assessment.structural_gate}, vision={assessment.vision_gate}",
        flush=True,
    )

    integrity = artifacts.verify(case_id)
    if integrity.get("missing") or integrity.get("changed"):
        raise RuntimeError("Artifact integrity failed: " + json.dumps(integrity, ensure_ascii=False))

    latest_path = SHOWCASE_ROOT / "LATEST.txt"
    expression = paper["expression_fulfillment"]
    atomic_write_text(
        latest_path,
        "\n".join(
            [
                f"case_id={case_id}",
                f"markdown={markdown_path}",
                f"tex={tex_path}",
                f"pdf={pdf_path}",
                f"pages={page_count}",
                f"figures={exported.figure_count}",
                f"tables={exported.table_count}",
                f"logistic_auc={analysis.logit_summary.auc:.6f}",
                f"rf_comparator_auc={analysis.rf_summary.auc:.6f}",
                f"final_logistic_holdout_auc={analysis.final_holdout_logit_auc:.6f}",
                f"expression_gate={expression.gate}",
                f"expression_required_missing={expression.required_missing_count}",
                f"pdf_visual_structural={assessment.structural_gate}",
                f"pdf_visual_vision={assessment.vision_gate}",
                f"paper_audit={paper['assessment'].gate}",
                f"visual_quality={paper['visual_quality'].gate}:{paper['visual_quality'].score}",
            ]
        )
        + "\n",
    )
    return {
        "case_id": case_id,
        "markdown": markdown_path,
        "tex": tex_path,
        "pdf": pdf_path,
        "pages": page_count,
        "figures": exported.figure_count,
        "tables": exported.table_count,
        "logistic_auc": analysis.logit_summary.auc,
        "rf_comparator_auc": analysis.rf_summary.auc,
        "final_logistic_holdout_auc": analysis.final_holdout_logit_auc,
        "expression_gate": expression.gate,
        "expression_required_missing": expression.required_missing_count,
        "audit": paper["assessment"].gate,
        "visual_quality": f"{paper['visual_quality'].gate}:{paper['visual_quality'].score}",
        "structural_gate": assessment.structural_gate,
        "vision_gate": assessment.vision_gate,
    }


def _compile_xelatex(tex_path: Path, *, passes: int = 3) -> Path:
    executable = shutil.which("xelatex")
    if executable is None:
        raise RuntimeError("xelatex is unavailable")
    for _ in range(passes):
        result = subprocess.run(
            [executable, "-interaction=nonstopmode", "-halt-on-error", tex_path.name],
            cwd=tex_path.parent,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        if result.returncode != 0:
            tail = "\n".join((result.stdout + "\n" + result.stderr).splitlines()[-120:])
            raise RuntimeError("XeLaTeX compilation failed:\n" + tail)
    pdf_path = tex_path.with_suffix(".pdf")
    if not pdf_path.is_file():
        raise RuntimeError("XeLaTeX returned success but PDF is missing")
    return pdf_path


if __name__ == "__main__":
    result = build_showcase()
    for key, value in result.items():
        print(f"{key}={value}")

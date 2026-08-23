from __future__ import annotations

import shutil
import subprocess
import urllib.error
from pathlib import Path

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.claims import ClaimRegistry
from mathworkstation.competition_latex_export import CompetitionLatexExporter
from mathworkstation.competition_paper_auditor import CompetitionPaperAuditor
from mathworkstation.context_visuals import ContextVisualCandidate, ContextVisualService
from mathworkstation.cumcm_2023_gate import (
    CUMCM_2023_C_DATA_DIR,
    cumcm_2023_c_contracts,
    link_cumcm_2023_c_dependencies,
    load_cumcm_2023_c_frames,
    prepare_cumcm_2023_c_plans,
    prepare_q3_plan,
    q1_answer,
    q2_answer,
    q3_answer,
    q4_answer,
)
from mathworkstation.datasets import DatasetRegistry
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.narrative_graph import NarrativeGraphService
from mathworkstation.paper_contracts import PaperContractService
from mathworkstation.problem_graph import ProblemGraphService
from mathworkstation.research_state_paper import ResearchStatePaperService
from mathworkstation.subproblem_engine import SubproblemEngineService
from mathworkstation.subproblem_paper_bridge import SubproblemPaperEvidenceBridge
from mathworkstation.whole_pdf_visual_review import WholePDFVisualReviewer


TITLE = "2023 CUMCM C 蔬菜类商品的自动定价与补货决策"
REPO_ROOT = Path(__file__).resolve().parents[1]
SHOWCASE_ROOT = REPO_ROOT / "docs" / "generated_samples" / "cumcm_2023_c_showcase"
OUTPUT_ROOT = SHOWCASE_ROOT / "workspace"


def build_showcase() -> dict[str, Path | str | int]:
    problem_pdf = CUMCM_2023_C_DATA_DIR / "C题.pdf"
    attachments = [CUMCM_2023_C_DATA_DIR / f"附件{index}.xlsx" for index in range(1, 5)]
    if not problem_pdf.is_file() or not all(path.is_file() for path in attachments):
        raise FileNotFoundError("Official CUMCM 2023 C problem/attachments are incomplete on this machine.")

    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    cases = CaseManager(OUTPUT_ROOT)
    case = cases.create_case("CUMCM", TITLE)
    case_id = case["case_id"]
    artifacts = ArtifactRegistry(cases)
    sources = [
        artifacts.ingest_file(case_id, problem_pdf, "input/problem/C题.pdf", "problem_source"),
        *[
            artifacts.ingest_file(case_id, path, f"input/data/附件{index}.xlsx", "observed_data")
            for index, path in enumerate(attachments, start=1)
        ],
    ]
    source_ids = [item["artifact_id"] for item in sources]

    contracts = PaperContractService(cases, artifacts)
    contracts.persist_subproblems(case_id, cumcm_2023_c_contracts())
    graphs = ProblemGraphService(cases, artifacts)
    graph = link_cumcm_2023_c_dependencies(graphs.builder.build(contracts.list_subproblems(case_id)))
    graphs.save(case_id, graph, source_ids)

    frames = load_cumcm_2023_c_frames()
    plans = prepare_cumcm_2023_c_plans(frames)
    claims = ClaimRegistry(cases, artifacts, DatasetRegistry(cases, artifacts))
    figures = FigureRegistry(cases, artifacts)
    engine = SubproblemEngineService(cases, artifacts, graphs)
    bridge = SubproblemPaperEvidenceBridge(cases, artifacts, contracts, claims, figures)

    q1_exec = engine.execute_node(
        case_id,
        "SP1",
        plans["SP1"],
        frame=frames["q1"],
        source_artifact_ids=source_ids,
        answer_text=q1_answer({})[0],
        limitation=q1_answer({})[1],
    )
    q1_text, q1_limitation = q1_answer(q1_exec["execution"]["result"])
    graph = graphs.load(case_id)
    graph.node("SP1").answer.answer = q1_text  # type: ignore[union-attr]
    graph.node("SP1").answer.limitation = q1_limitation  # type: ignore[union-attr]
    graphs.save(case_id, graph, [q1_exec["execution"]["artifact"]["artifact_id"]], created_by="showcase")
    bridge.project(case_id, "SP1", q1_exec)
    print(f"[showcase] {case_id} SP1 complete", flush=True)

    q2_exec = engine.execute_node(
        case_id,
        "SP2",
        plans["SP2"],
        frame=frames["category_daily"],
        source_artifact_ids=source_ids,
    )
    q2_text, q2_limitation = q2_answer(q2_exec["execution"]["result"])
    graph = graphs.load(case_id)
    graph.node("SP2").answer.answer = q2_text  # type: ignore[union-attr]
    graph.node("SP2").answer.limitation = q2_limitation  # type: ignore[union-attr]
    graphs.save(case_id, graph, [q2_exec["execution"]["artifact"]["artifact_id"]], created_by="showcase")
    bridge.project(case_id, "SP2", q2_exec)
    print(f"[showcase] {case_id} SP2 complete", flush=True)

    q3_exec = engine.execute_node(
        case_id,
        "SP3",
        prepare_q3_plan(q2_exec["execution"]["result"]),
        frame=frames["item_daily"],
        source_artifact_ids=source_ids,
    )
    q3_text, q3_limitation = q3_answer(q3_exec["execution"]["result"])
    graph = graphs.load(case_id)
    graph.node("SP3").answer.answer = q3_text  # type: ignore[union-attr]
    graph.node("SP3").answer.limitation = q3_limitation  # type: ignore[union-attr]
    graphs.save(case_id, graph, [q3_exec["execution"]["artifact"]["artifact_id"]], created_by="showcase")
    bridge.project(case_id, "SP3", q3_exec)
    print(f"[showcase] {case_id} SP3 complete", flush=True)

    q4_exec = engine.complete_synthesis(case_id, "SP4", q4_answer())
    bridge.project_synthesis(case_id, "SP4", q4_exec)
    if bridge.activate_if_complete(case_id, generation=1) is None:
        raise RuntimeError("Could not activate complete evidence lineage for showcase.")

    context_candidate = ContextVisualCandidate(
        candidate_id="fresh-produce-retail-context",
        title="生鲜果蔬零售场景",
        page_url="https://commons.wikimedia.org/wiki/File:Fruit_section_of_a_grocery_store.jpg",
        asset_url="https://commons.wikimedia.org/wiki/Special:Redirect/file/Fruit_section_of_a_grocery_store.jpg?width=1600",
        provider="Wikimedia Commons",
        author="Alabama Extension",
        license_id="CC0 1.0",
        license_url="https://creativecommons.org/publicdomain/zero/1.0/",
        source_date="2022-09-01",
        description="真实生鲜果蔬零售场景，用于帮助读者进入定价与补货问题语境，不作为数值证据。",
    )
    try:
        ContextVisualService(cases, artifacts, figures).materialize(case_id, context_candidate)
    except (OSError, ValueError, urllib.error.URLError, TimeoutError) as exc:
        # Context photography is optional document-layer context.  A transient
        # network failure must never invalidate solver evidence or block the
        # reproducible showcase build.
        print(f"[context-visual] optional retrieval skipped: {exc}")

    narrative = NarrativeGraphService(cases, artifacts, contracts, claims, figures, graphs)
    paper = ResearchStatePaperService(
        cases,
        artifacts,
        contracts,
        figures,
        narrative,
        CompetitionPaperAuditor(),
    ).generate(case_id, TITLE, competition="CUMCM")
    print(f"[showcase] {case_id} research-state paper complete", flush=True)
    if paper["assessment"].block_count:
        blockers = [item.code for item in paper["assessment"].findings if item.severity == "BLOCK"]
        raise RuntimeError("Paper hard gate blocked showcase: " + ", ".join(blockers))

    case_root = cases.case_root(case_id)
    submission_dir = case_root / "paper" / "submission"
    submission_dir.mkdir(parents=True, exist_ok=True)
    tex_path = submission_dir / "cumcm-2023-c-showcase.tex"
    exported = CompetitionLatexExporter().export(
        case_root / "paper" / "research_state" / "draft.md",
        tex_path,
        competition="CUMCM",
        composition_plan=paper["page_composition"],
    )
    print(f"[showcase] {case_id} LaTeX export complete", flush=True)
    pdf_path = _compile_xelatex(exported.tex_path)
    print(f"[showcase] {case_id} XeLaTeX complete", flush=True)
    pdf_visual = None
    if pdf_path is not None:
        pdf_visual = WholePDFVisualReviewer(cases, artifacts).review(case_id, pdf_path)
        print(f"[showcase] {case_id} whole-PDF review complete", flush=True)

    latest = SHOWCASE_ROOT / "LATEST.txt"
    latest.write_text(
        "\n".join(
            [
                f"case_id={case_id}",
                f"markdown={case_root / 'paper' / 'research_state' / 'draft.md'}",
                f"tex={tex_path}",
                f"pdf={pdf_path or ''}",
                f"figures={exported.figure_count}",
                f"tables={exported.table_count}",
                f"visual_quality={paper['visual_quality'].gate}:{paper['visual_quality'].score}",
                f"audit={paper['assessment'].gate}",
                f"pdf_visual_structural={pdf_visual['assessment'].structural_gate if pdf_visual else 'UNAVAILABLE'}",
                f"pdf_visual_vision={pdf_visual['assessment'].vision_gate if pdf_visual else 'UNAVAILABLE'}",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return {
        "case_id": case_id,
        "markdown": case_root / "paper" / "research_state" / "draft.md",
        "tex": tex_path,
        "pdf": pdf_path or "",
        "figures": exported.figure_count,
        "tables": exported.table_count,
        "visual_quality": f"{paper['visual_quality'].gate}:{paper['visual_quality'].score}",
        "audit": paper["assessment"].gate,
        "pdf_visual_structural": pdf_visual["assessment"].structural_gate if pdf_visual else "UNAVAILABLE",
        "pdf_visual_vision": pdf_visual["assessment"].vision_gate if pdf_visual else "UNAVAILABLE",
    }


def _compile_xelatex(tex_path: Path) -> Path | None:
    executable = shutil.which("xelatex")
    if executable is None:
        return None
    for _ in range(2):
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
            log_tail = "\n".join((result.stdout + "\n" + result.stderr).splitlines()[-80:])
            raise RuntimeError("XeLaTeX compilation failed:\n" + log_tail)
    pdf_path = tex_path.with_suffix(".pdf")
    return pdf_path if pdf_path.is_file() else None


if __name__ == "__main__":
    result = build_showcase()
    for key, value in result.items():
        print(f"{key}={value}")

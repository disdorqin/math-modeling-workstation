from pathlib import Path

import pandas as pd

from mathworkstation.artifact_registry import ArtifactRegistry
from mathworkstation.case_manager import CaseManager
from mathworkstation.claims import ClaimRegistry
from mathworkstation.competition_paper_auditor import CompetitionPaperAuditor, _summary_prior_semantically_present
from mathworkstation.datasets import DatasetRegistry
from mathworkstation.figure_registry import FigureRegistry
from mathworkstation.narrative_graph import NarrativeGraphService
from mathworkstation.paper_contracts import PaperContractService, SubproblemContract
from mathworkstation.problem_graph import ProblemGraphService
from mathworkstation.subproblem_engine import SubproblemEngineService
from mathworkstation.subproblem_paper_bridge import SubproblemPaperEvidenceBridge
from mathworkstation.wordle_2023_gate import prepare_wordle_2023_research


CASE_ROOT = Path("output/mcm-c-2023/v3/20260805-MCM-0001-EUP7")


def test_quantified_result_prior_accepts_humanized_numeric_table_caption() -> None:
    paper = """**Table 4. State-specific compact targets.**

| State | 2025 target | 2050 target |
|---|---:|---:|
| CA | 0.31 | 0.42 |
| AZ | 0.18 | 0.29 |
"""
    assert _summary_prior_semantically_present(paper, "结果量化、给出具体数字") is True




def _contracts() -> list[SubproblemContract]:
    return [
        SubproblemContract.model_validate_json(line)
        for line in (CASE_ROOT / "results/contracts/subproblems.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _narrative(tmp_path: Path):
    cases = CaseManager(tmp_path / "output")
    case = cases.create_case("MCM", "Wordle competition paper auditor Gate")
    case_id = case["case_id"]
    artifacts = ArtifactRegistry(cases)
    source = artifacts.ingest_file(
        case_id,
        CASE_ROOT / "input/data/uploaded/_wordle_data_clean.csv",
        "input/data/uploaded",
        "observed_data",
    )
    contracts = PaperContractService(cases, artifacts)
    contracts.persist_subproblems(case_id, _contracts())
    graphs = ProblemGraphService(cases, artifacts)
    graphs.persist(case_id, contracts.list_subproblems(case_id), [source["artifact_id"]])
    claims = ClaimRegistry(cases, artifacts, DatasetRegistry(cases, artifacts))
    figures = FigureRegistry(cases, artifacts)
    engine = SubproblemEngineService(cases, artifacts, graphs)
    bridge = SubproblemPaperEvidenceBridge(cases, artifacts, contracts, claims, figures)
    data, plans = prepare_wordle_2023_research(
        pd.read_csv(CASE_ROOT / "input/data/uploaded/_wordle_data_clean.csv")
    )
    for subproblem_id in ("SP1", "SP2", "SP3", "SP4", "SP5"):
        execution = engine.execute_node(
            case_id,
            subproblem_id,
            plans[subproblem_id],
            frame=data,
            source_artifact_ids=[source["artifact_id"]],
        )
        bridge.project(case_id, subproblem_id, execution)
    synthesis = engine.complete_synthesis(
        case_id,
        "SP6",
        "The editor letter synthesizes only the accepted findings from Questions 1 through 5.",
    )
    bridge.project_synthesis(case_id, "SP6", synthesis)
    assert bridge.activate_if_complete(case_id, generation=1)
    narrative = NarrativeGraphService(cases, artifacts, contracts, claims, figures, graphs).build(case_id)
    return narrative


def test_old_real_wordle_paper_is_blocked_for_known_pollution(tmp_path: Path) -> None:
    narrative = _narrative(tmp_path)
    old_paper = (CASE_ROOT / "paper/final.md").read_text(encoding="utf-8")

    assessment = CompetitionPaperAuditor().audit(old_paper, narrative)
    codes = {item.code for item in assessment.findings}

    assert assessment.gate == "BLOCK"
    assert assessment.reference_papers_count >= 10
    assert "INTERNAL_REGISTRY_ID_LEAK" in codes
    assert "FOREIGN_ENERGY_UNIT_POLLUTION" in codes
    assert "FOREIGN_CURRENCY_UNIT_POLLUTION" in codes
    assert "REFERENCE_PLACEHOLDER_FORBIDDEN" in codes or "VERIFIED_REFERENCES_MISSING" in codes


def test_auditor_routes_blocked_narrative_back_to_research(tmp_path: Path) -> None:
    narrative = _narrative(tmp_path).model_copy(deep=True)
    narrative.nodes[2].gate = "BLOCKED"
    narrative.nodes[2].blockers = ["VALIDATION_NOT_ACCEPTED"]
    narrative.gate = "BLOCKED"
    paper = """# Abstract\nQuestion 1 uses ridge regression and reports 1.23.\n\n# Question 1\nResult 1.23.\n\n# References\n[1] Smith J. Example study. 2020.\n[2] Doe A. Example method. 2021.\n[3] Roe B. Example validation. 2022.\n"""

    assessment = CompetitionPaperAuditor().audit(paper, narrative)
    research = [item for item in assessment.findings if item.defect_type == "RESEARCH"]

    assert assessment.gate == "BLOCK"
    assert any(item.subproblem_id == "SP3" and item.repair_phase == "validation" for item in research)


def test_excellent_c7_is_reported_as_summary_prior_not_full_corpus() -> None:
    assessment = CompetitionPaperAuditor().audit(
        "# Abstract\nSummary.\n\n# References\n[1] A. B. C. 2020.\n[2] D. E. F. 2021.\n[3] G. H. I. 2022.\n"
    )

    assert assessment.reference_papers_count == 11
    assert "extracted summaries" in assessment.reference_note
    assert "not treated as full-paper" in assessment.reference_note

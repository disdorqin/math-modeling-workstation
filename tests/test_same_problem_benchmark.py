from __future__ import annotations

from mathworkstation.narrative_graph import NarrativeGraph, NarrativeNode
from mathworkstation.same_problem_benchmark import (
    SameProblemExcellentAssessor,
    build_corpus_profile,
    profile_full_text,
)


def _o_paper(paper_id: str, *, mechanism: str = "SIR model", custom: str = "Subset Entropy"):
    text = f"""
2023 MCM/ICM Summary Sheet
Summary
For Task 1 we use {mechanism}, Bootstrap prediction intervals, and cross-validation to predict 12345 reports.
For Task 2 we define word attributes and {custom}; a Lasso model identifies relevant features.
For Task 3 K-means and Random Forest classify EERIE as hard with 91.3% accuracy.
Sensitivity analysis gives a 95% confidence interval and RMSE 1.2.
Keywords: Wordle; Bootstrap; K-means

Contents
1 Introduction
1.1 Literature Review
2 Assumptions and Notations
3 Data Preprocessing
4 Word Feature Engineering
5 Problem Analysis
5.1 Establishment of the Model
5.2 Solving the Model
6 Uncertainty Analysis
7 Sensitivity Analysis
8 Strengths and Weaknesses
9 Conclusion
10 Letter to the Puzzle Editor
References

Figure 1: Flow chart of our work
Figure 2: Result comparison
Table 1: Notations
Table 2: Prediction results

The green tile and yellow tile feedback drive our Wordle game-mechanics features. We use a wordbank and word frequency in English.
Dear Editor, our recommendation follows from the accepted results.
References
[1] Example A.
[2] Example B.
[3] Example C.
[4] Example D.
[5] Example E.
[6] Example F.
"""
    return profile_full_text(text, paper_id=paper_id, year=2023, problem="MCM-C-Wordle", page_count=24)


def _narrative() -> NarrativeGraph:
    research = [
        NarrativeNode(
            subproblem_id=f"SP{i}",
            title=f"Question {i}",
            role="RESEARCH",
            task_family=family,
            objective=f"objective {i}",
            method=method,
            answer=f"answer {i}",
            limitation="limited",
            validation_gate="PASS",
            gate="PASS",
        )
        for i, (family, method) in enumerate(
            [
                ("forecasting", "ridge time trend"),
                ("explanatory_inference", "standardized ridge"),
                ("distribution_forecasting", "multioutput ridge"),
                ("classification", "logistic regression"),
                ("exploratory_analysis", "spearman scan"),
            ],
            start=1,
        )
    ]
    synthesis = NarrativeNode(
        subproblem_id="SP6",
        title="Editor letter",
        role="SYNTHESIS",
        task_family="synthesis",
        objective="write editor deliverable",
        dependencies=[f"SP{i}" for i in range(1, 6)],
        method="evidence synthesis",
        answer="synthesis",
        limitation="accepted evidence only",
        gate="PASS",
    )
    return NarrativeGraph(
        case_id="case-wordle",
        gate="PASS",
        research_gate="PASS",
        model_graph_gate="PASS",
        evidence_graph_gate="PASS",
        nodes=[*research, synthesis],
        storyline=[],
        generated_at="2026-08-19T00:00:00+08:00",
    )


def test_full_text_profile_extracts_same_problem_competition_signals() -> None:
    profile = _o_paper("team-a")
    assert "SIR/differential equation" in profile.detected_methods
    assert "Bootstrap" in profile.detected_methods
    assert profile.structure_signals["literature_review"] is True
    assert profile.structure_signals["data_preprocessing"] is True
    assert profile.structure_signals["strengths_weaknesses"] is True
    assert profile.structure_signals["letter"] is True
    assert profile.domain_signals["word_feature_engineering"] is True
    assert profile.domain_signals["custom_domain_construct"] is True
    assert profile.validation_signals["uncertainty_interval"] is True
    assert profile.has_workflow_figure is True
    assert profile.reference_entries >= 5


def test_corpus_profile_uses_prevalence_not_single_paper_recipe() -> None:
    profiles = [
        _o_paper("team-a", custom="Subset Entropy"),
        _o_paper("team-b", custom="negentropy"),
        _o_paper("team-c", custom="regularity and purity"),
        profile_full_text(
            "Summary\nWe use Prophet and word attributes.\nContents\n1 Introduction\n2 Data Processing\n3 Sensitivity Analysis\nReferences\n[1] A\n[2] B\n[3] C",
            paper_id="team-d",
            year=2023,
            problem="MCM-C-Wordle",
            page_count=20,
        ),
        _o_paper("team-e", custom="word internal distance"),
    ]
    corpus = build_corpus_profile(profiles, corpus_id="mcm-2023-c-o", extraction_note="test")
    assert corpus.paper_count == 5
    assert corpus.prevalence["domain.word_feature_engineering"] >= 0.8
    assert corpus.prevalence["domain.custom_domain_construct"] >= 0.6
    assert corpus.prevalence["structure.letter"] >= 0.6
    assert corpus.median_abstract_method_count >= 2


def test_assessor_routes_same_problem_depth_gaps_upstream_not_to_prose() -> None:
    corpus = build_corpus_profile(
        [_o_paper(f"team-{i}") for i in range(5)],
        corpus_id="mcm-2023-c-o",
        extraction_note="test",
    )
    current = """
# Wordle Research Paper
# Abstract
For Question 1 we use ridge regression and report RMSE 1.2. For Question 2 we use logistic regression and report accuracy 0.7.
# 1 Problem Analysis and Decomposition
# 2 Assumptions and Scope
# 3 Models, Validation, and Results
The registered validation protocol uses a holdout. A prediction interval is reported.
| Metric | Value |
|---|---:|
| RMSE | 1.2 |
# 4 Practical Interpretation and Recommendations
# 5 Cross-Question Synthesis
# 6 Robustness and Limitations
# 7 Conclusions
# References
[1] A
[2] B
[3] C
"""
    assessment = SameProblemExcellentAssessor(corpus).assess(current, _narrative(), case_id="case-wordle")
    dimensions = {item.dimension: item for item in assessment.gaps}

    assert assessment.gate == "REVIEW"
    assert dimensions["same_problem_literature_review"].defect_type == "DOCUMENT"
    assert dimensions["same_problem_literature_review"].repair_phase == "paper_introduction"
    assert dimensions["same_problem_workflow_figure"].defect_type == "DOCUMENT"
    assert dimensions["same_problem_editor_letter"].defect_type == "DOCUMENT"
    assert dimensions["same_problem_custom_domain_construct"].defect_type == "RESEARCH"
    assert dimensions["same_problem_custom_domain_construct"].repair_phase == "modeling_brain"
    assert "SP2" in dimensions["same_problem_custom_domain_construct"].subproblem_ids
    assert dimensions["same_problem_popularity_mechanism"].defect_type == "RESEARCH"
    assert dimensions["same_problem_popularity_mechanism"].subproblem_ids == ["SP1"]


def test_assessor_does_not_require_non_recurrent_o_award_trick() -> None:
    profiles = [
        _o_paper("team-a", mechanism="SIR model"),
        _o_paper("team-b", mechanism="SIR model"),
        profile_full_text(
            "Summary\nARIMA with Bootstrap. Word attributes.\nContents\n1 Introduction\n2 Data Preprocessing\n3 Strengths and Weaknesses\nLetter\nDear Editor\nReferences\n[1] A\n[2] B\n[3] C\n[4] D\n[5] E",
            paper_id="team-c",
            year=2023,
            problem="MCM-C-Wordle",
            page_count=22,
        ),
        profile_full_text(
            "Summary\nProphet prediction interval. Word attributes.\nContents\n1 Introduction\n2 Data Preprocessing\n3 Strengths and Weaknesses\nLetter\nDear Editor\nReferences\n[1] A\n[2] B\n[3] C\n[4] D\n[5] E",
            paper_id="team-d",
            year=2023,
            problem="MCM-C-Wordle",
            page_count=22,
        ),
        profile_full_text(
            "Summary\nGaussian regression and Poisson process. Word attributes.\nContents\n1 Introduction\n2 Data Preprocessing\n3 Strengths and Weaknesses\nLetter\nDear Editor\nReferences\n[1] A\n[2] B\n[3] C\n[4] D\n[5] E",
            paper_id="team-e",
            year=2023,
            problem="MCM-C-Wordle",
            page_count=22,
        ),
    ]
    corpus = build_corpus_profile(profiles, corpus_id="mcm-2023-c-o", extraction_note="test")
    # Only 2/5 have an SIR/player mechanism, below the default 60% threshold.
    assert corpus.prevalence["domain.player_or_popularity_mechanism"] < 0.6
    assessment = SameProblemExcellentAssessor(corpus).assess("# Abstract\nWord attributes.\n# References\n[1] A\n[2] B\n[3] C", _narrative())
    assert "same_problem_popularity_mechanism" not in {item.dimension for item in assessment.gaps}

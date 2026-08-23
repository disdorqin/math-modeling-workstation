from __future__ import annotations

from mathworkstation.judge_validity import (
    CalibrationPaper,
    JudgeVote,
    aggregate_judge_validity,
    anonymize_paper_text,
    make_swapped_pair,
)


def _papers() -> list[CalibrationPaper]:
    return [
        CalibrationPaper(
            blind_id="paper-a",
            origin="REAL_EXCELLENT",
            competition="MCM",
            year=2024,
            problem_letter="C",
            problem_key="mcm-2024-c",
            source_path="external/2409404.pdf",
            award="O",
        ),
        CalibrationPaper(
            blind_id="paper-b",
            origin="WORKSTATION_CURRENT",
            competition="MCM",
            year=2024,
            problem_letter="C",
            problem_key="mcm-2024-c",
            source_path="generated/current.pdf",
            case_id="current",
        ),
        CalibrationPaper(
            blind_id="paper-c",
            origin="WORKSTATION_OLDER",
            competition="MCM",
            year=2024,
            problem_letter="C",
            problem_key="mcm-2024-c",
            source_path="generated/old.pdf",
            case_id="old",
        ),
    ]


def test_anonymizer_masks_award_and_team_identity_without_erasing_results() -> None:
    source = """Outstanding Winner\nTeam # 2409404\nUniversity: Example U\nAUC = 0.681 and cost = 2409404.25.\n"""
    value = anonymize_paper_text(source)

    assert "Outstanding" not in value
    assert "Team # 2409404" not in value
    assert "Example U" not in value
    assert "0.681" in value
    assert "2409404.25" in value


def test_swapped_pair_changes_position_but_preserves_identity() -> None:
    ab, ba = make_swapped_pair(
        swap_group="mcm24-real-current",
        left_id="paper-a",
        right_id="paper-b",
        kind="REAL_VS_CURRENT",
    )

    assert ab.left_id == ba.right_id == "paper-a"
    assert ab.right_id == ba.left_id == "paper-b"
    assert ab.swap_group == ba.swap_group


def test_no_blind_human_anchor_forces_inconclusive_h1() -> None:
    papers = _papers()
    ab, ba = make_swapped_pair(
        swap_group="mcm24-real-current",
        left_id="paper-a",
        right_id="paper-b",
        kind="REAL_VS_CURRENT",
    )
    votes = [
        JudgeVote("internal-auditor", "INTERNAL", ab.pair_id, "RIGHT", 0.8),
        JudgeVote("internal-auditor", "INTERNAL", ba.pair_id, "LEFT", 0.8),
    ]

    aggregate = aggregate_judge_validity(papers, [ab, ba], votes)

    assert aggregate["position_swap_consistency"] == 1.0
    assert aggregate["discrimination"]["internal-auditor"]["accuracy_vs_provenance_prior"] == 0.0
    assert aggregate["h1_judge_validity_bottleneck"] == "INCONCLUSIVE"
    assert aggregate["human_vote_count"] == 0


def test_blind_human_anchor_can_support_h1_when_internal_judge_reverses_real_pair() -> None:
    papers = _papers()
    ab, ba = make_swapped_pair(
        swap_group="mcm24-real-current",
        left_id="paper-a",
        right_id="paper-b",
        kind="REAL_VS_CURRENT",
    )
    votes = [
        JudgeVote("internal-auditor", "INTERNAL", ab.pair_id, "RIGHT", 0.8),
        JudgeVote("internal-auditor", "INTERNAL", ba.pair_id, "LEFT", 0.8),
        JudgeVote("human-1", "HUMAN", ab.pair_id, "LEFT", 0.9),
        JudgeVote("human-1", "HUMAN", ba.pair_id, "RIGHT", 0.9),
    ]

    aggregate = aggregate_judge_validity(papers, [ab, ba], votes)

    assert aggregate["position_swap_consistency"] == 1.0
    assert aggregate["cross_judge_agreement"] == 0.0
    assert aggregate["h1_judge_validity_bottleneck"] == "SUPPORTED"


def test_current_vs_older_uses_current_as_provenance_prior() -> None:
    papers = _papers()
    ab, ba = make_swapped_pair(
        swap_group="mcm24-current-old",
        left_id="paper-b",
        right_id="paper-c",
        kind="CURRENT_VS_OLDER",
    )
    votes = [
        JudgeVote("internal-auditor", "INTERNAL", ab.pair_id, "LEFT", 0.7),
        JudgeVote("internal-auditor", "INTERNAL", ba.pair_id, "RIGHT", 0.7),
    ]

    aggregate = aggregate_judge_validity(papers, [ab, ba], votes)

    assert aggregate["discrimination"]["internal-auditor"]["accuracy_vs_provenance_prior"] == 1.0
